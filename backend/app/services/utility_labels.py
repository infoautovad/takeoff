"""Extract water/sanitary/storm utility quantities from plan labels & callouts.

On civil plan PDFs, pipe sizes and lengths often live in callout text like:
  8" WATER MAIN, PROP. WM 12", 8" DIP WM (STA 10+00 TO 12+50), WATERMAIN 245 LF
"""

from __future__ import annotations

import re
from typing import Any

# Use horizontal whitespace only so labels on the next line are not glued on.
_S = r"[^\S\n]*"
_SIZE = rf"(?P<size>\d{{1,2}}(?:\.\d+)?){_S}(?:\"|''|in(?:ch(?:es)?)?)"
_QTY_LF = rf"(?P<qty>\d{{2,5}}(?:\.\d+)?){_S}(?:lf|lin(?:ear)?{_S}(?:ft|feet)|l\.?f\.?)\b"
_STA = (
    rf"(?:sta(?:tion)?\.?{_S})?(?P<sta1>\d{{1,3}}\+\d{{2}}(?:\.\d+)?)"
    rf"{_S}(?:to|[-–]){_S}"
    rf"(?:sta(?:tion)?\.?{_S})?(?P<sta2>\d{{1,3}}\+\d{{2}}(?:\.\d+)?)"
)

# Ordered patterns: (regex, network) — each match stays on one line
_LABEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 8" WATER MAIN … 245 LF
    (
        re.compile(
            rf"{_SIZE}{_S}"
            rf"(?:(?P<mat>dip|pvc|hdpe|di|ci|rcp|cpp){_S})?"
            rf"(?:prop(?:osed)?\.?{_S})?"
            r"(?P<kind>water\s*mains?|watermains?|w\.?\s*m\.?|wm)\b"
            rf"(?:{_S}[-:]?{_S}{_QTY_LF})?",
            re.I,
        ),
        "water",
    ),
    # WATER MAIN 8" … LF
    (
        re.compile(
            rf"(?:prop(?:osed)?\.?{_S})?"
            r"(?P<kind>water\s*mains?|watermains?)\b"
            rf"{_S}{_SIZE}"
            rf"(?:{_S}[-:]?{_S}{_QTY_LF})?",
            re.I,
        ),
        "water",
    ),
    # PROP. WM 12" STA 10+00 TO 12+50  (same line)
    (
        re.compile(
            rf"(?:prop(?:osed)?\.?{_S})?"
            r"(?P<kind>water\s*mains?|watermains?|wm)\b"
            rf"{_S}{_SIZE}{_S}{_STA}",
            re.I,
        ),
        "water",
    ),
    # 8" WM STA … TO … / 8" DIP WM STA …
    (
        re.compile(
            rf"{_SIZE}{_S}"
            rf"(?:(?:dip|pvc|hdpe){_S})?"
            rf"(?:prop(?:osed)?\.?{_S})?"
            r"(?P<kind>wm|w\.?\s*m\.?|water\s*mains?|watermains?)\b"
            rf"{_S}{_STA}",
            re.I,
        ),
        "water",
    ),
    # WATERMAIN 245 LF  (size unknown)
    (
        re.compile(
            rf"(?:prop(?:osed)?\.?{_S})?"
            r"(?P<kind>water\s*mains?|watermains?)\b"
            rf"{_S}[-:]?{_S}{_QTY_LF}",
            re.I,
        ),
        "water",
    ),
    # Fittings (same line)
    (
        re.compile(
            rf"(?:{_SIZE}{_S})?"
            r"(?P<kind>gate\s*valve|butterfly\s*valve|water\s*valve|\bvalve\b|"
            r"fire\s*hydrant|\bhydrant\b|\bbend\b|\belbow\b|\btee\b)\b"
            rf"(?:{_S}(?P<qty>\d{{1,3}}){_S}(?:ea|each|nos?))?",
            re.I,
        ),
        "water_fitting",
    ),
    # Sanitary / storm mains with size + optional LF
    (
        re.compile(
            rf"{_SIZE}{_S}"
            rf"(?:prop(?:osed)?\.?{_S})?"
            r"(?P<kind>sanitary\s*(?:sewer)?(?:\s*main)?|ss\s*main|"
            r"storm\s*(?:drain|sewer)?(?:\s*main)?)\b"
            rf"(?:{_S}{_QTY_LF})?",
            re.I,
        ),
        "other_pipe",
    ),
]


def _station_to_feet(sta: str) -> float | None:
    m = re.match(r"(\d+)\+(\d+(?:\.\d+)?)", sta.strip())
    if not m:
        return None
    return float(m.group(1)) * 100.0 + float(m.group(2))


def _size_label(raw: str | None) -> str | None:
    if not raw:
        return None
    m = re.search(r"(\d{1,2}(?:\.\d+)?)", raw)
    if not m:
        return None
    val = float(m.group(1))
    if val < 1 or val > 96:
        return None
    if abs(val - int(val)) < 0.01:
        return f"{int(val)}-Inch"
    return f"{val:g}-Inch"


def _kind_description(kind: str, network: str, size: str | None) -> tuple[str, str, str]:
    """Return description, category, unit."""
    k = (kind or "").lower().strip()
    size_bit = f"{size} " if size else ""
    if network == "water_fitting":
        if "hydrant" in k:
            return f"{size_bit}Fire Hydrant".strip(), "Utilities", "EA"
        if "bend" in k or "elbow" in k:
            return f"{size_bit}Water Bend / Elbow".strip(), "Utilities", "EA"
        if "tee" in k:
            return f"{size_bit}Water Tee".strip(), "Utilities", "EA"
        return f"{size_bit}Water Valve".strip(), "Utilities", "EA"
    if network == "water" or "water" in k or k in {"wm", "w.m.", "w.m", "w m"}:
        return f"{size_bit}Water Main".strip(), "Utilities", "LF"
    if "sanitary" in k or k.startswith("ss"):
        return f"{size_bit}Sanitary Sewer Pipe".strip(), "Drainage", "LF"
    if "storm" in k:
        return f"{size_bit}Storm Drain Pipe".strip(), "Drainage", "LF"
    return f"{size_bit}Utility Pipe".strip(), "Utilities", "LF"


def extract_utility_label_items(
    text: str,
    *,
    filename: str = "",
    document_id: int | None = None,
    mains_only: bool = False,
) -> list[dict[str, Any]]:
    """Parse plan text for utility label/callout quantities.

    When mains_only=True (EOQ/schedule documents), skip fitting/valve/hydrant invents
    that inflate false extras vs bid schedules.
    """
    if not text or len(text.strip()) < 8:
        return []

    cleaned = (
        text.replace("″", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    found: dict[str, dict[str, Any]] = {}

    for pattern, network in _LABEL_PATTERNS:
        if mains_only and network == "water_fitting":
            continue
        for match in pattern.finditer(cleaned):
            gd = match.groupdict()
            size = _size_label(gd.get("size"))
            kind = gd.get("kind") or ""
            desc, category, unit = _kind_description(kind, network, size)

            qty: float | None = None
            if gd.get("qty"):
                try:
                    qty = float(gd["qty"])
                except ValueError:
                    qty = None
            if qty is None and gd.get("sta1") and gd.get("sta2"):
                a = _station_to_feet(gd["sta1"])
                b = _station_to_feet(gd["sta2"])
                if a is not None and b is not None:
                    qty = abs(b - a)

            if qty is None and unit == "EA":
                qty = 1.0

            # Sized water main label without length: keep as EA? No — skip LF without qty
            if qty is None or qty <= 0:
                continue
            if unit == "LF" and (qty < 1 or qty > 200000):
                continue
            if unit == "EA" and qty > 500:
                continue

            key = f"{desc.lower()}|{unit.lower()}"
            snippet = re.sub(r"\s+", " ", match.group(0)).strip()[:120]
            conf = 92.0 if size and unit == "LF" else 88.0 if size else 84.0
            if key not in found:
                found[key] = {
                    "description": desc,
                    "category": category,
                    "unit": unit,
                    "quantity": qty,
                    "confidence": conf,
                    "status": "needs_review",
                    "calculation_method": f"Plan label/callout: '{snippet}'",
                    "source_reference": f"Drawing label — {snippet}",
                    "source_document_id": document_id,
                    "item_code": None,
                }
            else:
                existing = float(found[key]["quantity"])
                if unit == "LF":
                    if abs(qty - existing) / max(existing, 1) < 0.08:
                        found[key]["confidence"] = max(float(found[key]["confidence"]), conf)
                    else:
                        found[key]["quantity"] = existing + qty
                        found[key]["calculation_method"] += f" + '{snippet}'"
                else:
                    found[key]["quantity"] = existing + qty

    return list(found.values())
