"""USA CSI MasterFormat mapping for civil / roadway BOQ items.

Maps common civil descriptions to Division 31/32/33 (and related) CSI codes.
Also normalizes units used in USA highway takeoffs.
"""

from __future__ import annotations

import re
from typing import Any


# keywords (lower) → (csi_code, default_category, preferred_unit_hint or None)
CSI_RULES: list[tuple[list[str], str, str, str | None]] = [
    # Division 02 – Existing Conditions
    (["demolition", "remove pavement", "sawcut"], "02 41 13", "Demolition", None),
    (["clearing", "grubbing"], "31 11 00", "Site Clearing", "acre"),
    # Division 31 – Earthwork
    (["earthwork cut", "excavation", "cut to fill", "roadway excavation"], "31 23 16", "Earthwork", "m3"),
    (["earthwork fill", "embankment", "borrow", "fill"], "31 23 23", "Earthwork", "m3"),
    (["subgrade", "proof roll"], "31 22 13", "Earthwork", "m2"),
    (["geotextile", "geogrid", "stabilization fabric"], "31 05 19", "Earthwork", "m2"),
    # Division 32 – Exterior Improvements / Pavement
    (["gsb", "granular sub base", "granular subbase", "subbase"], "32 11 23", "Pavement", "m3"),
    (["wmm", "wet mix macadam", "aggregate base", "crushed aggregate base", "cab"], "32 11 23", "Pavement", "m3"),
    (["dbm", "dense bituminous", "bituminous base"], "32 12 16", "Pavement", "m3"),
    (["bituminous concrete", "asphalt concrete", "hma", "hot mix", "ac paving", "bc "], "32 12 16", "Pavement", "m3"),
    (["asphalt", "paving", "pavement"], "32 12 16", "Pavement", "m3"),
    (["prime coat", "tack coat"], "32 12 13", "Pavement", "m2"),
    (["concrete pavement", "pcc pavement", "rigid pavement"], "32 13 13", "Pavement", "m3"),
    (["kerb", "curb", "curbing", "kerbing"], "32 16 13", "Roadside", "m"),
    (["sidewalk", "footpath", "walkway", "pedestrian"], "32 16 23", "Roadside", "m2"),
    (["driveway"], "32 16 13", "Roadside", "m2"),
    (["guardrail", "barrier", "guiderail"], "32 17 23", "Roadside", "m"),
    (["fence", "fencing"], "32 31 13", "Roadside", "m"),
    (["road marking", "pavement marking", "striping", "thermoplastic"], "32 17 23", "Markings", "m"),
    (["traffic sign", "road sign", "signage"], "10 14 53", "Traffic", "nos"),
    (["signal", "traffic signal"], "34 41 13", "Traffic", "nos"),
    (["landscaping", "sodding", "seeding", "turf"], "32 92 00", "Landscaping", "m2"),
    # Division 33 – Utilities / Drainage
    (["culvert", "box culvert"], "33 42 13", "Drainage", "nos"),
    (["storm drain", "storm sewer", "drainage pipe", "drain pipe"], "33 41 00", "Drainage", "m"),
    (["drain", "drainage"], "33 40 00", "Drainage", "m"),
    (["manhole", "catch basin", "inlet", "junction box"], "33 05 61", "Drainage", "nos"),
    (["pipe", "sewer"], "33 31 00", "Utilities", "m"),
    (["water main", "waterline"], "33 11 00", "Utilities", "m"),
    # Structures / Concrete
    (["reinforced concrete", "rcc", "structural concrete"], "03 30 00", "Structures", "m3"),
    (["concrete"], "03 30 00", "Structures", "m3"),
    (["rebar", "reinforcement", "steel reinforcement"], "03 20 00", "Structures", "kg"),
    (["formwork"], "03 11 00", "Structures", "m2"),
    # Geometry / reference (still coded for BOQ completeness)
    (["road width", "carriageway", "alignment", "centerline"], "01 71 23", "Geometry", "m"),
]

CSI_CODE_RE = re.compile(r"\b(\d{2})\s*[-\s]?\s*(\d{2})\s*[-\s]?\s*(\d{2})(?:\.\d+)?\b")

UNIT_ALIASES = {
    "m3": "m3",
    "m³": "m3",
    "cu.m": "m3",
    "cu m": "m3",
    "cum": "m3",
    "cubic meter": "m3",
    "cubic meters": "m3",
    "cy": "cy",
    "cu.yd": "cy",
    "cubic yard": "cy",
    "cubic yards": "cy",
    "m2": "m2",
    "m²": "m2",
    "sq.m": "m2",
    "sq m": "m2",
    "sm": "m2",
    "square meter": "m2",
    "square meters": "m2",
    "sy": "sy",
    "sq.yd": "sy",
    "sqyd": "sy",
    "sq yd": "sy",
    "sq.yd.": "sy",
    "square yard": "sy",
    "square yards": "sy",
    "cy": "cy",
    "cu.yd": "cy",
    "cuyd": "cy",
    "cu yd": "cy",
    "cu.yd.": "cy",
    "cubic yard": "cy",
    "cubic yards": "cy",
    "sf": "sf",
    "sqft": "sf",
    "sq ft": "sf",
    "sq.ft": "sf",
    "sq.ft.": "sf",
    "square foot": "sf",
    "square feet": "sf",
    "m": "m",
    "lm": "m",
    "lin m": "m",
    "linear m": "m",
    "ft": "lf",
    "lf": "lf",
    "lft": "lf",
    "lin ft": "lf",
    "linear foot": "lf",
    "linear feet": "lf",
    "nos": "nos",
    "no": "nos",
    "no.": "nos",
    "each": "ea",
    "ea": "ea",
    "ls": "ls",
    "lump sum": "ls",
    "t": "t",
    "ton": "t",
    "tons": "t",
    "tonne": "t",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "mgal": "mgal",
    "kg": "kg",
    "acre": "acre",
    "ac": "acre",
}


def normalize_unit(unit: str | None) -> str:
    if not unit:
        return "unit"
    raw = str(unit).strip().lower().replace("³", "3").replace("²", "2")
    raw = re.sub(r"\s+", " ", raw)
    if raw in UNIT_ALIASES:
        return UNIT_ALIASES[raw]
    compact = raw.replace(".", "").replace(" ", "")
    return UNIT_ALIASES.get(compact, str(unit).strip())


def looks_like_csi(code: str | None) -> bool:
    if not code:
        return False
    return bool(CSI_CODE_RE.search(str(code)))


def normalize_csi_code(code: str | None) -> str | None:
    if not code:
        return None
    match = CSI_CODE_RE.search(str(code))
    if not match:
        return str(code).strip() or None
    return f"{match.group(1)} {match.group(2)} {match.group(3)}"


def map_csi(
    *,
    description: str,
    category: str | None = None,
    unit: str | None = None,
    existing_code: str | None = None,
) -> dict[str, Any]:
    """Return CSI code + normalized unit/category for a civil quantity item."""
    unit_n = normalize_unit(unit)
    if looks_like_csi(existing_code):
        return {
            "csi_code": normalize_csi_code(existing_code),
            "item_code": normalize_csi_code(existing_code),
            "category": category,
            "unit": unit_n,
            "csi_match": "provided",
            "csi_confidence": 98.0,
        }

    text = f"{description or ''} {category or ''}".lower()
    for keys, csi, cat, unit_hint in CSI_RULES:
        if any(k in text for k in keys):
            return {
                "csi_code": csi,
                "item_code": existing_code or csi,
                "category": category or cat,
                "unit": unit_n if unit else (unit_hint or unit_n),
                "csi_match": "mapped",
                "csi_confidence": 90.0,
            }

    # Fallback: keep existing client code if any; else unmapped civil misc
    return {
        "csi_code": None,
        "item_code": existing_code,
        "category": category or "General",
        "unit": unit_n,
        "csi_match": "unmapped",
        "csi_confidence": 40.0,
    }


def enrich_quantity_item(item: dict[str, Any]) -> dict[str, Any]:
    """Attach CSI code / normalized unit onto a quantity dict (mutates copy)."""
    out = dict(item)
    mapped = map_csi(
        description=str(out.get("description") or ""),
        category=out.get("category"),
        unit=out.get("unit"),
        existing_code=out.get("csi_code") or out.get("item_code"),
    )
    out["unit"] = mapped["unit"]
    out["category"] = mapped["category"]
    out["csi_code"] = mapped["csi_code"]
    # Prefer CSI as item_code when we mapped one and no prior client code
    if mapped["csi_code"] and (not out.get("item_code") or mapped["csi_match"] == "mapped"):
        if not looks_like_csi(out.get("item_code")):
            out["item_code"] = mapped["csi_code"]
    elif mapped["item_code"]:
        out["item_code"] = mapped["item_code"]
    # Boost confidence slightly when CSI mapped
    try:
        conf = float(out.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if mapped["csi_match"] in {"provided", "mapped"} and conf < 95:
        out["confidence"] = min(95.0, max(conf, mapped["csi_confidence"] - 5))
    out["csi_match"] = mapped["csi_match"]
    return out


def list_csi_catalog() -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for keys, csi, cat, unit in CSI_RULES:
        if csi not in seen:
            seen[csi] = {
                "csi_code": csi,
                "category": cat,
                "unit_hint": unit or "",
                "keywords": ", ".join(keys[:4]),
            }
    return list(seen.values())
