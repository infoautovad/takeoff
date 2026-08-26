"""Civil 3D station / offset / side — same formulas the product uses.

Civil 3D ``Alignment.StationOffset(x, y, out station, out offset)``:

* **Station** = alignment start station + distance along the alignment to the
  closest point (raw feet, displayed as ``12+34.56``).
* **Offset** is *signed*: **positive = RIGHT** of increasing station, negative = LEFT.
* **Side** on takeoff sheets is ``LT`` / ``RT`` / ``CL``.

Plan sheets also store the same values as:

* Civil object properties (``rawStation``, Easting/Northing, …)
* Block attributes (``STA``, ``STATION``, ``OFFSET``, ``SIDE``)
* Text / MTEXT callouts (``STA 5+48.11 8.2' RT``), often in paper space
"""

from __future__ import annotations

import math
import re
from typing import Any

# Civil plan station: 0+00, 5+48.11, 12+00
_STA_TOKEN = re.compile(r"(?P<sta>\d{1,5}\+\d{2}(?:\.\d+)?)")
_STA_LABELED = re.compile(
    r"(?:sta(?:tion)?\.?\s*[:#\-]?\s*)?(?P<sta>\d{1,5}\+\d{2}(?:\.\d+)?)",
    re.I,
)
# 15.0' LT   |   LT 15'   |   15.00 FT RT   |   8.2' RIGHT
_OFFSET_SIDE = re.compile(
    r"(?P<off>\d+(?:\.\d+)?)\s*(?:'|ft|feet|m)?\s*['\"]?\s*(?P<side>L\.?T\.?|R\.?T\.?|LEFT|RIGHT|CL|CTR|CENTER)"
    r"|(?P<side2>L\.?T\.?|R\.?T\.?|LEFT|RIGHT)\s*(?P<off2>\d+(?:\.\d+)?)\s*(?:'|ft|feet)?",
    re.I,
)
_STA_THEN_OFFSET = re.compile(
    r"(?P<sta>\d{1,5}\+\d{2}(?:\.\d+)?)"
    r"[^\d+]{0,48}"
    r"(?:(?P<off>\d+(?:\.\d+)?)\s*(?:'|ft|feet)?\s*(?P<side>L\.?T\.?|R\.?T\.?|LEFT|RIGHT)"
    r"|(?P<side2>L\.?T\.?|R\.?T\.?|LEFT|RIGHT)\s*(?P<off2>\d+(?:\.\d+)?))",
    re.I,
)

# Property-bag keys Civil / APS / block attributes actually use
_STA_KEYS = (
    "station",
    "raw station",
    "rawstation",
    "structure station",
    "pipe station",
    "refstation",
    "ref station",
    "sta",
    "sta.",
    "stn",
    "aligned station",
    "alignment station",
    "station along alignment",
    "station value",
    "start station",
    "starting station",
    "stastart",
)
_SIDE_KEYS = (
    "side",
    "offset side",
    "direction",
    "dir",
    "lt/rt",
    "l/r",
    "hand",
    "side of alignment",
    "offset direction",
)
_OFF_KEYS = (
    "offset",
    "2d offset",
    "horizontal offset",
    "offset from alignment",
    "rawoffset",
    "raw offset",
    "offset ft",
    "offset (ft)",
    "offset distance",
    "signed offset",
)
_XY_PAIRS = (
    ("easting", "northing"),
    ("east", "north"),
    ("start easting", "start northing"),
    ("end easting", "end northing"),
    ("position x", "position y"),
    ("pos x", "pos y"),
    ("insertion point x", "insertion point y"),
    ("insertionpointx", "insertionpointy"),
    ("insert x", "insert y"),
    ("location x", "location y"),
    ("refpt x", "refpt y"),
    ("ref pt x", "ref pt y"),
    ("center x", "center y"),
    ("origin x", "origin y"),
    ("geompositionx", "geompositiony"),
    ("x", "y"),
    ("start x", "start y"),
    ("start point x", "start point y"),
    ("end x", "end y"),
    ("end point x", "end point y"),
    ("min x", "min y"),  # bbox — refined below
)

_ATTR_STA_TAGS = frozenset(
    {"STA", "STATION", "STN", "STA_NO", "STANO", "ALIGNSTA", "RAWSTA", "RAW_STATION"}
)
_ATTR_SIDE_TAGS = frozenset({"SIDE", "DIR", "HAND", "LT_RT", "LTRT", "OFFSETSIDE"})
_ATTR_OFF_TAGS = frozenset({"OFFSET", "OFF", "OS", "HOFFSET", "OFFSET_FT", "OFFS"})


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        f = float(value)
        return f if math.isfinite(f) else None
    text = str(value).strip().replace(",", "").replace("'", "")
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if not m:
        return None
    try:
        f = float(m.group(0))
    except ValueError:
        return None
    return f if math.isfinite(f) else None


def station_to_feet(sta: Any) -> float | None:
    """Parse ``12+34.56`` or Civil raw station feet (``1234.56``)."""
    if sta is None or sta == "":
        return None
    if isinstance(sta, (int, float)) and not isinstance(sta, bool):
        f = float(sta)
        return f if math.isfinite(f) and 0 <= f < 1_000_000 else None
    s = str(sta).strip()
    m = re.match(r"(\d+)\+(\d+(?:\.\d+)?)$", s)
    if m:
        return float(m.group(1)) * 100.0 + float(m.group(2))
    # Allow leading STA
    m = _STA_TOKEN.search(s)
    if m and re.fullmatch(r"\s*(?:sta(?:tion)?\.?\s*)?\d+\+\d{2}(?:\.\d+)?\s*", s, re.I):
        return station_to_feet(m.group("sta"))
    try:
        f = float(s.replace(",", "").replace("'", ""))
    except ValueError:
        return None
    if math.isfinite(f) and 0 <= f < 1_000_000:
        return f
    return None


def feet_to_station(feet: float | None) -> str:
    if feet is None or not math.isfinite(feet):
        return ""
    feet = max(0.0, float(feet))
    plus = int(feet // 100)
    rem = feet - plus * 100
    if abs(rem - round(rem)) < 0.05:
        return f"{plus}+{int(round(rem)):02d}"
    return f"{plus}+{rem:05.2f}"


def coerce_station(value: Any) -> str:
    """Normalize any Civil station representation to ``12+34.56``."""
    ft = station_to_feet(value)
    if ft is None:
        m = _STA_TOKEN.search(str(value or ""))
        if m:
            ft = station_to_feet(m.group("sta"))
    return feet_to_station(ft) if ft is not None else ""


def side_code(side: Any) -> str:
    s = str(side or "").strip().lower().replace(".", "")
    if not s:
        return ""
    if re.search(r"\bleft\b|\blt\b|^l$", s) or s.endswith(" lt") or " lt " in f" {s} ":
        return "LT"
    if re.search(r"\bright\b|\brt\b|^r$", s) or s.endswith(" rt") or " rt " in f" {s} ":
        return "RT"
    if re.search(r"\b(cl|center|centre|ctr|on cl|on-cl)\b", s):
        return "CL"
    if s in {"lt", "rt", "cl"}:
        return s.upper()
    return ""


def civil_signed_offset(offset: float) -> tuple[str, float]:
    """Civil 3D signed offset → (side, absolute feet). Positive = RIGHT."""
    if abs(offset) < 0.05:
        return "CL", 0.0
    if offset > 0:
        return "RT", abs(offset)
    return "LT", abs(offset)


def format_offset(offset_ft: float | None, side: str | None) -> str:
    if offset_ft is None:
        return ""
    code = side_code(side)
    if not code or code == "CL":
        return f"{float(offset_ft):.1f}' CL"
    return f"{float(offset_ft):.1f}' {code}"


def _norm_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(key or "").lower()).strip()


def _lookup(props: dict[str, Any], keys: tuple[str, ...]) -> Any:
    if not props:
        return None
    exact = {_norm_key(k): v for k, v in props.items()}
    for key in keys:
        if key in exact and exact[key] not in (None, ""):
            return exact[key]
    # Substring only for longer keys so "sta" does not steal "start" / "state"
    long_keys = [k for k in keys if len(k) >= 5]
    if not long_keys:
        return None
    for nk, v in exact.items():
        if v in (None, ""):
            continue
        for key in long_keys:
            if key == nk or key in nk:
                return v
    return None


def _xy_from_string(raw: Any) -> list[float] | None:
    if raw is None:
        return None
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(raw))
    if len(nums) < 2:
        return None
    try:
        x, y = float(nums[0]), float(nums[1])
    except ValueError:
        return None
    # Reject tiny "0, 1" style enums; world/state-plane coords are large
    if abs(x) < 1 and abs(y) < 1:
        return None
    return [x, y]


def point_from_property_bag(props: dict[str, Any] | None) -> list[float] | None:
    """Best-effort world XY (Easting/Northing or insert) from a Civil/APS bag."""
    if not props:
        return None
    exact = {_norm_key(k): v for k, v in props.items()}

    for xk, yk in _XY_PAIRS:
        if xk == "min x":
            continue
        x = _to_float(exact.get(xk))
        y = _to_float(exact.get(yk))
        if x is not None and y is not None:
            return [float(x), float(y)]

    # Fuzzy: any *easting*/*x* paired with *northing*/*y*
    x_val = _lookup(props, ("easting", "position x", "insert x", "location x", "origin x", "center x"))
    y_val = _lookup(props, ("northing", "position y", "insert y", "location y", "origin y", "center y"))
    x = _to_float(x_val)
    y = _to_float(y_val)
    if x is not None and y is not None:
        return [float(x), float(y)]

    for key in (
        "location",
        "position",
        "insertion point",
        "geometry location",
        "insert",
        "refpt",
        "center",
        "origin",
        "geometry",
    ):
        pt = _xy_from_string(exact.get(key) or _lookup(props, (key,)))
        if pt:
            return pt

    # Bounding-box center (APS sometimes exposes only extents)
    minx = _to_float(exact.get("min x") or exact.get("minx") or exact.get("bbox min x"))
    maxx = _to_float(exact.get("max x") or exact.get("maxx") or exact.get("bbox max x"))
    miny = _to_float(exact.get("min y") or exact.get("miny") or exact.get("bbox min y"))
    maxy = _to_float(exact.get("max y") or exact.get("maxy") or exact.get("bbox max y"))
    if None not in (minx, maxx, miny, maxy):
        return [(minx + maxx) / 2.0, (miny + maxy) / 2.0]

    return None


def location_from_property_bag(props: dict[str, Any] | None) -> dict[str, Any]:
    """Station / side / offset / insert from a flat Civil, APS, or attrib dict."""
    props = props or {}
    sta_raw = _lookup(props, _STA_KEYS)
    side_raw = _lookup(props, _SIDE_KEYS)
    off_raw = _lookup(props, _OFF_KEYS)

    station = coerce_station(sta_raw)
    side = side_code(side_raw)
    offset_ft: float | None = None

    off_f = _to_float(off_raw)
    if off_f is not None:
        # Combined "15.0' LT" in the offset field
        parsed_side = side_code(str(off_raw))
        if parsed_side:
            side = side or parsed_side
            offset_ft = abs(off_f)
        elif side:
            offset_ft = abs(off_f)
        else:
            # Bare Civil signed offset (positive = RT)
            side, offset_ft = civil_signed_offset(off_f)

    # Combined strings anywhere in the bag
    if not station or not side or offset_ft is None:
        for v in props.values():
            parsed = parse_station_offset_text(str(v or ""))
            if not parsed.get("station") and not parsed.get("side"):
                continue
            station = station or parsed.get("station") or ""
            side = side or parsed.get("side") or ""
            if offset_ft is None and parsed.get("offset_ft") is not None:
                offset_ft = parsed["offset_ft"]

    insert = point_from_property_bag(props)
    return {
        "station": station,
        "side": side,
        "offset_ft": offset_ft,
        "offset": format_offset(offset_ft, side) if offset_ft is not None else "",
        "insert": insert,
        "raw_station": sta_raw,
    }


def parse_station_offset_text(text: str) -> dict[str, Any]:
    """Parse a civil callout: ``STA 5+48.11 8.2' RT``."""
    empty = {"station": "", "side": "", "offset_ft": None}
    if not text or not str(text).strip():
        return dict(empty)
    blob = str(text)

    m = _STA_THEN_OFFSET.search(blob)
    if m:
        side = side_code(m.group("side") or m.group("side2"))
        off = _to_float(m.group("off") or m.group("off2"))
        return {
            "station": coerce_station(m.group("sta")),
            "side": side,
            "offset_ft": abs(off) if off is not None else None,
        }

    sta_m = _STA_LABELED.search(blob)
    off_m = _OFFSET_SIDE.search(blob)
    station = coerce_station(sta_m.group("sta")) if sta_m else ""
    side = ""
    offset_ft = None
    if off_m:
        side = side_code(off_m.group("side") or off_m.group("side2"))
        offset_ft = _to_float(off_m.group("off") or off_m.group("off2"))
        if offset_ft is not None:
            offset_ft = abs(offset_ft)
    return {"station": station, "side": side, "offset_ft": offset_ft}


def attributes_to_dict(raw: Any) -> dict[str, Any]:
    """Normalize INSERT attributes from DXF / plugin / APS."""
    out: dict[str, Any] = {}
    if not raw:
        return out
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k is None or v is None:
                continue
            out[str(k).strip()] = v
            out[str(k).strip().upper()] = v
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            tag = item.get("tag") or item.get("name") or item.get("key")
            val = item.get("text") or item.get("value") or item.get("contents")
            if tag is not None and val is not None:
                out[str(tag).strip()] = val
                out[str(tag).strip().upper()] = val
    return out


def location_from_block_attributes(block: dict[str, Any]) -> dict[str, Any]:
    attrs = attributes_to_dict(
        block.get("attributes") or block.get("attribs") or block.get("atts")
    )
    if not attrs:
        return {"station": "", "side": "", "offset_ft": None, "insert": None}

    sta = None
    side = None
    off = None
    for k, v in attrs.items():
        ku = str(k).upper().replace(" ", "")
        if ku in _ATTR_STA_TAGS or ku.endswith("STATION") or ku == "STA":
            sta = v
        elif ku in _ATTR_SIDE_TAGS:
            side = v
        elif ku in _ATTR_OFF_TAGS:
            off = v

    bag = dict(attrs)
    if sta is not None:
        bag["station"] = sta
    if side is not None:
        bag["side"] = side
    if off is not None:
        bag["offset"] = off
    loc = location_from_property_bag(bag)
    # Attribute strings like "5+48.11 8.2' RT" on a single STA tag
    if (not loc["station"] or loc["offset_ft"] is None) and sta is not None:
        parsed = parse_station_offset_text(str(sta))
        loc["station"] = loc["station"] or parsed["station"]
        loc["side"] = loc["side"] or parsed["side"]
        if loc["offset_ft"] is None:
            loc["offset_ft"] = parsed["offset_ft"]
    return loc


def collect_location_labels(texts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Index drawing/sheet callouts that carry station and/or offset."""
    labels: list[dict[str, Any]] = []
    for t in texts or []:
        blob = str(t.get("text") or t.get("contents") or t.get("value") or "")
        parsed = parse_station_offset_text(blob)
        if not parsed["station"] and parsed["offset_ft"] is None:
            continue
        insert = None
        if str(t.get("space") or "").lower() != "paper":
            raw = t.get("insert") or t.get("position") or t.get("location")
            if isinstance(raw, (list, tuple)) and len(raw) >= 2:
                try:
                    insert = (float(raw[0]), float(raw[1]))
                except (TypeError, ValueError):
                    insert = None
        labels.append(
            {
                "text": blob,
                "station": parsed["station"],
                "side": parsed["side"],
                "offset_ft": parsed["offset_ft"],
                "insert": insert,
                "layer": str(t.get("layer") or ""),
                "space": str(t.get("space") or "model"),
                "used": False,
            }
        )
    return labels


def _text_kind_hints(text: str) -> set[str]:
    low = text.lower()
    hints: set[str] = set()
    mapping = (
        ("valve", "valve"),
        ("gv", "valve"),
        ("hydrant", "hydrant"),
        ("tee", "tee"),
        ("wye", "wye"),
        ("bend", "bend"),
        ("elbow", "bend"),
        ("reducer", "reducer"),
        ("manhole", "manhole"),
        (" mh", "manhole"),
        ("inlet", "inlet"),
        ("catch", "inlet"),
        ("fitting", "fitting"),
        ("structure", "structure"),
    )
    for key, hint in mapping:
        if key in low:
            hints.add(hint)
    return hints


def match_label_to_fitting(
    *,
    name: str,
    layer: str,
    type_label: str,
    insert: tuple[float, float] | None,
    labels: list[dict[str, Any]],
    snap_ft: float = 60.0,
) -> dict[str, Any] | None:
    """Pick the best unused station/offset callout for this fitting."""
    if not labels:
        return None
    blob = f"{name} {layer} {type_label}".lower()
    hints = _text_kind_hints(blob)
    best: dict[str, Any] | None = None
    best_score = -1.0

    for lab in labels:
        if lab.get("used"):
            continue
        score = 0.0
        lab_hints = _text_kind_hints(str(lab.get("text") or ""))
        if hints and lab_hints and hints & lab_hints:
            score += 8
        elif hints and lab_hints:
            score -= 2
        if insert and lab.get("insert"):
            d = math.hypot(insert[0] - lab["insert"][0], insert[1] - lab["insert"][1])
            if d <= snap_ft:
                score += max(0.0, 20.0 - d / 4.0)
            elif lab.get("space") != "paper":
                continue
        elif insert and lab.get("space") != "paper" and lab.get("insert"):
            continue
        if lab.get("station"):
            score += 3
        if lab.get("side") or lab.get("offset_ft") is not None:
            score += 2
        if score > best_score:
            best_score = score
            best = lab

    if best is None or best_score < 8:
        # Paper-space / lexical only: type hint match + station
        lexical: dict[str, Any] | None = None
        lex_score = -1.0
        for lab in labels:
            if lab.get("used") or not lab.get("station"):
                continue
            lab_hints = _text_kind_hints(str(lab.get("text") or ""))
            score = 4 if (hints and lab_hints and hints & lab_hints) else 0
            if score > lex_score:
                lex_score = score
                lexical = lab
        if lexical and lex_score >= 4:
            lexical["used"] = True
            return lexical
        return None

    best["used"] = True
    return best


def civil3d_station_offset(
    point: tuple[float, float],
    chain: list[tuple[float, float]],
    sta_start: float = 0.0,
) -> dict[str, Any] | None:
    """Mirror ``Alignment.StationOffset`` on a 2D alignment polyline.

    Returns station string, signed Civil offset (RT+), takeoff side, and abs feet.
    """
    if not point or len(chain) < 2:
        return None
    best_d = float("inf")
    best_sta = 0.0
    best_signed = 0.0
    cum = 0.0
    for i in range(1, len(chain)):
        x1, y1 = chain[i - 1]
        x2, y2 = chain[i]
        dx, dy = x2 - x1, y2 - y1
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-9:
            continue
        t = ((point[0] - x1) * dx + (point[1] - y1) * dy) / (seg_len * seg_len)
        t_clamped = max(0.0, min(1.0, t))
        proj = (x1 + t_clamped * dx, y1 + t_clamped * dy)
        d = math.hypot(point[0] - proj[0], point[1] - proj[1])
        # Cross > 0 → left of travel (LT). Civil signed offset is opposite (RT+).
        cross = dx * (point[1] - y1) - dy * (point[0] - x1)
        signed = d if cross < 0 else -d
        if abs(cross) < 1e-6 * seg_len or d < 0.05:
            signed = 0.0
        if d < best_d:
            best_d = d
            best_sta = cum + t_clamped * seg_len
            best_signed = signed
        cum += seg_len
    if best_d == float("inf"):
        return None
    side, off_abs = civil_signed_offset(best_signed) if abs(best_signed) >= 0.05 else ("CL", 0.0)
    # Prefer geometric LT/RT from cross (already encoded in signed)
    sta_ft = sta_start + best_sta
    return {
        "station": feet_to_station(sta_ft),
        "station_ft": sta_ft,
        "offset_ft": round(off_abs, 2),
        "side": side,
        "offset": format_offset(off_abs, side),
        "civil_signed_offset": round(best_signed, 2),
    }


def collect_pipe_ends(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    """Pipe start/end stations and XY — fittings usually sit on these joints."""
    ends: list[dict[str, Any]] = []
    for pipe in extraction.get("pipes") or []:
        network = pipe.get("network")
        size = pipe.get("diameter") or pipe.get("size") or pipe.get("part_size")
        side = side_code(pipe.get("side") or pipe.get("offset_side"))
        off = _to_float(pipe.get("offset_ft") if pipe.get("offset_ft") is not None else pipe.get("offset"))
        if off is not None and not side:
            side, off = civil_signed_offset(off)
        elif off is not None:
            off = abs(off)
        pairs = (
            (pipe.get("sta_start") or pipe.get("start_station"), pipe.get("start") or pipe.get("start_point")),
            (pipe.get("sta_end") or pipe.get("end_station"), pipe.get("end") or pipe.get("end_point")),
        )
        for sta, pt in pairs:
            station = coerce_station(sta)
            insert = None
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    insert = (float(pt[0]), float(pt[1]))
                except (TypeError, ValueError):
                    insert = None
            if not station and not insert:
                continue
            ends.append(
                {
                    "station": station,
                    "side": side,
                    "offset_ft": off,
                    "insert": insert,
                    "network": network,
                    "size": size,
                    "used": False,
                }
            )
    return ends


def match_pipe_end(
    *,
    insert: tuple[float, float] | None,
    network: str | None,
    ends: list[dict[str, Any]],
    snap_ft: float = 8.0,
) -> dict[str, Any] | None:
    best = None
    best_d = snap_ft
    for end in ends:
        if end.get("used") or not end.get("insert") or not insert:
            continue
        if network and end.get("network") and str(end["network"]).lower() != str(network).lower():
            continue
        d = math.hypot(insert[0] - end["insert"][0], insert[1] - end["insert"][1])
        if d <= best_d:
            best_d = d
            best = end
    if best:
        best["used"] = True
    return best


def typical_network_offset(
    segments: list[dict[str, Any]],
    network: str | None,
) -> tuple[str, float | None]:
    """Most common side/offset for a utility — Civil networks sit on a constant offset."""
    sides: dict[str, int] = {}
    offs: list[float] = []
    for s in segments or []:
        if network and s.get("network") and s.get("network") != network:
            continue
        side = side_code(s.get("side") or s.get("side_of_alignment"))
        if side:
            sides[side] = sides.get(side, 0) + 1
        off = s.get("offset_ft")
        if off is None and s.get("offset") is not None:
            off = _to_float(s.get("offset"))
        if off is not None:
            offs.append(abs(float(off)))
    side = max(sides, key=sides.get) if sides else ""
    offset_ft = None
    if offs:
        offs.sort()
        offset_ft = offs[len(offs) // 2]
    return side, offset_ft


def useful_property_attr(label: str) -> bool:
    """Whether an APS properties.db attribute should be loaded for stationing."""
    low = (label or "").lower()
    keys = (
        "layer",
        "length",
        "area",
        "type",
        "name",
        "handle",
        "radius",
        "perimeter",
        "measurement",
        "contents",
        "textcontent",
        "text",
        "pipe",
        "structure",
        "alignment",
        "parcel",
        "network",
        "part size",
        "diameter",
        "inner",
        "outer",
        "material",
        "cut",
        "fill",
        "volume",
        "surface",
        "slope",
        "description",
        "family",
        "style",
        "station",
        "sta",
        "stn",
        "start",
        "end",
        "refstart",
        "refend",
        "easting",
        "northing",
        "east",
        "north",
        "offset",
        "side",
        "direction",
        "location",
        "position",
        "insert",
        "insertion",
        "origin",
        "center",
        "coord",
        "bbox",
        "min x",
        "max x",
        "min y",
        "max y",
        "minx",
        "maxx",
        "raw",
        "align",
        "refpt",
        "geom",
    )
    if any(k in low for k in keys):
        return True
    # Lone X / Y / Z geometry attributes
    token = re.sub(r"[^a-z0-9]+", " ", low).strip()
    if token in {"x", "y", "z", "x y", "xy"}:
        return True
    return False
