"""Municipal Estimate Of Quantities section grouping.

Groups EOQ lines the way agency bid schedules / EOQ sheets do
(Removals, Grading, Watermain, Sanitary Sewer, …), so UI and exports
show bold section headers with items underneath.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, TypeVar

T = TypeVar("T")

# Display order matches typical municipal EOQ / bid schedule flow.
EOQ_GROUP_ORDER: list[str] = [
    "General",
    "Traffic Control",
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
    "Dams & Reservoirs",
    "Building",
    "Landscaping & Irrigation",
    "Miscellaneous",
    "Special",
]

_ALTERNATE_RE = re.compile(
    r"\b(?:additive|deductive|bid)?\s*"
    r"(?:alternate\b|option\b|alt\.?)\s*"
    r"(?:no\.?|number|#)?\s*[-:]?\s*"
    r"['\"]?([A-Za-z]|[0-9]{1,2})['\"]?\b",
    re.I,
)
_ALTERNATE_PREFIX_RE = re.compile(
    r"^(?:additive|deductive|bid)?\s*"
    r"(?:alternate\b|option\b|alt\.?)\s*"
    r"(?:no\.?|number|#)?\s*[-:]?\s*"
    r"['\"]?([A-Za-z]|[0-9]{1,2})['\"]?\s*"
    r"(?:[-–—:]+|\s+-\s+)\s*",
    re.I,
)

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
    # General (LS / project setup) vs Traffic Control (signing / TTC devices)
    (
        [
            "mobilization",
            "demobilization",
            "tax on city",
            "winter maintenance",
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
        "General",
    ),
    (
        [
            "traffic control",
            "temporary traffic",
            "flagging",
            "barricade",
            "mailbox",
            "changeable message",
            "pcms",
            "business sign",
            "gravel access",
            "channeliz",
        ],
        "Traffic Control",
    ),
    (
        ["clearing", "grubbing", "tree removal", "stump", "brush"],
        "Clearing & Grubbing",
    ),
    (
        [
            "dam embankment",
            "earthfill dam",
            "dam excavation",
            "cofferdam",
            "spillway",
            "reservoir lining",
            "pond lining",
            "reservoir",
            "impoundment",
            "stilling basin",
            "intake tower",
            "dam crest",
        ],
        "Dams & Reservoirs",
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
            "brickwork",
            "plaster",
            "flooring",
            "roofing",
            "doors",
            "window",
            "house",
            "building",
            "dwelling",
            "apartment",
            "masonry",
            "blockwork",
            "tile",
        ],
        "Building",
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
    (
        [
            "water",
            "valve",
            "pipe",
            "fitting",
            "bend",
            "elbow",
            "tee",
            "reducer",
            "retainer gland",
            "long sleeve",
            "mj plug",
            "restrained joint",
        ],
        "Watermain",
    ),
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
    "dams & reservoirs": "Dams & Reservoirs",
    "building": "Building",
    "architecture": "Building",
    "demolition": "Removals",
    "site clearing": "Clearing & Grubbing",
    "geometry": "Miscellaneous",
    "general": "General",
    "traffic control": "Traffic Control",
    "general / traffic control": "General",
    "bid schedule": "Miscellaneous",
    "unmapped takeoff": "Special",
    "special": "Special",
}


def detect_alternate_section(*texts: str | None) -> str | None:
    """Return 'Alternate A' / 'Alternate B' when plan text names an alternate."""
    blob = " ".join(str(text or "") for text in texts)
    if not blob.strip():
        return None
    match = _ALTERNATE_RE.search(blob)
    if not match:
        return None
    token = str(match.group(1) or "").strip().upper()
    if not token:
        return None
    # Ignore false hits like "alternate water" / "option of".
    if token.isalpha() and len(token) != 1:
        return None
    return f"Alternate {token}"


def strip_alternate_label(description: str | None) -> str:
    """Remove leading 'Alternate A -' / 'Alt. B —' text once the section header owns it."""
    text = str(description or "").strip()
    if not text:
        return ""
    cleaned = _ALTERNATE_PREFIX_RE.sub("", text, count=1).strip(" -–—:")
    return cleaned or text


def resolve_eoq_group(
    *,
    description: str | None = None,
    category: str | None = None,
    source_reference: str | None = None,
) -> str:
    """Return canonical EOQ section name for an EOQ line."""
    alternate = detect_alternate_section(category, description, source_reference)
    if alternate:
        return alternate
    if looks_like_mobilization(description):
        return "General"
    cat = (category or "").strip()
    cat_low = cat.lower()
    if cat_low in {"general / traffic control", "general/traffic control"}:
        matched = _match_description(description or "")
        return matched or "General"
    if cat:
        alias = _CATEGORY_ALIASES.get(cat_low)
        if alias:
            # Still refine Utilities/Drainage/General using description when possible
            if alias in {"Watermain", "Storm Sewer", "Sanitary Sewer", "Miscellaneous", "General", "Special"}:
                refined = _match_description(description or "")
                if refined:
                    return refined
            return alias
        if cat in EOQ_GROUP_ORDER:
            return cat

    matched = _match_description(f"{description or ''} {category or ''}")
    if matched:
        return matched
    if cat_low in {"unmapped takeoff", "special"}:
        return "Special"
    return "Miscellaneous"


def _match_description(text: str) -> str | None:
    low = text.lower()
    if not low.strip():
        return None
    for keys, group in _GROUP_RULES:
        if any(k in low for k in keys):
            return group
    return None


def looks_like_mobilization(description: str | None) -> bool:
    text = str(description or "").strip().lower()
    if not text or "demobilization" in text:
        return False
    return bool(re.search(r"\bmobilization\b", text))


def group_sort_key(group: str) -> tuple[int, str]:
    try:
        return (EOQ_GROUP_ORDER.index(group), group)
    except ValueError:
        return (len(EOQ_GROUP_ORDER), group)


def group_items(
    items: Iterable[T],
    *,
    get_description,
    get_category,
    repeat_mobilization: bool = False,
) -> list[tuple[str, list[T]]]:
    """Partition items into ordered (group_name, items) sections. Empty groups omitted.

    When repeat_mobilization is True (Excel), Mobilization is listed at the top of General.
    It is never copied into Traffic Control.
    """
    buckets: dict[str, list[T]] = {}
    for item in items:
        source_ref = getattr(item, "source_reference", None)
        if source_ref is None and isinstance(item, dict):
            source_ref = item.get("source_reference")
        group = resolve_eoq_group(
            description=get_description(item),
            category=get_category(item),
            source_reference=str(source_ref or ""),
        )
        buckets.setdefault(group, []).append(item)
    mobs = [
        item
        for rows in buckets.values()
        for item in rows
        if looks_like_mobilization(get_description(item))
        and not detect_alternate_section(get_category(item), get_description(item))
    ]
    if mobs:
        for name in list(buckets.keys()):
            if name == "General" or detect_alternate_section(name):
                continue
            buckets[name] = [i for i in buckets[name] if not looks_like_mobilization(get_description(i))]
            if not buckets[name]:
                del buckets[name]
        gen = buckets.setdefault("General", [])
        for mob in reversed(mobs):
            if mob not in gen:
                gen.insert(0, mob)
    ordered: list[tuple[str, list[T]]] = []
    alternate_names = sorted(
        (name for name in buckets if detect_alternate_section(name)),
        key=_alternate_sort_key,
    )
    for name in EOQ_GROUP_ORDER:
        if name == "Special":
            for alt_name in alternate_names:
                if buckets.get(alt_name):
                    ordered.append((alt_name, buckets.pop(alt_name)))
        if name in buckets and buckets[name]:
            ordered.append((name, buckets.pop(name)))
    for name in sorted(buckets.keys()):
        if buckets[name]:
            ordered.append((name, buckets[name]))
    return ordered


def _alternate_sort_key(name: str) -> tuple[int, int | str]:
    token = name.rsplit(" ", 1)[-1]
    if token.isdigit():
        return (1, int(token))
    return (0, token)


def assign_group_category(item: dict[str, Any]) -> dict[str, Any]:
    """Set item['category'] to the canonical EOQ group (copy)."""
    out = dict(item)
    group = resolve_eoq_group(
        description=str(out.get("description") or ""),
        category=out.get("category"),
        source_reference=str(out.get("source_reference") or ""),
    )
    out["category"] = group
    out["eoq_group"] = group
    if detect_alternate_section(group):
        out["description"] = strip_alternate_label(str(out.get("description") or ""))
    return out
