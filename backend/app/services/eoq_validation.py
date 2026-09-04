"""Deterministic validation for extracted EOQ quantity candidates.

Runs after AI/CAD extraction and before EOQ persistence to enforce:
- Unit sanity checks
- Duplicate/conflict resolution for same-source rows
- Schedule-priority override when schedule and plan-derived duplicates collide
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.services.csi_mapper import normalize_unit
from app.services.item_combine import item_is_schedule
from app.services.traffic_control import looks_like_agency_bid_number

_SIZE_RE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*-?\s*(?:inch|in|\"|'')", re.I)

_LINEAR_HINTS = (
    "watermain",
    "water main",
    "water line",
    "sanitary sewer",
    "storm sewer",
    "pipe",
    "curb",
    "gutter",
    "guardrail",
    "fence",
)
_AREA_HINTS = (
    "sidewalk",
    "pavement",
    "asphalt",
    "seeding",
    "sodding",
    "erosion",
    "landscap",
    "traffic control",
)
_COUNT_HINTS = (
    "hydrant",
    "valve",
    "manhole",
    "inlet",
    "catch basin",
    "fitting",
    "elbow",
    "tee",
    "reducer",
    "barricade",
    "mailbox",
    "sign",
    "door",
    "window",
)
_LUMP_HINTS = (
    "mobilization",
    "winter maintenance",
    "allowance",
    "temporary gravel access",
    "tax on city",
)
_VOLUME_HINTS = (
    "excavation",
    "embankment",
    "concrete",
    "fill",
    "cut",
    "riprap",
)
_MASS_HINTS = (
    "fertiliz",
    "rebar",
    "bituminous",
    "hma",
)

_UNIT_FAMILIES = {
    "linear": {"lf", "m"},
    "area": {"sf", "sy", "m2"},
    "volume": {"cy", "m3"},
    "count": {"ea", "nos"},
    "lump": {"ls"},
    "mass": {"t", "lb", "kg"},
    "capacity": {"mgal", "ac-ft"},
}


def validate_extracted_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate and de-conflict extracted quantity rows deterministically."""
    normalized: list[dict[str, Any]] = []
    dropped_bad_qty = 0
    dropped_non_positive = 0
    unit_flags = 0

    for idx, raw in enumerate(items):
        desc = str(raw.get("description") or "").strip()
        if not desc:
            continue
        qty = _to_float(raw.get("quantity"))
        if qty is None:
            dropped_bad_qty += 1
            continue

        item = dict(raw)
        item["__validation_order"] = idx
        item["quantity"] = qty
        item["unit"] = normalize_unit(str(item.get("unit") or "unit"))

        schedule_row = _is_schedule_row(item)
        if qty <= 0 and not schedule_row:
            dropped_non_positive += 1
            continue

        if not schedule_row:
            expected = _expected_unit_families(
                description=desc,
                category=str(item.get("category") or ""),
            )
            if expected:
                actual = _unit_family(str(item.get("unit") or ""))
                if actual not in expected:
                    item = _append_validation_note(
                        item,
                        f"unit '{item['unit']}' may be inconsistent for item type",
                        force_review=True,
                        max_confidence=85.0,
                    )
                    unit_flags += 1

        normalized.append(item)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in normalized:
        grouped[_item_group_key(item)].append(item)

    out: list[dict[str, Any]] = []
    schedule_overrides = 0
    source_conflicts = 0
    exact_duplicates = 0

    for _group_key, rows in sorted(
        grouped.items(),
        key=lambda kv: min(int(r.get("__validation_order", 0)) for r in kv[1]),
    ):
        deduped, dupe_count = _dedupe_exact_rows(rows)
        exact_duplicates += dupe_count

        schedule_rows = [r for r in deduped if _is_schedule_row(r)]
        if schedule_rows:
            winner = _pick_best(schedule_rows)
            non_schedule_rows = [r for r in deduped if not _is_schedule_row(r)]
            if non_schedule_rows:
                schedule_overrides += len(non_schedule_rows)
                winner = _append_validation_note(
                    winner,
                    "kept authoritative schedule quantity over duplicate plan takeoff rows",
                    force_review=False,
                )
            if _has_conflicting_quantities(schedule_rows):
                winner = _append_validation_note(
                    winner,
                    "conflicting schedule duplicates detected; kept highest-confidence row",
                    force_review=True,
                    max_confidence=89.0,
                )
                source_conflicts += 1
            out.append(winner)
            continue

        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in deduped:
            by_source[_source_signature(row)].append(row)

        for source_rows in by_source.values():
            if len(source_rows) == 1:
                out.append(source_rows[0])
                continue
            if _has_conflicting_quantities(source_rows):
                source_conflicts += len(source_rows) - 1
                winner = _append_validation_note(
                    _pick_best(source_rows),
                    "conflicting duplicate quantities from same source; kept highest-confidence row",
                    force_review=True,
                    max_confidence=88.0,
                )
                out.append(winner)
            else:
                out.append(_pick_best(source_rows))

    for item in out:
        item.pop("__validation_order", None)

    notes: list[str] = []
    if dropped_bad_qty:
        notes.append(f"Dropped {dropped_bad_qty} row(s) with non-numeric quantity.")
    if dropped_non_positive:
        notes.append(f"Dropped {dropped_non_positive} row(s) with non-positive quantity.")
    if exact_duplicates:
        notes.append(f"Collapsed {exact_duplicates} exact duplicate row(s).")
    if schedule_overrides:
        notes.append(f"Applied schedule-priority on {schedule_overrides} duplicate plan row(s).")
    if source_conflicts:
        notes.append(f"Resolved {source_conflicts} conflicting duplicate row(s).")
    if unit_flags:
        notes.append(f"Flagged {unit_flags} unit-sanity mismatch row(s) for engineer review.")

    return out, notes


def _dedupe_exact_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    bucket: dict[tuple[str, float, str], dict[str, Any]] = {}
    dropped = 0
    for row in rows:
        key = (
            _source_signature(row),
            round(_to_float(row.get("quantity")) or 0.0, 4),
            _norm_text(str(row.get("calculation_method") or ""))[:120],
        )
        prev = bucket.get(key)
        if prev is None:
            bucket[key] = row
            continue
        dropped += 1
        bucket[key] = _pick_best([prev, row])
    return list(bucket.values()), dropped


def _is_schedule_row(item: dict[str, Any]) -> bool:
    if item.get("bid_template_line_id"):
        return True
    code = str(item.get("item_code") or "").strip()
    if code and looks_like_agency_bid_number(code):
        return True
    return item_is_schedule(item)


def _item_group_key(item: dict[str, Any]) -> str:
    unit = normalize_unit(str(item.get("unit") or "unit"))
    category = _norm_text(str(item.get("category") or ""))
    desc = _norm_text(str(item.get("description") or ""))
    size = _size_token(str(item.get("description") or ""))
    size_blob = f"|size:{size}" if size else ""
    if desc:
        return f"desc:{desc}{size_blob}|unit:{unit}|cat:{category}"

    item_code = str(item.get("item_code") or "").strip().lower()
    if item_code and looks_like_agency_bid_number(item_code):
        return f"code:{item_code}|unit:{unit}|cat:{category}"
    return f"fallback:unknown|unit:{unit}|cat:{category}"


def _source_signature(item: dict[str, Any]) -> str:
    doc_id = str(item.get("source_document_id") or "")
    page = str(item.get("source_page") or "")
    source_ref = str(item.get("source_reference") or item.get("source") or "").strip()
    if not source_ref:
        source_ref = str(item.get("calculation_method") or "").strip()[:80]
    return f"{doc_id}|{page}|{_norm_text(source_ref)[:160]}"


def _append_validation_note(
    item: dict[str, Any],
    note: str,
    *,
    force_review: bool,
    max_confidence: float | None = None,
) -> dict[str, Any]:
    out = dict(item)
    method = str(out.get("calculation_method") or "").strip()
    marker = f"validation: {note}"
    if marker.lower() not in method.lower():
        out["calculation_method"] = f"{method} | {marker}".strip(" |")
    if force_review:
        out["validation_needs_review"] = True
    if max_confidence is not None:
        conf = _to_float(out.get("confidence"))
        if conf is None:
            out["confidence"] = max_confidence
        else:
            out["confidence"] = min(conf, max_confidence)
    return out


def _pick_best(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def score(row: dict[str, Any]) -> tuple[float, float, float, float]:
        conf = _to_float(row.get("confidence")) or 0.0
        qty = abs(_to_float(row.get("quantity")) or 0.0)
        src = 1.0 if str(row.get("source_reference") or row.get("source") or "").strip() else 0.0
        bid = 1.0 if _is_schedule_row(row) else 0.0
        return (bid, src, conf, qty)

    return dict(max(rows, key=score))


def _has_conflicting_quantities(rows: list[dict[str, Any]]) -> bool:
    seen: list[float] = []
    for row in rows:
        qty = _to_float(row.get("quantity"))
        if qty is None:
            continue
        if not any(_near_equal(qty, v) for v in seen):
            seen.append(qty)
        if len(seen) >= 2:
            return True
    return False


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _near_equal(a: float, b: float, rel_tol: float = 0.02) -> bool:
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base <= rel_tol


def _norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _size_token(description: str) -> str | None:
    m = _SIZE_RE.search(description or "")
    if not m:
        return None
    try:
        raw = float(m.group(1))
    except ValueError:
        return None
    if abs(raw - int(raw)) < 0.01:
        return str(int(raw))
    return f"{raw:g}"


def _expected_unit_families(*, description: str, category: str) -> set[str] | None:
    blob = f"{description} {category}".lower()
    if "traffic control" in blob:
        return {"area", "count", "lump"}
    if any(h in blob for h in _LUMP_HINTS):
        return {"lump"}
    if any(h in blob for h in _COUNT_HINTS):
        return {"count"}
    if any(h in blob for h in _LINEAR_HINTS):
        return {"linear"}
    if any(h in blob for h in _AREA_HINTS):
        return {"area"}
    if any(h in blob for h in _VOLUME_HINTS):
        return {"volume"}
    if any(h in blob for h in _MASS_HINTS):
        return {"mass"}
    return None


def _unit_family(unit: str) -> str:
    norm = normalize_unit(unit)
    for family, units in _UNIT_FAMILIES.items():
        if norm in units:
            return family
    return "other"
