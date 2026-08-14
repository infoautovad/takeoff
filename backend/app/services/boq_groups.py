"""Municipal Estimate of Quantities section grouping.

Groups BOQ lines the way agency bid schedules / EOQ sheets do
(Removals, Grading, Watermain, Sanitary Sewer, …), so UI and exports
show bold section headers with items underneath.
"""

from __future__ import annotations

from typing import Any, Iterable, TypeVar

T = TypeVar("T")

# Display order matches typical municipal EOQ / bid schedule flow.
BOQ_GROUP_ORDER: list[str] = [
    "General / Traffic Control",
    "Removals",
    "Clearing & Grubbing",
    "Grading",
    "Erosion Control / Restoration",
    "Surfacing",
    "Curb, Gutter & Sidewalk",
    "Storm Sewer",
    "Watermain",
    "Sanitary Sewer",
    "Water & Sewer Services",
    "Traffic Signals & Signing",
    "Lighting & Electrical",
    "Gas & Dry Utilities",
    "Structures",
    "Landscaping & Irrigation",
    "Miscellaneous",
    "Unmapped Takeoff",
]

# keyword (lower) → group. First match wins — order matters (specific before generic).
_GROUP_RULES: list[tuple[list[str], str]] = [
    # Removals / demolition first
    (
        [
            "remove ",
            "removal",
            "demolition",
            "sawcut",
            "saw cut",
            "abandon",
            "salvage and remove",
            "mill and remove",
        ],
        "Removals",
    ),
    # General / traffic
    (
        [
            "mobilization",
            "demobilization",
            "traffic control",
            "temporary traffic",
            "flagging",
            "construction entrance",
            "field office",
            "bonds and insurance",
            "survey",
            "staking",
            "audiovisual",
            "video record",
            "permit",
            "allowance",
            "contingency",
        ],
        "General / Traffic Control",
    ),
    (
        ["clearing", "grubbing", "tree removal", "stump", "brush"],
        "Clearing & Grubbing",
    ),
    # Grading / earthwork
    (
        [
            "unclassified excavation",
            "excavation",
            "earthwork",
            "embankment",
            "borrow",
            "cut ",
            "fill ",
            "grading",
            "subgrade",
            "topsoil",
            "proof roll",
            "scarify",
            "compaction",
            "trench stabilization",
            "select backfill",
            "imported fill",
            "rock excavation",
        ],
        "Grading",
    ),
    # Erosion / restoration
    (
        [
            "erosion",
            "silt fence",
            "inlet protection",
            "sediment",
            "seeding",
            "sodding",
            "mulch",
            "fertiliz",
            "hydroseed",
            "weed control",
            "water for vegetation",
            "turf establishment",
            "soil blanket",
            "wattle",
            "swppp",
            "temporary seeding",
        ],
        "Erosion Control / Restoration",
    ),
    # Surfacing / pavement
    (
        [
            "aggregate base",
            "crushed aggregate",
            "asphalt",
            "hma",
            "hot mix",
            "bituminous",
            "pavement",
            "paving",
            "gsb",
            "wmm",
            "dbm",
            "prime coat",
            "tack coat",
            "milling",
            "overlay",
            "chip seal",
            "surface course",
            "binder course",
            "pcc pavement",
            "concrete pavement",
        ],
        "Surfacing",
    ),
    (
        [
            "curb and gutter",
            "curb",
            "gutter",
            "sidewalk",
            "driveway",
            "crosswalk",
            "ramp",
            "ada",
            "detectable warning",
            "kerb",
        ],
        "Curb, Gutter & Sidewalk",
    ),
    # Watermain (before generic pipe/water)
    (
        [
            "watermain",
            "water main",
            "waterline",
            "water line",
            "pvc watermain",
            "dip wm",
            "c900",
            "fire hydrant",
            "hydrant",
            "gate valve",
            "butterfly valve",
            "water valve",
            "blowoff",
            "blow-off",
            "air release",
            "water meter",
            "thrust block",
            "trenchless",
            "directional drill",
            "casing pipe",
            "potable",
        ],
        "Watermain",
    ),
    # Sanitary
    (
        [
            "sanitary sewer",
            "sanitary pipe",
            "sanitary manhole",
            "ssmh",
            "force main",
            "forcemain",
            "sewer service",
            "sanitary service",
            "cleanout",
            "lift station",
        ],
        "Sanitary Sewer",
    ),
    # Storm
    (
        [
            "storm sewer",
            "storm drain",
            "storm pipe",
            "catch basin",
            "inlet",
            "culvert",
            "headwall",
            "endwall",
            "junction box",
            "retention",
            "detention",
            "rcp ",
            "storm manhole",
            "drainage structure",
            "underdrain",
            "french drain",
        ],
        "Storm Sewer",
    ),
    (
        [
            "water service",
            "service connection",
            "corporation stop",
            "curb stop",
            "meter pit",
            "tap ",
            "house connection",
            "lateral",
        ],
        "Water & Sewer Services",
    ),
    (
        [
            "traffic signal",
            "signal pole",
            "pavement marking",
            "striping",
            "thermoplastic",
            "road sign",
            "traffic sign",
            "signage",
            "delineator",
            "object marker",
        ],
        "Traffic Signals & Signing",
    ),
    (
        [
            "street light",
            "lighting",
            "luminaire",
            "electrical conduit",
            "pull box",
            "transformer",
            "electric",
        ],
        "Lighting & Electrical",
    ),
    (
        ["gas main", "gas service", "telecom", "fiber", "telephone", "cable tv", "joint trench"],
        "Gas & Dry Utilities",
    ),
    (
        [
            "bridge",
            "retaining wall",
            "reinforced concrete",
            "structural concrete",
            "rebar",
            "formwork",
            "pile",
            "footing",
            "abutment",
            "box culvert",
        ],
        "Structures",
    ),
    (
        [
            "landscape",
            "irrigation",
            "planting",
            "tree ",
            "shrub",
            "groundcover",
            "sod ",
        ],
        "Landscaping & Irrigation",
    ),
    # Broad utility fallbacks
    (["sewer"], "Sanitary Sewer"),
    (["drain", "drainage"], "Storm Sewer"),
    (["water", "valve", "pipe", "fitting", "bend", "tee", "reducer"], "Watermain"),
    (["fence", "guardrail", "barrier"], "Miscellaneous"),
]

_CATEGORY_ALIASES: dict[str, str] = {
    "utilities": "Watermain",
    "utility": "Watermain",
    "drainage": "Storm Sewer",
    "earthwork": "Grading",
    "pavement": "Surfacing",
    "roadside": "Curb, Gutter & Sidewalk",
    "landscaping": "Landscaping & Irrigation",
    "traffic": "Traffic Signals & Signing",
    "markings": "Traffic Signals & Signing",
    "structures": "Structures",
    "demolition": "Removals",
    "site clearing": "Clearing & Grubbing",
    "geometry": "Miscellaneous",
    "general": "General / Traffic Control",
    "bid schedule": "Miscellaneous",
    "unmapped takeoff": "Unmapped Takeoff",
}


def resolve_boq_group(
    *,
    description: str | None = None,
    category: str | None = None,
) -> str:
    """Return canonical EOQ section name for a BOQ line."""
    cat = (category or "").strip()
    if cat:
        alias = _CATEGORY_ALIASES.get(cat.lower())
        if alias:
            # Still refine Utilities/Drainage using description when possible
            if alias in {"Watermain", "Storm Sewer", "Sanitary Sewer", "Miscellaneous"}:
                refined = _match_description(description or "")
                if refined:
                    return refined
            return alias
        if cat in BOQ_GROUP_ORDER:
            return cat

    matched = _match_description(f"{description or ''} {category or ''}")
    if matched:
        return matched
    if cat and cat.lower() == "unmapped takeoff":
        return "Unmapped Takeoff"
    return "Miscellaneous"


def _match_description(text: str) -> str | None:
    low = text.lower()
    if not low.strip():
        return None
    for keys, group in _GROUP_RULES:
        if any(k in low for k in keys):
            return group
    return None


def group_sort_key(group: str) -> tuple[int, str]:
    try:
        return (BOQ_GROUP_ORDER.index(group), group)
    except ValueError:
        return (len(BOQ_GROUP_ORDER), group)


def group_items(items: Iterable[T], *, get_description, get_category) -> list[tuple[str, list[T]]]:
    """Partition items into ordered (group_name, items) sections. Empty groups omitted."""
    buckets: dict[str, list[T]] = {}
    for item in items:
        group = resolve_boq_group(
            description=get_description(item),
            category=get_category(item),
        )
        buckets.setdefault(group, []).append(item)
    ordered: list[tuple[str, list[T]]] = []
    for name in BOQ_GROUP_ORDER:
        if name in buckets and buckets[name]:
            ordered.append((name, buckets.pop(name)))
    for name in sorted(buckets.keys()):
        if buckets[name]:
            ordered.append((name, buckets[name]))
    return ordered


def assign_group_category(item: dict[str, Any]) -> dict[str, Any]:
    """Set item['category'] to the canonical EOQ group (copy)."""
    out = dict(item)
    # Preserve unmapped marker as group
    if str(out.get("bid_match_method") or "") == "unmapped" or str(out.get("category") or "").lower() == "unmapped takeoff":
        out["category"] = "Unmapped Takeoff"
        out["boq_group"] = "Unmapped Takeoff"
        return out
    group = resolve_boq_group(description=str(out.get("description") or ""), category=out.get("category"))
    out["category"] = group
    out["boq_group"] = group
    return out
