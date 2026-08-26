"""General civil estimator — EOQ from any design (road, utility, dam, reservoir, building).

Used when drawings/CAD exist. Formulas follow common QS practice:

* Trench excavation CY = trench_width × trench_depth × length / 27
* Bedding CY = trench_width × bedding_thickness × length / 27
* Pavement layer CY = width × thickness × length / 27  (HMA also as tons @ 145 pcf)
* Areas from hatch/closed polyline layers
* Counts from named blocks (doors, windows, lights, trees, …)

Assumptions are written into calculation_method so an engineer can review them.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

# --- Project type -----------------------------------------------------------

_TYPE_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("dam", ("dam", "spillway", "gallery", "abutment", "crest", "cofferdam", "stilling basin")),
    ("reservoir", ("reservoir", "impoundment", "pond lining", "tank farm", "clearwell", "storage tank")),
    ("building", ("building", "house", "residence", "dwelling", "apartment", "floor plan", "architectural")),
    ("road", ("roadway", "highway", "pavement", "typical section", "carriageway", "asphalt", "hma")),
    ("utility", ("watermain", "water main", "sanitary", "storm sewer", "force main")),
]


def detect_project_types(*blobs: Any) -> list[str]:
    text = " ".join(str(b or "") for b in blobs).lower()
    found: list[str] = []
    for kind, keys in _TYPE_HINTS:
        if any(k in text for k in keys):
            found.append(kind)
    return found or ["civil"]


# --- Typical-section / text takeoff ----------------------------------------

_THICK_IN = re.compile(
    r"(?P<name>GSB|WMM|DBM|BC|HMA|PCC|sub[- ]?base|base\s*course|binder|surface\s*course|"
    r"aggregate\s*base|asphalt|concrete\s*pavement|sidewalk|curb)"
    r"[^\n]{0,40}?(?P<th>\d+(?:\.\d+)?)\s*(?P<u>mm|cm|in(?:ch(?:es)?)?|\"|ft|m)\b",
    re.I,
)
_WIDTH = re.compile(
    r"(?:road|carriageway|pavement|roadway|crest|dam)\s*width[^\d]{0,16}(?P<w>\d+(?:\.\d+)?)\s*(?P<u>m|ft|')?",
    re.I,
)
_LENGTH = re.compile(
    r"(?:length|alignment\s*length|road\s*length|crest\s*length)[^\d]{0,16}"
    r"(?P<l>\d{2,6}(?:\.\d+)?)\s*(?P<u>m|ft|km|mi)?",
    re.I,
)
_STA_RANGE = re.compile(
    r"(?P<a>\d{1,4}\+\d{2}(?:\.\d+)?)\s*(?:to|[-–—])\s*(?P<b>\d{1,4}\+\d{2}(?:\.\d+)?)",
    re.I,
)

_BUILDING = [
    ("Brickwork", "Building", "CY", r"\bbrick(?:work)?\b.*?(\d{1,6}(?:\.\d+)?)\s*(m3|m³|cy|cu\.?\s*yd)"),
    ("RCC Concrete", "Building", "CY", r"\b(?:rcc|reinforced\s*concrete)\b.*?(\d{1,6}(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Foundation Concrete", "Building", "CY", r"\bfoundation(?:s)?\b.*?(\d{1,6}(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Doors", "Building", "EA", r"\bdoors?\b.*?(\d{1,4})\s*(nos?|ea|each)"),
    ("Windows", "Building", "EA", r"\bwindows?\b.*?(\d{1,4})\s*(nos?|ea|each)"),
    ("Plastering", "Building", "SF", r"\bplaster(?:ing)?\b.*?(\d{1,7}(?:\.\d+)?)\s*(m2|m²|sf|sft)"),
    ("Flooring", "Building", "SF", r"\bfloor(?:ing)?\b.*?(\d{1,7}(?:\.\d+)?)\s*(m2|m²|sf|sft)"),
    ("Roofing", "Building", "SF", r"\broof(?:ing)?\b.*?(\d{1,7}(?:\.\d+)?)\s*(m2|m²|sf|sft)"),
    ("Formwork", "Building", "SF", r"\bformwork\b.*?(\d{1,7}(?:\.\d+)?)\s*(m2|m²|sf|sft)"),
    ("Painting", "Building", "SF", r"\bpaint(?:ing)?\b.*?(\d{1,7}(?:\.\d+)?)\s*(m2|m²|sf|sft)"),
]
_DAM = [
    ("Dam Embankment Fill", "Dams & Reservoirs", "CY", r"\b(?:dam\s+)?embankment\b.*?(\d{1,8}(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Dam Excavation", "Dams & Reservoirs", "CY", r"\b(?:dam|foundation)\s*excavation\b.*?(\d{1,8}(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Spillway Concrete", "Dams & Reservoirs", "CY", r"\bspillway\b.*?(\d{1,7}(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Riprap", "Dams & Reservoirs", "CY", r"\briprap\b.*?(\d{1,7}(?:\.\d+)?)\s*(m3|m³|cy|ton)"),
    ("Reservoir Lining", "Dams & Reservoirs", "SF", r"\b(?:reservoir|pond|tank)\s*lin(?:ing|er)\b.*?(\d{1,8}(?:\.\d+)?)\s*(m2|m²|sf)"),
    ("Cutoff Trench", "Dams & Reservoirs", "CY", r"\bcutoff(?:\s+trench)?\b.*?(\d{1,8}(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Filter / Drain Material", "Dams & Reservoirs", "CY", r"\b(?:filter\s*(?:material|zone)|chimney\s*drain)\b.*?(\d{1,8}(?:\.\d+)?)\s*(m3|m³|cy)"),
    ("Reservoir Capacity", "Dams & Reservoirs", "MGAL", r"\bcapacit(?:y|ies)\b.*?(\d{1,6}(?:\.\d+)?)\s*(mgal|million\s*gal|acre[- ]?ft|ml)"),
]
_SHOULDER = re.compile(
    r"shoulder[^\d]{0,20}(?P<w>\d+(?:\.\d+)?)\s*(?P<u>m|ft|'|in)?",
    re.I,
)


def _to_feet(val: float, unit: str | None) -> float:
    u = (unit or "ft").lower().replace("'", "ft")
    if u in {"mm"}:
        return val / 304.8
    if u in {"cm"}:
        return val / 30.48
    if u in {"m", "meter", "metre"}:
        return val * 3.280839895
    if u in {"km"}:
        return val * 3280.839895
    if u in {"mi", "mile"}:
        return val * 5280.0
    if u in {"in", "inch", "inches", '"'}:
        return val / 12.0
    return val


def _sta_feet(sta: str) -> float | None:
    m = re.match(r"(\d+)\+(\d+(?:\.\d+)?)", sta.strip())
    if not m:
        return None
    return float(m.group(1)) * 100.0 + float(m.group(2))


def items_from_design_text(text: str, *, filename: str = "plan") -> list[dict[str, Any]]:
    """Quantity lines from typical sections, BOQ-like sentences, and civil callouts."""
    if not (text or "").strip():
        return []
    items: list[dict[str, Any]] = []
    width_ft = None
    wm = _WIDTH.search(text)
    if wm:
        width_ft = _to_feet(float(wm.group("w")), wm.group("u"))

    length_ft = None
    lm = _LENGTH.search(text)
    if lm:
        length_ft = _to_feet(float(lm.group("l")), lm.group("u"))
    sm = _STA_RANGE.search(text)
    if sm and length_ft is None:
        a, b = _sta_feet(sm.group("a")), _sta_feet(sm.group("b"))
        if a is not None and b is not None:
            length_ft = abs(b - a)

    # Pavement layers from typical section
    if width_ft and length_ft and width_ft > 2 and length_ft > 20:
        seen_layer: set[str] = set()
        for m in _THICK_IN.finditer(text):
            name = m.group("name").strip()
            key = name.lower()
            if key in seen_layer:
                continue
            seen_layer.add(key)
            th_ft = _to_feet(float(m.group("th")), m.group("u"))
            if th_ft <= 0 or th_ft > 4:
                continue
            cy = width_ft * th_ft * length_ft / 27.0
            label = _layer_label(name)
            items.append(
                _qty(
                    description=label,
                    category="Surfacing",
                    unit="CY",
                    quantity=round(cy, 2),
                    method=(
                        f"Typical section: {width_ft:.1f}' wide × {th_ft * 12:.1f}\" thick × "
                        f"{length_ft:.0f}' long / 27 (from '{filename}')"
                    ),
                    confidence=82.0,
                )
            )
            if any(k in key for k in ("hma", "asphalt", "dbm", "bc", "bituminous", "binder", "surface")):
                tons = cy * 145.0 / 2000.0  # ~145 pcf HMA
                items.append(
                    _qty(
                        description=f"{label} (HMA tons)",
                        category="Surfacing",
                        unit="TON",
                        quantity=round(tons, 2),
                        method=f"HMA tons from CY × 145 pcf / 2000 ({filename})",
                        confidence=78.0,
                    )
                )
        sy = width_ft * length_ft / 9.0
        low = text.lower()
        if "prime" in low:
            items.append(
                _qty(
                    "Prime Coat",
                    "Surfacing",
                    "SY",
                    round(sy, 2),
                    f"Typical section area {width_ft:.1f}' × {length_ft:.0f}' / 9 ({filename})",
                    74.0,
                )
            )
        if "tack" in low:
            items.append(
                _qty(
                    "Tack Coat",
                    "Surfacing",
                    "SY",
                    round(sy, 2),
                    f"Typical section area {width_ft:.1f}' × {length_ft:.0f}' / 9 ({filename})",
                    74.0,
                )
            )
        sm = _SHOULDER.search(text)
        if sm:
            sh_ft = _to_feet(float(sm.group("w")), sm.group("u"))
            if 1.0 < sh_ft < 20.0:
                items.append(
                    _qty(
                        "Shoulder Area",
                        "Surfacing",
                        "SF",
                        round(sh_ft * length_ft * 2.0, 2),
                        f"2 shoulders × {sh_ft:.1f}' × {length_ft:.0f}' ({filename})",
                        72.0,
                    )
                )

    combined = _BUILDING + _DAM
    for desc, cat, unit, pat in combined:
        m = re.search(pat, text, re.I | re.S)
        if not m:
            continue
        try:
            qty = float(str(m.group(1)).replace(",", ""))
        except (TypeError, ValueError):
            continue
        raw_u = (m.group(2) if m.lastindex and m.lastindex >= 2 else unit) or unit
        items.append(
            _qty(
                description=desc,
                category=cat,
                unit=_norm_unit(raw_u, unit),
                quantity=qty,
                method=f"Design text quantity on '{filename}'",
                confidence=80.0,
            )
        )
    return items


def _layer_label(name: str) -> str:
    n = name.lower()
    mapping = {
        "gsb": "Granular Sub-Base (GSB)",
        "wmm": "Wet Mix Macadam (WMM)",
        "dbm": "Dense Bituminous Macadam (DBM)",
        "bc": "Bituminous Concrete (BC)",
        "hma": "Hot Mix Asphalt",
        "pcc": "PCC Pavement",
        "subbase": "Aggregate Subbase",
        "sub-base": "Aggregate Subbase",
        "base course": "Aggregate Base Course",
        "aggregate base": "Aggregate Base Course",
        "binder": "Asphalt Binder Course",
        "surface course": "Asphalt Surface Course",
        "asphalt": "Asphalt Pavement",
        "concrete pavement": "Concrete Pavement",
        "sidewalk": "Concrete Sidewalk",
        "curb": "Concrete Curb",
    }
    for k, v in mapping.items():
        if k in n:
            return v
    return name.title()


def _norm_unit(raw: str, fallback: str) -> str:
    r = (raw or fallback or "unit").lower()
    if r in {"m3", "m³", "cy", "cu.yd", "cu yd"}:
        return "CY"
    if r in {"m2", "m²", "sf", "sft"}:
        return "SF"
    if r in {"ton", "tons", "t"}:
        return "TON"
    if r in {"nos", "no", "ea", "each"}:
        return "EA"
    if r in {"mgal", "million gal"}:
        return "MGAL"
    if r in {"acre-ft", "acre ft"}:
        return "AC-FT"
    return fallback.upper()


# --- Trench from pipes (CAD) ------------------------------------------------

def trench_items_from_pipes(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    """Standard trench pay items from pipe length + diameter.

    Width = max(OD + 2.0 ft, 2.5 ft). Cover defaults to 4.0 ft if unknown.
    Bedding = 6 inches. Pipe displacement subtracted from backfill.
    """
    groups: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"lf": 0.0, "od": 0.0, "n": 0})
    pipes = list(extraction.get("pipes") or [])
    # Prefer Civil pipe objects so centerline polylines do not double trench CY.
    pipe_rows = pipes if pipes else list(extraction.get("polylines") or [])
    for pipe in pipe_rows:
        layer = str(pipe.get("layer") or "")
        name = str(pipe.get("name") or "")
        blob = f"{name} {layer} {pipe.get('network') or ''} {pipe.get('description') or ''}".lower()
        if not any(k in blob for k in ("pipe", "water", "sewer", "storm", "san", "main", "casing")):
            continue
        try:
            length = float(pipe.get("length") or 0)
        except (TypeError, ValueError):
            length = 0.0
        if length < 1:
            continue
        od_ft = _pipe_od_ft(pipe)
        net = "utility"
        if "water" in blob:
            net = "water"
        elif "sanitary" in blob or ("sewer" in blob and "storm" not in blob):
            net = "sanitary"
        elif "storm" in blob:
            net = "storm"
        elif "casing" in blob:
            net = "casing"
        key = (net, f"{od_ft:.2f}")
        groups[key]["lf"] += length
        groups[key]["od"] += od_ft
        groups[key]["n"] += 1

    items: list[dict[str, Any]] = []
    cover_ft = 4.0
    bedding_ft = 0.5
    for (net, _odk), g in groups.items():
        lf = g["lf"]
        od = g["od"] / max(g["n"], 1)
        width = max(od + 2.0, 2.5)
        depth = cover_ft + od + bedding_ft
        excav_cy = width * depth * lf / 27.0
        bed_cy = width * bedding_ft * lf / 27.0
        pipe_cy = math.pi * (od / 2.0) ** 2 * lf / 27.0
        backfill_cy = max(0.0, excav_cy - bed_cy - pipe_cy)
        label = {
            "water": "Watermain",
            "sanitary": "Sanitary Sewer",
            "storm": "Storm Sewer",
            "casing": "Casing",
        }.get(net, "Utility")
        method = (
            f"Trench from {label} pipes: width {width:.1f}' (= OD+2' min 2.5'), "
            f"cover assumed {cover_ft:.0f}', bedding {bedding_ft * 12:.0f}\", L={lf:.0f} LF"
        )
        items.append(_qty(f"{label} Trench Excavation", "Grading", "CY", round(excav_cy, 2), method, 76.0))
        items.append(_qty(f"{label} Pipe Bedding", "Grading", "CY", round(bed_cy, 2), method, 76.0))
        items.append(_qty(f"{label} Trench Backfill", "Grading", "CY", round(backfill_cy, 2), method, 76.0))
    return items


def _pipe_od_ft(pipe: dict[str, Any]) -> float:
    for key in ("diameter", "inner_diameter", "outer_diameter", "size"):
        try:
            d = float(pipe.get(key) or 0)
        except (TypeError, ValueError):
            d = 0.0
        if d <= 0:
            continue
        if d > 20:  # already inches-ish large; treat as inches if < 80
            if d < 80:
                return d / 12.0
            return d  # feet
        if d < 8:  # feet (Civil often stores 0.67 ft = 8")
            return d
        return d / 12.0  # inches
    # parse from name
    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*(?:\"|in)", str(pipe.get("name") or pipe.get("layer") or ""), re.I)
    if m:
        return float(m.group(1)) / 12.0
    return 1.0  # 12" default


# --- Extra CAD layers (buildings, dams, roads) ------------------------------

_LAYER_LENGTH = (
    (("curb", "kerb", "gutter"), "Concrete Curb and Gutter", "Curb, Gutter & Sidewalk", "LF"),
    (("sidewalk", "walkway", "footpath"), "Concrete Sidewalk", "Curb, Gutter & Sidewalk", "LF"),
    (("guardrail", "barrier"), "Guardrail", "Miscellaneous", "LF"),
    (("fence",), "Fence", "Miscellaneous", "LF"),
    (("a-wall", "partition", "wall-"), "Wall", "Building", "LF"),
    (("crest",), "Dam Crest", "Dams & Reservoirs", "LF"),
    (("spillway",), "Spillway", "Dams & Reservoirs", "LF"),
    (("ditch", "swale"), "Roadside Ditch", "Storm Sewer", "LF"),
)
_BLOCK_COUNTS = (
    (("door",), "Doors", "Building"),
    (("window", "glaz"), "Windows", "Building"),
    (("column", "pillar"), "Columns", "Building"),
    (("pile",), "Piles", "Structures"),
    (("luminaire", "lightpole", "light pole", "streetlight", "street light"), "Light Poles", "Lighting & Electrical"),
    (("tree", "shrub"), "Trees / Shrubs", "Landscaping & Irrigation"),
    (("bollard",), "Bollards", "Miscellaneous"),
    (("catch", "inlet"), "Storm Drainage Inlet", "Drainage"),
)


def items_from_civil_layers(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    scale = 1.0
    items: list[dict[str, Any]] = []
    length_acc: dict[str, float] = defaultdict(float)

    for ent in list(extraction.get("lines") or []) + list(extraction.get("polylines") or []):
        layer = str(ent.get("layer") or "")
        low = layer.lower()
        try:
            length = float(ent.get("length") or 0)
        except (TypeError, ValueError):
            length = 0.0
        for keys, desc, cat, unit in _LAYER_LENGTH:
            if any(k in low for k in keys) and length > 0.5:
                length_acc[f"{desc}|{cat}|{unit}"] += length * scale
                break

    counts: dict[str, int] = defaultdict(int)
    for block in extraction.get("blocks") or []:
        blob = f"{block.get('name') or ''} {block.get('layer') or ''} {block.get('type') or ''}".lower()
        for keys, desc, cat in _BLOCK_COUNTS:
            if any(k in blob for k in keys):
                counts[f"{desc}|{cat}|EA"] += 1
                break

    for key, qty in length_acc.items():
        desc, cat, unit = key.split("|")
        items.append(_qty(desc, cat, unit, round(qty, 2), f"Sum of CAD lengths on matching {desc.lower()} layers", 84.0))
    for key, qty in counts.items():
        desc, cat, unit = key.split("|")
        items.append(_qty(desc, cat, unit, float(qty), f"Count of CAD blocks classified as {desc}", 88.0))
    return items


def _qty(description: str, category: str, unit: str, quantity: float, method: str, confidence: float) -> dict[str, Any]:
    return {
        "description": description,
        "category": category,
        "unit": unit.upper(),
        "quantity": float(quantity),
        "layer": "",
        "entity_type": "ESTIMATOR",
        "calculation_method": method,
        "confidence": confidence,
    }


def merge_estimator_items(base: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append extras unless the same description+unit already exists (don't double-count)."""
    seen = {(str(i.get("description") or "").strip().lower(), str(i.get("unit") or "").upper()) for i in base}
    out = list(base)
    for item in extra:
        key = (str(item.get("description") or "").strip().lower(), str(item.get("unit") or "").upper())
        if key in seen or float(item.get("quantity") or 0) <= 0:
            continue
        seen.add(key)
        out.append(item)
    return out


def expand_cad_takeoff(extraction: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    extra = trench_items_from_pipes(extraction)
    extra.extend(items_from_civil_layers(extraction))
    texts = " ".join(str(t.get("text") or "") for t in (extraction.get("texts") or [])[:400])
    extra.extend(items_from_design_text(texts, filename="CAD text"))
    return merge_estimator_items(items, extra)
