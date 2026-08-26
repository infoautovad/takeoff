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

# Explicit size callouts: 30x30, 24" x 36", 48-Inch x 30-Inch, 2 ft x 2.5 ft
_UNIT = r"(?:\"|''|in(?:ch(?:es)?)?|ft|feet|')"
_SIZE_PATTERNS = [
    re.compile(
        rf"(?P<w>\d+(?:\.\d+)?)\s*-?\s*(?P<wu>{_UNIT})?\s*[x×]\s*"
        rf"(?P<h>\d+(?:\.\d+)?)\s*-?\s*(?P<hu>{_UNIT})?",
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
    r"\btemporary\s+business\s+sign\b|"
    r"\b(?:portable\s+)?changeable\s+message\s+sign\b|"
    r"\bpcms\b|"
    r"\bmailbox\b|"
    r"\bgravel\s+access\b|"
    r"\bwinter\s+maintenance\b|"
    r"\btraffic\s+control\s*,?\s*misc|"
    r"\btemporary\s+traffic\s+control\b(?!.*\bsign)|"
    r"\bttc\b(?!.*\bsign)"
    r")",
    re.I,
)

_GENERIC_TC_RE = re.compile(
    r"^\s*traffic\s+control(?:\s*\(signing\))?\s*$",
    re.I,
)

# Bid-schedule companions under a Traffic Control heading — never roll into SqFt.
_DISTINCT_TC_PAY_RE = re.compile(
    r"(?:"
    r"\bbarricade\b|"
    r"\bchanneliz(?:er|ation)\b|"
    r"\bdrum\b|"
    r"\bcone\b|"
    r"\bpcms\b|"
    r"\bchangeable\s+message\b|"
    r"\bbusiness\s+sign\b|"
    r"\bmailbox\b|"
    r"\bgravel\s+access\b|"
    r"\bwinter\s+maintenance\b|"
    r"\btraffic\s+control\s*,?\s*misc|"
    r"\bflagging\b|"
    r"\bpilot\s+car\b"
    r")",
    re.I,
)

_AGENCY_BID_NO_RE = re.compile(r"^\s*(?:special|\d{1,4}\.\d{2,4}[a-z]?)\s*$", re.I)

_PLAN_DEVICE_HINTS = (
    "graphic count",
    "symbol",
    "symbols",
    "project total",
    "itemized table",
    "mutcd ref",
    "consolidated",
    "in²",
    "in2",
    "÷144",
    "/144",
    "width(in)",
    "default_conventional",
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


def _evidence_blob(item: dict[str, Any]) -> str:
    return (
        f"{item.get('calculation_method') or ''} "
        f"{item.get('source_reference') or ''} "
        f"{item.get('source') or ''} "
        f"{item.get('description') or ''}"
    ).lower()


def looks_like_agency_bid_number(code: Any) -> bool:
    raw = str(code or "").strip()
    if not raw:
        return False
    # CSI MasterFormat uses spaces: "01 71 13" — not an agency bid number
    if re.match(r"^\d{2}\s+\d{2}\s+\d{2}", raw):
        return False
    return bool(_AGENCY_BID_NO_RE.match(raw))


def is_distinct_traffic_pay_item(item: dict[str, Any]) -> bool:
    """True for bid-schedule Traffic Control companions (barricade, PCMS, mailbox, …)."""
    desc = str(item.get("description") or "")
    if _GENERIC_TC_RE.match(desc.strip()):
        return False
    if _DISTINCT_TC_PAY_RE.search(desc):
        return True
    unit = str(item.get("unit") or "").lower()
    if "traffic control" in desc.lower() and unit in {"ls", "lump sum"}:
        return True
    return False


def is_plan_device_takeoff(item: dict[str, Any]) -> bool:
    """F-sheet device tables, graphic symbol counts, MUTCD 30×30 rollups — not bid rows."""
    blob = _evidence_blob(item)
    return any(h in blob for h in _PLAN_DEVICE_HINTS)


def is_generic_traffic_control_signing(item: dict[str, Any]) -> bool:
    desc = str(item.get("description") or "").strip()
    if not _GENERIC_TC_RE.match(desc):
        return False
    if is_distinct_traffic_pay_item(item):
        return False
    return True


def _unit_is_sqft(unit: Any) -> bool:
    u = str(unit or "").lower().replace(".", "").replace(" ", "")
    return u in {"sqft", "sf", "squarefoot", "squarefeet", "sqft"}


def is_traffic_sign_item(item: dict[str, Any]) -> bool:
    """True for individual MUTCD/plan signs (not schedule pay items or signals)."""
    desc = str(item.get("description") or "")
    cat = str(item.get("category") or "")
    method = str(item.get("calculation_method") or "")
    ref = str(item.get("source_reference") or "")
    blob = f"{desc} {cat} {method} {ref}"

    if is_distinct_traffic_pay_item(item):
        return False
    if is_generic_traffic_control_signing(item):
        return False
    if _SIGN_NEGATIVE.search(blob) and not _SIGN_POSITIVE.search(desc):
        return False
    if _SIGN_NEGATIVE.search(desc):
        return False
    if extract_mutcd_code(desc, ref):
        return True
    if _SIGN_POSITIVE.search(desc):
        return True
    unit = str(item.get("unit") or "").lower()
    if unit in {"each", "ea", "nos"} and re.search(r"\bsign", desc, re.I):
        return True
    if parse_sign_size_inches(desc) and re.search(
        r"sign|traffic|mutcd|warning|regulatory|guide|signing", blob, re.I
    ):
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
    unit = str(item.get("unit") or "").lower().replace(".", "").replace(" ", "")
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

    # Count: Each/EA quantity = number of faces. Inches are the face size, never the pay unit.
    unit_l = str(item.get("unit") or "").lower().replace(".", "")
    if unit_l in {"each", "ea", "nos", "no", "unit", ""}:
        count = qty
    else:
        count = 1.0
    if count <= 0:
        count = 1.0
    face_sf = inches_to_sqft(width_in, height_in)
    formula = f"{width_in:g} in × {height_in:g} in = {face_sf:g} SqFt (in²÷144)"
    if count != 1.0:
        formula = f"{count:g} × {formula}"
    return {
        "sqft": round(face_sf * count, 4),
        "count": count,
        "width_in": width_in,
        "height_in": height_in,
        "face_sqft": face_sf,
        "formula": formula,
        "size_source": size_source,
        "code": code,
        "description": desc,
    }


def _prefer_schedule_tc_row(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Keep the bid-schedule Traffic Control SqFt row over a MUTCD-computed one."""
    def score(row: dict[str, Any]) -> tuple[int, float]:
        pts = 0
        if looks_like_agency_bid_number(row.get("item_code")):
            pts += 8
        blob = _evidence_blob(row)
        if any(h in blob for h in ("estimate of quantities", "bid item", "est. qty", "eoq schedule", "std bid")):
            pts += 6
        if is_plan_device_takeoff(row):
            pts -= 8
        try:
            conf = float(row.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        return pts, conf

    return candidate if score(candidate) > score(existing) else existing


def _filter_plan_invented_when_schedule(
    kept: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop F-sheet extras when a real Traffic Control bid section was captured."""
    has_gravel_ls = any(
        re.search(r"gravel\s+access", str(i.get("description") or ""), re.I)
        and str(i.get("unit") or "").lower() in {"ls", "lump sum"}
        for i in kept
    )
    out: list[dict[str, Any]] = []
    for item in kept:
        desc = str(item.get("description") or "")
        unit = str(item.get("unit") or "").lower()
        planish = is_plan_device_takeoff(item) and not looks_like_agency_bid_number(item.get("item_code"))
        if planish and re.search(r"channeliz", desc, re.I):
            continue
        if has_gravel_ls and re.search(r"gravel\s+access", desc, re.I) and unit not in {"ls", "lump sum"}:
            continue
        out.append(item)

    barricades = [i for i in out if re.search(r"barricade", str(i.get("description") or ""), re.I)]
    if len(barricades) > 1:
        best = barricades[0]
        for b in barricades[1:]:
            best = _prefer_schedule_tc_row(best, b)
        out = [
            i
            for i in out
            if i is best or not re.search(r"barricade", str(i.get("description") or ""), re.I)
        ]
    return out


def consolidate_traffic_control_signs(
    items: list[dict[str, Any]],
    *,
    allow_online_refresh: bool = True,
    schedule_present: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Schedule Traffic Control pay items stay intact; MUTCD plan signs roll to SqFt only if no schedule."""
    if not items:
        return items, {"sign_rows": 0, "total_sqft": 0.0}

    if allow_online_refresh and not schedule_present:
        try:
            refresh_mutcd_from_online()
        except Exception:  # noqa: BLE001
            pass

    kept: list[dict[str, Any]] = []
    existing_tc: dict[str, Any] | None = None
    sign_details: list[dict[str, Any]] = []
    dropped_plan_signs = 0

    for raw in items:
        item = dict(raw)
        if is_distinct_traffic_pay_item(item):
            kept.append(item)
            continue

        if is_generic_traffic_control_signing(item):
            if _unit_is_sqft(item.get("unit")):
                existing_tc = _prefer_schedule_tc_row(existing_tc, item) if existing_tc else item
            elif schedule_present:
                # LS/Each "Traffic Control" without "Miscellaneous" — keep if it has a bid number
                if looks_like_agency_bid_number(item.get("item_code")):
                    kept.append(item)
                elif existing_tc is None:
                    existing_tc = item
            else:
                existing_tc = item
            continue

        if is_traffic_sign_item(item):
            if schedule_present:
                dropped_plan_signs += 1
                continue
            detail = resolve_sign_area_sqft(item, allow_online_refresh=False)
            sign_details.append(detail)
            continue

        kept.append(item)

    meta = {
        "sign_rows": len(sign_details) + dropped_plan_signs,
        "dropped_plan_signs": dropped_plan_signs,
        "total_sqft": 0.0,
        "details": sign_details[:80],
        "mutcd_source": (_load_mutcd() or {}).get("source_url"),
        "schedule_present": schedule_present,
    }

    if schedule_present:
        kept = _filter_plan_invented_when_schedule(kept)
        if existing_tc is not None:
            if _unit_is_sqft(existing_tc.get("unit")):
                existing_tc = dict(existing_tc)
                existing_tc["unit"] = "SqFt"
                existing_tc["category"] = existing_tc.get("category") or "General / Traffic Control"
                kept.append(existing_tc)
                try:
                    meta["total_sqft"] = round(float(existing_tc.get("quantity") or 0), 2)
                except (TypeError, ValueError):
                    meta["total_sqft"] = 0.0
            else:
                kept.append(existing_tc)
        return kept, meta

    total_sqft = 0.0
    if existing_tc is not None and _unit_is_sqft(existing_tc.get("unit")):
        try:
            total_sqft += float(existing_tc.get("quantity") or 0)
        except (TypeError, ValueError):
            pass
    for detail in sign_details:
        total_sqft += float(detail.get("sqft") or 0)
    meta["total_sqft"] = round(total_sqft, 2)

    if not sign_details and existing_tc is None:
        return items, meta
    if total_sqft <= 0 and not sign_details:
        if existing_tc:
            kept.append(existing_tc)
        return kept, meta

    if sign_details:
        sources = sorted({d.get("size_source") or "" for d in sign_details if d.get("size_source")})
        formulas = [str(d.get("formula")) for d in sign_details if d.get("formula")]
        method = (
            f"Consolidated {len(sign_details)} traffic sign(s) into SqFt of sign face. "
            f"USA pay unit is square feet, not inches: width(in)×height(in)÷144. "
            f"Size sources: {', '.join(s for s in sources if s) or 'n/a'}."
        )
        if formulas:
            method += " " + "; ".join(formulas[:8])
            if len(formulas) > 8:
                method += f" (+{len(formulas) - 8} more)"
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
            "item_code": (existing_tc or {}).get("item_code")
            if looks_like_agency_bid_number((existing_tc or {}).get("item_code"))
            else (existing_tc or {}).get("item_code"),
            "description": "Traffic Control",
            "category": "General / Traffic Control",
            "unit": "SqFt",
            "quantity": round(total_sqft, 2),
            "source_document_id": src_doc,
            "source_page": (existing_tc or {}).get("source_page"),
            "source_reference": "; ".join(ref_bits) or "Traffic signing takeoff",
            "calculation_method": method
            if not (existing_tc and _unit_is_sqft(existing_tc.get("unit")) and not is_plan_device_takeoff(existing_tc))
            else str(existing_tc.get("calculation_method") or method),
            "confidence": 90.0
            if any((d.get("size_source") or "").startswith(("plan", "mutcd")) for d in sign_details)
            else 82.0,
            "status": "needs_review",
            "traffic_control_breakdown": sign_details,
        }
        rolled = enrich_quantity_item(rolled)
        rolled["unit"] = "SqFt"
        kept.append(rolled)
        meta["rolled_into"] = "Traffic Control"
        return kept, meta

    if existing_tc:
        kept.append(existing_tc)
    return kept, meta
