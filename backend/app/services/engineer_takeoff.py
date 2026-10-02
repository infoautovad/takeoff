"""Civil-estimator merge of bid-schedule rows and drawing takeoff.

An estimator building an EOQ from a plan set:
1. Copies the Estimate of Quantities / Bid Items sheet (the pay-item list).
2. Uses typicals, plan/profile, and details to measure, fill blank cells,
   and catch pay items the schedule missed.
3. Never overwrites a printed schedule quantity with typical-section math,
   symbol counts, or F-sheet device lists.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.incidental import should_drop_incidental_item
from app.services.item_combine import pay_items_similar
from app.services.traffic_control import (
    is_distinct_traffic_pay_item,
    is_generic_traffic_control_signing,
    is_plan_device_takeoff,
    looks_like_agency_bid_number,
)

_REMOVE_RE = re.compile(
    r"\b(remove|removal|salvage|abandon|demolish|demolition|saw(?:cut)?)\b",
    re.I,
)
_LS_UNITS = frozenset({"ls", "lump sum", "lump-sum"})

_FAMILY_RES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:aggregate\s+base|crushed\s+(?:stone|aggregate)|granular\s+base|\babc\b)", re.I), "abc"),
    (re.compile(r"\b(?:hot\s*mix|\bhma\b|asphalt\s+(?:concrete|pavement|surfacing)|bituminous)", re.I), "hma"),
    (re.compile(r"\b(?:geotextile|geogrid|pavement\s+fabric)", re.I), "geotextile"),
    (re.compile(r"\b(?:unclassified\s+excavation|common\s+excavation)", re.I), "unclass_exc"),
    (re.compile(r"\b(?:curb|gutter)\b", re.I), "curb"),
    (re.compile(r"\b(?:sidewalk|pcc\s+approach|concrete\s+approach)", re.I), "sidewalk"),
    (re.compile(r"\bbarricade", re.I), "barricade"),
    (re.compile(r"\b(?:class\s+m-?6|structural\s+concrete)\b", re.I), "m6_concrete"),
    (re.compile(r"\b(?:rcp|reinforced\s+concrete\s+pipe)\b", re.I), "rcp"),
    (re.compile(r"\btype\s+[by]\s+(?:frame|casting)", re.I), "type_frame"),
    (re.compile(r"\bfertiliz", re.I), "fertilizer"),
    (re.compile(r"\b(?:seeding|seed\s+mix)\b", re.I), "seed"),
    (re.compile(r"\b(?:watering|water\s+for\s+vegetation)\b", re.I), "watering"),
]

_CORE_TYPICAL_FAMILIES = frozenset(
    {"abc", "hma", "geotextile", "curb", "sidewalk", "m6_concrete"}
)


def is_core_typical_pay_item(item: dict[str, Any]) -> bool:
    """Pavement / curb / fabric from a typical section — keep even if a (possibly fake) schedule exists."""
    fam = _family(item)
    if fam in _CORE_TYPICAL_FAMILIES:
        return True
    desc = _desc(item).lower()
    return any(k in desc for k in ("prime coat", "tack coat", "geotextile", "pavement fabric"))

_TYPICAL_HINTS = (
    "typical section",
    "wide ×",
    "wide x",
    "/ 27",
    "145 pcf",
    "design takeoff",
    "cover assumed",
    "trench width",
)


def _blob(item: dict[str, Any]) -> str:
    return (
        f"{item.get('calculation_method') or ''} "
        f"{item.get('source_reference') or ''} "
        f"{item.get('source') or ''}"
    ).lower()


def _desc(item: dict[str, Any]) -> str:
    return str(item.get("description") or "").strip()


def _qty(item: dict[str, Any]) -> float:
    try:
        return float(item.get("quantity") or 0)
    except (TypeError, ValueError):
        return 0.0


def _unit_key(item: dict[str, Any]) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(item.get("unit") or "").strip().lower())


def _is_ls(item: dict[str, Any]) -> bool:
    return _unit_key(item) in {"ls", "lumpsum"} or str(item.get("unit") or "").strip().lower() in _LS_UNITS


def _norm_bid_code(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text == "special":
        return "special"
    if re.fullmatch(r"\d+\.\d+", text):
        return text.rstrip("0").rstrip(".")
    return text


def _remove_like(item: dict[str, Any]) -> bool:
    return bool(_REMOVE_RE.search(_desc(item)))


def _family(item: dict[str, Any]) -> str:
    text = _desc(item)
    for pattern, key in _FAMILY_RES:
        if pattern.search(text):
            return key
    return ""


def _qty_blank(item: dict[str, Any]) -> bool:
    if bool(item.get("quantity_blank")):
        return True
    raw = item.get("raw_quantity")
    if raw is not None and str(raw).strip() == "":
        return True
    if _is_ls(item):
        return False
    return _qty(item) <= 0


def _unit_blank(item: dict[str, Any]) -> bool:
    if bool(item.get("unit_blank")):
        return True
    raw = item.get("raw_unit")
    if raw is not None and str(raw).strip() == "":
        return True
    unit = str(item.get("unit") or "").strip()
    return (not unit) or unit.upper() == "UNIT"


def is_typical_section_invent(item: dict[str, Any]) -> bool:
    if str(item.get("entity_type") or "").upper() == "ESTIMATOR":
        return True
    blob = _blob(item)
    return any(h in blob for h in _TYPICAL_HINTS)


def is_device_list_item(item: dict[str, Any]) -> bool:
    """F-sheet / MUTCD extras — not Traffic Control bid rows or hydrant/MH counts."""
    desc = _desc(item).lower()
    blob = _blob(item)
    if "channelizer" in desc or "channelizer" in blob:
        return True
    if looks_like_agency_bid_number(item.get("item_code")):
        return False
    if is_distinct_traffic_pay_item(item):
        return False
    if is_generic_traffic_control_signing(item):
        return False
    if any(h in blob for h in ("project total", "mutcd ref", "÷144", "/144")):
        return True
    if "itemized list" in blob and re.search(r"\b(drum|cone|sign face)\b", desc):
        return True
    trafficish = any(
        k in f"{blob} {desc}"
        for k in ("mutcd", "sign face", "graphic count")
    )
    if trafficish and is_plan_device_takeoff(item):
        return True
    return False


def _codes_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ca, cb = _norm_bid_code(a.get("item_code")), _norm_bid_code(b.get("item_code"))
    if not ca or not cb:
        return False
    if ca == "special" or cb == "special":
        return False
    return ca == cb


def _compatible_actions(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return _remove_like(a) == _remove_like(b)


def match_score(schedule: dict[str, Any], drawing: dict[str, Any]) -> float:
    """Higher = same pay item. 0 = do not match."""
    if not _desc(schedule) or not _desc(drawing):
        return 0.0
    if not _compatible_actions(schedule, drawing):
        return 0.0
    if _is_ls(schedule) != _is_ls(drawing) and _is_ls(schedule):
        return 0.0

    score = 0.0
    if _codes_match(schedule, drawing):
        score += 100.0
    same_unit = _unit_key(schedule) == _unit_key(drawing) and bool(_unit_key(schedule))
    if same_unit and pay_items_similar(schedule, drawing):
        score += 80.0
    elif pay_items_similar(
        {**drawing, "unit": schedule.get("unit") or drawing.get("unit")},
        schedule,
    ) and (_unit_blank(schedule) or same_unit):
        score += 70.0

    fam_s, fam_d = _family(schedule), _family(drawing)
    if fam_s and fam_s == fam_d and _compatible_actions(schedule, drawing):
        if same_unit or _unit_blank(schedule):
            score += 40.0
        else:
            # Same material, different unit (ABC Ton vs CY) — not a fill match.
            score += 0.0

    sa, sb = _size_token(_desc(schedule)), _size_token(_desc(drawing))
    if sa and sb and sa != sb:
        return 0.0
    return score


def _size_token(description: str) -> str:
    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*-?\s*(?:inch|in|\"|'')", description, re.I)
    return m.group(1) if m else ""


def _best_drawing_index(
    schedule: dict[str, Any],
    drawings: list[dict[str, Any] | None],
) -> tuple[int, float]:
    best_i, best_s = -1, 0.0
    for i, drawing in enumerate(drawings):
        if drawing is None:
            continue
        score = match_score(schedule, drawing)
        if score > best_s:
            best_i, best_s = i, score
    return best_i, best_s


def _drawing_duplicates_schedule(drawing: dict[str, Any], schedule_rows: list[dict[str, Any]]) -> bool:
    """True when the drawing row is the same pay item (or same material family) already listed."""
    for row in schedule_rows:
        if not _compatible_actions(row, drawing):
            continue
        if _codes_match(row, drawing):
            return True
        if _unit_key(row) == _unit_key(drawing) and pay_items_similar(row, drawing):
            return True
        fam_s, fam_d = _family(row), _family(drawing)
        if fam_s and fam_s == fam_d:
            return True
    return False


def is_trench_assumption(item: dict[str, Any]) -> bool:
    """Invented trench/bedding CY from cover assumptions — not a typical pavement takeoff."""
    blob = _blob(item)
    desc = _desc(item).lower()
    if "cover assumed" in blob or "trench width" in blob:
        return True
    return bool(re.search(r"trench\s+excavation|pipe\s+bedding|haunch", desc))


def _keep_unmatched_drawing(
    drawing: dict[str, Any],
    schedule_rows: list[dict[str, Any]],
    *,
    schedule_is_thin: bool,
) -> bool:
    if not _desc(drawing):
        return False
    if _qty(drawing) <= 0 and not _is_ls(drawing):
        return False
    if is_device_list_item(drawing):
        return False
    if should_drop_incidental_item(drawing, scheduled=False, drop_default_extras=True):
        return False
    if is_trench_assumption(drawing):
        return False
    if _drawing_duplicates_schedule(drawing, schedule_rows):
        return False
    if is_typical_section_invent(drawing):
        if is_core_typical_pay_item(drawing):
            return True
        # Other typical-section math only when the transcribed schedule looks incomplete.
        if not schedule_is_thin:
            return False
    return True


def _apply_drawing_to_schedule(schedule: dict[str, Any], drawing: dict[str, Any]) -> dict[str, Any]:
    """Keep schedule identity/qty; fill blanks; attach drawing evidence."""
    out = dict(schedule)
    draw_ref = str(drawing.get("source_reference") or drawing.get("source") or "").strip()
    draw_method = str(drawing.get("calculation_method") or "").strip()
    sched_qty = _qty(schedule)
    draw_qty = _qty(drawing)

    filled = False
    if _qty_blank(schedule) and draw_qty > 0 and not (_is_ls(schedule) and not _is_ls(drawing)):
        if _unit_blank(schedule) or _unit_key(schedule) == _unit_key(drawing) or not _unit_key(drawing):
            out["quantity"] = drawing.get("quantity")
            out["quantity_blank"] = False
            out["raw_quantity"] = str(drawing.get("quantity") or "")
            filled = True
            if _unit_blank(schedule) and not _unit_blank(drawing):
                out["unit"] = drawing.get("unit")
                out["unit_blank"] = False
                out["raw_unit"] = str(drawing.get("unit") or "")
            marker = (
                f"Blank schedule quantity filled from drawing takeoff "
                f"({draw_qty:g} {drawing.get('unit') or ''}{' — ' + draw_ref if draw_ref else ''})."
            )
            base = str(out.get("calculation_method") or "")
            out["calculation_method"] = f"{base} | {marker}".strip(" |")
            out["status"] = "needs_review"
            out["needs_review"] = True
            out["filled_from_drawing"] = True

    if not filled and draw_qty > 0 and sched_qty > 0:
        rel = abs(draw_qty - sched_qty) / max(abs(sched_qty), 1e-9)
        if rel > 0.05:
            note = (
                f"Drawing check {draw_qty:g} {drawing.get('unit') or ''} "
                f"vs schedule {sched_qty:g} {schedule.get('unit') or ''} "
                f"(schedule quantity kept"
                f"{'; ' + draw_ref if draw_ref else ''})."
            )
            base = str(out.get("calculation_method") or "")
            if "drawing check" not in base.lower():
                out["calculation_method"] = f"{base} | {note}".strip(" |")
            out["drawing_quantity_check"] = draw_qty

    if draw_ref:
        existing = str(out.get("drawing_evidence") or "").strip()
        if draw_ref not in existing:
            out["drawing_evidence"] = f"{existing}; {draw_ref}".strip("; ")
    if draw_method and "typical" in draw_method.lower():
        out["drawing_method"] = draw_method
    return out


def merge_schedule_with_drawings(
    schedule_rows: list[dict[str, Any]],
    drawing_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Schedule is the bid list. Drawings fill blanks, check qty, and add missed pay items."""
    stats = {
        "schedule_rows": len(schedule_rows),
        "drawing_rows": len(drawing_rows),
        "filled_blanks": 0,
        "qty_checks": 0,
        "added_from_drawings": 0,
        "dropped_drawing_rows": 0,
    }
    if not schedule_rows:
        kept = []
        for item in drawing_rows:
            if is_device_list_item(item):
                stats["dropped_drawing_rows"] += 1
                continue
            if should_drop_incidental_item(item, scheduled=False, drop_default_extras=True):
                stats["dropped_drawing_rows"] += 1
                continue
            kept.append(dict(item))
        stats["added_from_drawings"] = len(kept)
        return kept, stats

    pool: list[dict[str, Any] | None] = [dict(item) for item in drawing_rows if _desc(item)]
    merged: list[dict[str, Any]] = []

    for raw in schedule_rows:
        schedule = dict(raw)
        idx, score = _best_drawing_index(schedule, pool)
        if idx >= 0 and score >= 70:
            drawing = pool[idx]
            assert drawing is not None
            before_blank = _qty_blank(schedule)
            before_qty = _qty(schedule)
            schedule = _apply_drawing_to_schedule(schedule, drawing)
            if before_blank and not _qty_blank(schedule):
                stats["filled_blanks"] += 1
            if schedule.get("drawing_quantity_check") is not None and before_qty > 0:
                stats["qty_checks"] += 1
            pool[idx] = None
        merged.append(schedule)

    schedule_is_thin = len(schedule_rows) < 20
    for drawing in pool:
        if drawing is None:
            continue
        if _keep_unmatched_drawing(drawing, merged, schedule_is_thin=schedule_is_thin):
            added = dict(drawing)
            added["added_from_drawing"] = True
            if not str(added.get("calculation_method") or "").strip():
                added["calculation_method"] = "Drawing takeoff — pay item not listed on transcribed schedule"
            merged.append(added)
            stats["added_from_drawings"] += 1
        else:
            stats["dropped_drawing_rows"] += 1

    return merged, stats
