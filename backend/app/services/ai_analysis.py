"""Civil document intelligence: OpenAI when configured, heuristic fallback otherwise.

PDF plans use text/tables PLUS rendered drawing sheets via OpenAI vision so
engineering drawings (not only OCR text) drive EOQ quantities.
"""

from __future__ import annotations

import json
import re
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
5. When a Bid Items / Estimate Of Quantities table exists, COPY those table rows as the pay-item list.
   Do NOT invent extras from F-sheets, typical sections, trench assumptions, graphic/symbol counts,
   or device “Project Totals” tables. Do NOT decompose a bundled schedule item into fittings
   (elbows, tees, valves, hydrants, plugs, reducers, casing/carrier segments) unless those are separate schedule rows.
6. When a schedule quantity exists, NEVER replace it by counting symbols, reading a detail callout, or measuring geometry.
7. Keep schedule-distinct variants separate (furnish vs install, left vs right flange, diameters, materials, alternates).
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
- Copy BID ITEM / Standard Bid Item Number (e.g. 634.0110, 9.0010, Special).
- Do NOT add extra bid items from F-sheet device tables (“Project Totals”), graphic channelizer counts, or individual MUTCD signs.
  Those faces are already inside the schedule Traffic Control SqFt quantity.
ELSE (no bid schedule for signing):
- Do NOT list individual STOP/YIELD/Speed Limit/MUTCD signs as separate Each pay items.
- Roll those sign faces into ONE pay item: description "Traffic Control", unit SqFt (width×height in inches ÷ 144).
- Keep barricades, drums, PCMS, temporary business signs, and true TTC LS items as their own pay items when evidenced.

EVIDENCE:
Every output item should cite a schedule/pay-item row in source_reference / calculation_method
(e.g. "EOQ schedule p.3 row"). Omit invents without schedule evidence.
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
    "typical section",
    "assumed ",
    "cover assumed",
    "trench width",
    "estimator takeoff",
    "estimator allowance",
    "civil estimator",
    "visible labeled",
    "unique labeled",
    "one table row counted",
    "counted as one proposed",
    "measured from",
    "inferred from station",
    "mutcd",
    "consolidated",
    "project total",
    "itemized table",
    "f-sheet",
    "sheets f",
    "incidental",
    "no separate pay",
    "no separate measurement",
    "subsidiary to",
)
_DERIVED_METHOD_HINTS = (
    "geometry",
    "hatch",
    "typical section",
    "inferred",
    "assumed",
    "from drawing symbol",
    "from symbol",
    "plan label",
    "callout",
)
# Plan-derived water / utility components that dominate false extras (Test 2).
_GENERIC_INFERRED_DESC = re.compile(
    r"(?:"
    r"(?:\d+[-\s]?inch\s+)?(?:gravity\s+)?(?:sanitary\s+)?sewer\s+main|"
    r"(?:\d+[-\s]?inch\s+)?(?:c900|dr\s*\d+\s+)?(?:pvc\s+)?water\s+main|"
    r"(?:\d+[-\s]?inch\s+)?restrained\s+joint|"
    r"(?:\d+[-\s]?inch\s+)?(?:steel\s+)?casing\s+pipe|"
    r"(?:\d+[-\s]?inch\s+)?(?:rj\s+)?(?:pvc\s+)?carrier\s+pipe|"
    r"sanitary\s+sewer\s+manhole|"
    r"(?:\d+[-\s]?inch\s+)?fire\s+hydrant|"
    r"(?:\d+[-\s]?inch\s+)?(?:salvaged\s+)?(?:gate\s+)?valve|"
    r"water\s+(?:valve|tee|bend|elbow)|"
    r"(?:\d+[-\s]?inch\s+)?(?:x\s*\d+[-\s]?inch\s+)?mj\s+(?:reducer|elbow|tee|bend)|"
    r"(?:\d+[-\s]?inch\s+)?(?:long\s+)?sleeve|"
    r"(?:\d+[-\s]?inch\s+)?plug\b|"
    r"utility\s+locate|"
    r"aggregate\s+base|"
    r"geotextile|"
    r"asphalt\s+concrete\s+pavement|"
    r"concrete\s+curb\s+and\s+gutter"
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

        # Deterministic label pass — skip when EOQ/schedule text is present so plan
        # fittings/valves do not flood extras (Training Test 2).
        label_result = None
        if not _content_has_eoq_schedule(content):
            label_result = _analyze_utility_labels(
                filename=filename,
                content=content,
                document_id=document_id,
            )
        else:
            # Still allow sized water-main LF labels only (no fittings).
            label_result = _analyze_utility_labels(
                filename=filename,
                content=content,
                document_id=document_id,
                mains_only=True,
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

        merged_parts = [r for r in (text_result, label_result, vision_result) if r]
        if len(merged_parts) >= 2:
            merged = merged_parts[0]
            for part in merged_parts[1:]:
                merged = _merge_analysis_results(merged, part)
            if errors:
                merged["notes"] = (merged.get("notes") or "") + " | ".join(errors)
            return _finalize_analysis(merged, content=content)
        if vision_result:
            return _finalize_analysis(vision_result, content=content)
        if label_result and label_result.get("items"):
            return _finalize_analysis(label_result, content=content)
        if text_result and text_result.get("items"):
            return _finalize_analysis(text_result, content=content)
        if text_result:
            return _finalize_analysis(text_result, content=content)

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
    for it in _items_from_document_tables(content, filename=filename, document_id=document_id):
        key = str(it.get("description") or "").lower()
        if key and key not in seen:
            seen.add(key)
            items.append(it)

    schedule_present = _content_has_eoq_schedule(content)

    # 2) Regex over free text — skip when a Bid Items / EOQ table is the pay-item source
    text = content.text or ""
    pattern_rows = () if schedule_present else CIVIL_PATTERNS
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
    label_pack = _analyze_utility_labels(
        filename=filename,
        content=content,
        document_id=document_id,
        mains_only=_content_has_eoq_schedule(content),
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

    if not _content_has_eoq_schedule(content):
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


def _items_from_openai_payload(
    data: dict[str, Any],
    *,
    filename: str,
    document_id: int,
    default_method: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw_item in data.get("items") or []:
        qty = _parse_number(raw_item.get("quantity"))
        if qty is None or not raw_item.get("description"):
            continue
        conf = _parse_number(raw_item.get("confidence")) or Decimal("80")
        built = _item(
                description=str(raw_item.get("description")).strip(),
                category=str(raw_item.get("category") or "General"),
                unit=str(raw_item.get("unit") or "unit"),
                quantity=qty,
                item_code=(str(raw_item["item_code"]) if raw_item.get("item_code") else None),
                document_id=document_id,
                page=raw_item.get("source_page"),
                source=f"{filename}"
                + (f" - Page {raw_item.get('source_page')}" if raw_item.get("source_page") else "")
                + (f" - {raw_item.get('source_reference')}" if raw_item.get("source_reference") else ""),
                method=str(raw_item.get("calculation_method") or default_method),
                confidence=float(conf),
                status=str(raw_item.get("status") or "needs_review"),
                source_reference=raw_item.get("source_reference"),
            )
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

    clipped = (content.text or "")[:50000]
    tables_preview = json.dumps(content.tables[:12], ensure_ascii=True)[:18000]
    design_takeoff = not _content_has_eoq_schedule(content)
    system, catalog_rules, code_hint = _catalog_prompt_bits(bid_catalog, design_takeoff=design_takeoff)

    design_or_schedule = (
        "No EOQ/bid schedule was detected — act as a civil estimator and generate pay items from "
        "typical sections, dimensions, and callouts (roads, utilities, dams, reservoirs, buildings)."
        if design_takeoff
        else "Harvest EVERY row from EOQ / Bid Items / quantity tables (ITEM NUMBER, BID ITEM, DESCRIPTION, UNITS, EST. QTY or ITEM NO, STD BID NO, APPROX. QUANTITY). For a Traffic Control heading, copy every row in that section, including LS and Each companions, and the SqFt EST. QTY as printed."
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
    items = _items_from_openai_payload(
        data, filename=filename, document_id=document_id, default_method="OpenAI text/table extraction"
    )
    return {
        "engine": "openai",
        "summary": data.get("summary") or f"OpenAI text-analyzed '{filename}'.",
        "facts": data.get("facts") or [],
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

    plan = plan_pdf_vision_pages(
        pdf_path,
        max_pages=max_pages,
        min_score=min_score,
        force_utility_pages=force_utility_pages,
        scan_all_pages=scan_all_pages,
        batch_pages=batch_pages,
    )
    if not plan.selected_pages:
        raise RuntimeError("No PDF pages could be rendered for vision")

    design_takeoff = not _content_has_eoq_schedule(content)
    system, catalog_rules, code_hint = _catalog_prompt_bits(
        bid_catalog, design_takeoff=design_takeoff
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
        + (
            "No schedule: generate civil-estimator EOQ from typical sections, dimensions, and counts. "
            "Do not take off incidental trench/bedding/fittings or add them into pipe quantities."
            if design_takeoff
            else "Do not invent fittings/valves from plan details when a schedule exists. "
            "Do not take off incidental work or add it into a parent bid-item quantity."
        )
    )
    all_items: list[dict[str, Any]] = []
    all_facts: list[Any] = []
    summaries: list[str] = []
    vision_pages_meta: list[dict[str, Any]] = []
    batch_errors: list[str] = []
    batch_index = 0

    for batch in iter_rendered_pdf_batches(pdf_path, plan, dpi=dpi, batch_pages=batch_pages):
        batch_index += 1
        page_meta = ", ".join(f"p{p.page} ({p.reason})" for p in batch)
        images = [{"page": p.page, "png_b64": p.png_b64} for p in batch]
        vision_pages_meta.extend({"page": p.page, "reason": p.reason} for p in batch)
        coverage_note = (
            f"This is batch {batch_index} of the PDF. "
            f"Document has {plan.page_count} page(s); this request covers pages "
            f"{[p.page for p in batch]}. Extract ALL bid/takeoff items visible on THESE sheets only."
        )
        sheet_job = (
            """
Primary job:
- If an Estimate Of Quantities / bid quantity table appears, extract EVERY row (LEFT then RIGHT).
- Continuation “(Ctd.)” keeps the parent category. Include Alternates, LS, Traffic Control, Removals, landscaping.
- Copy APPROX. QUANTITY from the schedule cell. Do not count symbols when the schedule shows a project total.
- On sheets WITHOUT an EOQ table: take off pay items as a civil estimator from typical sections, dimensions,
  hatch areas, and printed counts (roads, utilities, dams/reservoirs, buildings). Show formulas in calculation_method.
  Assumed HMA 145 pcf — write assumptions down. Do not invent trench/bedding/backfill or fittings unless they
  are printed as pay items. Never add incidental work into a parent quantity.
"""
            if design_takeoff
            else """
Primary job:
- If an Estimate Of Quantities / Bid Items table appears (ITEM NUMBER, BID ITEM, DESCRIPTION, UNITS, EST. QTY
  or ITEM NO / STD BID NO / APPROX. QUANTITY), extract EVERY row from LEFT then RIGHT. That schedule is the
  ONLY source for pay items on that sheet.
- Traffic Control section: copy EVERY row under the heading — not only the SqFt signing line. Typical companions:
  Traffic Control (SqFt = EST. QTY), Traffic Control Miscellaneous (LS), barricades (Each), temporary business
  signs, portable changeable message signs, temporary mailbox, temporary gravel access (LS), winter maintenance (LS).
  Copy the BID ITEM number (e.g. 634.0110 or Special). Do not recompute Traffic Control SqFt from MUTCD 30×30.
  Do not add channelizers or MUTCD signs from F-sheet graphics or device “Project Totals” tables.
- Continuation: if the header says “(Ctd.)” / Continued, keep extracting rows into the parent category.
- Include Alternates, LS/general, Traffic Control/Signals/Lighting, Removals, Erosion/Landscaping.
- Copy the EST. QTY / APPROX. QUANTITY from the schedule cell. Do not count symbols when the schedule shows a total.
- On pure plan/profile/detail sheets WITHOUT an EOQ/Bid Items table: do not invent water fittings, valves,
  hydrants, casing/carrier segments, pavement layers, or extra traffic devices from symbols.
- Incidental notes (incidental to / included in / no separate payment): omit those items entirely. Do not add
  their counts or volumes into the parent bid item.
"""
        )
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
      "item_code": "optional STD BID NO",
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
  "needs_review": true
}}
"""
        try:
            data = ask_openai_vision_json(vision_system, user, images)
        except Exception as exc:
            batch_errors.append(f"batch {batch_index} pages {[p.page for p in batch]}: {exc}")
            continue
        batch_items = _items_from_openai_payload(
            data,
            filename=filename,
            document_id=document_id,
            default_method="OpenAI vision — engineering drawing sheet",
        )
        all_items.extend(batch_items)
        all_facts.extend(data.get("facts") or [])
        if data.get("summary"):
            summaries.append(str(data["summary"]))

    # Merge duplicate keys across batches (same desc/unit)
    merged_pack = _merge_analysis_results(
        {"items": [], "facts": [], "summary": "", "needs_review": False},
        {
            "items": all_items,
            "facts": all_facts,
            "summary": " ".join(summaries).strip(),
            "needs_review": len(all_items) == 0,
            "vision_pages": vision_pages_meta,
        },
    )
    items = merged_pack.get("items") or all_items
    scanned = len(plan.selected_pages)
    summary = (
        f"Vision-analyzed {scanned}/{plan.page_count} page(s) from '{filename}' "
        f"in {batch_index} batch(es)."
    )
    if summaries:
        summary = f"{summary} {' '.join(summaries[:3])}"
    if plan.truncated:
        summary += (
            f" Safety cap skipped {len(plan.skipped_pages)} page(s) "
            f"(set OPENAI_VISION_MAX_PAGES=0 and OPENAI_VISION_SCAN_ALL_PAGES=true for full scan)."
        )
    if batch_errors:
        summary += " Batch errors: " + " | ".join(batch_errors[:5])

    return {
        "engine": "openai+vision",
        "summary": summary,
        "facts": merged_pack.get("facts") or all_facts,
        "items": items,
        "needs_review": bool(merged_pack.get("needs_review"))
        or len(items) == 0
        or plan.truncated
        or bool(batch_errors),
        "vision_pages": vision_pages_meta,
        "notes": (" | ".join(batch_errors) if batch_errors else None),
        "vision_coverage": {
            "page_count": plan.page_count,
            "selected_pages": plan.selected_pages,
            "skipped_pages": plan.skipped_pages,
            "truncated": plan.truncated,
            "scan_all": plan.scan_all,
            "batch_pages": batch_pages,
            "batches": batch_index,
            "forced_utility_pages": plan.forced_utility_pages,
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

    if is_plan_device_takeoff(item):
        return False
    if looks_like_agency_bid_number(item.get("item_code")):
        return True
    blob = _item_evidence_blob(item)
    return any(h in blob for h in _SCHEDULE_METHOD_HINTS)


def _should_drop_incidental_item(item: dict[str, Any]) -> bool:
    """Incidental children are omitted; their quantities are never added to a parent."""
    return should_drop_incidental_item(
        item,
        scheduled=_is_schedule_pay_item(item),
        drop_default_extras=True,
    )


def _is_plan_invent_extra(item: dict[str, Any]) -> bool:
    """F-sheet devices, symbol counts, MUTCD rollups, assumed trench, typical sections."""
    from app.services.traffic_control import is_plan_device_takeoff, looks_like_agency_bid_number

    if looks_like_agency_bid_number(item.get("item_code")):
        return False
    if is_plan_device_takeoff(item):
        return True
    blob = _item_evidence_blob(item)
    if any(h in blob for h in _PLAN_INVENT_HINTS):
        # Vision may still cite a bid table in the same blob — that is a schedule row.
        if any(h in blob for h in _SCHEDULE_METHOD_HINTS):
            return False
        return True
    entity = str(item.get("entity_type") or "").upper()
    if entity == "ESTIMATOR":
        return True
    if re.search(r"\bsheet f\d", blob) and any(
        h in blob for h in ("graphic", "symbol", "project total", "itemized", "measured", "approximate")
    ):
        return True
    return False


def _method_rank(item: dict[str, Any]) -> int:
    """Higher = more trustworthy evidence for EOQ accuracy."""
    if _is_plan_invent_extra(item):
        return 0
    if _is_schedule_pay_item(item):
        return 3
    method = _item_evidence_blob(item)
    desc = str(item.get("description") or "")
    if _GENERIC_INFERRED_DESC.search(desc) and any(
        h in method for h in ("label", "callout", "drawing", "symbol", "geometry")
    ):
        return 0
    if any(h in method for h in ("label", "callout")):
        return 1
    if any(h in method for h in _DERIVED_METHOD_HINTS):
        return 0
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
    return any(k in header for k in ("project total", "project totals", "itemized"))


def _is_bid_schedule_table(table: dict[str, Any]) -> bool:
    """True for Bid Items / EOQ / quantity-schedule tables — not F-sheet device tables."""
    if _is_plan_device_table(table):
        return False
    header = _table_header_text(table)
    if any(
        k in header
        for k in (
            "std bid",
            "standard bid",
            "est. qty",
            "est qty",
            "approx. quantity",
            "approx quantity",
            "bid item",
            "item description",
            "for bidding",
            "proposal quantity",
        )
    ):
        return True
    if (
        ("description" in header or "particular" in header)
        and ("quantity" in header or "qty" in header)
        and ("unit" in header)
        and not any(k in header for k in ("tjb", "fjb", "fitting", "locator", "channelizer"))
    ):
        return True
    return False


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


def _items_from_document_tables(
    content: ExtractedContent,
    *,
    filename: str,
    document_id: int,
) -> list[dict[str, Any]]:
    """Copy Bid Items / EOQ tables as pay items. Skip F-sheet Project Totals tables."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    tables = list(content.tables or [])
    schedule_tables = [t for t in tables if _is_bid_schedule_table(t)]
    if schedule_tables:
        chosen = schedule_tables
        schedule_copy = True
    else:
        chosen = [t for t in tables if not _is_plan_device_table(t)]
        schedule_copy = False

    for table in chosen:
        page = table.get("page")
        rows = table.get("rows") or []
        if not rows:
            continue
        header = [str(c or "").lower() for c in rows[0]]
        qty_idx = _find_col(header, list(_QTY_COL_NAMES))
        desc_idx = _find_col(header, list(_DESC_COL_NAMES))
        unit_idx = _find_col(header, list(_UNIT_COL_NAMES))
        code_idx = _find_col(header, list(_CODE_COL_NAMES))

        if qty_idx is None and len(header) >= 3:
            for i, h in enumerate(header):
                if "unit" in h:
                    unit_idx = i
                if any(k in h for k in ("item", "desc", "material")):
                    desc_idx = i
                if any(k in h for k in ("qty", "quantity")):
                    qty_idx = i
            if qty_idx is None and len(header) >= 3:
                desc_idx, unit_idx, qty_idx = 0, 1, 2

        method = (
            "Extracted from quantity table"
            if schedule_copy
            else "Extracted from tabular quantity sheet"
        )
        source = (
            f"{filename} - Bid Items / EOQ table" + (f" p.{page}" if page else "")
            if schedule_copy
            else f"{filename}" + (f" - Table p.{page}" if page else " - Table")
        )
        source_reference = "Bid Items / EOQ table" if schedule_copy else source

        data_rows = rows[1:] if desc_idx is not None else rows
        for row in data_rows:
            if not row or desc_idx is None or qty_idx is None:
                joined = " ".join(str(c or "") for c in row).strip()
                if not joined:
                    continue
                mapped = _map_alias(joined)
                qty = _parse_number(row[-1] if row else None)
                if mapped and qty is not None:
                    key = mapped[0].lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(
                        _item(
                            description=mapped[0],
                            category=mapped[1],
                            unit=(
                                row[unit_idx]
                                if unit_idx is not None and unit_idx < len(row) and row[unit_idx]
                                else mapped[2]
                            ),
                            quantity=qty,
                            document_id=document_id,
                            page=page,
                            source=source,
                            method=method,
                            source_reference=source_reference,
                            confidence=92,
                        )
                    )
                continue

            if desc_idx >= len(row) or qty_idx >= len(row):
                continue
            desc = str(row[desc_idx] or "").strip()
            if not desc or _SKIP_TABLE_DESC_RE.match(desc):
                continue
            row_joined = " ".join(str(c or "") for c in row)
            if description_is_incidental_child(desc) or (
                not schedule_copy and description_is_incidental_child(row_joined)
            ):
                continue
            qty = _parse_number(row[qty_idx])
            if qty is None:
                continue
            mapped = _map_alias(desc)
            description = mapped[0] if mapped else desc
            category = mapped[1] if mapped else "General"
            unit = (
                str(row[unit_idx]).strip()
                if unit_idx is not None and unit_idx < len(row) and str(row[unit_idx] or "").strip()
                else (mapped[2] if mapped else "unit")
            )
            code = (
                str(row[code_idx]).strip()
                if code_idx is not None and code_idx < len(row) and row[code_idx]
                else None
            )
            key = description.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(
                _item(
                    description=description,
                    category=category,
                    unit=unit,
                    quantity=qty,
                    item_code=code,
                    document_id=document_id,
                    page=page,
                    source=source,
                    method=method,
                    source_reference=source_reference,
                    confidence=94,
                )
            )
    return items


def _content_has_eoq_schedule(content: ExtractedContent | None) -> bool:
    if not content:
        return False
    blob = (content.text or "").lower()
    if "estimate of quantities" in blob:
        return True
    if re.search(r"\bbid items\b", blob) and any(
        k in blob
        for k in (
            "est. qty",
            "est qty",
            "std bid",
            "item description",
            "approx. quantity",
            "approx quantity",
            "bid item",
        )
    ):
        return True
    if any(
        k in blob
        for k in (
            "item description",
            "approx. quantity",
            "approx quantity",
            "std bid",
            "standard bid",
            "for bidding purposes only",
            "est. qty",
            "est qty",
        )
    ) and any(k in blob for k in ("quantity", "unit", "item")):
        return True
    return any(_is_bid_schedule_table(t) for t in (content.tables or []) if t.get("rows"))


def _should_drop_inferred_extra(
    item: dict[str, Any],
    *,
    schedule_present: bool,
) -> bool:
    """When a Bid Items / EOQ table exists, keep schedule rows and drop F-sheet invents."""
    if not schedule_present:
        return False
    if _looks_like_schedule_item(item):
        return False
    desc = str(item.get("description") or "").strip()
    if not desc:
        return True
    if _is_plan_invent_extra(item) or _is_plan_derived(item):
        return True
    if _GENERIC_INFERRED_DESC.search(desc) and _method_rank(item) <= 1:
        return True
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

    schedule_present = _content_has_eoq_schedule(content) or any(
        _looks_like_schedule_item(i) for i in items
    )

    cleaned: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        if _should_drop_inferred_extra(item, schedule_present=schedule_present):
            dropped += 1
            continue
        cleaned.append(item)

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
    if dropped:
        note = f"Filtered {dropped} low-evidence inferred item(s) (schedule-first policy)."
        out["notes"] = ((out.get("notes") or "") + " | " + note).strip(" |")
        summary = out.get("summary") or ""
        out["summary"] = f"{summary} {note}".strip()
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
    items: list[dict[str, Any]] = []
    for source in (text_result.get("items") or [], vision_result.get("items") or []):
        for item in source:
            if not item.get("description"):
                continue
            normalized = dict(item)
            normalized["unit"] = _normalize_contract_unit(normalized.get("unit"))
            if _should_drop_incidental_item(normalized):
                continue
            items.append(normalized)

    facts = list(text_result.get("facts") or []) + list(vision_result.get("facts") or [])
    summary = (
        f"{vision_result.get('summary') or ''} "
        f"Also merged text/table takeoff ({len(text_result.get('items') or [])} text items, "
        f"{len(vision_result.get('items') or [])} drawing items → {len(items)} unique)."
    ).strip()
    return {
        "engine": "openai+vision",
        "summary": summary,
        "facts": facts,
        "items": items,
        "needs_review": bool(text_result.get("needs_review") or vision_result.get("needs_review"))
        or len(items) == 0,
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
