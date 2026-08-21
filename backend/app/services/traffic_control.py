"""Traffic Control signing: consolidate individual signs into one SqFt pay item.

Size priority:
1. Explicit dimensions on the plan / DWG / item text (inches or feet)
2. MUTCD designation code lookup (local table mirrored from FHWA MUTCD)
3. Name alias → MUTCD code (STOP → R1-1, etc.)
4. Default conventional-road size when clearly a sign but size unknown

Optional online refresh: FHWA MUTCD / Standard Highway Signs pages when reachable.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "mutcd_sign_sizes.json"
_MUTCD_CACHE: dict[str, Any] | None = None

# MUTCD designation: R1-1, W20-7a, S5-1, G20-2, M4-5, OM1-1, etc.
_MUTCD_CODE_RE = re.compile(
    r"\b([RWMGSODP]|OM|I)[A-Z]?\d{1,2}(?:[A-Z])?(?:-\d{1,2}[A-Za-z]{0,2})(?:P)?\b",
    re.I,
)

# Explicit size callouts: 30x30, 24" x 36", 2'-0" x 3'-0", 30 in x 30 in, 2.5 ft x 2.5 ft
_SIZE_PATTERNS = [
    re.compile(
        r"(?P<w>\d+(?:\.\d+)?)\s*(?P<wu>(?:\"|''|in(?:ch(?:es)?)?|ft|feet|')?)\s*[x×]\s*"
        r"(?P<h>\d+(?:\.\d+)?)\s*(?P<hu>(?:\"|''|in(?:ch(?:es)?)?|ft|feet|')?)",
        re.I,
    ),
    re.compile(
        r"(?P<w>\d+(?:\.\d+)?)\s*(?P<wu>\"|''|in)\s*[x×]\s*(?P<h>\d+(?:\.\d+)?)\s*(?P<hu>\"|''|in)?",
        re.I,
    ),
]

_SIGN_POSITIVE = re.compile(
    r"(?:"
    r"\b(?:traffic\s+)?(?:control\s+)?signs?\b|"
    r"\bsigning\b|"
    r"\bsignage\b|"
    r"\broad\s+sign\b|"
    r"\bwarning\s+sign\b|"
    r"\bregulatory\s+sign\b|"
    r"\bguide\s+sign\b|"
    r"\btemp(?:orary)?\s+sign\b|"
    r"\bstop\s+sign\b|"
    r"\byield\s+sign\b|"
    r"\bspeed\s+limit\b|"
    r"\bdo\s+not\s+enter\b|"
    r"\bwrong\s+way\b|"
    r"\bone\s+way\b|"
    r"\bno\s+parking\b|"
    r"\broad\s+work\s+ahead\b|"
    r"\bend\s+road\s+work\b|"
    r"\bflagger\b|"
    r"\bchevron\b|"
    r"\bmutcd\b|"
    r"\b[rwmgsodp]\d{1,2}-\d{1,2}[a-z]?\b"
    r")",
    re.I,
)

_SIGN_NEGATIVE = re.compile(
    r"(?:"
    r"\btraffic\s+signal\b|"
    r"\bsignal\s+(?:head|pole|cabinet|controller|mast)\b|"
    r"\bpavement\s+mark(?:ing)?\b|"
    r"\bstrip(?:e|ing)\b|"
    r"\bthermoplastic\b|"
    r"\bchanneliz(?:er|ation)\b|"
    r"\bbarricade\b|"
    r"\bdrum\b|"
    r"\bcone\b|"
    r"\bdelineator\b|"
    r"\bflagger\s+(?:station|hours?)\b|"
    r"\bmobilization\b|"
    r"\btemporary\s+traffic\s+control\b(?!.*\bsign)|"
    r"\bttc\b(?!.*\bsign)"
    r")",
    re.I,
)

_GENERIC_TC_RE = re.compile(
    r"^\s*traffic\s+control(?:\s*\(signing\))?\s*$",
    re.I,
)


def _load_mutcd() -> dict[str, Any]:
    global _MUTCD_CACHE
    if _MUTCD_CACHE is not None:
        return _MUTCD_CACHE
    try:
        _MUTCD_CACHE = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("MUTCD size table missing/unreadable (%s); using empty fallback", exc)
        _MUTCD_CACHE = {
            "signs": {},
            "name_aliases": {},
            "default_unknown_sign_in": {"width_in": 30, "height_in": 30},
            "source_url": "https://mutcd.fhwa.dot.gov/",
        }
    return _MUTCD_CACHE


def refresh_mutcd_from_online(*, timeout_s: float = 8.0) -> dict[str, Any]:
    """Best-effort online check that MUTCD resources are reachable; keep local sizes.

    Full FHWA PDF table parsing is brittle; we verify the official pages and keep the
    curated local table (MUTCD 11th Edition conventional-road defaults) as authority.
    """
    catalog = _load_mutcd()
    urls = [
        str(catalog.get("source_url") or "https://mutcd.fhwa.dot.gov/kno_11th_Editionr1.htm"),
        str(
            catalog.get("standard_highway_signs_url")
            or "https://mutcd.fhwa.dot.gov/shsm_interim/index.htm"
        ),
        "https://mutcd.fhwa.dot.gov/",
    ]
    checked: list[dict[str, Any]] = []
    try:
        import httpx

        with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
            for url in urls:
                try:
                    resp = client.head(url)
                    if resp.status_code >= 400:
                        resp = client.get(url)
                    checked.append(
                        {
                            "url": url,
                            "status": resp.status_code,
                            "ok": resp.status_code < 400,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    checked.append({"url": url, "ok": False, "error": str(exc)[:160]})
    except Exception as exc:  # noqa: BLE001
        checked.append({"url": "httpx", "ok": False, "error": str(exc)[:160]})

    catalog = dict(catalog)
    catalog["online_check"] = {
        "checked_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "results": checked,
        "using_local_table": True,
        "sign_count": len(catalog.get("signs") or {}),
    }
    global _MUTCD_CACHE
    _MUTCD_CACHE = catalog
    return catalog


def inches_to_sqft(width_in: float, height_in: float) -> float:
    return round((float(width_in) * float(height_in)) / 144.0, 4)


def _to_inches(value: float, unit: str | None) -> float:
    u = (unit or "").strip().lower()
    if u in {"ft", "feet", "'", "’"}:
        return value * 12.0
    # bare number next to another inch unit, or empty → inches (MUTCD convention)
    return value


def parse_sign_size_inches(*texts: Any) -> tuple[float, float] | None:
    blob = " ".join(str(t) for t in texts if t)
    if not blob.strip():
        return None
    for pattern in _SIZE_PATTERNS:
        m = pattern.search(blob)
        if not m:
            continue
        w = _to_inches(float(m.group("w")), m.group("wu"))
        h = _to_inches(float(m.group("h")), m.groupdict().get("hu") or m.group("wu"))
        # Sanity: sign faces are rarely < 6" or > 20'
        if 6 <= w <= 240 and 6 <= h <= 240:
            return w, h
    return None


def extract_mutcd_code(*texts: Any) -> str | None:
    blob = " ".join(str(t) for t in texts if t)
    m = _MUTCD_CODE_RE.search(blob)
    if not m:
        return None
    code = m.group(0).upper().replace(" ", "")
    # Normalize OM1-1 style already matched; ensure hyphen form for R11 etc.
    return code


def lookup_mutcd_size(
    *,
    code: str | None = None,
    description: str | None = None,
    allow_online_refresh: bool = False,
) -> dict[str, Any] | None:
    catalog = _load_mutcd()
    if allow_online_refresh:
        try:
            catalog = refresh_mutcd_from_online()
        except Exception:  # noqa: BLE001
            pass

    signs: dict[str, Any] = catalog.get("signs") or {}
    aliases: dict[str, str] = {
        str(k).lower(): str(v).upper() for k, v in (catalog.get("name_aliases") or {}).items()
    }

    resolved = (code or "").upper().strip() or None
    if resolved and resolved not in signs:
        # Try without trailing plaque letter variants already in table
        alt = resolved.rstrip("P")
        if alt in signs:
            resolved = alt
        else:
            resolved = None

    if not resolved and description:
        low = re.sub(r"[^a-z0-9]+", " ", description.lower()).strip()
        # Longest alias first
        for alias in sorted(aliases.keys(), key=len, reverse=True):
            if alias in low or low == alias:
                resolved = aliases[alias]
                break

    if resolved and resolved in signs:
        entry = signs[resolved]
        return {
            "code": resolved,
            "name": entry.get("name"),
            "width_in": float(entry["width_in"]),
            "height_in": float(entry["height_in"]),
            "source": "mutcd_table",
            "source_url": catalog.get("source_url"),
        }

    return None


def is_traffic_sign_item(item: dict[str, Any]) -> bool:
    """True for individual traffic/control signs (not signals, striping, TTC LS, etc.)."""
    desc = str(item.get("description") or "")
    cat = str(item.get("category") or "")
    method = str(item.get("calculation_method") or "")
    ref = str(item.get("source_reference") or "")
    blob = f"{desc} {cat} {method} {ref}"

    if _GENERIC_TC_RE.match(desc.strip()):
        # Existing rollup line — not an individual sign to measure again
        return False
    if _SIGN_NEGATIVE.search(blob) and not _SIGN_POSITIVE.search(desc):
        return False
    if extract_mutcd_code(desc, ref):
        return True
    if _SIGN_POSITIVE.search(desc):
        return True
    # Category + Each unit often used for sign callouts
    unit = str(item.get("unit") or "").lower()
    if unit in {"each", "ea", "nos"} and re.search(r"\bsign", desc, re.I):
        return True
    return False


def resolve_sign_area_sqft(
    item: dict[str, Any],
    *,
    allow_online_refresh: bool = False,
) -> dict[str, Any]:
    """Resolve one sign face area in SqFt with size provenance."""
    desc = str(item.get("description") or "")
    extras = [
        item.get("size"),
        item.get("source_reference"),
        item.get("calculation_method"),
        item.get("notes"),
    ]
    qty = float(item.get("quantity") or 1) or 1.0
    # If already SqFt and description is a single sign type, trust quantity as total SF for that row
    unit = str(item.get("unit") or "").lower().replace(".", "")
    if unit in {"sqft", "sf", "squarefoot", "squarefeet"} and qty > 0:
        return {
            "sqft": round(qty, 4),
            "count": 1.0,
            "width_in": None,
            "height_in": None,
            "size_source": "item_sqft",
            "code": extract_mutcd_code(desc),
            "description": desc,
        }

    plan_size = parse_sign_size_inches(desc, *extras)
    code = extract_mutcd_code(desc, *extras)
    mutcd = lookup_mutcd_size(
        code=code,
        description=desc,
        allow_online_refresh=allow_online_refresh,
    )

    width_in: float | None = None
    height_in: float | None = None
    size_source = "default_mutcd_30x30"

    if plan_size:
        width_in, height_in = plan_size
        size_source = "plan_or_dwg_callout"
    elif mutcd:
        width_in = float(mutcd["width_in"])
        height_in = float(mutcd["height_in"])
        size_source = f"mutcd:{mutcd.get('code')}"
        code = mutcd.get("code") or code
    else:
        catalog = _load_mutcd()
        default = catalog.get("default_unknown_sign_in") or {"width_in": 30, "height_in": 30}
        width_in = float(default["width_in"])
        height_in = float(default["height_in"])
        size_source = "default_conventional_30x30"

    # Count: Each/EA quantity = number of faces; if unit already SF handled above
    count = qty if str(item.get("unit") or "").lower() in {"each", "ea", "nos", "no", "unit", ""} else 1.0
    if count <= 0:
        count = 1.0
    face_sf = inches_to_sqft(width_in, height_in)
    return {
        "sqft": round(face_sf * count, 4),
        "count": count,
        "width_in": width_in,
        "height_in": height_in,
        "face_sqft": face_sf,
        "size_source": size_source,
        "code": code,
        "description": desc,
    }


def consolidate_traffic_control_signs(
    items: list[dict[str, Any]],
    *,
    allow_online_refresh: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Replace individual traffic signs with one SqFt 'Traffic Control' item."""
    if not items:
        return items, {"sign_rows": 0, "total_sqft": 0.0}

    # One online refresh per consolidation pass (not per sign)
    if allow_online_refresh:
        try:
            refresh_mutcd_from_online()
        except Exception:  # noqa: BLE001
            pass

    kept: list[dict[str, Any]] = []
    existing_tc: dict[str, Any] | None = None
    sign_details: list[dict[str, Any]] = []
    total_sqft = 0.0

    for raw in items:
        item = dict(raw)
        desc = str(item.get("description") or "").strip()
        if _GENERIC_TC_RE.match(desc):
            # Prefer converting prior Each/LS Traffic Control into the SF rollup target
            unit = str(item.get("unit") or "").lower()
            if unit in {"sqft", "sf", "square foot", "square feet"}:
                try:
                    total_sqft += float(item.get("quantity") or 0)
                except (TypeError, ValueError):
                    pass
                existing_tc = item
                continue
            # Drop LS/Each generic Traffic Control — replaced by SF signing total
            existing_tc = item
            continue

        if is_traffic_sign_item(item):
            detail = resolve_sign_area_sqft(item, allow_online_refresh=False)
            total_sqft += float(detail["sqft"])
            sign_details.append(detail)
            continue

        kept.append(item)

    meta = {
        "sign_rows": len(sign_details),
        "total_sqft": round(total_sqft, 2),
        "details": sign_details[:80],
        "mutcd_source": (_load_mutcd() or {}).get("source_url"),
    }

    if not sign_details and existing_tc is None:
        return items, meta
    if total_sqft <= 0 and not sign_details:
        # Nothing to roll up
        if existing_tc:
            kept.append(existing_tc)
        return kept, meta

    sources = sorted({d.get("size_source") or "" for d in sign_details if d.get("size_source")})
    method = (
        f"Consolidated {len(sign_details)} traffic sign(s) into SqFt "
        f"(plan/DWG sizes when present, else MUTCD conventional-road sizes). "
        f"Size sources: {', '.join(s for s in sources if s) or 'n/a'}."
    )
    codes = [d.get("code") for d in sign_details if d.get("code")]
    ref_bits = []
    if codes:
        ref_bits.append("codes " + ", ".join(sorted(set(str(c) for c in codes))[:12]))
    if meta.get("mutcd_source"):
        ref_bits.append(f"MUTCD ref {meta['mutcd_source']}")

    from app.services.csi_mapper import enrich_quantity_item

    src_doc = (existing_tc or {}).get("source_document_id")
    if src_doc is None:
        src_doc = next((i.get("source_document_id") for i in items if i.get("source_document_id")), None)

    rolled = {
        "item_code": (existing_tc or {}).get("item_code"),
        "description": "Traffic Control",
        "category": "General / Traffic Control",
        "unit": "SqFt",
        "quantity": round(total_sqft, 2),
        "source_document_id": src_doc,
        "source_page": (existing_tc or {}).get("source_page"),
        "source_reference": "; ".join(ref_bits) or "Traffic signing takeoff",
        "calculation_method": method,
        "confidence": 90.0
        if any((d.get("size_source") or "").startswith(("plan", "mutcd")) for d in sign_details)
        else 82.0,
        "status": "needs_review",
        "traffic_control_breakdown": sign_details,
    }

    kept.append(enrich_quantity_item(rolled))
    meta["rolled_into"] = "Traffic Control"
    return kept, meta
