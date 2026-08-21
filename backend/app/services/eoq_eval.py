"""Compare expected vs actual EOQ takeoff for gold-set / regression checks.

Used by tests and `scripts/run_gold_set.py`. No OpenAI/APS required for
pure quantity_engine cases; full PDF cases can feed precomputed actual items.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


CATEGORY_ALIASES = {
    "utilities": "Utilities",
    "utility": "Utilities",
    "drainage": "Drainage",
    "earthwork": "Earthwork",
    "pavement": "Pavement",
    "roadside": "Roadside",
    "structures": "Structures",
    "geometry": "Geometry",
    "bid schedule": "Bid schedule",
    "unmapped takeoff": "Unmapped takeoff",
}


def _norm_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _norm_unit(value: str | None) -> str:
    u = _norm_text(value).replace(".", "")
    aliases = {
        "lf": "lf",
        "lin ft": "lf",
        "linear feet": "lf",
        "linear foot": "lf",
        "ft": "lf",
        "feet": "lf",
        "foot": "lf",
        "m": "m",
        "lm": "m",
        "ea": "ea",
        "each": "ea",
        "nos": "ea",
        "no": "ea",
        "cy": "cy",
        "cu yd": "cy",
        "cuyd": "cy",
        "m3": "m3",
        "cum": "m3",
        "sf": "sf",
        "sq ft": "sf",
        "sqft": "sf",
        "sy": "sy",
        "sq yd": "sy",
        "sqyd": "sy",
        "ls": "ls",
        "lump sum": "ls",
        "ton": "ton",
        "tons": "ton",
        "lb": "lb",
        "lbs": "lb",
        "acre": "acre",
        "hour": "hour",
        "hr": "hour",
    }
    return aliases.get(u, u or "unit")


def _norm_category(value: str | None) -> str:
    key = _norm_text(value)
    return CATEGORY_ALIASES.get(key, (value or "Other").strip() or "Other")


def _size_token(text: str) -> str | None:
    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*-?\s*(?:inch|in|\"|'')", text, re.I)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if abs(val - int(val)) < 0.01:
        return f"{int(val)}-inch"
    return f"{val:g}-inch"


def _tokens(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "of", "a", "an", "to", "in", "on", "or", "type", "size"}
    return {t for t in re.findall(r"[a-z0-9.]+", text.lower()) if len(t) > 1 and t not in stop}


@dataclass
class ExpectedItem:
    description: str
    unit: str
    category: str | None = None
    quantity: float | None = None
    quantity_tolerance: float = 0.05  # relative
    quantity_abs_tolerance: float = 1.0
    item_code: str | None = None
    required: bool = True


@dataclass
class MatchHit:
    expected: dict[str, Any]
    actual: dict[str, Any]
    qty_ok: bool
    qty_delta: float | None
    method: str


@dataclass
class CompareReport:
    expected_count: int = 0
    actual_count: int = 0
    hits: list[MatchHit] = field(default_factory=list)
    misses: list[dict[str, Any]] = field(default_factory=list)
    extras: list[dict[str, Any]] = field(default_factory=list)
    misses_by_category: dict[str, int] = field(default_factory=dict)
    qty_errors: list[dict[str, Any]] = field(default_factory=list)
    unmapped_actual: list[dict[str, Any]] = field(default_factory=list)
    recall: float = 0.0
    precision_proxy: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        visual = getattr(self, "_visual", None) or {}
        return {
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
            "hits": [
                {
                    "expected": h.expected,
                    "actual": {
                        "description": h.actual.get("description"),
                        "unit": h.actual.get("unit"),
                        "quantity": h.actual.get("quantity"),
                        "item_code": h.actual.get("item_code"),
                        "category": h.actual.get("category"),
                    },
                    "actual_description": h.actual.get("description"),
                    "qty_ok": h.qty_ok,
                    "qty_delta": h.qty_delta,
                    "method": h.method,
                }
                for h in self.hits
            ],
            "misses": self.misses,
            "extras": [
                {
                    "description": e.get("description"),
                    "unit": e.get("unit"),
                    "category": e.get("category"),
                    "quantity": e.get("quantity"),
                    "item_code": e.get("item_code"),
                    "calculation_method": e.get("calculation_method"),
                }
                for e in self.extras
            ],
            "misses_by_category": self.misses_by_category,
            "qty_errors": self.qty_errors,
            "unmapped_actual": [
                {"description": u.get("description"), "unit": u.get("unit")}
                for u in self.unmapped_actual
            ],
            "recall": self.recall,
            "precision_proxy": self.precision_proxy,
            "visual": visual,
        }


def parse_expected_items(raw: list[dict[str, Any]] | dict[str, Any]) -> list[ExpectedItem]:
    rows = raw.get("items") if isinstance(raw, dict) else raw
    out: list[ExpectedItem] = []
    for row in rows or []:
        out.append(
            ExpectedItem(
                description=str(row.get("description") or ""),
                unit=str(row.get("unit") or "UNIT"),
                category=row.get("category"),
                quantity=float(row["quantity"]) if row.get("quantity") is not None else None,
                quantity_tolerance=float(row.get("quantity_tolerance", 0.05)),
                quantity_abs_tolerance=float(row.get("quantity_abs_tolerance", 1.0)),
                item_code=row.get("item_code"),
                required=bool(row.get("required", True)),
            )
        )
    return out


def _item_match_score(expected: ExpectedItem, actual: dict[str, Any]) -> tuple[float, str]:
    ed = _norm_text(expected.description)
    ad = _norm_text(str(actual.get("description") or ""))
    # Normalize compound utility words so "watermain" ≈ "water main"
    ed = ed.replace("watermain", "water main").replace("stormsewer", "storm sewer")
    ad = ad.replace("watermain", "water main").replace("stormsewer", "storm sewer")
    eu = _norm_unit(expected.unit)
    au = _norm_unit(str(actual.get("unit") or ""))
    if not ed or not ad:
        return 0.0, "empty"

    e_size = _size_token(ed)
    a_size = _size_token(ad)
    size_conflict = bool(e_size and a_size and e_size != a_size)
    unit_conflict = bool(eu != au and eu != "unit" and au != "unit")

    if ed == ad:
        base, method = 100.0, "exact"
    elif ed in ad or ad in ed:
        base, method = 90.0, "substring"
    else:
        et, at = _tokens(ed), _tokens(ad)
        if not et or not at:
            return 0.0, "no_tokens"
        # Prefer recall-friendly overlap vs expected tokens (original gold-set behavior),
        # but also consider Jaccard so long AutoVAD strings don't dominate.
        overlap_exp = len(et & at) / max(len(et), 1)
        overlap_jac = len(et & at) / max(len(et | at), 1)
        overlap = max(overlap_exp, overlap_jac)
        base = overlap * 100.0
        method = "token_overlap"
        if e_size and a_size and e_size == a_size:
            base = min(100.0, base + 15.0)
        # Soft boost when most expected tokens are present
        if overlap_exp >= 0.7:
            base = max(base, 70.0)

    # Soft near-miss path for unit/size conflicts (do not hard-match these)
    if size_conflict:
        return min(base, 48.0), "size_mismatch"
    if unit_conflict:
        return min(base, 52.0), "unit_mismatch"
    if base >= 55:
        return base, method
    return base, "no_match" if base < 20 else "weak_overlap"


def _qty_ok(expected: ExpectedItem, actual_qty: float) -> tuple[bool, float | None]:
    if expected.quantity is None:
        return True, None
    delta = abs(actual_qty - expected.quantity)
    rel = delta / max(abs(expected.quantity), 1e-9)
    ok = delta <= expected.quantity_abs_tolerance or rel <= expected.quantity_tolerance
    return ok, delta


def _reason_for_miss(*, method: str, best_score: float, best_actual: dict[str, Any] | None) -> str:
    if not best_actual or best_score < 15:
        return "Not found in AutoVAD EOQ — missing schedule/pay-item extraction"
    if method == "unit_mismatch":
        return (
            f"Looks similar to “{best_actual.get('description')}” but unit differs "
            f"({best_actual.get('unit')}) — treat as unmatched"
        )
    if method == "size_mismatch":
        return (
            f"Similar wording to “{best_actual.get('description')}” but pipe/size differs"
        )
    if method in {"weak_overlap", "token_overlap", "no_match"} and best_score >= 20:
        return (
            f"Near wording to “{best_actual.get('description')}” "
            f"(similarity {best_score:.0f}%) but below match threshold"
        )
    return "Not confidently matched to any AutoVAD line"


def _reason_for_extra(act: dict[str, Any]) -> str:
    desc = str(act.get("description") or "")
    method = str(act.get("calculation_method") or act.get("source_reference") or "").lower()
    if any(k in method for k in ("label", "callout", "drawing", "symbol", "geometry")):
        return "Plan/detail-derived item not listed on original EOQ schedule"
    if re.search(r"valve|hydrant|elbow|tee|bend|reducer|plug|casing|carrier", desc, re.I):
        return "Likely fitting/appurtenance invent — not a matching original pay item"
    return "Extra AutoVAD line with no matching original EOQ item"


def compare_eoq(
    expected: list[ExpectedItem] | list[dict[str, Any]] | dict[str, Any],
    actual: list[dict[str, Any]],
) -> CompareReport:
    """Match expected gold items to actual takeoff/EOQ rows; report misses by category."""
    if isinstance(expected, list) and expected and isinstance(expected[0], ExpectedItem):
        exp_items = expected  # type: ignore[assignment]
    else:
        exp_items = parse_expected_items(expected)  # type: ignore[arg-type]
    report = CompareReport(expected_count=len(exp_items), actual_count=len(actual))
    used_actual: set[int] = set()

    matched_rows: list[dict[str, Any]] = []
    near_miss_rows: list[dict[str, Any]] = []
    line_audit: list[dict[str, Any]] = []
    by_category: dict[str, dict[str, float]] = {}

    def cat_bucket(cat: str | None) -> dict[str, float]:
        key = _norm_category(cat)
        if key not in by_category:
            by_category[key] = {
                "expected": 0,
                "matched": 0,
                "qty_error": 0,
                "missed": 0,
                "near_miss": 0,
                "extras": 0,
            }
        return by_category[key]

    for exp in exp_items:
        cat = _norm_category(exp.category)
        cat_bucket(cat)["expected"] += 1

        best_idx = -1
        best_score = 0.0
        best_method = "no_match"
        for idx, act in enumerate(actual):
            if idx in used_actual:
                continue
            score, method = _item_match_score(exp, act)
            if score > best_score:
                best_score = score
                best_idx = idx
                best_method = method

        best_act = actual[best_idx] if best_idx >= 0 else None

        # Hard match
        if best_idx >= 0 and best_score >= 55 and best_method not in {"unit_mismatch", "size_mismatch"}:
            act = actual[best_idx]
            used_actual.add(best_idx)
            try:
                aqty = float(act.get("quantity") or 0)
            except (TypeError, ValueError):
                aqty = 0.0
            ok, delta = _qty_ok(exp, aqty)
            hit = MatchHit(
                expected=asdict(exp),
                actual=act,
                qty_ok=ok,
                qty_delta=delta,
                method=best_method,
            )
            report.hits.append(hit)
            status = "matched" if ok else "qty_error"
            reason = (
                "Matched description/unit; quantities within tolerance"
                if ok
                else (
                    f"Matched item but quantity differs — original {exp.quantity} vs AutoVAD {aqty} "
                    f"(Δ {delta})"
                )
            )
            row = {
                "status": status,
                "category": cat,
                "item_code": exp.item_code or act.get("item_code"),
                "original_description": exp.description,
                "original_unit": exp.unit,
                "original_qty": exp.quantity,
                "autovad_description": act.get("description"),
                "autovad_unit": act.get("unit"),
                "autovad_qty": aqty,
                "qty_ok": ok,
                "qty_delta": delta,
                "similarity": round(best_score, 1),
                "match_method": best_method,
                "reason": reason,
            }
            matched_rows.append(row)
            line_audit.append(row)
            cat_bucket(cat)["matched"] += 1
            if not ok:
                cat_bucket(cat)["qty_error"] += 1
                report.qty_errors.append(
                    {
                        "description": exp.description,
                        "expected_qty": exp.quantity,
                        "actual_qty": aqty,
                        "delta": delta,
                        "unit": exp.unit,
                        "category": cat,
                        "autovad_description": act.get("description"),
                        "reason": reason,
                    }
                )
            continue

        # Near-miss: looks similar but not accepted
        if best_act is not None and best_score >= 20:
            try:
                aqty = float(best_act.get("quantity") or 0)
            except (TypeError, ValueError):
                aqty = None
            reason = _reason_for_miss(method=best_method, best_score=best_score, best_actual=best_act)
            near = {
                "status": "near_miss",
                "category": cat,
                "item_code": exp.item_code,
                "original_description": exp.description,
                "original_unit": exp.unit,
                "original_qty": exp.quantity,
                "autovad_description": best_act.get("description"),
                "autovad_unit": best_act.get("unit"),
                "autovad_qty": aqty,
                "similarity": round(best_score, 1),
                "match_method": best_method,
                "reason": reason,
            }
            near_miss_rows.append(near)
            cat_bucket(cat)["near_miss"] += 1
            # Still count as miss for recall if required
            if exp.required:
                miss = {
                    "description": exp.description,
                    "unit": exp.unit,
                    "category": cat,
                    "quantity": exp.quantity,
                    "item_code": exp.item_code,
                    "reason": reason,
                    "nearest_autovad": best_act.get("description"),
                    "similarity": round(best_score, 1),
                }
                report.misses.append(miss)
                report.misses_by_category[cat] = report.misses_by_category.get(cat, 0) + 1
                cat_bucket(cat)["missed"] += 1
                line_audit.append({**near, "status": "miss_near"})
            continue

        if exp.required:
            reason = _reason_for_miss(method=best_method, best_score=best_score, best_actual=best_act)
            miss = {
                "description": exp.description,
                "unit": exp.unit,
                "category": cat,
                "quantity": exp.quantity,
                "item_code": exp.item_code,
                "reason": reason,
                "nearest_autovad": (best_act or {}).get("description"),
                "similarity": round(best_score, 1) if best_act else 0,
            }
            report.misses.append(miss)
            report.misses_by_category[cat] = report.misses_by_category.get(cat, 0) + 1
            cat_bucket(cat)["missed"] += 1
            line_audit.append(
                {
                    "status": "miss",
                    "category": cat,
                    "item_code": exp.item_code,
                    "original_description": exp.description,
                    "original_unit": exp.unit,
                    "original_qty": exp.quantity,
                    "autovad_description": (best_act or {}).get("description"),
                    "autovad_unit": (best_act or {}).get("unit"),
                    "autovad_qty": (best_act or {}).get("quantity"),
                    "similarity": round(best_score, 1) if best_act else 0,
                    "match_method": best_method,
                    "reason": reason,
                }
            )

    extras_rows: list[dict[str, Any]] = []
    for idx, act in enumerate(actual):
        if idx not in used_actual:
            report.extras.append(act)
            reason = _reason_for_extra(act)
            cat = _norm_category(str(act.get("category") or "Other"))
            cat_bucket(cat)["extras"] += 1
            extras_rows.append(
                {
                    "status": "extra",
                    "category": cat,
                    "item_code": act.get("item_code"),
                    "autovad_description": act.get("description"),
                    "autovad_unit": act.get("unit"),
                    "autovad_qty": act.get("quantity"),
                    "reason": reason,
                    "source": act.get("calculation_method") or act.get("source_reference"),
                }
            )
        method = str(act.get("bid_match_method") or "")
        if method == "unmapped" or (
            act.get("bid_template_line_id") is None
            and str(act.get("category") or "").lower() == "unmapped takeoff"
        ):
            report.unmapped_actual.append(act)

    required = sum(1 for e in exp_items if e.required) or len(exp_items) or 1
    report.recall = round(len(report.hits) / required, 4)
    report.precision_proxy = round(
        len(report.hits) / max(len(actual), 1),
        4,
    )

    # Attach engineer visual payload on the report object via to_dict extension
    report._visual = {  # type: ignore[attr-defined]
        "matched": matched_rows,
        "near_misses": near_miss_rows,
        "misses": list(report.misses),
        "qty_errors": report.qty_errors,
        "extras": extras_rows,
        "line_audit": line_audit,
        "by_category": [
            {"category": k, **v}
            for k, v in sorted(by_category.items(), key=lambda kv: (-kv[1]["missed"], -kv[1]["expected"], kv[0]))
        ],
        "summary": {
            "expected": report.expected_count,
            "autovad": report.actual_count,
            # All hard matches (qty OK + qty error) — what the Matched table shows
            "matched": len(matched_rows),
            "matched_qty_ok": len([r for r in matched_rows if r["status"] == "matched"]),
            "qty_errors": len(report.qty_errors),
            "near_misses": len(near_miss_rows),
            "misses": len(report.misses),
            "extras": len(extras_rows),
            "recall": report.recall,
            "precision_proxy": report.precision_proxy,
        },
    }
    return report


def summarize_report(report: CompareReport) -> str:
    lines = [
        f"Recall: {report.recall:.0%}  ({len(report.hits)}/{report.expected_count} expected)",
        f"Actual rows: {report.actual_count}  |  extras: {len(report.extras)}  |  qty errors: {len(report.qty_errors)}",
    ]
    if report.misses_by_category:
        cats = ", ".join(f"{k}={v}" for k, v in sorted(report.misses_by_category.items()))
        lines.append(f"Misses by category: {cats}")
    for m in report.misses[:12]:
        lines.append(f"  MISS [{m.get('category')}] {m.get('description')} ({m.get('unit')})")
    for q in report.qty_errors[:8]:
        lines.append(
            f"  QTY  {q.get('description')}: expected {q.get('expected_qty')} "
            f"got {q.get('actual_qty')} (delta {q.get('delta')})"
        )
    return "\n".join(lines)
