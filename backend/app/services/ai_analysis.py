"""Civil document intelligence: OpenAI when configured, heuristic fallback otherwise.

PDF plans use text/tables PLUS rendered drawing sheets via OpenAI vision so
engineering drawings (not only OCR text) drive EOQ quantities.
"""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.services.extractors import ExtractedContent
from app.services.incidental import (
    description_is_incidental_child,
    extraction_should_skip,
    quantity_inflated_by_incidentals,
    should_drop_incidental_item,
)
from app.services.item_combine import combine_similar_pay_items

CIVIL_PATTERNS: list[tuple[str, str, str, str]] = [
    # description_key, category, unit_hint, regex
    ("GSB", "Pavement", "m3", r"\bGSB\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cu\.?\s*m|cubic\s*meters?|cy|cu\.?\s*yd)"),
    ("WMM", "Pavement", "m3", r"\bWMM\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cu\.?\s*m|cubic\s*meters?|cy|cu\.?\s*yd)"),
    ("DBM", "Pavement", "m3", r"\bDBM\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cu\.?\s*m|cubic\s*meters?|cy|cu\.?\s*yd)"),
    ("Bituminous Concrete", "Pavement", "m3", r"\b(?:BC|Bituminous\s*Concrete)\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|t|ton|tons?|cy)"),
    ("Asphalt", "Pavement", "m3", r"\bAsphalt\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|t|ton|tons?|cy)"),
    ("HMA", "Pavement", "ton", r"\b(?:HMA|Hot\s*Mix\s*Asphalt)\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(t|ton|tons?|cy|m3)"),
    ("Earthwork Cut", "Earthwork", "m3", r"\b(?:Cut|Excavation)\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cy|cu\.?\s*yd)"),
    ("Earthwork Fill", "Earthwork", "m3", r"\b(?:Fill|Embankment)\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cy|cu\.?\s*yd)"),
    ("Concrete", "Structures", "m3", r"\bConcrete\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Kerb", "Roadside", "m", r"\bKerb(?:ing)?\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m|lm|lin(?:ear)?\s*m|lf|ft)"),
    ("Curb and Gutter", "Roadside", "lf", r"\bCurb(?:ing)?(?:\s*(?:and|&)\s*Gutter)?\b.*?(\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*(lf|lft|ft|m)"),
    ("Sidewalk", "Roadside", "sf", r"\bSidewalk\b.*?(\d{1,7}(?:,\d{3})*(?:\.\d+)?)\s*(sf|sq\.?\s*ft|m2|m²|sy)"),
    ("Culvert", "Drainage", "nos", r"\bCulvert(?:s)?\b.*?(\d{1,4})\s*(nos?|no\.?|each|ea)"),
    ("Drainage", "Drainage", "m", r"\bDrain(?:age)?\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m|lm|lf|ft)"),
    ("Brickwork", "Building", "cy", r"\bBrick(?:work)?\b.*?(\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Plastering", "Building", "sf", r"\bPlaster(?:ing)?\b.*?(\d{1,7}(?:,\d{3})*(?:\.\d+)?)\s*(m2|m²|sf)"),
    ("Doors", "Building", "ea", r"\bDoors?\b.*?(\d{1,4})\s*(nos?|ea|each)"),
    ("Windows", "Building", "ea", r"\bWindows?\b.*?(\d{1,4})\s*(nos?|ea|each)"),
    ("Dam Embankment Fill", "Dams & Reservoirs", "cy", r"\b(?:Dam\s+)?Embankment\b.*?(\d{1,8}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Spillway Concrete", "Dams & Reservoirs", "cy", r"\bSpillway\b.*?(\d{1,7}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Riprap", "Dams & Reservoirs", "cy", r"\bRiprap\b.*?(\d{1,7}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cy|ton)"),
    ("Reservoir Lining", "Dams & Reservoirs", "sf", r"\b(?:Reservoir|Pond)\s*Lin(?:ing|er)\b.*?(\d{1,8}(?:,\d{3})*(?:\.\d+)?)\s*(m2|m²|sf)"),
    ("Road Width", "Geometry", "m", r"\b(?:Road|Carriageway)\s*Width\b.*?(\d{1,2}(?:\.\d+)?)\s*(m|ft)\b"),
]

ITEM_ALIASES = {
    "gsb": ("GSB", "Pavement", "m3"),
    "granular sub base": ("GSB", "Pavement", "m3"),
    "wmm": ("WMM", "Pavement", "m3"),
    "wet mix macadam": ("WMM", "Pavement", "m3"),
    "dbm": ("DBM", "Pavement", "m3"),
    "dense bituminous macadam": ("DBM", "Pavement", "m3"),
    "bc": ("Bituminous Concrete", "Pavement", "m3"),
    "bituminous concrete": ("Bituminous Concrete", "Pavement", "m3"),
    "asphalt": ("Asphalt", "Pavement", "m3"),
    "hma": ("HMA", "Pavement", "ton"),
    "kerb": ("Kerb", "Roadside", "m"),
    "curb": ("Curb and Gutter", "Roadside", "lf"),
    "sidewalk": ("Sidewalk", "Roadside", "sf"),
    "culvert": ("Culvert", "Drainage", "nos"),
    "concrete": ("Concrete", "Structures", "m3"),
    "excavation": ("Earthwork Cut", "Earthwork", "m3"),
    "cut": ("Earthwork Cut", "Earthwork", "m3"),
    "fill": ("Earthwork Fill", "Earthwork", "m3"),
    "embankment": ("Earthwork Fill", "Earthwork", "m3"),
    "brickwork": ("Brickwork", "Building", "cy"),
    "plaster": ("Plastering", "Building", "sf"),
    "doors": ("Doors", "Building", "ea"),
    "windows": ("Windows", "Building", "ea"),
    "spillway": ("Spillway Concrete", "Dams & Reservoirs", "cy"),
    "riprap": ("Riprap", "Dams & Reservoirs", "cy"),
    "reservoir lining": ("Reservoir Lining", "Dams & Reservoirs", "sf"),
    "dam embankment": ("Dam Embankment Fill", "Dams & Reservoirs", "cy"),
}

# Shared accuracy rules for text + vision takeoff (Training Lab Test 1/2 failure modes).
TAKEOFF_ACCURACY_RULES = """
SOURCE OF TRUTH (strict — follow in order):
1. Estimate Of Quantities / bid schedule / proposal quantity tables are AUTHORITATIVE.
   For every item, copy description, STD BID NO / item_code, unit, and quantity from the SAME schedule row.
2. Treat “(Ctd.)”, “continued”, and repeated table headers as ONE continuous schedule.
   Extract ALL rows on continuation pages and keep the parent category (e.g. Water Main, not only “Water Main (Ctd.)”).
3. Include Alternate A / Alternate B / option sections as valid pay items; keep the alternate label in category or description.
4. Include lump-sum and non-physical rows: Mobilization, Tax on City Furnished Materials, Winter Maintenance,
   Traffic Control, temporary items, signals, lighting, removals, erosion/landscaping.
5. Copy Bid Items / Estimate Of Quantities / proposal quantity rows when they exist.
   Also keep other evidenced pay items (pipe, pavement, curb, sidewalk, hydrants, valves as EA,
   manholes, removals, earthwork, landscaping, structures). Combine duplicates later.
   Do NOT add: incidental trench/bedding/backfill/fittings, individual MUTCD sign faces as Each items,
   graphic channelizer counts, or traffic-control device “Project Totals” / itemized device tables.
6. When the SAME pay item appears on both a bid schedule and a plan callout, keep one row and use
   the schedule quantity. Do not replace a schedule quantity by counting symbols.
7. Keep schedule-distinct variants separate (furnish vs install, diameters, materials, alternates).
8. INCIDENTAL WORK is not a pay item. If a note says work is incidental to / included in / paid under a bid item
   (or "no separate payment/measurement"), do NOT output it as its own quantity AND do NOT add it into the parent
   item quantity. Parent qty = the pay item only (schedule cell or measured pipe/pavement), never parent + incidentals.
   Typical-section details for bedding, trench, backfill, fittings, tracer wire, thrust blocks, polywrap, and testing
   are construction details unless that work is its own Bid Items / EOQ row.
9. Same pay item on multiple sheets/locations (e.g. Fertilizer 1,189 lb and Fertilizer 39 lb) is ONE bid item.
   Keep the same description/unit so location quantities can be combined. Do not invent a second pay item name.

REQUIRED SEARCH PASSES:
- General / LS / tax / temporary / winter maintenance
- Traffic Control, Traffic Signals, Lighting
- Removals / abandon / sawcut / salvage / clear & grub
- Grading / topsoil
- Erosion Control, Planting & Landscaping (seed, fertilizer, silt fence, wattles, riprap, blankets, weed control)
- Surfacing / curb / pavement
- Water Main (+ continuation pages), Storm Sewer, Sanitary Sewer
- Structures / bridges / retaining walls
- Dams, spillways, reservoirs / pond lining
- Building: brickwork, RCC, doors, windows, plaster, flooring, roofing
- Alternate A / Alternate B sections

UNITS (normalize on output):
LS, Each, Ft, LFt, SqFt, SqYd, CuYd, Ton, Lb, Acre, Hour, MGal, Ac-Ft.
Map ea→Each, lf→Ft when the schedule does not specify otherwise. Preserve decimals (e.g. 4.2 Acre, 7.3 Ton).

TRAFFIC CONTROL:
IF a Bid Items / Estimate Of Quantities table has a Traffic Control section:
- Copy EVERY row under that heading (BID ITEM number, description, unit, EST. QTY). Do not collapse the section to one line.
- "Traffic Control" with unit SqFt uses the schedule EST. QTY as-is. Never recompute it from MUTCD 30×30 or plan symbol counts.
- Keep companion pay items as separate rows when listed: Traffic Control Miscellaneous (LS), barricades (Each),
  temporary business signs (Each), portable changeable message signs (Each), temporary mailbox (Each),
  temporary gravel access (LS), winter maintenance (LS), and any other printed Traffic Control bid rows.
- Copy BID ITEM / Standard Bid Item Number when printed (agency numbers like 634.0110 or Special — not CSI “01 55 26”).
- Do NOT add extra bid items from traffic-control device tables (“Project Totals”, itemized device lists),
  graphic channelizer counts, or individual MUTCD signs. Those faces belong in Traffic Control SqFt when that pay item exists.
ELSE (no bid schedule for signing):
- Do NOT list individual STOP/YIELD/Speed Limit/MUTCD signs as separate Each pay items.
- Roll those sign faces into ONE pay item: description "Traffic Control", unit SqFt (width×height in inches ÷ 144).
- Keep barricades, drums, PCMS, temporary business signs, and true TTC LS items as their own pay items when evidenced.

EVIDENCE:
Cite a schedule row, typical section, dimension, sheet, or callout in source_reference / calculation_method.
Do not omit a pay item that is printed as a quantity just because another sheet also has a table.
"""

DESIGN_TAKEOFF_RULES = """
NO BID SCHEDULE — CIVIL ESTIMATOR MODE (design / drawings only):
This PDF/drawing is a design, not an agency bid schedule. You MUST generate a complete Estimate of Quantities
from the design evidence (typical sections, dimensions, callouts, hatch areas, counts, tables of quantities
printed on the drawing). Cover whichever of these the design actually shows:

ROADS / HIGHWAYS:
- Pavement layers from typical section: width × thickness × length / 27 = CY (HMA also tons @ 145 pcf).
- Prime/tack coat SY = width × length / 9. Curb/gutter LF, sidewalk SF, shoulders, markings.
- Earthwork cut/fill CY when cross-sections or mass-haul notes exist. Do not invent corridor volumes without numbers.

UTILITIES:
- Pipe LF by size and network (water / sanitary / storm). Count valves, hydrants, manholes, and inlets as EA when they are proposed pay items.
- Do NOT take off trench excavation, bedding, backfill, tracer wire, polywrap, thrust blocks, testing, or fittings as separate quantities unless they appear as their own Bid Items / EOQ / table-of-quantities row. Those are incidental to the pipe.
- Do NOT add incidental fitting counts, bedding volumes, or trench CY into the pipe LF (or any parent bid item).

DAMS & RESERVOIRS:
- Embankment fill, foundation excavation, cutoff, filter/drain, riprap, spillway/stilling-basin concrete.
- Reservoir / pond lining SF, capacity MGAL or Ac-Ft when stated. Do not fake 3D dam volumes from a 2D outline alone.

BUILDINGS / HOUSES:
- Brickwork/blockwork CY, RCC/foundation CY, plaster/flooring/roofing/formwork SF, doors/windows EA.
- Floor/roof areas from stated dimensions (L×W) when no schedule exists.

RULES:
- Use numbers printed on the design (station range, width, thickness, counts). Show the formula in calculation_method.
- If a value is assumed (cover, trench width, HMA density), say so and set confidence 70-80.
- Do NOT invent items the design does not support. Do NOT omit a pay item that the typical section or schedule-like table shows.
- Do NOT output incidental/included work as extra pay items, and do not add those amounts into a parent quantity.
- Keep Traffic Control sign rollup (one SqFt item) as in the shared rules below.

""" + TAKEOFF_ACCURACY_RULES.split("REQUIRED SEARCH PASSES:")[-1].split("EVIDENCE:")[0] + """
EVIDENCE:
Cite the typical section, dimension, sheet, or callout in source_reference / calculation_method.
"""

_SCHEDULE_METHOD_HINTS = (
    "quantity sheet",
    "estimate of quantities",
    "bid items",
    "bid item",
    "std bid",
    "standard bid",
    "eoq",
    "pay item",
    "proposal quantity",
    "est. qty",
    "est qty",
    "approx. quantity",
    "approx quantity",
    "for bidding purposes",
    "extracted table total",
    "extracted from quantity table",
    "extracted from eoq",
    "extracted from tabular quantity",
    "eoq schedule",
)
_PLAN_INVENT_HINTS = (
    "graphic count",
    "channelizer symbol",
    "from drawing symbol",
    "from symbol",
    "cover assumed",
    "trench width",
    "estimator takeoff",
    "estimator allowance",
    "one table row counted",
    "counted as one proposed",
    "project total",
    "itemized table",
    "mutcd ref",
    "÷144",
    "/144",
)
_DERIVED_METHOD_HINTS = (
    "geometry",
    "hatch",
    "from drawing symbol",
    "from symbol",
)
# Incidental fittings / casing only — never core bid items (water main, pavement, curb).
_GENERIC_INFERRED_DESC = re.compile(
    r"(?:"
    r"(?:\d+[-\s]?inch\s+)?restrained\s+joint|"
    r"(?:\d+[-\s]?inch\s+)?(?:steel\s+)?casing\s+pipe|"
    r"(?:\d+[-\s]?inch\s+)?(?:rj\s+)?(?:pvc\s+)?carrier\s+pipe|"
    r"water\s+(?:tee|bend|elbow)|"
    r"(?:\d+[-\s]?inch\s+)?(?:x\s*\d+[-\s]?inch\s+)?mj\s+(?:reducer|elbow|tee|bend)|"
    r"(?:\d+[-\s]?inch\s+)?(?:long\s+)?sleeve|"
    r"(?:\d+[-\s]?inch\s+)?plug\b|"
    r"utility\s+locate"
    r")",
    re.I,
)

_CONTRACT_UNIT_MAP = {
    "ea": "Each",
    "each": "Each",
    "nos": "Each",
    "no": "Each",
    "no.": "Each",
    "lf": "Ft",
    "l.f.": "Ft",
    "l.f": "Ft",
    "lin ft": "Ft",
    "linear ft": "Ft",
    "linear feet": "Ft",
    "ft": "Ft",
    "feet": "Ft",
    "sy": "SqYd",
    "sqyd": "SqYd",
    "sq yd": "SqYd",
    "sq.yd": "SqYd",
    "sf": "SqFt",
    "sqft": "SqFt",
    "sq ft": "SqFt",
    "cy": "CuYd",
    "cuyd": "CuYd",
    "cu yd": "CuYd",
    "ls": "LS",
    "lump sum": "LS",
    "ton": "Ton",
    "tons": "Ton",
    "lb": "Lb",
    "lbs": "Lb",
    "acre": "Acre",
    "acres": "Acre",
    "hour": "Hour",
    "hr": "Hour",
    "mgal": "MGal",
    "ac-ft": "Ac-Ft",
    "acre-ft": "Ac-Ft",
    "acre ft": "Ac-Ft",
}


def analyze_content(
    *,
    filename: str,
    content: ExtractedContent,
    document_id: int,
    bid_catalog: list[dict[str, Any]] | None = None,
    file_path: Path | str | None = None,
) -> dict[str, Any]:
    from app.config import get_settings
    from app.services.openai_client import openai_configured

    settings = get_settings()
    path = Path(file_path) if file_path else None

    if openai_configured():
        text_result: dict[str, Any] | None = None
        vision_result: dict[str, Any] | None = None
        errors: list[str] = []

        try:
            text_result = _analyze_with_openai(
                filename=filename,
                content=content,
                document_id=document_id,
                bid_catalog=bid_catalog,
            )
        except Exception as exc:
            errors.append(f"text AI: {exc}")

        # Full labels unless a Bid Items table was actually extracted (not just mentioned).
        label_result = _analyze_utility_labels(
            filename=filename,
            content=content,
            document_id=document_id,
            mains_only=_pdf_has_copied_bid_table(content),
        )

        if (
            settings.openai_pdf_vision_enabled
            and path
            and path.exists()
            and path.suffix.lower() == ".pdf"
        ):
            try:
                vision_result = _analyze_pdf_drawings_with_vision(
                    filename=filename,
                    content=content,
                    document_id=document_id,
                    pdf_path=path,
                    bid_catalog=bid_catalog,
                    max_pages=settings.openai_vision_max_pages,
                    dpi=settings.openai_vision_dpi,
                    min_score=settings.openai_vision_min_score,
                    force_utility_pages=settings.openai_vision_force_utility_pages,
                    scan_all_pages=settings.openai_vision_scan_all_pages,
                    batch_pages=settings.openai_vision_batch_pages,
                )
            except Exception as exc:
                errors.append(f"drawing vision: {exc}")

        if vision_result and vision_result.get("schedule_mode_active"):
            if text_result:
                strict_text_items = [
                    dict(item)
                    for item in (text_result.get("items") or [])
                    if _is_strict_schedule_lock_row(dict(item))
                ]
                dropped = len(text_result.get("items") or []) - len(strict_text_items)
                text_result = dict(text_result)
                text_result["items"] = strict_text_items
                text_result["schedule_mode_active"] = True
                if dropped:
                    note = (
                        f"Suppressed {dropped} non-schedule text row(s) "
                        "because an authoritative schedule was detected in vision."
                    )
                    text_result["summary"] = f"{text_result.get('summary') or ''} {note}".strip()
            # Label/callout rows are intentionally skipped in schedule mode.
            merged_parts = [r for r in (text_result, vision_result) if r]
        else:
            merged_parts = [r for r in (text_result, label_result, vision_result) if r]
        merged: dict[str, Any] | None = None
        if len(merged_parts) >= 2:
            merged = merged_parts[0]
            for part in merged_parts[1:]:
                merged = _merge_analysis_results(merged, part)
        elif vision_result:
            merged = vision_result
        elif label_result and label_result.get("items"):
            merged = label_result
        elif text_result:
            merged = text_result

        if merged is not None:
            if errors:
                merged["notes"] = ((merged.get("notes") or "") + " | " + " | ".join(errors)).strip(" |")
            if _takeoff_is_thin(merged.get("items") or [], content):
                heuristic = _analyze_heuristic(
                    filename=filename, content=content, document_id=document_id
                )
                merged = _merge_analysis_results(merged, heuristic)
                note = "Augmented thin AI takeoff with heuristic civil extractor (no copied Bid Items table)."
                merged["notes"] = ((merged.get("notes") or "") + " | " + note).strip(" |")
            return _finalize_analysis(merged, content=content)

        heuristic = _analyze_heuristic(filename=filename, content=content, document_id=document_id)
        if errors:
            heuristic["notes"] = f"OpenAI failed ({'; '.join(errors)}); used heuristic fallback."
        return _finalize_analysis(heuristic, content=content)

    return _finalize_analysis(
        _analyze_heuristic(filename=filename, content=content, document_id=document_id),
        content=content,
    )


def _analyze_heuristic(*, filename: str, content: ExtractedContent, document_id: int) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1) Structured tables (CSV/Excel/PDF). Bid Items / EOQ tables are copied as-is;
    # F-sheet “Project Totals” / device tables are not pay items.
    table_items = _items_from_document_tables(content, filename=filename, document_id=document_id)
    items.extend(table_items)
    for it in table_items:
        key = str(it.get("description") or "").lower()
        if key:
            seen.add(key)

    schedule_copied = _pdf_has_copied_bid_table(content)

    # 2) Regex over free text — skip only when a Bid Items table was actually extracted
    text = content.text or ""
    pattern_rows = () if schedule_copied else CIVIL_PATTERNS
    for desc, category, unit_hint, pattern in pattern_rows:
        if desc.lower() in seen:
            continue
        chosen = None
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            qty = _parse_number(match.group(1))
            if qty is None:
                continue
            if extraction_should_skip(desc, text, match.start()):
                continue
            chosen = match
            break
        if chosen is None:
            continue
        qty = _parse_number(chosen.group(1))
        if qty is None:
            continue
        unit = (chosen.group(2) if chosen.lastindex and chosen.lastindex >= 2 else unit_hint) or unit_hint
        unit = _normalize_unit(unit)
        page = _guess_page(text, chosen.start(), content)
        seen.add(desc.lower())
        items.append(
            _item(
                description=desc,
                category=category,
                unit=unit,
                quantity=qty,
                document_id=document_id,
                page=page,
                source=f"{filename}" + (f" - Page {page}" if page else ""),
                method="Pattern match from document text",
                confidence=78,
            )
        )

    # Water main / utility labels & callouts (often the only size/LF source on plans)
    if not schedule_copied:
        label_pack = _analyze_utility_labels(
            filename=filename,
            content=content,
            document_id=document_id,
            mains_only=False,
        )
        for it in (label_pack.get("items") or []):
            key = str(it.get("description") or "").lower()
            if key and key not in seen:
                seen.add(key)
                items.append(it)

    # Geometry notes
    facts: list[dict[str, Any]] = []
    from app.services.civil_estimator import detect_project_types, items_from_design_text

    project_types = detect_project_types(filename, text)
    if project_types:
        facts.append({"key": "project_types", "value": ", ".join(project_types)})

    if not _pdf_has_copied_bid_table(content):
        for it in items_from_design_text(text, filename=filename):
            key = str(it.get("description") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            qty = _parse_number(it.get("quantity"))
            if qty is None:
                continue
            items.append(
                _item(
                    description=str(it.get("description")),
                    category=str(it.get("category") or "General"),
                    unit=str(it.get("unit") or "unit"),
                    quantity=qty,
                    document_id=document_id,
                    page=None,
                    source=f"{filename} - design takeoff",
                    method=str(it.get("calculation_method") or "Civil estimator from design text"),
                    confidence=float(it.get("confidence") or 80),
                )
            )

    width_match = re.search(r"\b(?:Road|Carriageway)\s*Width\b[^\d]{0,20}(\d{1,2}(?:\.\d+)?)\s*(m|ft)\b", text, re.I)
    if width_match:
        facts.append({"key": "road_width_m", "value": width_match.group(1), "source_page": _guess_page(text, width_match.start(), content)})

    chainage_match = re.search(r"\b(?:Chainage|Ch\.?)\s*[:\-]?\s*([\d\+\.]+(?:\s*(?:to|\-)\s*[\d\+\.]+)?)", text, re.I)
    if chainage_match:
        facts.append({"key": "chainage", "value": chainage_match.group(1), "source_page": _guess_page(text, chainage_match.start(), content)})

    summary = (
        f"Analyzed '{filename}' with heuristic civil extractor. "
        f"Found {len(items)} quantity item(s)"
        + (f" and {len(facts)} geometry/note fact(s)." if facts else ".")
    )
    if not items:
        summary += " No explicit quantities found — flagging for engineer review."

    return {
        "engine": "heuristic",
        "summary": summary,
        "facts": facts,
        "items": items,
        "needs_review": len(items) == 0,
    }


def _catalog_prompt_bits(
    bid_catalog: list[dict[str, Any]] | None,
    *,
    design_takeoff: bool = False,
) -> tuple[str, str, str]:
    catalog = bid_catalog or []
    catalog_preview = json.dumps(catalog[:100], ensure_ascii=True)[:12000] if catalog else "[]"
    takeoff_rules = DESIGN_TAKEOFF_RULES if design_takeoff else TAKEOFF_ACCURACY_RULES
    if catalog:
        system = (
            "You are a USA civil/highway quantity surveyor AI for AutoVAD. "
            "An agency bid template is active. Extract ONLY items needed for THIS project "
            "with evidence in schedules, quantity tables, drawings, or explicit callouts. "
            "Prefer bid/EOQ schedule quantities over geometry. Return STRICT JSON only."
        )
        catalog_rules = f"""
ACTIVE BID TEMPLATE (Standard Bid Item Number / description / unit):
{catalog_preview}

Template rules:
- Do NOT dump the entire bid list.
- Only include bid lines evidenced in schedules/tables/plans/callouts.
- When matched, use the template description EXACTLY, its unit, and Standard Bid Item Number as item_code.
- Unmatched but evidenced schedule/callout work may still be included with empty item_code.
- Never invent extras that are not on the template or clearly called out.
{takeoff_rules}
"""
        code_hint = "Use Standard Bid Item Numbers from the active template when matched."
    else:
        role = (
            "civil estimator AI for AutoVAD. Produce a complete Estimate of Quantities from the design "
            "(roads, utilities, dams, reservoirs, buildings) when no bid schedule exists."
            if design_takeoff
            else "USA civil/highway quantity surveyor AI for AutoVAD. Extract Estimate Of Quantities / EOQ pay items. "
            "Prefer quantity schedules and explicit callouts over inferred geometry."
        )
        system = f"You are a {role} Return STRICT JSON only."
        catalog_rules = f"""
No agency bid template — use exact schedule/pay-item wording when an EOQ table is present;
otherwise use clear USA civil/CSI descriptions
(earthwork, pavement, curb/gutter, sidewalk, drainage, utilities, dams, reservoirs, buildings, removals).
{takeoff_rules}
"""
        code_hint = "Prefer STD BID NO / USA CSI codes when identifiable."
    return system, catalog_rules, code_hint


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _schedule_pages_from_facts(facts: Any) -> set[int]:
    pages: set[int] = set()
    if not isinstance(facts, list):
        return pages
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        key = str(fact.get("key") or "").strip().lower()
        if key not in {"eoq_table_found", "bid_schedule_found", "bid_items_table_found", "schedule_table_found"}:
            continue
        if not _truthy_flag(fact.get("value")):
            continue
        page = _safe_int(fact.get("source_page"))
        if page and page > 0:
            pages.add(page)
    return pages


def _schedule_evidence_blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def _has_strict_schedule_reference(blob: str) -> bool:
    hints = (
        "bid items / eoq table",
        "bid items table",
        "estimate of quantities schedule",
        "eoq schedule",
        "for bidding purposes",
        "std bid",
        "standard bid item number",
        "item number",
        "extracted from quantity table (strict grid transcription)",
    )
    return any(h in blob for h in hints)


def _has_non_bid_detail_reference(blob: str) -> bool:
    hints = (
        "estimated quantities table",
        "project totals",
        "itemized list",
        "city material procurement",
        "earthwork quantities",
        "typical section",
        "plan callout",
        "drawing callout",
        "profile callout",
        "long inlet",
        "dia. outlet",
        "constant column",
        "variable column",
    )
    return any(h in blob for h in hints)


def _looks_like_schedule_item_number(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return bool(re.fullmatch(r"\d{1,5}[a-z]?", text))


def _looks_like_agency_or_special_bid_code(value: Any) -> bool:
    from app.services.traffic_control import looks_like_agency_bid_number

    code = str(value or "").strip()
    if not code:
        return False
    if code.lower() == "special":
        return True
    return looks_like_agency_bid_number(code)


def _has_schedule_identifiers(
    *,
    item_number: Any = None,
    item_no: Any = None,
    line_number: Any = None,
    item_code: Any = None,
) -> bool:
    if _looks_like_agency_or_special_bid_code(item_code):
        return True
    for value in (item_number, item_no, line_number):
        if _looks_like_schedule_item_number(value):
            return True
    return False


def _is_authoritative_schedule_row(item: dict[str, Any]) -> bool:
    blob = _item_evidence_blob(item)
    if any(
        h in blob
        for h in (
            "callout",
            "drawing label",
            "plan label",
            "graphic count",
            "from symbol",
            "itemized list",
            "project total",
        )
    ):
        return False
    if _has_non_bid_detail_reference(blob) and not _has_strict_schedule_reference(blob):
        return False
    has_identifiers = _has_schedule_identifiers(
        item_number=item.get("item_number"),
        item_no=item.get("item_no"),
        line_number=item.get("line_number"),
        item_code=item.get("item_code"),
    )
    if has_identifiers:
        if bool(item.get("table_transcribed")) or bool(item.get("schedule_authoritative")):
            return True
        if _has_strict_schedule_reference(blob):
            return True
    if _has_strict_schedule_reference(blob):
        if has_identifiers:
            return True
        if not bool(item.get("quantity_blank")) and not bool(item.get("unit_blank")):
            return True
    return False


def _raw_item_marked_schedule(
    raw_item: dict[str, Any],
    *,
    default_method: str,
    assume_schedule_rows: bool,
    schedule_pages: set[int] | None,
) -> bool:
    if assume_schedule_rows:
        return True
    blob = _schedule_evidence_blob(
        raw_item.get("calculation_method") or default_method,
        raw_item.get("source_reference"),
        raw_item.get("description"),
        raw_item.get("category"),
    )
    row_type = str(
        raw_item.get("row_type")
        or raw_item.get("item_type")
        or raw_item.get("kind")
        or raw_item.get("type")
        or ""
    ).strip().lower()
    if row_type in {"other", "callout", "detail", "derived", "plan"}:
        return False
    has_identifiers = _has_schedule_identifiers(
        item_number=raw_item.get("item_number"),
        item_no=raw_item.get("item_no"),
        line_number=raw_item.get("line_number"),
        item_code=raw_item.get("item_code"),
    )
    strict_ref = _has_strict_schedule_reference(blob)
    detail_ref = _has_non_bid_detail_reference(blob)
    desc_text = str(raw_item.get("description") or "").strip()
    qty_text = str(raw_item.get("quantity") or "").strip()
    unit_text = str(raw_item.get("unit") or "").strip()
    has_measure = bool(qty_text or unit_text)

    if row_type in {"schedule", "schedule_row", "bid_schedule", "eoq_schedule", "bid_item", "table_row"}:
        if detail_ref and not strict_ref and not has_identifiers:
            return False
        if has_identifiers:
            return True
        if strict_ref and has_measure and len(desc_text) >= 4:
            return True
        return False

    if _truthy_flag(raw_item.get("table_transcribed")) or _truthy_flag(raw_item.get("schedule_row")) or _truthy_flag(
        raw_item.get("table_row")
    ):
        if detail_ref and not strict_ref and not has_identifiers:
            return False
        if has_identifiers:
            return True
        if strict_ref and has_measure and len(desc_text) >= 4:
            return True
        return False

    if has_identifiers and strict_ref:
        return True

    page = _safe_int(raw_item.get("source_page"))
    if schedule_pages and page and page in schedule_pages:
        if has_identifiers and not detail_ref:
            return True

    if strict_ref:
        return True
    if any(h in blob for h in _SCHEDULE_METHOD_HINTS) and not detail_ref and has_identifiers:
        return True
    return False


def _normalize_item_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _items_from_openai_payload(
    data: dict[str, Any],
    *,
    filename: str,
    document_id: int,
    default_method: str,
    assume_schedule_rows: bool = False,
    schedule_pages: set[int] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    schedule_pages = set(schedule_pages or set())
    for raw_item in data.get("items") or []:
        if not isinstance(raw_item, dict):
            continue
        description = str(raw_item.get("description") or "").strip()
        if not description:
            continue
        schedule_row = _raw_item_marked_schedule(
            raw_item,
            default_method=default_method,
            assume_schedule_rows=assume_schedule_rows,
            schedule_pages=schedule_pages,
        )
        qty_raw = raw_item.get("quantity")
        qty_raw_text = "" if qty_raw is None else str(qty_raw).strip()
        qty_blank = qty_raw_text == ""
        qty = _parse_number(qty_raw)
        if qty is None:
            if schedule_row:
                qty = Decimal("0")
                qty_blank = True
            else:
                continue

        conf = _parse_number(raw_item.get("confidence")) or Decimal("80")
        category_raw = str(raw_item.get("category") or "").strip()
        unit_raw = str(raw_item.get("unit") or "").strip()
        unit_blank = unit_raw == ""
        item_code = _normalize_item_code(raw_item.get("item_code"))
        method = str(raw_item.get("calculation_method") or default_method)
        built = _item(
            description=description,
            category=category_raw or "General",
            unit=unit_raw or "UNIT",
            quantity=qty,
            item_code=item_code,
            document_id=document_id,
            page=raw_item.get("source_page"),
            source=f"{filename}"
            + (f" - Page {raw_item.get('source_page')}" if raw_item.get("source_page") else "")
            + (f" - {raw_item.get('source_reference')}" if raw_item.get("source_reference") else ""),
            method=method,
            confidence=float(conf),
            status=str(raw_item.get("status") or "needs_review"),
            source_reference=raw_item.get("source_reference"),
        )
        if schedule_row:
            # Keep authoritative schedule rows stable through downstream pruning/grouping.
            built["table_transcribed"] = True
            built["schedule_authoritative"] = True
            if category_raw:
                built["category"] = category_raw
            item_no_raw = raw_item.get("item_number")
            if item_no_raw is None or str(item_no_raw).strip() == "":
                item_no_raw = raw_item.get("item_no")
            if item_no_raw is None or str(item_no_raw).strip() == "":
                item_no_raw = raw_item.get("line_number")
            item_no = str(item_no_raw).strip() if item_no_raw is not None else ""
            if item_no:
                built["item_number"] = item_no
            built["raw_unit"] = unit_raw
            built["raw_quantity"] = qty_raw_text
            built["unit_blank"] = unit_blank
            built["quantity_blank"] = qty_blank
            if qty_blank or unit_blank:
                marker = "Preserved blank schedule cell(s) exactly as transcribed."
                base_method = str(built.get("calculation_method") or method)
                if marker.lower() not in base_method.lower():
                    built["calculation_method"] = f"{base_method} | {marker}".strip(" |")
                built["status"] = "needs_review"
                built["needs_review"] = True
            if not item_code:
                built["bid_item_code_missing"] = True
                built["status"] = "needs_review"
                built["needs_review"] = True
        if _should_drop_incidental_item(built):
            continue
        items.append(built)
    return items


def _analyze_with_openai(
    *,
    filename: str,
    content: ExtractedContent,
    document_id: int,
    bid_catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.services.openai_client import ask_openai_json

    clipped = _text_for_openai(content, char_limit=80000)
    tables_preview = json.dumps(_tables_for_openai(content), ensure_ascii=True)[:40000]
    schedule_table_copied = _pdf_has_copied_bid_table(content)
    # Prompt style depends on whether a real EOQ table was copied from the PDF.
    system, catalog_rules, code_hint = _catalog_prompt_bits(bid_catalog, design_takeoff=True)

    if schedule_table_copied:
        design_or_schedule = (
            "A structured Bid Items / EOQ table was detected. Transcribe ONLY rows inside that table grid. "
            "Ignore all surrounding boilerplate text/logos/stamps/notes. Do not generate missing cells; keep blanks blank. "
            "Parse section headers sequentially and assign each following row to that section until the next section header."
        )
    else:
        design_or_schedule = (
            "Copy every Bid Items / EOQ / EST. QTY / STD BID row if a quantity schedule is in this text. "
            "Also extract other evidenced pay items from notes and tables (roads, utilities, dams, "
            "reservoirs, buildings, removals, traffic control, paving, curb). "
            "Traffic-control device lists / Project Totals are not the bid schedule."
        )

    user = f"""
Extract Estimate Of Quantities / EOQ pay items from the document TEXT and TABLES.
(Drawing sheets are analyzed separately via vision.)

Rules:
- {design_or_schedule}
- Merge continuation tables: “(Ctd.)”, “continued”, repeated headers → same category; do not stop at page breaks.
- Include Alternates (A/B), LS items (Mobilization, Tax…), Traffic Control/Signals/Lighting, Removals, Erosion/Landscaping.
- Copy the schedule quantity cell — do not substitute a detail/callout count — WHEN a schedule exists.
- Do NOT invent water fittings/valves/hydrants/pipe segments from free text unless they are schedule rows OR this is design-only takeoff with printed sizes/counts.
- Skip incidental/included work. Do not list it separately and do not add it into the parent bid-item quantity.
- If unsure, omit inventing values and mark needs_review.
{catalog_rules}

Document filename: {filename}
Document id: {document_id}

TEXT:
{clipped}

TABLES_JSON:
{tables_preview}

Return JSON shape:
{{
  "summary": "string",
  "facts": [{{"key":"eoq_table_found","value":"true","source_page":1}}],
  "items": [
    {{
      "item_code": "optional Standard Bid Item Number or CSI",
      "description": "exact schedule description",
      "category": "Water Main",
      "unit": "Ft",
      "quantity": 245,
      "source_page": 4,
      "source_reference": "EOQ schedule table",
      "calculation_method": "Extracted from Estimate Of Quantities schedule",
      "confidence": 95,
      "status": "needs_review"
    }}
  ],
  "needs_review": false
}}
"""
    data = ask_openai_json(system + " " + code_hint, user)
    facts = data.get("facts") or []
    schedule_pages = _schedule_pages_from_facts(facts)
    items = _items_from_openai_payload(
        data,
        filename=filename,
        document_id=document_id,
        default_method="OpenAI text/table extraction",
        assume_schedule_rows=schedule_table_copied,
        schedule_pages=schedule_pages,
    )
    return {
        "engine": "openai",
        "summary": data.get("summary") or f"OpenAI text-analyzed '{filename}'.",
        "facts": facts,
        "items": items,
        "needs_review": bool(data.get("needs_review")) or len(items) == 0,
    }


def _analyze_utility_labels(
    *,
    filename: str,
    content: ExtractedContent,
    document_id: int,
    mains_only: bool = False,
) -> dict[str, Any]:
    """Deterministic extraction of water main / utility quantities from label text."""
    from app.services.utility_labels import extract_utility_label_items

    raw_items = extract_utility_label_items(
        content.text or "",
        filename=filename,
        document_id=document_id,
        mains_only=mains_only,
    )
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        qty = _parse_number(raw.get("quantity"))
        if qty is None or not raw.get("description"):
            continue
        items.append(
            _item(
                description=str(raw["description"]),
                category=str(raw.get("category") or "Utilities"),
                unit=str(raw.get("unit") or "LF"),
                quantity=qty,
                document_id=document_id,
                page=raw.get("source_page"),
                source=f"{filename} - {raw.get('source_reference') or 'label'}",
                method=str(raw.get("calculation_method") or "Plan label/callout"),
                confidence=float(raw.get("confidence") or 85),
                status=str(raw.get("status") or "needs_review"),
                source_reference=raw.get("source_reference"),
            )
        )
    return {
        "engine": "label-parser",
        "summary": (
            f"Label/callout parser found {len(items)} utility item(s) "
            f"(water main / fittings / related) in '{filename}'."
        ),
        "facts": [],
        "items": items,
        "needs_review": True,
    }


def _missing_schedule_code_count(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if _is_authoritative_schedule_row(item) and not str(item.get("item_code") or "").strip())


def _schedule_row_match_key(item: dict[str, Any]) -> str:
    desc = re.sub(r"\s+", " ", str(item.get("description") or "").strip().lower())
    unit = _normalize_contract_unit(str(item.get("unit") or "UNIT")).lower()
    raw_qty = item.get("raw_quantity")
    if raw_qty is None:
        raw_qty = item.get("quantity")
    qty = re.sub(r"\s+", " ", str(raw_qty if raw_qty is not None else "").strip().lower())
    return f"{desc}|{unit}|{qty}"


def _fill_missing_schedule_codes(
    schedule_rows: list[dict[str, Any]],
    reread_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    by_item_no: dict[str, str] = {}
    by_key: dict[str, set[str]] = {}
    for row in reread_rows:
        code = str(row.get("item_code") or "").strip()
        if not code:
            continue
        item_no = str(row.get("item_number") or row.get("item_no") or "").strip().lower()
        if item_no:
            by_item_no[item_no] = code
        key = _schedule_row_match_key(row)
        by_key.setdefault(key, set()).add(code)

    updated = 0
    patched: list[dict[str, Any]] = []
    for row in schedule_rows:
        out = dict(row)
        if str(out.get("item_code") or "").strip():
            patched.append(out)
            continue
        replacement: str | None = None
        item_no = str(out.get("item_number") or out.get("item_no") or "").strip().lower()
        if item_no:
            replacement = by_item_no.get(item_no)
        if not replacement:
            key = _schedule_row_match_key(out)
            choices = by_key.get(key) or set()
            if len(choices) == 1:
                replacement = next(iter(choices))
        if replacement:
            out["item_code"] = replacement
            out.pop("bid_item_code_missing", None)
            updated += 1
        patched.append(out)
    return patched, updated


def _is_strict_schedule_lock_row(item: dict[str, Any]) -> bool:
    if not _is_authoritative_schedule_row(item):
        return False
    blob = _item_evidence_blob(item)
    if _has_non_bid_detail_reference(blob) and not _has_strict_schedule_reference(blob):
        return False
    has_identifiers = _has_schedule_identifiers(
        item_number=item.get("item_number"),
        item_no=item.get("item_no"),
        line_number=item.get("line_number"),
        item_code=item.get("item_code"),
    )
    if _has_strict_schedule_reference(blob):
        if has_identifiers:
            return True
        if not bool(item.get("quantity_blank")) and not bool(item.get("unit_blank")):
            return len(str(item.get("description") or "").strip()) >= 4
        return False
    return has_identifiers


def _normalized_schedule_category(value: Any) -> str:
    text = re.sub(r"\s*\(ctd\.?\)\s*$", "", str(value or ""), flags=re.I).strip().lower()
    return text


def _should_lock_strict_schedule_mode(
    schedule_rows: list[dict[str, Any]],
    non_schedule_rows: list[dict[str, Any]],
) -> bool:
    strong_rows = [row for row in schedule_rows if _is_strict_schedule_lock_row(row)]
    if len(strong_rows) < 2:
        return False

    identified = sum(
        1
        for row in strong_rows
        if _has_schedule_identifiers(
            item_number=row.get("item_number"),
            item_no=row.get("item_no"),
            line_number=row.get("line_number"),
            item_code=row.get("item_code"),
        )
    )
    if identified < max(2, min(6, len(strong_rows) // 4)):
        return False

    strict_ref_rows = sum(1 for row in strong_rows if _has_strict_schedule_reference(_item_evidence_blob(row)))
    detail_ref_rows = sum(1 for row in strong_rows if _has_non_bid_detail_reference(_item_evidence_blob(row)))
    if strict_ref_rows == 0 and detail_ref_rows > 0:
        return False
    if detail_ref_rows >= max(3, int(len(strong_rows) * 0.7)):
        return False

    if non_schedule_rows:
        if len(strong_rows) <= 8 and len(non_schedule_rows) >= 30:
            return False
        schedule_cats = {
            _normalized_schedule_category(row.get("category"))
            for row in strong_rows
            if _normalized_schedule_category(row.get("category"))
        }
        if len(schedule_cats) <= 1 and len(non_schedule_rows) >= 40:
            return False

    return True


def _focused_reread_schedule_pages_with_vision(
    *,
    filename: str,
    document_id: int,
    pdf_path: Path,
    schedule_pages: list[int],
    dpi: int,
    batch_pages: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    from app.services.openai_client import ask_openai_vision_json
    from app.services.pdf_vision import VisionPagePlan, iter_rendered_pdf_batches

    pages = sorted({int(p) for p in schedule_pages if int(p) > 0})
    if not pages:
        return [], []

    plan = VisionPagePlan(
        page_count=max(pages),
        selected_pages=pages,
        skipped_pages=[],
        truncated=False,
        forced_utility_pages=[],
        scan_all=False,
        batch_size=max(1, min(int(batch_pages or 1), 2)),
        reasons={p: "focused schedule reread" for p in pages},
        large_document=False,
    )
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    system = (
        "You transcribe civil Bid Items / Estimate Of Quantities schedule rows exactly from rendered plan sheets. "
        "Return STRICT JSON only. Never infer, compute, or hallucinate values."
    )

    for batch in iter_rendered_pdf_batches(pdf_path, plan, dpi=dpi, batch_pages=plan.batch_size):
        page_list = [p.page for p in batch]
        images = [{"page": p.page, "png_b64": p.png_b64} for p in batch]
        user = f"""
Document: {filename}
Pages: {page_list}

Task:
- Read ONLY the Bid Items / Estimate Of Quantities table rows.
- Ignore all non-schedule text (notes, callouts, details, title block, logos, stamps).
- Copy each row exactly from the table grid.
- item_code must come from BID ITEM / STD BID NO column; if a cell is blank, return empty string.
- Keep blank UNIT or quantity cells blank (quantity may be null/empty).

Return JSON:
{{
  "items": [
    {{
      "row_type": "schedule",
      "item_number": "1",
      "item_code": "9.0010",
      "description": "Mobilization",
      "category": "General Items",
      "unit": "LS",
      "quantity": "1",
      "source_page": 1,
      "source_reference": "Bid Items / EOQ table",
      "calculation_method": "Extracted from Estimate Of Quantities schedule",
      "confidence": 99,
      "status": "needs_review"
    }}
  ]
}}
"""
        try:
            data = ask_openai_vision_json(system, user, images)
        except Exception as exc:
            errors.append(f"focused schedule reread pages {page_list}: {exc}")
            continue
        finally:
            for img in images:
                img["png_b64"] = ""
            images.clear()
        out.extend(
            _items_from_openai_payload(
                data,
                filename=filename,
                document_id=document_id,
                default_method="OpenAI vision — focused schedule reread",
                assume_schedule_rows=True,
                schedule_pages=set(page_list),
            )
        )
    return out, errors


def _analyze_pdf_drawings_with_vision(
    *,
    filename: str,
    document_id: int,
    pdf_path: Path,
    bid_catalog: list[dict[str, Any]] | None = None,
    max_pages: int = 0,
    dpi: int = 150,
    min_score: float = 18.0,
    force_utility_pages: bool = True,
    scan_all_pages: bool = True,
    batch_pages: int = 8,
    content: ExtractedContent | None = None,
) -> dict[str, Any]:
    from app.services.openai_client import ask_openai_vision_json
    from app.services.pdf_vision import iter_rendered_pdf_batches, plan_pdf_vision_pages
    from app.config import get_settings

    settings = get_settings()
    file_bytes = 0
    try:
        file_bytes = pdf_path.stat().st_size
    except OSError:
        file_bytes = 0

    plan = plan_pdf_vision_pages(
        pdf_path,
        max_pages=max_pages,
        min_score=min_score,
        force_utility_pages=force_utility_pages,
        scan_all_pages=scan_all_pages,
        batch_pages=batch_pages,
        page_texts=list(content.pages) if content and content.pages else None,
        file_bytes=file_bytes,
        large_page_threshold=settings.openai_vision_large_page_threshold,
        large_file_mb=settings.openai_vision_large_file_mb,
        large_max_pages=settings.openai_vision_large_max_pages,
    )
    if not plan.selected_pages:
        raise RuntimeError("No PDF pages could be rendered for vision")

    if plan.large_document:
        batch_pages = min(int(batch_pages or 4), int(settings.openai_vision_large_batch_pages or 2))
        dpi = int(settings.openai_vision_large_dpi or dpi or 150)
    vision_budget = float(settings.openai_vision_max_seconds or 0)
    if plan.large_document:
        large_budget = float(settings.openai_vision_large_max_seconds or 0)
        vision_budget = large_budget if large_budget else vision_budget

    system, catalog_rules, code_hint = _catalog_prompt_bits(
        bid_catalog, design_takeoff=True
    )

    # Hint model with OCR snippets that look like water-main labels
    label_hints = ""
    if content and content.text:
        snippets = []
        for line in (content.text or "").splitlines():
            low = line.lower()
            if any(k in low for k in ("water main", "watermain", " wm", "wm ", 'water"', "dip wm", "prop. wm", "proposed wm")):
                snippets.append(line.strip()[:160])
            if len(snippets) >= 40:
                break
        if snippets:
            label_hints = "OCR/label snippets that may appear on sheets:\n" + "\n".join(f"- {s}" for s in snippets)

    vision_system = (
        system
        + " "
        + code_hint
        + " Prefer EOQ/bid schedules on sheets when present. Merge (Ctd.) pages. "
        + "Keep evidenced plan pay items (pipe, pavement, curb, hydrant, removals). "
        + "Do not take off incidental trench/bedding/fittings or add them into parent quantities. "
        + "Do not add MUTCD sign faces or graphic channelizers as extra bid items."
    )
    schedule_rows: list[dict[str, Any]] = []
    non_schedule_rows: list[dict[str, Any]] = []
    all_facts: list[Any] = []
    summaries: list[str] = []
    vision_pages_meta: list[dict[str, Any]] = []
    batch_errors: list[str] = []
    batch_index = 0
    schedule_detected = False
    schedule_pages: set[int] = set()
    suppressed_non_schedule_rows = 0
    strict_mode_relaxed = False
    focused_reread_rows = 0
    focused_reread_code_fills = 0
    started = time.monotonic()
    budget_stopped = False

    for batch in iter_rendered_pdf_batches(pdf_path, plan, dpi=dpi, batch_pages=batch_pages):
        if not batch:
            continue
        elapsed = time.monotonic() - started
        if vision_budget > 0 and elapsed >= vision_budget:
            remaining = [
                p
                for p in plan.selected_pages
                if p not in {m["page"] for m in vision_pages_meta}
            ]
            batch_errors.append(
                f"Stopped vision after {int(elapsed)}s (budget {int(vision_budget)}s). "
                f"Bid/qty sheets are scanned first; skipped remaining page(s) {remaining[:24]}."
            )
            budget_stopped = True
            break
        batch_index += 1
        page_meta = ", ".join(f"p{p.page} ({p.reason})" for p in batch)
        images = [{"page": p.page, "png_b64": p.png_b64} for p in batch]
        vision_pages_meta.extend({"page": p.page, "reason": p.reason} for p in batch)
        batch_pages_list = [p.page for p in batch]
        if schedule_detected:
            coverage_note = (
                f"This is batch {batch_index} of the PDF and an authoritative schedule was already detected. "
                f"Only schedule continuation rows are needed from pages {batch_pages_list}."
            )
            sheet_job = """
Primary job (schedule mode):
- Extract ONLY Bid Items / Estimate Of Quantities table rows on THESE pages.
- Ignore plan callouts/details/notes even if they contain quantities.
- Include row_type="schedule" for each row.
- Copy BID ITEM / STD BID NO into item_code. If the table cell is blank, leave item_code as empty string.
- Preserve blank UNIT / EST. QTY cells as blank (quantity may be null/empty).
"""
        else:
            coverage_note = (
                f"This is batch {batch_index} of the PDF. "
                f"Document has {plan.page_count} page(s); this request covers pages {batch_pages_list}."
            )
            sheet_job = """
Primary job:
- First detect whether a Bid Items / Estimate Of Quantities table is visible on THESE pages
  (ITEM NUMBER, BID ITEM, DESCRIPTION, UNITS, EST. QTY or STD BID NO / APPROX. QUANTITY).
- If such a table is present, transcribe ONLY those schedule rows and set row_type="schedule".
- If no such table is present on these pages, you may return other evidenced pay items with row_type="other".
- Traffic-control device tables (“Project Totals”, itemized device lists) are NOT the bid schedule.
- Do not invent trench/bedding/backfill/fittings unless printed as pay items.
- Do not add channelizers or individual MUTCD signs from traffic-control graphics.
"""
        user = f"""
You are looking at RENDERED ENGINEERING PLAN SHEETS from a civil PDF (not just OCR text).

Document: {filename}
Rendered sheets: {page_meta}
{coverage_note}
{sheet_job}
{catalog_rules}

{label_hints}

Return JSON:
{{
  "summary": "EOQ tables / continuation / alternates found on these sheets",
  "facts": [{{"key":"eoq_table_found","value":"true","source_page":1}}],
  "items": [
    {{
      "row_type": "schedule",
      "item_number": "1",
      "item_code": "optional STD BID NO",
      "description": "exact schedule description",
      "category": "Water Main",
      "unit": "Ft",
      "quantity": "245",
      "source_page": 4,
      "source_reference": "EOQ schedule table",
      "calculation_method": "Extracted from Estimate Of Quantities schedule",
      "confidence": 95,
      "status": "needs_review"
    }}
  ],
  "needs_review": true
}}
"""
        try:
            data = ask_openai_vision_json(vision_system, user, images)
        except Exception as exc:
            batch_errors.append(f"batch {batch_index} pages {[p.page for p in batch]}: {exc}")
            continue
        finally:
            for img in images:
                img["png_b64"] = ""
            images.clear()
        batch_facts = data.get("facts") or []
        all_facts.extend(batch_facts)
        for pg in _schedule_pages_from_facts(batch_facts):
            schedule_pages.add(pg)
        batch_items = _items_from_openai_payload(
            data,
            filename=filename,
            document_id=document_id,
            default_method="OpenAI vision — plan sheet",
            schedule_pages=_schedule_pages_from_facts(batch_facts),
        )
        batch_schedule_rows = [it for it in batch_items if _is_strict_schedule_lock_row(it)]
        for item in batch_schedule_rows:
            page_no = _safe_int(item.get("source_page"))
            if page_no and page_no > 0:
                schedule_pages.add(page_no)

        batch_non_schedule_rows = [it for it in batch_items if not _is_strict_schedule_lock_row(it)]
        if batch_schedule_rows:
            schedule_detected = True
            schedule_rows.extend(batch_schedule_rows)
        non_schedule_rows.extend(batch_non_schedule_rows)
        if data.get("summary"):
            summaries.append(str(data["summary"]))

    if schedule_detected and schedule_rows:
        lock_candidate = _should_lock_strict_schedule_mode(schedule_rows, non_schedule_rows)
        missing_codes_before = _missing_schedule_code_count(schedule_rows)
        if lock_candidate and missing_codes_before > 0:
            focus_pages = sorted(schedule_pages)
            reread_rows, reread_errors = _focused_reread_schedule_pages_with_vision(
                filename=filename,
                document_id=document_id,
                pdf_path=pdf_path,
                schedule_pages=focus_pages,
                dpi=dpi,
                batch_pages=batch_pages,
            )
            if reread_errors:
                batch_errors.extend(reread_errors)
            if reread_rows:
                focused_reread_rows = len(reread_rows)
                patched_rows, patched_count = _fill_missing_schedule_codes(schedule_rows, reread_rows)
                schedule_rows = patched_rows
                focused_reread_code_fills = patched_count
                if (
                    len(reread_rows) >= max(2, len(schedule_rows) - 2)
                    and _missing_schedule_code_count(reread_rows) < _missing_schedule_code_count(schedule_rows)
                ):
                    schedule_rows = reread_rows

    schedule_mode_active = bool(schedule_detected and schedule_rows and _should_lock_strict_schedule_mode(schedule_rows, non_schedule_rows))
    if schedule_detected and schedule_rows and schedule_mode_active:
        all_items = schedule_rows
        suppressed_non_schedule_rows = len(non_schedule_rows)
    else:
        all_items = schedule_rows + non_schedule_rows
        strict_mode_relaxed = bool(schedule_detected and schedule_rows)

    # Merge duplicate keys across batches (same desc/unit)
    merged_pack = _merge_analysis_results(
        {"items": [], "facts": [], "summary": "", "needs_review": False},
        {
            "items": all_items,
            "facts": all_facts,
            "summary": " ".join(summaries).strip(),
            "needs_review": len(all_items) == 0,
            "vision_pages": vision_pages_meta,
            "schedule_mode_active": schedule_mode_active,
        },
    )
    items = merged_pack.get("items") or all_items
    scanned_pages = sorted({int(m["page"]) for m in vision_pages_meta})
    skipped_render = [p for p in plan.selected_pages if p not in scanned_pages]
    scanned = len(scanned_pages)
    summary = (
        f"Vision-analyzed {scanned}/{plan.page_count} page(s) from '{filename}' "
        f"in {batch_index} batch(es)."
    )
    if summaries:
        summary = f"{summary} {' '.join(summaries[:3])}"
    if plan.large_document:
        summary += (
            f" Large plan set ({plan.page_count} page(s)): vision scans every page in batches "
            f"({len(plan.selected_pages)} queued). Completeness over speed — this can take over an hour."
        )
    elif plan.truncated:
        summary += (
            f" Safety cap skipped {len(plan.skipped_pages)} page(s) "
            f"(set OPENAI_VISION_MAX_PAGES=0 and OPENAI_VISION_SCAN_ALL_PAGES=true for full scan)."
        )
    if batch_errors:
        summary += " Batch errors: " + " | ".join(batch_errors[:5])
    if suppressed_non_schedule_rows:
        summary += (
            f" Suppressed {suppressed_non_schedule_rows} non-schedule row(s) "
            "after schedule detection in EOQ mode."
        )
    if strict_mode_relaxed:
        summary += (
            " Detected schedule-like tables but evidence was not authoritative enough "
            "to lock strict schedule mode; kept hybrid extraction."
        )
    if focused_reread_rows:
        summary += (
            f" Focused schedule re-read on {focused_reread_rows} row(s) "
            f"to recover missing bid item codes ({focused_reread_code_fills} filled)."
        )

    return {
        "engine": "openai+vision",
        "summary": summary,
        "facts": merged_pack.get("facts") or all_facts,
        "items": items,
        "needs_review": bool(merged_pack.get("needs_review"))
        or len(items) == 0
        or plan.truncated
        or bool(batch_errors)
        or budget_stopped,
        "vision_pages": vision_pages_meta,
        "notes": (" | ".join(batch_errors) if batch_errors else None),
        "schedule_mode_active": schedule_mode_active,
        "vision_coverage": {
            "page_count": plan.page_count,
            "selected_pages": scanned_pages or plan.selected_pages,
            "skipped_pages": plan.skipped_pages + skipped_render,
            "truncated": plan.truncated or budget_stopped or bool(skipped_render),
            "scan_all": plan.scan_all and not budget_stopped,
            "batch_pages": batch_pages,
            "batches": batch_index,
            "forced_utility_pages": plan.forced_utility_pages,
            "budget_stopped": budget_stopped,
            "large_document": plan.large_document,
        },
    }


def _normalize_contract_unit(unit: str | None) -> str:
    raw = str(unit or "UNIT").strip()
    if not raw:
        return "UNIT"
    key = re.sub(r"\s+", " ", raw.lower().replace("³", "3"))
    return _CONTRACT_UNIT_MAP.get(key, raw)


def _item_evidence_blob(item: dict[str, Any]) -> str:
    return (
        f"{item.get('calculation_method') or ''} "
        f"{item.get('source_reference') or ''} "
        f"{item.get('source') or ''}"
    ).lower()


def _is_schedule_pay_item(item: dict[str, Any]) -> bool:
    """True when the row came from a Bid Items / EOQ / quantity-schedule table."""
    from app.services.traffic_control import is_plan_device_takeoff, looks_like_agency_bid_number

    if (bool(item.get("table_transcribed")) or bool(item.get("schedule_authoritative"))) and _is_authoritative_schedule_row(item):
        return True
    if is_plan_device_takeoff(item):
        return False
    if looks_like_agency_bid_number(item.get("item_code")):
        return True
    blob = _item_evidence_blob(item)
    return any(h in blob for h in _SCHEDULE_METHOD_HINTS)


def _should_drop_incidental_item(item: dict[str, Any]) -> bool:
    """Incidental children are omitted; their quantities are never added to a parent."""
    if bool(item.get("table_transcribed")):
        # Transcribed schedule rows are authoritative and must be preserved as-is.
        return False
    return should_drop_incidental_item(
        item,
        scheduled=_is_schedule_pay_item(item),
        drop_default_extras=True,
    )


def _is_plan_invent_extra(item: dict[str, Any]) -> bool:
    """Traffic-control device graphics / assumed trench — not core pay items."""
    from app.services.traffic_control import is_plan_device_takeoff, looks_like_agency_bid_number

    if looks_like_agency_bid_number(item.get("item_code")):
        return False
    if is_plan_device_takeoff(item):
        return True
    blob = _item_evidence_blob(item)
    if any(h in blob for h in _PLAN_INVENT_HINTS):
        if any(h in blob for h in _SCHEDULE_METHOD_HINTS):
            return False
        return True
    entity = str(item.get("entity_type") or "").upper()
    return entity == "ESTIMATOR"


def _method_rank(item: dict[str, Any]) -> int:
    """Higher = more trustworthy evidence when merging duplicates. Never zero-rank vision plan sheets."""
    from app.services.traffic_control import is_plan_device_takeoff, looks_like_agency_bid_number

    blob = _item_evidence_blob(item)
    if "engineering drawing sheet" in blob or "openai vision — plan sheet" in blob:
        if _is_schedule_pay_item(item):
            return 3
        return 1
    if _is_schedule_pay_item(item):
        return 3
    if is_plan_device_takeoff(item) and not looks_like_agency_bid_number(item.get("item_code")):
        return 0
    if any(h in blob for h in _DERIVED_METHOD_HINTS):
        return 1
    return 1


def _looks_like_schedule_item(item: dict[str, Any]) -> bool:
    return _is_schedule_pay_item(item)


def _is_plan_derived(item: dict[str, Any]) -> bool:
    if _is_schedule_pay_item(item):
        return False
    if _is_plan_invent_extra(item):
        return True
    method = _item_evidence_blob(item)
    return any(
        h in method
        for h in (
            "plan label",
            "callout",
            "drawing label",
            "geometry",
            "from symbol",
            "graphic count",
            "project total",
            "itemized table",
            "itemized list",
            "typical section",
            "inferred",
        )
    )


def _table_header_text(table: dict[str, Any]) -> str:
    rows = table.get("rows") or []
    if not rows:
        return ""
    return " ".join(str(c or "") for c in rows[0]).lower()


def _is_plan_device_table(table: dict[str, Any]) -> bool:
    header = _table_header_text(table)
    return any(
        k in header
        for k in (
            "project total",
            "project totals",
            "itemized",
            "channelizer",
            "mutcd",
        )
    )


def _is_bid_schedule_table(table: dict[str, Any]) -> bool:
    """True for Bid Items / EOQ / quantity-schedule tables — not F-sheet device tables."""
    if _is_plan_device_table(table):
        return False
    rows = table.get("rows") or []
    return _schedule_table_layout(rows) is not None


def _pdf_has_copied_bid_table(content: ExtractedContent | None) -> bool:
    """True only when pdfplumber actually extracted a Bid Items / EOQ table."""
    if not content:
        return False
    return any(_is_bid_schedule_table(t) for t in (content.tables or []) if t.get("rows"))


def _takeoff_is_thin(items: list[dict[str, Any]], content: ExtractedContent | None) -> bool:
    """True when AI returned a callout scrap instead of a project EOQ."""
    if _pdf_has_copied_bid_table(content):
        return False
    n = sum(1 for i in items if str(i.get("description") or "").strip())
    pages = 1
    if content is not None:
        try:
            pages = int(content.page_count or 1)
        except (TypeError, ValueError):
            pages = 1
    if n < 20:
        return True
    return pages >= 15 and n < 30


_QTY_COL_NAMES = (
    "approx. quantity",
    "approx quantity",
    "est. qty",
    "est qty",
    "quantity",
    "quantities",
    "qty",
    "qnty",
)
_ITEM_NO_COL_NAMES = (
    "item number",
    "item no",
    "item #",
    "line number",
    "line no",
    "line #",
    "line",
    "#",
)
_DESC_COL_NAMES = (
    "item description",
    "description",
    "particular",
    "material",
    "desc",
    "item",
)
_UNIT_COL_NAMES = ("units", "unit", "uom")
_CODE_COL_NAMES = (
    "std bid no",
    "standard bid",
    "std bid",
    "bid item",
    "item code",
    "item_code",
    "bid no",
    "code",
)
_SKIP_TABLE_DESC_RE = re.compile(
    r"^(project\s+)?totals?$|"
    r"^(item(\s*(no|number|#))?|bid item|description|item description|"
    r"units?|est\.?\s*qty|approx\.?\s*quantity|quantity|std bid.*)$",
    re.I,
)
_CATEGORY_ONLY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\s/&,\-\(\)\.:]{1,120}$")
_SCHEDULE_HEADER_REJECT_HINTS = (
    "itemized list",
    "project total",
    "project totals",
    "channelizer",
    "mutcd",
)
_UNIT_TOKEN_HINTS = {
    "ls",
    "lf",
    "ea",
    "each",
    "ft",
    "feet",
    "m",
    "km",
    "sqft",
    "sf",
    "sy",
    "cy",
    "ton",
    "tons",
    "kg",
    "lb",
}


def _row_cell(row: list[Any], idx: int | None) -> str:
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return str(row[idx] or "").strip()


def _schedule_table_layout(rows: list[Any]) -> tuple[int, int, int, int, int | None, int | None] | None:
    """Locate schedule header row and key columns inside a raw table."""
    if not rows:
        return None
    for header_idx in range(min(len(rows), 8)):
        header_row = rows[header_idx]
        if not isinstance(header_row, list):
            continue
        header = [str(c or "").strip().lower() for c in header_row]
        if not any(header):
            continue
        header_blob = " ".join(header)
        if any(k in header_blob for k in _SCHEDULE_HEADER_REJECT_HINTS):
            continue
        desc_idx = _find_col(header, list(_DESC_COL_NAMES))
        unit_idx = _find_col(header, list(_UNIT_COL_NAMES))
        qty_idx = _find_col(header, list(_QTY_COL_NAMES))
        code_idx = _find_col(header, list(_CODE_COL_NAMES))
        item_no_idx = _find_col(header, list(_ITEM_NO_COL_NAMES))
        if desc_idx is None or unit_idx is None or qty_idx is None:
            continue
        if code_idx is None and item_no_idx is None:
            continue
        return (header_idx, desc_idx, unit_idx, qty_idx, code_idx, item_no_idx)
    return None


def _looks_like_item_or_code_token(text: str) -> bool:
    low = str(text or "").strip().lower()
    if not low:
        return False
    if re.fullmatch(r"\d{1,5}(?:\.\d{1,5})?[a-z]?", low):
        return True
    if re.fullmatch(r"[a-z]{1,3}\d{1,5}(?:\.\d{1,5})?[a-z]?", low):
        return True
    compact = low.replace(" ", "")
    digits = sum(ch.isdigit() for ch in compact)
    letters = sum(ch.isalpha() for ch in compact)
    if digits >= 1 and letters <= 2 and len(compact) <= 14:
        return True
    return False


def _looks_like_unit_token(text: str) -> bool:
    low = str(text or "").strip().lower().replace("³", "3")
    if not low:
        return False
    compact = re.sub(r"[^a-z0-9]", "", low)
    if compact in _UNIT_TOKEN_HINTS:
        return True
    # Common punctuation variants: Sq.Ft, Cu.Yd, etc.
    return compact in {"sqft", "cuyd", "linft", "linfeet", "each", "ea", "ls", "lf", "cy", "sy", "ton", "tons"}


def _looks_like_category_header_row(
    *,
    description: str,
    item_number: str,
    bid_item: str,
    unit: str,
    qty: str,
) -> bool:
    if not description:
        return False
    low = description.strip().lower()
    if item_number or bid_item or unit or qty:
        return False
    if _SKIP_TABLE_DESC_RE.match(description):
        return False
    if any(
        token in low
        for token in (
            "for bidding",
            "estimate of quantities",
            "bid items",
            "project no",
            "project number",
            "sheet",
            "date",
            "prepared by",
            "city of",
            "department",
            "company",
            "continued",
            "(ctd",
        )
    ):
        return False
    return bool(_CATEGORY_ONLY_RE.match(description))


def _extract_row_category_header(
    row: list[Any],
    *,
    desc_idx: int,
    unit_idx: int,
    qty_idx: int,
    code_idx: int | None,
    item_no_idx: int | None,
) -> str | None:
    qty_txt = _row_cell(row, qty_idx)
    if qty_txt and _parse_number(qty_txt) is not None:
        return None
    bid_item_txt = _row_cell(row, code_idx)
    if bid_item_txt and _looks_like_item_or_code_token(bid_item_txt):
        return None
    item_no_txt = _row_cell(row, item_no_idx)
    if item_no_txt and _looks_like_item_or_code_token(item_no_txt):
        return None
    unit_txt = _row_cell(row, unit_idx)
    if unit_txt and _looks_like_unit_token(unit_txt):
        return None

    candidates: list[str] = []
    desc = _row_cell(row, desc_idx)
    if desc:
        candidates.append(desc)
    for idx, raw in enumerate(row):
        text = str(raw or "").strip()
        if not text:
            continue
        if text in candidates:
            continue
        if idx in {qty_idx, unit_idx}:
            continue
        if idx == code_idx and _looks_like_item_or_code_token(text):
            continue
        if idx == item_no_idx and _looks_like_item_or_code_token(text):
            continue
        candidates.append(text)

    for candidate in candidates:
        if _looks_like_category_header_row(
            description=candidate,
            item_number="",
            bid_item="",
            unit="",
            qty="",
        ):
            return candidate.rstrip(":").strip()
    return None


def _extract_row_description(
    row: list[Any],
    *,
    desc_idx: int,
    unit_idx: int,
    qty_idx: int,
    code_idx: int | None,
    item_no_idx: int | None,
) -> str:
    desc = _row_cell(row, desc_idx)
    if desc:
        return desc
    for idx, raw in enumerate(row):
        text = str(raw or "").strip()
        if not text:
            continue
        if idx in {qty_idx, unit_idx, code_idx, item_no_idx}:
            continue
        if _parse_number(text) is not None:
            continue
        if _looks_like_unit_token(text):
            continue
        return text
    return ""


def _items_from_document_tables(
    content: ExtractedContent,
    *,
    filename: str,
    document_id: int,
) -> list[dict[str, Any]]:
    """Strictly transcribe Bid Items / EOQ table rows from the grid only."""
    items: list[dict[str, Any]] = []
    tables = list(content.tables or [])
    chosen = [t for t in tables if _is_bid_schedule_table(t)]
    if not chosen:
        return items

    for table in chosen:
        page = table.get("page")
        rows = table.get("rows") or []
        if not rows:
            continue
        layout = _schedule_table_layout(rows)
        if not layout:
            continue
        header_idx, desc_idx, unit_idx, qty_idx, code_idx, item_no_idx = layout

        method = "Extracted from quantity table (strict grid transcription)"
        source = f"{filename} - Bid Items / EOQ table" + (f" p.{page}" if page else "")
        source_reference = "Bid Items / EOQ table"
        current_category: str | None = None
        table_items: list[dict[str, Any]] = []
        numbered_or_coded = 0
        non_blank_qty = 0

        data_rows = rows[header_idx + 1 :]
        for row in data_rows:
            if not row:
                continue

            item_no = _row_cell(row, item_no_idx)
            bid_item = _row_cell(row, code_idx)
            desc = _extract_row_description(
                row,
                desc_idx=desc_idx,
                unit_idx=unit_idx,
                qty_idx=qty_idx,
                code_idx=code_idx,
                item_no_idx=item_no_idx,
            )
            unit_raw = _row_cell(row, unit_idx)
            qty_raw = _row_cell(row, qty_idx)

            if not any(str(c or "").strip() for c in row):
                continue

            category_header = _extract_row_category_header(
                row,
                desc_idx=desc_idx,
                unit_idx=unit_idx,
                qty_idx=qty_idx,
                code_idx=code_idx,
                item_no_idx=item_no_idx,
            )
            if category_header:
                current_category = category_header
                continue

            if not desc or _SKIP_TABLE_DESC_RE.match(desc):
                continue

            qty = _parse_number(qty_raw)
            qty_blank = not qty_raw
            if qty is None:
                # Keep the row (strict transcription) even if quantity cell is blank/non-numeric.
                qty = Decimal("0")
            category = current_category or "General"
            unit = unit_raw or "UNIT"

            item = _item(
                description=desc,
                category=category,
                unit=unit,
                quantity=qty,
                item_code=bid_item or None,
                document_id=document_id,
                page=page,
                source=source,
                method=method,
                source_reference=source_reference,
                confidence=90 if (qty_blank or not unit_raw) else 99,
            )
            # Keep transcription category exactly as seen in the schedule section headers.
            item["category"] = category
            item["table_transcribed"] = True
            item["item_number"] = item_no or None
            item["raw_unit"] = unit_raw
            item["raw_quantity"] = qty_raw
            item["quantity_blank"] = qty_blank
            item["unit_blank"] = not bool(unit_raw)
            item["status"] = "needs_review" if (qty_blank or not unit_raw) else item.get("status", "needs_review")
            if qty_blank or not unit_raw:
                base_method = str(item.get("calculation_method") or method)
                item["calculation_method"] = (
                    f"{base_method} | Preserved blank schedule cell(s) exactly as transcribed."
                )
                item["needs_review"] = True
            if item_no or bid_item:
                numbered_or_coded += 1
            if not qty_blank:
                non_blank_qty += 1
            table_items.append(item)

        # Guardrail: OCR noise can produce a false one-row "table".
        # Keep tiny tables only if they clearly look like a real bid row.
        if not table_items:
            continue
        if len(table_items) == 1 and numbered_or_coded == 0:
            continue
        if len(table_items) >= 2 and numbered_or_coded == 0 and non_blank_qty < 2:
            continue
        items.extend(table_items)
    return items


def _content_has_eoq_schedule(content: ExtractedContent | None) -> bool:
    if not content:
        return False
    blob = (content.text or "").lower()
    if "itemized list" in blob and "est. qty" not in blob and "std bid" not in blob:
        # F-sheet device lists often mention quantities; that is not a Bid Items table.
        blob_for_detect = blob.replace("itemized list", " ")
    else:
        blob_for_detect = blob
    if "estimate of quantities" in blob_for_detect:
        return True
    if re.search(r"\bbid items\b", blob_for_detect) and any(
        k in blob_for_detect
        for k in (
            "est. qty",
            "est qty",
            "std bid",
            "approx. quantity",
            "approx quantity",
            "for bidding purposes",
        )
    ):
        return True
    return any(_is_bid_schedule_table(t) for t in (content.tables or []) if t.get("rows"))


def _has_authoritative_schedule(
    content: ExtractedContent | None,
    items: list[dict[str, Any]],
) -> bool:
    """True only when a real Bid Items / EOQ table was captured — not an F-sheet list."""
    from app.services.traffic_control import is_plan_device_takeoff, looks_like_agency_bid_number

    if content:
        copied = _items_from_document_tables(content, filename="plan", document_id=0)
        strict_copied = [row for row in copied if _is_strict_schedule_lock_row(row)]
        if strict_copied:
            return True
    strict_rows = [item for item in items if _is_strict_schedule_lock_row(item)]
    if len(strict_rows) >= 2:
        return True
    if len(strict_rows) == 1 and _has_schedule_identifiers(
        item_number=strict_rows[0].get("item_number"),
        item_no=strict_rows[0].get("item_no"),
        line_number=strict_rows[0].get("line_number"),
        item_code=strict_rows[0].get("item_code"),
    ):
        return True
    coded = 0
    strong = 0
    for item in items:
        if is_plan_device_takeoff(item):
            continue
        blob = _item_evidence_blob(item)
        if "itemized list" in blob or re.search(r"\bsheet f\d", blob):
            continue
        if looks_like_agency_bid_number(item.get("item_code")):
            coded += 1
            continue
        if any(
            h in blob
            for h in (
                "estimate of quantities",
                "est. qty",
                "std bid",
                "approx. quantity",
                "for bidding purposes",
            )
        ):
            strong += 1
    return coded >= 5 or strong >= 8


def _page_looks_like_bid_schedule(text: str) -> bool:
    low = (text or "").lower()
    if "itemized list" in low or "project totals" in low:
        return False
    return any(
        k in low
        for k in (
            "estimate of quantities",
            "est. qty",
            "est qty",
            "std bid",
            "approx. quantity",
            "approx quantity",
            "for bidding purposes",
        )
    ) or (
        re.search(r"\bbid items\b", low)
        and any(k in low for k in ("est. qty", "est qty", "std bid", "item number", "units"))
    )


def _text_for_openai(content: ExtractedContent, *, char_limit: int = 80000) -> str:
    """Put Bid Items / EOQ pages first so a 50k clip is not only F-sheets / notes."""
    pages = list(content.pages or [])
    if pages:
        bid_pages = [p for p in pages if _page_looks_like_bid_schedule(p.text)]
        other = [p for p in pages if p not in bid_pages]
        ordered = bid_pages + other
        text = "\n\n".join(f"--- Page {p.page} ---\n{p.text}" for p in ordered if (p.text or "").strip())
        if text.strip():
            return text[:char_limit]
    return (content.text or "")[:char_limit]


def _tables_for_openai(content: ExtractedContent) -> list[dict[str, Any]]:
    """Send real bid-schedule tables first; skip F-sheet device tables."""
    tables = [t for t in (content.tables or []) if t.get("rows")]
    schedule = [t for t in tables if _is_bid_schedule_table(t)]
    rest = [t for t in tables if t not in schedule and not _is_plan_device_table(t)]
    return (schedule + rest)[:40]


def _should_drop_inferred_extra(
    item: dict[str, Any],
    *,
    schedule_present: bool = False,
) -> bool:
    """Kept for tests/callers. Never deletes pipe/paving/curb because a schedule exists."""
    return False


def _prefer_schedule_quantity(
    existing: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """When merging duplicates, keep schedule wording/qty over derived geometry.

    Never replace a clean parent quantity with one that folded in incidental work.
    """
    e_blob = _item_evidence_blob(existing)
    c_blob = _item_evidence_blob(candidate)
    e_inflated = quantity_inflated_by_incidentals(e_blob)
    c_inflated = quantity_inflated_by_incidentals(c_blob)
    if c_inflated and not e_inflated:
        return dict(existing)
    if e_inflated and not c_inflated:
        return dict(candidate)

    er = _method_rank(existing)
    cr = _method_rank(candidate)
    if cr > er:
        return dict(candidate)
    if er > cr:
        return dict(existing)
    try:
        old_c = float(existing.get("confidence") or 0)
        new_c = float(candidate.get("confidence") or 0)
        old_q = float(existing.get("quantity") or 0)
        new_q = float(candidate.get("quantity") or 0)
    except (TypeError, ValueError):
        return dict(existing)
    # Prefer schedule-coded item_code
    if candidate.get("item_code") and not existing.get("item_code"):
        return dict(candidate)
    if existing.get("item_code") and not candidate.get("item_code"):
        return dict(existing)
    if new_c > old_c + 2:
        if c_inflated:
            return dict(existing)
        return dict(candidate)
    # When both schedule-grade, prefer the larger qty (avoids detail undercounts)
    # unless the larger figure mixed in incidental work.
    if er >= 2 and cr >= 2 and new_q > old_q * 1.15 and not c_inflated:
        return dict(candidate)
    if abs(new_c - old_c) <= 2 and new_q > old_q and er == 0 and not c_inflated:
        return dict(candidate)
    if abs(new_c - old_c) <= 2 and er >= 2:
        return dict(existing)
    if abs(new_c - old_c) <= 2 and new_q > old_q and not c_inflated:
        return dict(candidate)
    return dict(existing)


def _finalize_analysis(result: dict[str, Any], *, content: ExtractedContent | None = None) -> dict[str, Any]:
    """Copy Bid Items / EOQ tables as pay items; drop F-sheet and estimator invents."""
    items = [dict(i) for i in (result.get("items") or []) if i.get("description")]
    if content is not None:
        doc_id = 0
        for existing in items:
            try:
                doc_id = int(existing.get("source_document_id") or 0)
            except (TypeError, ValueError):
                doc_id = 0
            if doc_id:
                break
        copied = _items_from_document_tables(content, filename="plan", document_id=doc_id)
        if copied:
            items = copied + items

    if not items:
        return result

    for item in items:
        item["unit"] = _normalize_contract_unit(item.get("unit"))
        # Normalize continuation category labels
        cat = str(item.get("category") or "")
        if cat:
            item["category"] = re.sub(
                r"\s*\(ctd\.?\)\s*$",
                "",
                cat,
                flags=re.I,
            ).strip() or cat

    before_incidental = len(items)
    items = [item for item in items if not _should_drop_incidental_item(item)]
    incidental_dropped = before_incidental - len(items)
    if not items:
        out = dict(result)
        out["items"] = []
        note = "Dropped incidental-to-bid-item work (not separately paid)."
        out["notes"] = ((out.get("notes") or "") + " | " + note).strip(" |")
        return out

    schedule_present = _has_authoritative_schedule(content, items)
    cleaned = list(items)
    table_transcribed_present = any(bool(i.get("table_transcribed")) for i in cleaned)
    strict_schedule_mode = bool(result.get("schedule_mode_active"))
    dropped_non_schedule = 0

    if schedule_present and table_transcribed_present:
        schedule_rows = [i for i in cleaned if bool(i.get("table_transcribed"))]
        schedule_desc = {
            re.sub(r"\s+", " ", str(i.get("description") or "").strip().lower())
            for i in schedule_rows
            if str(i.get("description") or "").strip()
        }
        schedule_codes = {
            str(i.get("item_code") or "").strip().lower()
            for i in schedule_rows
            if str(i.get("item_code") or "").strip()
        }
        non_schedule_rows: list[dict[str, Any]] = []
        for item in cleaned:
            if bool(item.get("table_transcribed")):
                continue
            desc_key = re.sub(r"\s+", " ", str(item.get("description") or "").strip().lower())
            code_key = str(item.get("item_code") or "").strip().lower()
            if (desc_key and desc_key in schedule_desc) or (code_key and code_key in schedule_codes):
                dropped_non_schedule += 1
                continue
            if strict_schedule_mode and not _is_strict_schedule_lock_row(item):
                dropped_non_schedule += 1
                continue
            category = str(item.get("category") or "").strip().lower()
            if category in {"general", "miscellaneous"} and not _is_schedule_pay_item(item):
                dropped_non_schedule += 1
                continue
            non_schedule_rows.append(item)
        before_combine = len(non_schedule_rows)
        non_schedule_rows = combine_similar_pay_items(non_schedule_rows)
        combined_groups = before_combine - len(non_schedule_rows)
        cleaned = schedule_rows + non_schedule_rows
    else:
        before_combine = len(cleaned)
        cleaned = combine_similar_pay_items(cleaned)
        combined_groups = before_combine - len(cleaned)

    # Roll individual traffic signs → one SqFt "Traffic Control" item
    from app.services.traffic_control import consolidate_traffic_control_signs

    cleaned, tc_meta = consolidate_traffic_control_signs(
        cleaned,
        allow_online_refresh=not schedule_present,
        schedule_present=schedule_present,
    )
    for item in cleaned:
        item["unit"] = _normalize_contract_unit(item.get("unit"))

    out = dict(result)
    out["items"] = cleaned
    if incidental_dropped:
        inc_note = (
            f"Omitted {incidental_dropped} incidental item(s); "
            "not separately paid and not added to parent quantities."
        )
        out["notes"] = ((out.get("notes") or "") + " | " + inc_note).strip(" |")
        out["summary"] = f"{(out.get('summary') or '')} {inc_note}".strip()
    if combined_groups:
        comb_note = (
            f"Combined {combined_groups} similar pay item(s) from multiple locations into one quantity."
        )
        out["notes"] = ((out.get("notes") or "") + " | " + comb_note).strip(" |")
        out["summary"] = f"{(out.get('summary') or '')} {comb_note}".strip()
    if dropped_non_schedule:
        if strict_schedule_mode:
            prune_note = (
                f"Dropped {dropped_non_schedule} non-schedule row(s) "
                "because an authoritative bid schedule was detected."
            )
        else:
            prune_note = (
                f"Dropped {dropped_non_schedule} non-table General/Misc row(s) "
                "because a strict bid schedule table was transcribed."
            )
        out["notes"] = ((out.get("notes") or "") + " | " + prune_note).strip(" |")
        out["summary"] = f"{(out.get('summary') or '')} {prune_note}".strip()
    if tc_meta.get("sign_rows"):
        tc_note = (
            f"Rolled {tc_meta['sign_rows']} traffic sign(s) into Traffic Control "
            f"({tc_meta.get('total_sqft')} SqFt; plan sizes or MUTCD)."
        )
        out["notes"] = ((out.get("notes") or "") + " | " + tc_note).strip(" |")
        out["summary"] = f"{(out.get('summary') or '')} {tc_note}".strip()
        out["traffic_control"] = tc_meta
    out["needs_review"] = bool(out.get("needs_review")) or len(cleaned) == 0
    return out


def _merge_analysis_results(text_result: dict[str, Any], vision_result: dict[str, Any]) -> dict[str, Any]:
    """Union text/table items with drawing-vision items.

    Keep every location takeoff; similar rows are summed later in finalize.
    """
    strict_schedule_mode = bool(
        text_result.get("schedule_mode_active")
        or vision_result.get("schedule_mode_active")
    )
    items: list[dict[str, Any]] = []
    suppressed = 0
    for source in (text_result.get("items") or [], vision_result.get("items") or []):
        for item in source:
            if not item.get("description"):
                continue
            normalized = dict(item)
            normalized["unit"] = _normalize_contract_unit(normalized.get("unit"))
            if strict_schedule_mode and not _is_strict_schedule_lock_row(normalized):
                suppressed += 1
                continue
            if _should_drop_incidental_item(normalized):
                continue
            items.append(normalized)

    facts = list(text_result.get("facts") or []) + list(vision_result.get("facts") or [])
    summary = (
        f"{vision_result.get('summary') or ''} "
        f"Also merged text/table takeoff ({len(text_result.get('items') or [])} text items, "
        f"{len(vision_result.get('items') or [])} drawing items → {len(items)} unique)."
    ).strip()
    if strict_schedule_mode and suppressed:
        summary = f"{summary} Suppressed {suppressed} non-schedule row(s) in schedule mode.".strip()
    return {
        "engine": "openai+vision",
        "summary": summary,
        "facts": facts,
        "items": items,
        "needs_review": bool(text_result.get("needs_review") or vision_result.get("needs_review"))
        or len(items) == 0,
        "schedule_mode_active": strict_schedule_mode,
        "vision_pages": vision_result.get("vision_pages") or [],
        "vision_coverage": vision_result.get("vision_coverage")
        or text_result.get("vision_coverage"),
    }


def answer_engineering_question(*, question: str, context: str) -> dict[str, Any]:
    from app.services.openai_client import openai_configured

    if openai_configured():
        try:
            return _answer_with_openai(question=question, context=context)
        except Exception as exc:
            fallback = _answer_heuristic(question=question, context=context)
            fallback["answer"] = f"{fallback['answer']}\n\n(Note: OpenAI unavailable: {exc})"
            return fallback
    return _answer_heuristic(question=question, context=context)


def _answer_with_openai(*, question: str, context: str) -> dict[str, Any]:
    from app.services.openai_client import ask_openai_json

    system = (
        "You are AutoVAD, an assistant for civil engineers working on USA road projects. "
        "Answer using ONLY the project context. If unknown, say you don't have enough information. "
        "Return STRICT JSON only."
    )
    user = f"""
CONTEXT:
{context[:50000]}

QUESTION:
{question}

Return JSON:
{{
  "answer": "markdown-friendly answer",
  "sources": [{{"label":"Page 18 – Table 4.2","document_id":1,"page":18}}]
}}
"""
    data = ask_openai_json(system, user, temperature=0.2)
    return {
        "answer": data.get("answer") or "No answer returned.",
        "sources": data.get("sources") or [],
        "engine": "openai",
    }


def _answer_heuristic(*, question: str, context: str) -> dict[str, Any]:
    q = question.lower()
    sources: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in context.splitlines() if ln.strip()]

    def find_lines(keywords: list[str]) -> list[str]:
        hits = []
        for ln in lines:
            low = ln.lower()
            if any(k in low for k in keywords):
                hits.append(ln)
            if len(hits) >= 8:
                break
        return hits

    if "road width" in q or "carriageway" in q:
        hits = find_lines(["road width", "carriageway width", "width"])
        if hits:
            return {"answer": "From project documents:\n- " + "\n- ".join(hits[:5]), "sources": sources, "engine": "heuristic"}

    if "gsb" in q:
        hits = find_lines(["gsb"])
        if hits:
            return {"answer": "GSB references found:\n- " + "\n- ".join(hits[:6]), "sources": sources, "engine": "heuristic"}

    if "wmm" in q:
        hits = find_lines(["wmm"])
        if hits:
            return {"answer": "WMM references found:\n- " + "\n- ".join(hits[:6]), "sources": sources, "engine": "heuristic"}

    if "culvert" in q:
        hits = find_lines(["culvert"])
        if hits:
            return {"answer": "Culvert references found:\n- " + "\n- ".join(hits[:6]), "sources": sources, "engine": "heuristic"}

    if "pavement" in q or "layer" in q:
        hits = find_lines(["gsb", "wmm", "dbm", "bituminous", "asphalt", "pavement"])
        if hits:
            return {"answer": "Pavement-related findings:\n- " + "\n- ".join(hits[:8]), "sources": sources, "engine": "heuristic"}

    if "eoq" in q or "boq" in q or "quantity" in q or "how much" in q:
        hits = find_lines(["quantity", "qty", "m3", "gsb", "wmm", "eoq", "boq"])
        if hits:
            return {"answer": "Quantity-related findings:\n- " + "\n- ".join(hits[:8]), "sources": sources, "engine": "heuristic"}

    # generic keyword search
    keywords = [w for w in re.findall(r"[a-zA-Z]{3,}", q) if w not in {"what", "where", "show", "find", "this", "that", "from", "with", "have", "many", "much"}]
    hits = find_lines(keywords[:4]) if keywords else []
    if hits:
        return {
            "answer": "I found these related excerpts in the project documents:\n- " + "\n- ".join(hits[:8]),
            "sources": sources,
            "engine": "heuristic",
        }

    return {
        "answer": (
            "I don't have enough extracted information to answer confidently yet. "
            "Run AI analysis on the uploaded documents, then ask again."
        ),
        "sources": [],
        "engine": "heuristic",
    }


def _item(
    *,
    description: str,
    category: str,
    unit: str,
    quantity: Decimal,
    document_id: int,
    page: int | None,
    source: str,
    method: str,
    confidence: float,
    item_code: str | None = None,
    status: str = "needs_review",
    source_reference: str | None = None,
) -> dict[str, Any]:
    from app.services.csi_mapper import enrich_quantity_item

    raw = {
        "item_code": item_code,
        "description": description,
        "category": category,
        "unit": _normalize_contract_unit(unit),
        "quantity": float(quantity),
        "source_document_id": document_id,
        "source_page": page,
        "source_reference": source_reference or source,
        "calculation_method": method,
        "confidence": confidence,
        "status": status,
    }
    return enrich_quantity_item(raw)


def _map_alias(text: str) -> tuple[str, str, str] | None:
    low = text.lower()
    for key, value in ITEM_ALIASES.items():
        if key in low:
            return value
    return None


def _find_col(header: list[str], names: list[str]) -> int | None:
    """Pick the column whose header best matches (longest / exact name wins)."""
    best: tuple[int, int] | None = None
    for i, raw in enumerate(header):
        h = str(raw or "").strip().lower()
        if not h:
            continue
        for n in names:
            key = str(n or "").strip().lower()
            if not key:
                continue
            if key == h:
                score = 1000 + len(key)
            elif key in h:
                score = len(key)
            else:
                continue
            if best is None or score > best[0]:
                best = (score, i)
    return best[1] if best else None


def _parse_number(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def _normalize_unit(unit: str) -> str:
    u = unit.strip().lower().replace("³", "3")
    mapping = {
        "m3": "m3",
        "cu.m": "m3",
        "cu m": "m3",
        "cubic meter": "m3",
        "cubic meters": "m3",
        "m": "m",
        "lm": "m",
        "lin m": "m",
        "linear m": "m",
        "nos": "nos",
        "no": "nos",
        "no.": "nos",
        "each": "nos",
        "ea": "nos",
        "t": "t",
        "ton": "t",
        "tons": "t",
    }
    return mapping.get(u, unit.strip())


def _guess_page(full_text: str, pos: int, content: ExtractedContent) -> int | None:
    prefix = full_text[:pos]
    pages = re.findall(r"--- Page (\d+) ---", prefix)
    if pages:
        return int(pages[-1])
    if content.pages:
        return content.pages[0].page
    return None
