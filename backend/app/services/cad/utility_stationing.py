"""Centerline-based utility stationing, offsets, fittings, and bid rollups.

Stationing is always relative to the roadway / project CENTERLINE (CL).
LT/RT is computed from alignment travel direction (2D cross product), not
drawing screen orientation.

Outputs feed Excel:
  - Bid Quantity Summary (rolled up FROM detail)
  - Linear Quantity Breakdown (sta/offset/side/length)
  - Fittings / Bends / Connections
  - Quantity QA/QC flags
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

from app.services.cad.civil_location import (
    coerce_station,
    collect_location_labels,
    collect_pipe_ends,
    format_offset as _civil_format_offset,
    location_from_block_attributes,
    location_from_property_bag,
    match_label_to_fitting,
    match_pipe_end,
    parse_station_offset_text,
    point_from_property_bag,
    side_code as _civil_side_code,
    station_to_feet as _civil_station_to_feet,
    typical_network_offset,
)
from app.services.cad.quantity_engine import (
    classify_fitting,
    detect_network,
    extract_size_label,
)

_STA_PAIR = re.compile(
    r"(?:sta(?:tion)?\.?\s*)?(?P<sta1>\d{1,4}\+\d{2}(?:\.\d+)?)"
    r"\s*(?:to|[-–—]|thru|through)\s*"
    r"(?:sta(?:tion)?\.?\s*)?(?P<sta2>\d{1,4}\+\d{2}(?:\.\d+)?)",
    re.I,
)
_STA_ONE = re.compile(r"(?:sta(?:tion)?\.?\s*)?(?P<sta>\d{1,4}\+\d{2}(?:\.\d+)?)", re.I)

_UTILITY_KIND = re.compile(
    r"(?P<kind>"
    r"water\s*mains?|watermains?|\bwm\b|w\.?\s*m\.?|"
    r"sanitary\s*(?:sewer)?(?:\s*main)?|\bss\b|"
    r"storm\s*(?:drain|sewer)?(?:\s*main)?|"
    r"force\s*main|forcemain|"
    r"casing(?:\s*pipe)?|carrier(?:\s*pipe)?"
    r")",
    re.I,
)

# Prefer true centerline names first
_CL_NAME_HINTS = (
    "centerline",
    "centreline",
    "center line",
    "centre line",
    "cl alignment",
    " roadway cl",
    "road cl",
    "baseline",
    "p_cl",
    "_cl",
    "cl_",
)
_ALIGN_NAME_HINTS = _CL_NAME_HINTS + (
    "alignment",
    "cl-",
    " cl",
    "roadway",
    "profile",
)


def _is_centerline_name(*parts: Any) -> bool:
    """True for P_CL / CL_ / CENTERLINE style names (underscore-safe)."""
    low = " ".join(str(p) for p in parts if p).lower()
    if not low.strip():
        return False
    if any(h in low for h in _CL_NAME_HINTS):
        return True
    if re.search(r"center\s*line|centre\s*line|baseline", low):
        return True
    # Token CL including P_CL_50th, X_CL, CL-1 (underscore is a word char so \bcl\b fails)
    if re.search(r"(?:^|[^a-z0-9])cl(?:[^a-z0-9]|$)", low.replace("_", " ")):
        return True
    return False

# Offset change (ft) above which a run is treated as non-parallel to CL
_NONPARALLEL_OFFSET_DELTA_FT = 3.0
_MIN_BEND_DEG = 12.0


def station_to_feet(sta: str | None) -> float | None:
    """Parse ``12+34.56`` or Civil raw station feet."""
    return _civil_station_to_feet(sta)


def feet_to_station(feet: float | None) -> str:
    if feet is None or not math.isfinite(feet):
        return ""
    feet = max(0.0, float(feet))
    plus = int(feet // 100)
    rem = feet - plus * 100
    if abs(rem - round(rem)) < 0.05:
        return f"{plus}+{int(round(rem)):02d}"
    return f"{plus}+{rem:05.2f}"


def format_offset(offset_ft: float | None, side: str | None) -> str:
    """Civil style: 18.5' RT"""
    return _civil_format_offset(offset_ft, side)


def _side_code(side: str | None) -> str:
    return _civil_side_code(side)


def _network_label(network: str | None) -> str:
    return {
        "water": "Water Main",
        "sanitary": "Sanitary Sewer",
        "storm": "Storm Sewer",
        "casing": "Casing",
        "force": "Force Main",
    }.get((network or "").lower(), "Underground Utility")


def _kind_to_network(kind: str) -> str | None:
    k = kind.lower()
    if "water" in k or k in {"wm", "w.m", "w m"}:
        return "water"
    if "sanitary" in k or k == "ss":
        return "sanitary"
    if "storm" in k:
        return "storm"
    if "force" in k:
        return "force"
    if "casing" in k or "carrier" in k:
        return "casing"
    return detect_network(kind)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _polyline_length(pts: list[tuple[float, float]]) -> float:
    return sum(_dist(pts[i - 1], pts[i]) for i in range(1, len(pts)))


def _as_point(raw: Any) -> tuple[float, float] | None:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            return float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            return None
    if isinstance(raw, dict):
        try:
            return float(raw.get("x")), float(raw.get("y"))
        except (TypeError, ValueError):
            return None
    return None


def _as_points(raw: Any) -> list[tuple[float, float]]:
    if not raw or not isinstance(raw, list):
        return []
    out: list[tuple[float, float]] = []
    for p in raw:
        pt = _as_point(p)
        if pt:
            out.append(pt)
    return out


def _project_point_on_polyline(
    point: tuple[float, float],
    chain: list[tuple[float, float]],
) -> tuple[float, float, str] | None:
    """Return (station_along_ft, offset_ft, side LT/RT/CL) vs CL travel direction."""
    if len(chain) < 2:
        return None
    best_d = float("inf")
    best_sta = 0.0
    best_side = "CL"
    best_off = 0.0
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
        d = _dist(point, proj)
        # Positive cross = left of CL travel direction → LT
        cross = dx * (point[1] - y1) - dy * (point[0] - x1)
        if abs(cross) < 1e-6 * seg_len or d < 0.05:
            side = "CL"
        else:
            side = "LT" if cross > 0 else "RT"
        if d < best_d:
            best_d = d
            best_sta = cum + t_clamped * seg_len
            best_side = side
            best_off = d
        cum += seg_len
    if best_d == float("inf"):
        return None
    return best_sta, best_off, best_side


def _build_centerline(extraction: dict[str, Any]) -> dict[str, Any]:
    """Always prefer roadway CENTERLINE for stationing — require geometry when possible."""
    alignments = list(extraction.get("alignments") or [])
    polylines = list(extraction.get("polylines") or [])
    lines = list(extraction.get("lines") or [])
    candidates: list[dict[str, Any]] = []

    def add(name: str, layer: Any, pts: list, length: float, sta0: float, source: str, bonus: float) -> None:
        has_geom = len(pts) >= 2
        # Geometry is mandatory for station/offset — heavily prefer it
        geom_bonus = 100_000 if has_geom else 0
        cl_bonus = bonus
        candidates.append(
            {
                "name": name,
                "layer": layer,
                "points": pts,
                "length": length if length > 0 else (_polyline_length(pts) if has_geom else 0),
                "sta_start": sta0,
                "score": (length or 0) + cl_bonus + geom_bonus,
                "source": source,
                "is_centerline": cl_bonus >= 20_000 or _is_centerline_name(name, layer),
                "has_geometry": has_geom,
            }
        )

    for a in alignments:
        pts = _as_points(a.get("points") or a.get("vertices") or a.get("coords"))
        length = float(a.get("length") or (_polyline_length(pts) if pts else 0) or 0)
        name = str(a.get("name") or a.get("layer") or "Alignment")
        layer = a.get("layer") or name
        sta0 = station_to_feet(str(a.get("sta_start") or a.get("staStart") or "") or None) or 0.0
        bonus = 0.0
        if _is_centerline_name(name, layer):
            bonus = 50_000
        elif any(h in f"{name} {layer}".lower() for h in _ALIGN_NAME_HINTS):
            bonus = 15_000
        add(name, layer, pts, length, sta0, "alignment", bonus)

    for pl in polylines:
        layer = str(pl.get("layer") or "")
        name = str(pl.get("name") or layer)
        if not _is_centerline_name(name, layer) and not any(
            h in f"{layer} {name}".lower() for h in ("alignment", "roadway")
        ):
            continue
        pts = _as_points(pl.get("points") or pl.get("vertices") or pl.get("coords"))
        length = float(pl.get("length") or (_polyline_length(pts) if pts else 0) or 0)
        bonus = 50_000 if _is_centerline_name(name, layer) else 12_000
        add(name or layer, layer, pts, length, 0.0, "polyline_cl", bonus)

    # Also consider ANY polyline on a CL-like layer even if earlier filter missed
    for pl in polylines:
        layer = str(pl.get("layer") or "")
        if not _is_centerline_name(layer):
            continue
        pts = _as_points(pl.get("points") or pl.get("vertices") or pl.get("coords"))
        if len(pts) < 2:
            continue
        length = float(pl.get("length") or _polyline_length(pts) or 0)
        add(layer, layer, pts, length, 0.0, "polyline_cl_layer", 55_000)

    if not candidates:
        for pl in polylines:
            layer = str(pl.get("layer") or "")
            if detect_network(layer):
                continue
            pts = _as_points(pl.get("points") or pl.get("vertices") or pl.get("coords"))
            if len(pts) < 2:
                continue
            length = float(pl.get("length") or _polyline_length(pts) or 0)
            if length < 50:
                continue
            add(layer or "Reference CL", layer, pts, length, 0.0, "longest_polyline", 0)

    if not any(c.get("has_geometry") for c in candidates) and lines:
        for line in lines:
            layer = str(line.get("layer") or "")
            if not _is_centerline_name(layer, line.get("name")):
                continue
            s = _as_point(line.get("start"))
            e = _as_point(line.get("end"))
            pts = [p for p in (s, e) if p]
            if len(pts) == 2:
                add(
                    layer or "CL line",
                    layer,
                    pts,
                    float(line.get("length") or _dist(pts[0], pts[1])),
                    0.0,
                    "line_cl",
                    50_000,
                )

    if not candidates and lines:
        best = max(lines, key=lambda L: float(L.get("length") or 0), default=None)
        if best and best.get("start") and best.get("end"):
            pts = [p for p in (_as_point(best["start"]), _as_point(best["end"])) if p]
            if len(pts) == 2:
                add(
                    str(best.get("layer") or "Line CL"),
                    best.get("layer"),
                    pts,
                    float(best.get("length") or _dist(pts[0], pts[1])),
                    0.0,
                    "line",
                    0,
                )

    if not candidates:
        return {
            "name": "CENTERLINE (assumed 0+00 — no CL geometry found)",
            "layer": None,
            "points": [],
            "length": 0.0,
            "sta_start": 0.0,
            "source": "none",
            "is_centerline": False,
            "has_geometry": False,
        }

    # Prefer geometry-bearing CL; among those, highest score
    with_geom = [c for c in candidates if c.get("has_geometry")]
    pool = with_geom or candidates
    best = max(pool, key=lambda c: float(c.get("score") or 0))
    best = _hydrate_centerline_points(best, polylines=polylines, lines=lines)

    raw_name = str(best.get("name") or "CL")
    if best.get("is_centerline") and not raw_name.upper().startswith("CL"):
        best["name"] = raw_name  # keep CAD name like P_CL 50th Street
    elif not best.get("is_centerline"):
        best["name"] = f"CL (proxy) — {raw_name}"
    return best


def _hydrate_centerline_points(
    cl: dict[str, Any],
    *,
    polylines: list[dict[str, Any]],
    lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """If CL was chosen by name/length only, attach matching polyline/line vertices."""
    if len(cl.get("points") or []) >= 2:
        cl["has_geometry"] = True
        return cl

    name = str(cl.get("name") or "").lower()
    layer = str(cl.get("layer") or "").lower()
    for prefix in ("cl — ", "cl (proxy) — "):
        if name.startswith(prefix):
            name = name[len(prefix) :]

    best_pts: list[tuple[float, float]] = []
    best_len = 0.0
    for pl in polylines:
        pl_layer = str(pl.get("layer") or "").lower()
        pl_name = str(pl.get("name") or "").lower()
        pts = _as_points(pl.get("points") or pl.get("vertices") or pl.get("coords"))
        if len(pts) < 2:
            continue
        matched = (
            (layer and (layer == pl_layer or layer in pl_layer or pl_layer in layer))
            or (name and (name == pl_layer or name in pl_layer or pl_layer in name or name in pl_name))
            or _is_centerline_name(pl_layer, pl_name)
        )
        if not matched:
            continue
        length = _polyline_length(pts)
        if length > best_len:
            best_len = length
            best_pts = pts

    if not best_pts:
        for line in lines:
            pl_layer = str(line.get("layer") or "").lower()
            if not (
                (layer and layer in pl_layer)
                or (name and name in pl_layer)
                or _is_centerline_name(pl_layer)
            ):
                continue
            s = _as_point(line.get("start"))
            e = _as_point(line.get("end"))
            pts = [p for p in (s, e) if p]
            if len(pts) == 2:
                length = _dist(pts[0], pts[1])
                if length > best_len:
                    best_len = length
                    best_pts = pts

    if best_pts:
        cl = dict(cl)
        cl["points"] = [[p[0], p[1]] for p in best_pts]
        cl["length"] = best_len or cl.get("length") or 0
        cl["has_geometry"] = True
        cl["source"] = f"{cl.get('source') or 'cl'}+hydrated_vertices"
        return cl

    # Last resort: station axis only (offsets stay blank without world XY on pipes)
    length = float(cl.get("length") or 0)
    if length > 1:
        cl = dict(cl)
        cl["points"] = [[0.0, 0.0], [length, 0.0]]
        cl["has_geometry"] = True
        cl["synthetic_geometry"] = True
        cl["source"] = f"{cl.get('source') or 'cl'}+synthetic_station_axis"
    return cl


def _size_display(size: str | None) -> str:
    if not size:
        return ""
    s = str(size).strip()
    if re.search(r"inch", s, re.I):
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        return f'{m.group(1)}"' if m else s
    if '"' in s or "''" in s:
        return s
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return f'{m.group(1)}"' if m else s


def _locate(
    point: tuple[float, float] | None,
    cl: dict[str, Any],
) -> dict[str, Any]:
    chain = list(cl.get("points") or [])
    sta0 = float(cl.get("sta_start") or 0.0)
    empty = {
        "station": "",
        "station_ft": None,
        "offset_ft": None,
        "side": "",
        "offset_label": "",
        "alignment": cl.get("name") or "CL",
        "associated": False,
    }
    # Synthetic station axis is not in drawing coordinates — do not project world XY onto it
    if cl.get("synthetic_geometry"):
        return empty
    if not point or len(chain) < 2:
        return empty
    proj = _project_point_on_polyline(point, chain)
    if not proj:
        return empty
    sta_ft = sta0 + proj[0]
    side = proj[2]
    off = proj[1]
    return {
        "station": feet_to_station(sta_ft),
        "station_ft": sta_ft,
        "offset_ft": round(off, 2),
        "side": side,
        "offset_label": format_offset(off, side),
        "alignment": cl.get("name") or "CL",
        "associated": True,
    }


def _segment_row(
    *,
    network: str | None,
    size: str | None,
    length: float,
    layer: str,
    pts: list[tuple[float, float]],
    cl: dict[str, Any],
    source: str,
    method: str,
    name: str = "",
) -> dict[str, Any] | None:
    if length <= 0.05 and len(pts) < 2:
        return None
    if length <= 0.05 and pts:
        length = _polyline_length(pts)
    if length <= 0.05:
        return None

    from_loc = _locate(pts[0] if pts else None, cl)
    to_loc = _locate(pts[-1] if len(pts) > 1 else (pts[0] if pts else None), cl)

    from_sta = from_loc["station"]
    to_sta = to_loc["station"]
    from_off = from_loc["offset_ft"]
    to_off = to_loc["offset_ft"]
    from_side = from_loc["side"]
    to_side = to_loc["side"]

    # Dominant side for parallel runs
    side = from_side or to_side
    offset_ft = from_off
    if from_off is not None and to_off is not None:
        offset_ft = (from_off + to_off) / 2.0

    nonparallel = False
    if from_off is not None and to_off is not None:
        if abs(from_off - to_off) >= _NONPARALLEL_OFFSET_DELTA_FT or (
            from_side and to_side and from_side != to_side and from_side != "CL" and to_side != "CL"
        ):
            nonparallel = True

    util = _network_label(network)
    size_d = _size_display(size)
    flags: list[str] = []
    if not from_loc["associated"] or not to_loc["associated"]:
        flags.append("line_not_associated_with_alignment")
    if not size_d:
        flags.append("unknown_size")

    return {
        "item": util,
        "utility": util,
        "network": network or "utility",
        "size": size_d,
        "description": f"{size_d + ' ' if size_d else ''}{util}".strip(),
        "from_station": from_sta,
        "to_station": to_sta,
        "side": side,
        "offset_ft": round(offset_ft, 2) if offset_ft is not None else None,
        "offset": format_offset(offset_ft, side) if offset_ft is not None else "",
        "from_offset_ft": round(from_off, 2) if from_off is not None else None,
        "to_offset_ft": round(to_off, 2) if to_off is not None else None,
        "from_offset": format_offset(from_off, from_side) if from_off is not None else "",
        "to_offset": format_offset(to_off, to_side) if to_off is not None else "",
        "nonparallel": nonparallel,
        "length": round(length, 2),
        "quantity_lf": round(length, 2),
        "unit": "LF",
        "layer": layer,
        "alignment": cl.get("name") or "CL",
        "source": source,
        "method": method,
        "name": name,
        "flags": flags,
        # legacy keys for older consumers
        "side_of_alignment": side,
        "direction": "Increasing station"
        if (from_loc.get("station_ft") or 0) <= (to_loc.get("station_ft") or 0)
        else "Decreasing station",
    }


def _split_polyline_runs(
    pts: list[tuple[float, float]],
    *,
    network: str | None,
    size: str | None,
    layer: str,
    cl: dict[str, Any],
) -> list[dict[str, Any]]:
    """Split a pipe polyline into straight station runs between bend vertices."""
    if len(pts) < 2:
        return []
    # Find bend indices
    bend_idx = {0, len(pts) - 1}
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        if n1 < 1e-6 or n2 < 1e-6:
            continue
        cosang = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        deflection = abs(math.degrees(math.acos(cosang)))
        if deflection >= _MIN_BEND_DEG:
            bend_idx.add(i)
    ordered = sorted(bend_idx)
    rows: list[dict[str, Any]] = []
    for i in range(len(ordered) - 1):
        i0, i1 = ordered[i], ordered[i + 1]
        sub = pts[i0 : i1 + 1]
        length = _polyline_length(sub)
        row = _segment_row(
            network=network,
            size=size,
            length=length,
            layer=layer,
            pts=sub,
            cl=cl,
            source="CAD POLYLINE segment",
            method=f"Centerline station/offset; segment vertices {i0}→{i1}",
        )
        if row:
            rows.append(row)
    if not rows:
        row = _segment_row(
            network=network,
            size=size,
            length=_polyline_length(pts),
            layer=layer,
            pts=pts,
            cl=cl,
            source="CAD POLYLINE",
            method="Centerline station/offset on full polyline",
        )
        if row:
            rows.append(row)
    return rows


def _segments_from_texts(extraction: dict[str, Any], cl: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for t in extraction.get("texts") or []:
        text = str(t.get("text") or t.get("contents") or "").strip()
        if not text:
            continue
        kind_m = _UTILITY_KIND.search(text)
        sta_m = _STA_PAIR.search(text)
        if not kind_m or not sta_m:
            continue
        network = _kind_to_network(kind_m.group("kind"))
        size = extract_size_label(text)
        a = station_to_feet(sta_m.group("sta1"))
        b = station_to_feet(sta_m.group("sta2"))
        if a is None or b is None:
            continue
        length = abs(b - a)
        util = _network_label(network)
        size_d = _size_display(size)
        rows.append(
            {
                "item": util,
                "utility": util,
                "network": network or "utility",
                "size": size_d,
                "description": f"{size_d + ' ' if size_d else ''}{util}".strip(),
                "from_station": feet_to_station(a),
                "to_station": feet_to_station(b),
                "side": "",
                "offset": "",
                "offset_ft": None,
                "from_offset": "",
                "to_offset": "",
                "from_offset_ft": None,
                "to_offset_ft": None,
                "nonparallel": False,
                "length": round(length, 2),
                "quantity_lf": round(length, 2),
                "unit": "LF",
                "layer": t.get("layer") or "",
                "alignment": cl.get("name") or "CL",
                "source": "plan/DWG text callout",
                "method": f"Station range from text on CL: '{text[:100]}'",
                "flags": ["station_from_text_no_offset"],
                "side_of_alignment": "",
                "direction": "Increasing station" if b >= a else "Decreasing station",
            }
        )
    return rows


def _segments_from_geometry(extraction: dict[str, Any], cl: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for pipe in extraction.get("pipes") or []:
        layer = str(pipe.get("layer") or "")
        name = str(pipe.get("name") or "")
        network = detect_network(name, layer, pipe.get("network"), pipe.get("description"))
        if not network and not any(
            k in f"{layer} {name}".lower() for k in ("pipe", "water", "sewer", "storm", "san", "main", "casing")
        ):
            continue
        size = extract_size_label(name, layer, pipe.get("diameter"), pipe.get("part_size"), pipe.get("description"))
        length = float(pipe.get("length") or 0)
        pts = _as_points(pipe.get("points") or pipe.get("coords"))
        # Civil 3D / APS often expose start/end without vertices
        s_pt = _as_point(pipe.get("start") or pipe.get("start_point"))
        e_pt = _as_point(pipe.get("end") or pipe.get("end_point"))
        if len(pts) < 2 and s_pt and e_pt:
            pts = [s_pt, e_pt]
            if length <= 0:
                length = _dist(s_pt, e_pt)

        sta_s = pipe.get("sta_start") or pipe.get("start_station") or pipe.get("refStart")
        sta_e = pipe.get("sta_end") or pipe.get("end_station") or pipe.get("refEnd")
        if sta_s and sta_e and length <= 0:
            a = station_to_feet(sta_s)
            b = station_to_feet(sta_e)
            if a is not None and b is not None:
                length = abs(b - a)

        side = pipe.get("side") or pipe.get("offset_side")
        offset = pipe.get("offset") or pipe.get("offset_ft")

        extra = {
            "start_structure": pipe.get("start_structure") or pipe.get("startStructure"),
            "end_structure": pipe.get("end_structure") or pipe.get("endStructure"),
            "sta_start_raw": sta_s,
            "sta_end_raw": sta_e,
        }

        if pts and len(pts) >= 2 and not cl.get("synthetic_geometry"):
            added = _split_polyline_runs(pts, network=network, size=size, layer=layer or name, cl=cl)
            for r in added:
                r.update({k: v for k, v in extra.items() if v})
                _stamp_civil_pipe_location(r, sta_s, sta_e, length, side, offset)
            rows.extend(added)
            continue

        row = _segment_row(
            network=network,
            size=size,
            length=length,
            layer=layer or name,
            pts=pts if not cl.get("synthetic_geometry") else [],
            cl=cl,
            source="CAD PIPE",
            method="Pipe associated to centerline",
            name=name,
        )
        if row:
            row.update({k: v for k, v in extra.items() if v})
            _stamp_civil_pipe_location(row, sta_s, sta_e, length, side, offset)
            rows.append(row)

    for pl in extraction.get("polylines") or []:
        layer = str(pl.get("layer") or "")
        network = detect_network(layer, pl.get("name"))
        if not network and not any(
            k in layer.lower() for k in ("pipe", "water", "sewer", "storm", "san", "casing", "main")
        ):
            continue
        if any(h in layer.lower() for h in ("centerline", "centreline", "alignment")) and not network:
            continue
        size = extract_size_label(layer, pl.get("name"))
        pts = _as_points(pl.get("points") or pl.get("vertices") or pl.get("coords"))
        if pts:
            rows.extend(_split_polyline_runs(pts, network=network, size=size, layer=layer, cl=cl))
        else:
            length = float(pl.get("length") or 0)
            row = _segment_row(
                network=network,
                size=size,
                length=length,
                layer=layer,
                pts=[],
                cl=cl,
                source="CAD POLYLINE",
                method="Polyline length (no vertices for offset)",
            )
            if row:
                row["flags"] = list(row.get("flags") or []) + ["line_not_associated_with_alignment"]
                rows.append(row)

    for line in extraction.get("lines") or []:
        layer = str(line.get("layer") or "")
        network = detect_network(layer, line.get("name"))
        if not network and not any(
            k in layer.lower() for k in ("pipe", "water", "sewer", "storm", "san", "casing", "main")
        ):
            continue
        size = extract_size_label(layer, line.get("name"))
        s = _as_point(line.get("start"))
        e = _as_point(line.get("end"))
        pts = [p for p in (s, e) if p]
        length = float(line.get("length") or (_dist(pts[0], pts[1]) if len(pts) == 2 else 0))
        row = _segment_row(
            network=network,
            size=size,
            length=length,
            layer=layer,
            pts=pts,
            cl=cl,
            source="CAD LINE",
            method="Line endpoints projected to centerline",
        )
        if row:
            rows.append(row)

    return rows


def _stamp_civil_pipe_location(
    row: dict[str, Any],
    sta_s: Any,
    sta_e: Any,
    length: float,
    side: Any,
    offset: Any,
) -> None:
    """Apply Civil start/end station (one or both) and side/offset onto a linear row."""
    if not row.get("from_station") or not row.get("to_station"):
        a = station_to_feet(sta_s) if sta_s not in (None, "") else None
        b = station_to_feet(sta_e) if sta_e not in (None, "") else None
        if a is not None and b is not None:
            row["from_station"] = feet_to_station(a)
            row["to_station"] = feet_to_station(b)
            if float(row.get("quantity_lf") or 0) <= 0:
                row["quantity_lf"] = round(abs(b - a), 2)
                row["length"] = row["quantity_lf"]
            row["method"] = f"Pipe start/end station on CL ({row['from_station']} → {row['to_station']})"
        elif a is not None and length > 0:
            row["from_station"] = feet_to_station(a)
            row["to_station"] = feet_to_station(a + length)
            row["method"] = f"Pipe start station + 2D length ({row['from_station']} + {length:.1f} lf)"
        elif b is not None and length > 0:
            row["to_station"] = feet_to_station(b)
            row["from_station"] = feet_to_station(max(0.0, b - length))
            row["method"] = f"Pipe end station − 2D length ({row['to_station']} − {length:.1f} lf)"
        if row.get("from_station") and row.get("to_station"):
            row["flags"] = [f for f in (row.get("flags") or []) if f != "line_not_associated_with_alignment"]

    if side:
        row["side"] = _side_code(str(side)) or row.get("side")
        row["side_of_alignment"] = row.get("side")
    if offset is not None and offset != "":
        try:
            off_f = abs(float(offset))
            row["offset_ft"] = off_f
            row["offset"] = format_offset(off_f, row.get("side"))
        except (TypeError, ValueError):
            parsed_side = _side_code(str(offset))
            if parsed_side:
                row["side"] = row.get("side") or parsed_side
            row["offset"] = str(offset)


def _norm_obj_name(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


def _find_connection_by_name(name: Any, connections: list[dict[str, Any]]) -> dict[str, Any] | None:
    needle = _norm_obj_name(name)
    if len(needle) < 2:
        return None
    exact = [c for c in connections if _norm_obj_name(c.get("name")) == needle]
    if exact:
        return exact[0]
    for c in connections:
        other = _norm_obj_name(c.get("name"))
        if other and (needle in other or other in needle):
            return c
    return None


def _linear_needs_station(row: dict[str, Any]) -> bool:
    return not str(row.get("from_station") or "").strip() or not str(row.get("to_station") or "").strip()


def _linear_net_compat(seg: dict[str, Any], conn: dict[str, Any]) -> bool:
    sn = str(seg.get("network") or "").lower()
    cn = str(conn.get("network") or "").lower()
    if sn and cn and sn not in {"utility", ""} and cn not in {"utility", ""}:
        return sn == cn
    su = str(seg.get("utility") or "").lower()
    cu = str(conn.get("utility") or "").lower()
    if su and cu and su != "underground utility" and cu != "underground utility":
        return su == cu
    sl = str(seg.get("layer") or "").lower()
    clayer = str(conn.get("layer") or "").lower()
    if sl and sl not in {"0", "defpoints"} and clayer and sl == clayer:
        return True
    # Generic Civil pipes (layer 0) may connect any stationed structure
    if sn in {"", "utility"} or su in {"", "underground utility"}:
        return True
    return False


def _apply_end_locations(row: dict[str, Any], a: dict[str, Any], b: dict[str, Any], method: str) -> None:
    sa = station_to_feet(a.get("station"))
    sb = station_to_feet(b.get("station"))
    if sa is None or sb is None:
        return
    if sa <= sb:
        row["from_station"] = feet_to_station(sa)
        row["to_station"] = feet_to_station(sb)
        from_c, to_c = a, b
    else:
        row["from_station"] = feet_to_station(sb)
        row["to_station"] = feet_to_station(sa)
        from_c, to_c = b, a
    side = _side_code(from_c.get("side") or to_c.get("side"))
    off = from_c.get("offset_ft")
    if off is None:
        off = to_c.get("offset_ft")
    if off is None:
        m = re.search(r"[-+]?\d+(?:\.\d+)?", str(from_c.get("offset") or to_c.get("offset") or ""))
        off = float(m.group(0)) if m else None
    if side:
        row["side"] = side
        row["side_of_alignment"] = side
    if off is not None:
        row["offset_ft"] = abs(float(off))
        row["offset"] = format_offset(row["offset_ft"], side)
        row["from_offset"] = from_c.get("offset") or format_offset(from_c.get("offset_ft"), from_c.get("side"))
        row["to_offset"] = to_c.get("offset") or format_offset(to_c.get("offset_ft"), to_c.get("side"))
        fo, to_ = from_c.get("offset_ft"), to_c.get("offset_ft")
        if fo is not None and to_ is not None and abs(float(fo) - float(to_)) >= _NONPARALLEL_OFFSET_DELTA_FT:
            row["nonparallel"] = True
    row["method"] = method
    row["flags"] = [f for f in (row.get("flags") or []) if f != "line_not_associated_with_alignment"]


def _fill_linear_from_connections(
    segments: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> None:
    """Civil pipe networks: station a run from its start/end structures or nearby fittings."""
    if not segments:
        return

    # 1) Named start/end structures on the pipe (Civil 3D pipe network)
    for seg in segments:
        if not _linear_needs_station(seg):
            continue
        a = _find_connection_by_name(seg.get("start_structure"), connections)
        b = _find_connection_by_name(seg.get("end_structure"), connections)
        if a and b and a.get("station") and b.get("station"):
            _apply_end_locations(
                seg, a, b, f"Pipe network structures '{a.get('name')}' → '{b.get('name')}'"
            )

    stationed = [c for c in connections if station_to_feet(c.get("station")) is not None]
    used: set[int] = set()

    # 2) Pair fittings whose station span ≈ pipe 2D length (parallel-to-CL networks)
    blanks = [s for s in segments if _linear_needs_station(s)]
    blanks.sort(key=lambda s: float(s.get("quantity_lf") or s.get("length") or 0), reverse=True)
    for seg in blanks:
        length = float(seg.get("quantity_lf") or seg.get("length") or 0)
        if length < 1:
            continue
        best: tuple[float, dict[str, Any], dict[str, Any]] | None = None
        for i, a in enumerate(stationed):
            if id(a) in used or not _linear_net_compat(seg, a):
                continue
            sa = station_to_feet(a.get("station"))
            if sa is None:
                continue
            for b in stationed[i + 1 :]:
                if id(b) in used or not _linear_net_compat(seg, b):
                    continue
                sb = station_to_feet(b.get("station"))
                if sb is None:
                    continue
                delta = abs(sb - sa)
                if delta < 1:
                    continue
                err = abs(delta - length)
                rel = err / max(length, delta)
                if rel > 0.35 and err > 25:
                    continue
                score = rel
                if seg.get("size") and (
                    str(a.get("size") or "") == str(seg.get("size"))
                    or str(b.get("size") or "") == str(seg.get("size"))
                ):
                    score -= 0.08
                if best is None or score < best[0]:
                    best = (score, a, b)
        if best:
            _, a, b = best
            used.add(id(a))
            used.add(id(b))
            _apply_end_locations(
                seg, a, b, f"Fitting stations {a.get('station')} → {b.get('station')} (span ≈ pipe length)"
            )

    # 3) Remaining blanks: walk station envelope of that utility (Civil draft)
    leftovers = [s for s in segments if _linear_needs_station(s)]
    if leftovers and stationed:
        by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for c in stationed:
            by_key[str(c.get("network") or c.get("utility") or "")].append(c)
        for seg in leftovers:
            length = float(seg.get("quantity_lf") or seg.get("length") or 0)
            if length < 1:
                continue
            pool = [
                c
                for c in stationed
                if _linear_net_compat(seg, c)
            ]
            fts = sorted(station_to_feet(c.get("station")) for c in pool if station_to_feet(c.get("station")) is not None)
            if not fts:
                continue
            cursor = fts[0]
            # If another leftover already placed on this network, continue from last to_station
            same = [
                s
                for s in segments
                if s is not seg
                and not _linear_needs_station(s)
                and _linear_net_compat(s, pool[0])
            ]
            if same:
                ends = [station_to_feet(s.get("to_station")) for s in same]
                ends = [e for e in ends if e is not None]
                if ends:
                    cursor = max(cursor, max(ends))
            seg["from_station"] = feet_to_station(cursor)
            seg["to_station"] = feet_to_station(cursor + length)
            typ_side, typ_off = typical_network_offset(segments, seg.get("network"))
            if not seg.get("side"):
                # Prefer a fitting's side at this utility
                for c in pool:
                    if c.get("side"):
                        seg["side"] = _side_code(c.get("side"))
                        break
                seg["side"] = seg.get("side") or typ_side
                seg["side_of_alignment"] = seg.get("side")
            if seg.get("offset_ft") is None:
                for c in pool:
                    if c.get("offset_ft") is not None:
                        seg["offset_ft"] = c.get("offset_ft")
                        break
                if seg.get("offset_ft") is None:
                    seg["offset_ft"] = typ_off
                if seg.get("offset_ft") is not None:
                    seg["offset"] = format_offset(float(seg["offset_ft"]), seg.get("side"))
            seg["method"] = (
                f"Stationed along {seg.get('utility') or 'utility'} using fitting envelope "
                f"from {seg['from_station']}"
            )
            seg["flags"] = [f for f in (seg.get("flags") or []) if f != "line_not_associated_with_alignment"]
            seg["flags"] = list(seg.get("flags") or []) + ["station_inferred_from_fittings"]

    # Side/offset only (stations already known)
    for seg in segments:
        if not seg.get("from_station"):
            continue
        if seg.get("side") and seg.get("offset"):
            continue
        typ_side, typ_off = typical_network_offset(
            [s for s in segments if s.get("side") and s.get("offset")],
            seg.get("network"),
        )
        if not typ_side:
            for c in stationed:
                if _linear_net_compat(seg, c) and c.get("side"):
                    typ_side = _side_code(c.get("side"))
                    if typ_off is None:
                        typ_off = c.get("offset_ft")
                    break
        if not seg.get("side") and typ_side:
            seg["side"] = typ_side
            seg["side_of_alignment"] = typ_side
        if not seg.get("offset") and typ_off is not None:
            seg["offset_ft"] = typ_off
            seg["offset"] = format_offset(float(typ_off), seg.get("side"))


def _angle_from_name(*texts: Any) -> str:
    blob = " ".join(str(t) for t in texts if t)
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*°", blob)
    if m:
        return f"{m.group(1)}°"
    m = re.search(r"\b(90|45|22\.5|11\.25|60|30)\b", blob)
    if m:
        return f"{m.group(1)}°"
    return ""


def _fitting_insert_point(block: dict[str, Any]) -> tuple[float, float] | None:
    for key in ("insert", "position", "location", "point", "ref_point", "geometry_point", "center"):
        pt = _as_point(block.get(key))
        if pt:
            return pt
    x = block.get("easting") or block.get("x") or block.get("pos_x")
    y = block.get("northing") or block.get("y") or block.get("pos_y")
    try:
        if x is not None and y is not None:
            return (float(x), float(y))
    except (TypeError, ValueError):
        pass
    bag_pt = point_from_property_bag(block)
    return (float(bag_pt[0]), float(bag_pt[1])) if bag_pt else None


def _infer_side_offset_from_segments(
    station: str,
    network: str | None,
    segments: list[dict[str, Any]],
) -> tuple[str, float | None, str]:
    """Copy side/offset from a linear run that covers this station."""
    sta = station_to_feet(station)
    if sta is None or not segments:
        return "", None, ""
    best: dict[str, Any] | None = None
    best_dist = float("inf")
    for s in segments:
        if network and s.get("network") and s.get("network") != network:
            continue
        a = station_to_feet(str(s.get("from_station") or ""))
        b = station_to_feet(str(s.get("to_station") or ""))
        if a is None or b is None:
            continue
        lo, hi = min(a, b), max(a, b)
        if lo - 2 <= sta <= hi + 2:
            dist = 0.0 if lo <= sta <= hi else min(abs(sta - lo), abs(sta - hi))
            if dist < best_dist:
                best_dist = dist
                best = s
    if not best:
        return "", None, ""
    side = _side_code(str(best.get("side") or best.get("side_of_alignment") or ""))
    off = best.get("offset_ft")
    if off is None and best.get("offset") is not None:
        m = re.search(r"[-+]?\d*\.?\d+", str(best.get("offset")))
        try:
            off = float(m.group(0)) if m else None
        except (TypeError, ValueError):
            off = None
    label = str(best.get("offset") or "") or format_offset(float(off) if off is not None else None, side)
    return side, float(off) if off is not None else None, label


def _resolve_fitting_location(
    block: dict[str, Any],
    cl: dict[str, Any],
    *,
    network: str | None = None,
    segments: list[dict[str, Any]] | None = None,
    labels: list[dict[str, Any]] | None = None,
    pipe_ends: list[dict[str, Any]] | None = None,
    type_label: str = "",
) -> dict[str, Any]:
    """Civil 3D StationOffset, then properties, attributes, labels, pipe joints."""
    alignment = cl.get("name") or "CL"
    insert = _fitting_insert_point(block)
    loc = _locate(insert, cl)

    bag = location_from_property_bag(block)
    attrs = location_from_block_attributes(block)
    name_blob = " ".join(str(block.get(k) or "") for k in ("name", "description", "type", "layer"))
    name_parsed = parse_station_offset_text(name_blob)

    prop_sta = (
        bag.get("station")
        or attrs.get("station")
        or coerce_station(block.get("station") or block.get("sta") or block.get("ref_station") or block.get("rawStation"))
        or (name_parsed or {}).get("station")
        or ""
    )
    prop_side = _side_code(
        bag.get("side")
        or attrs.get("side")
        or block.get("side")
        or block.get("offset_side")
        or (name_parsed or {}).get("side")
    )
    prop_off_f = bag.get("offset_ft")
    if prop_off_f is None:
        prop_off_f = attrs.get("offset_ft")
    if prop_off_f is None:
        prop_off_f = (name_parsed or {}).get("offset_ft")

    station = loc["station"] or coerce_station(prop_sta) or str(prop_sta or "").strip()
    # Raw numbers like 548.11 → 5+48.11
    if station and "+" not in station:
        station = coerce_station(station) or station
    side = loc["side"] or prop_side
    offset_ft = loc["offset_ft"] if loc["offset_ft"] is not None else prop_off_f
    offset_label = loc["offset_label"] or format_offset(offset_ft, side)
    method_bits: list[str] = []
    if loc["associated"]:
        method_bits.append("Civil StationOffset (insert → CL)")
    elif prop_sta:
        method_bits.append("Civil station property / attribute")
    if prop_side or prop_off_f is not None:
        method_bits.append("Civil side/offset property")

    # Nearby plan-sheet / model callouts (STA + 15' LT)
    if labels and (not station or not side or offset_ft is None):
        hit = match_label_to_fitting(
            name=str(block.get("name") or ""),
            layer=str(block.get("layer") or ""),
            type_label=type_label or str(block.get("type") or ""),
            insert=insert,
            labels=labels,
        )
        if hit:
            station = station or hit.get("station") or ""
            side = side or hit.get("side") or ""
            if offset_ft is None:
                offset_ft = hit.get("offset_ft")
            method_bits.append("plan-sheet station/offset label")

    # Snap to pipe start/end (Civil structures sit on pipe joints)
    if pipe_ends and (not station or not side or offset_ft is None):
        hit = match_pipe_end(insert=insert, network=network, ends=pipe_ends)
        if hit:
            station = station or hit.get("station") or ""
            side = side or hit.get("side") or ""
            if offset_ft is None:
                offset_ft = hit.get("offset_ft")
            method_bits.append("pipe-network joint")

    if station and (not side or offset_ft is None) and segments:
        inf_side, inf_off, inf_label = _infer_side_offset_from_segments(station, network, segments)
        if not side and inf_side:
            side = inf_side
        if offset_ft is None and inf_off is not None:
            offset_ft = inf_off
            offset_label = inf_label or format_offset(offset_ft, side)
        elif not offset_label and inf_label:
            offset_label = inf_label
        if inf_side or inf_off is not None:
            method_bits.append("side/offset from pipe run at station")

    # Whole-network typical offset (water often a constant 15' LT, etc.)
    if station and (not side or offset_ft is None) and segments:
        typ_side, typ_off = typical_network_offset(segments, network)
        if not side and typ_side:
            side = typ_side
        if offset_ft is None and typ_off is not None:
            offset_ft = typ_off
        if typ_side or typ_off is not None:
            method_bits.append("typical network offset")

    if offset_ft is not None and not offset_label:
        offset_label = format_offset(offset_ft, side)
    elif offset_ft is not None and side and "CL" in offset_label and side != "CL":
        offset_label = format_offset(offset_ft, side)

    associated = bool(loc["associated"] or (station and (side or offset_ft is not None)))
    return {
        "station": station,
        "side": side,
        "offset_ft": round(float(offset_ft), 2) if offset_ft is not None else None,
        "offset_label": offset_label,
        "alignment": alignment,
        "associated": associated,
        "insert": insert,
        "method": ", ".join(method_bits) or "no CL association",
    }


def _connections_from_blocks(
    extraction: dict[str, Any],
    cl: dict[str, Any],
    *,
    segments: list[dict[str, Any]] | None = None,
    labels: list[dict[str, Any]] | None = None,
    pipe_ends: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    segs = segments or []
    labs = labels or []
    ends = pipe_ends or []
    for block in extraction.get("blocks") or []:
        name = str(block.get("name") or "BLOCK")
        layer = str(block.get("layer") or "")
        btype = str(block.get("type") or "")
        classified = classify_fitting(name, layer) or classify_fitting(name, btype)
        blob = f"{name} {layer} {btype} {block.get('description') or ''}".lower()
        is_conn = bool(classified) or any(
            k in blob
            for k in (
                "bend",
                "elbow",
                "tee",
                "wye",
                "valve",
                "hydrant",
                "fitting",
                "reducer",
                "cross",
                "plug",
                "cap",
                "cleanout",
                "manhole",
                "inlet",
                "junction",
                "connection",
                "structure",
                "casing",
                "sleeve",
            )
        )
        if not is_conn:
            continue

        network = detect_network(name, layer, btype, block.get("description"))
        size = extract_size_label(name, layer, block.get("size"), block.get("description"), btype)
        type_label = classified[0] if classified else name
        if classified and classified[0] == "Manhole" and network == "sanitary":
            type_label = "Sanitary Sewer Manhole"
        elif classified and classified[0] == "Manhole" and network == "storm":
            type_label = "Storm Sewer Manhole"

        loc = _resolve_fitting_location(
            block,
            cl,
            network=network,
            segments=segs,
            labels=labs,
            pipe_ends=ends,
            type_label=type_label,
        )
        angle = _angle_from_name(name, btype, block.get("description"))
        connects = _network_label(network) if network else ""
        if size:
            connects = f"{_size_display(size)} {connects}".strip()

        flags: list[str] = []
        if not loc["associated"]:
            flags.append("line_not_associated_with_alignment")
        if not loc["station"]:
            flags.append("missing_station")
        if not loc["side"] or loc["offset_ft"] is None:
            flags.append("missing_side_offset")
        if type_label.lower() in {"block", name.lower()} and not classified:
            flags.append("unidentified_fitting")
        if not size:
            flags.append("unknown_size")

        rows.append(
            {
                "type": type_label,
                "connection_type": type_label,
                "size": _size_display(size),
                "station": loc["station"],
                "side": loc["side"],
                "offset_ft": loc["offset_ft"],
                "offset": loc["offset_label"],
                "direction_from_alignment": loc["side"],
                "angle": angle,
                "angle_type": angle or type_label,
                "connects_to": connects,
                "utility": _network_label(network),
                "network": network or "utility",
                "quantity": 1,
                "unit": "EA",
                "layer": layer,
                "alignment": loc["alignment"],
                "source": "CAD block / fitting",
                "method": (
                    f"{loc['method']}: '{name}' @ {loc['station'] or '—'} "
                    f"({loc['offset_label'] or 'no offset'})"
                ),
                "name": name,
                "flags": flags,
                "confidence": 90.0 if loc["associated"] and classified else 70.0,
            }
        )
    return rows


def _bends_from_polylines(extraction: dict[str, Any], cl: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pl in extraction.get("polylines") or []:
        layer = str(pl.get("layer") or "")
        network = detect_network(layer, pl.get("name"))
        if not network and not any(
            k in layer.lower() for k in ("pipe", "water", "sewer", "storm", "san", "casing", "main")
        ):
            continue
        pts = _as_points(pl.get("points") or pl.get("vertices") or pl.get("coords"))
        if len(pts) < 3:
            continue
        size = extract_size_label(layer, pl.get("name"))
        for i in range(1, len(pts) - 1):
            a, b, c = pts[i - 1], pts[i], pts[i + 1]
            v1 = (b[0] - a[0], b[1] - a[1])
            v2 = (c[0] - b[0], c[1] - b[1])
            n1 = math.hypot(*v1)
            n2 = math.hypot(*v2)
            if n1 < 1e-6 or n2 < 1e-6:
                continue
            cosang = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
            deflection = abs(math.degrees(math.acos(cosang)))
            if deflection < _MIN_BEND_DEG:
                continue
            # Snap to common bend angles
            snapped = deflection
            for cand in (11.25, 22.5, 45.0, 60.0, 90.0):
                if abs(deflection - cand) <= 6:
                    snapped = cand
                    break
            loc = _locate(b, cl)
            util = _network_label(network)
            size_d = _size_display(size)
            rows.append(
                {
                    "type": "Bend",
                    "connection_type": f"Bend ({snapped:g}°)",
                    "size": size_d,
                    "station": loc["station"],
                    "side": loc["side"],
                    "offset_ft": loc["offset_ft"],
                    "offset": loc["offset_label"],
                    "direction_from_alignment": loc["side"],
                    "angle": f"{snapped:g}°",
                    "angle_type": f"{snapped:g}°",
                    "connects_to": f"{size_d} {util}".strip(),
                    "utility": util,
                    "network": network or "utility",
                    "quantity": 1,
                    "unit": "EA",
                    "layer": layer,
                    "alignment": loc["alignment"],
                    "source": "Polyline deflection",
                    "method": f"Vertex deflection {deflection:.1f}° → {snapped:g}° on CL",
                    "name": f"BEND@{loc['station'] or i}",
                    "flags": [] if loc["associated"] else ["line_not_associated_with_alignment"],
                    "confidence": 88.0 if loc["associated"] else 65.0,
                }
            )
    return rows


def _merge_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    text_rows = [r for r in rows if "text" in str(r.get("source") or "").lower()]
    geo_rows = [r for r in rows if r not in text_rows]
    out = list(text_rows)
    for g in geo_rows:
        dup = False
        for t in out:
            if t.get("network") != g.get("network"):
                continue
            if (t.get("size") or "") != (g.get("size") or ""):
                continue
            tq = float(t.get("quantity_lf") or 0)
            gq = float(g.get("quantity_lf") or 0)
            if tq > 0 and abs(tq - gq) / max(tq, 1) < 0.05:
                dup = True
                break
        if not dup:
            out.append(g)

    def sort_key(r: dict[str, Any]) -> tuple:
        ft = station_to_feet(str(r.get("from_station") or "")) or 0.0
        return (str(r.get("item") or r.get("utility") or ""), str(r.get("size") or ""), ft)

    out.sort(key=sort_key)
    return out


def build_bid_summary_from_detail(
    segments: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    *,
    eoq_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Roll Bid Quantity Summary FROM detail tables (source of truth)."""
    lf_groups: dict[tuple[str, str], float] = defaultdict(float)
    for s in segments:
        key = (str(s.get("item") or s.get("utility") or "Utility"), str(s.get("size") or ""))
        lf_groups[key] += float(s.get("quantity_lf") or s.get("length") or 0)

    ea_groups: dict[tuple[str, str, str], float] = defaultdict(float)
    for c in connections:
        typ = str(c.get("type") or c.get("connection_type") or "Fitting")
        # Group bends by angle when present
        angle = str(c.get("angle") or "")
        if "bend" in typ.lower() and angle:
            typ = f"Bend {angle}"
        key = (typ, str(c.get("size") or ""), str(c.get("utility") or ""))
        ea_groups[key] += float(c.get("quantity") or 1)

    # Optional bid item codes from EOQ lines
    code_by_desc: dict[str, str] = {}
    for item in eoq_items or []:
        desc = str(item.get("description") or "").strip().lower()
        code = str(item.get("item_code") or item.get("csi_code") or "").strip()
        if desc and code:
            code_by_desc[desc] = code

    summary: list[dict[str, Any]] = []
    for (util, size), qty in sorted(lf_groups.items(), key=lambda x: (x[0][0], x[0][1])):
        desc = f"{size + ' ' if size else ''}{util}".strip()
        code = ""
        for d, c in code_by_desc.items():
            if util.lower() in d and (not size or size.replace('"', "").split("-")[0] in d):
                code = c
                break
        summary.append(
            {
                "bid_item": code,
                "description": desc,
                "unit": "LF",
                "quantity": round(qty, 2),
                "detail_source": "Linear Quantity Breakdown",
                "rollup_note": f"Sum of station runs = {round(qty, 2)} LF",
            }
        )

    for (typ, size, util), qty in sorted(ea_groups.items(), key=lambda x: (x[0][0], x[0][1])):
        desc = f"{size + ' ' if size else ''}{typ}".strip()
        if util and util.lower() not in desc.lower():
            desc = f"{desc} ({util})"
        code = ""
        for d, c in code_by_desc.items():
            if typ.lower().split()[0] in d and (not size or size.replace('"', "")[:2] in d):
                code = c
                break
        summary.append(
            {
                "bid_item": code,
                "description": desc,
                "unit": "EA",
                "quantity": round(qty, 0) if abs(qty - round(qty)) < 0.01 else round(qty, 2),
                "detail_source": "Fittings / Bends / Connections",
                "rollup_note": f"Count of discrete components = {int(qty) if abs(qty-round(qty))<0.01 else qty} EA",
            }
        )
    return summary


def build_qa_flags(
    segments: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    cl: dict[str, Any],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if not cl.get("points") or len(cl.get("points") or []) < 2:
        flags.append(
            {
                "severity": "high",
                "issue": "no_centerline_geometry",
                "message": "No centerline geometry found — stations/offsets may be incomplete. Verify CL in DWG.",
                "object": cl.get("name") or "CL",
                "station": "",
                "suggestion": "Ensure roadway centerline / alignment exists in CAD (named CL / CENTERLINE).",
            }
        )
    elif not cl.get("is_centerline"):
        flags.append(
            {
                "severity": "medium",
                "issue": "centerline_proxy",
                "message": f"Using proxy alignment '{cl.get('name')}' — confirm it is the project centerline.",
                "object": cl.get("name"),
                "station": "",
                "suggestion": "Rename/include true CL alignment for stationing.",
            }
        )

    for s in segments:
        for f in s.get("flags") or []:
            flags.append(
                {
                    "severity": "medium" if f != "unknown_size" else "low",
                    "issue": f,
                    "message": f"Linear run flagged: {f}",
                    "object": s.get("description") or s.get("item"),
                    "station": f"{s.get('from_station')}–{s.get('to_station')}",
                    "suggestion": "Review association to centerline / size callout.",
                }
            )
        # Overlap heuristic: same utility+size overlapping station ranges
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for s in segments:
        by_key[(str(s.get("network")), str(s.get("size")))].append(s)
    for key, group in by_key.items():
        for i, a in enumerate(group):
            af = station_to_feet(a.get("from_station"))
            at = station_to_feet(a.get("to_station"))
            if af is None or at is None:
                continue
            a0, a1 = min(af, at), max(af, at)
            for b in group[i + 1 :]:
                bf = station_to_feet(b.get("from_station"))
                bt = station_to_feet(b.get("to_station"))
                if bf is None or bt is None:
                    continue
                b0, b1 = min(bf, bt), max(bf, bt)
                overlap = max(0.0, min(a1, b1) - max(a0, b0))
                if overlap > 5:
                    flags.append(
                        {
                            "severity": "high",
                            "issue": "overlapping_pipe",
                            "message": f"Overlapping {key[1]} {key[0]} runs (~{overlap:.0f} ft station overlap)",
                            "object": a.get("description"),
                            "station": f"{a.get('from_station')} / {b.get('from_station')}",
                            "suggestion": "Check for duplicate geometry or double-counted segments.",
                        }
                    )

    for c in connections:
        for f in c.get("flags") or []:
            flags.append(
                {
                    "severity": "high" if f == "unidentified_fitting" else "medium",
                    "issue": f,
                    "message": f"Fitting flagged: {f}",
                    "object": f"{c.get('type')} {c.get('size')}".strip(),
                    "station": c.get("station") or "",
                    "suggestion": "Identify block / verify CL projection.",
                }
            )
        conf = float(c.get("confidence") or 100)
        if conf < 75:
            flags.append(
                {
                    "severity": "medium",
                    "issue": "low_ai_confidence",
                    "message": f"Low confidence ({conf:.0f}) on {c.get('type')}",
                    "object": c.get("name") or c.get("type"),
                    "station": c.get("station") or "",
                    "suggestion": "Engineer review recommended.",
                }
            )

    # Disconnected endpoints: segment ends with no nearby fitting within 5 ft station
    conn_stas = [station_to_feet(c.get("station")) for c in connections]
    conn_stas = [x for x in conn_stas if x is not None]
    for s in segments:
        for end_key in ("from_station", "to_station"):
            st = station_to_feet(s.get(end_key))
            if st is None or not conn_stas:
                continue
            if min(abs(st - cs) for cs in conn_stas) > 8:
                # Only flag if length is substantial mid-run ends are ok at stubs
                pass  # soft — skip noisy disconnected flags for now

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (severity_rank.get(str(f.get("severity")), 9), str(f.get("issue"))))
    return flags


def build_utilities_detail(
    extraction: dict[str, Any],
    *,
    eoq_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build CL-based stationing, fittings, bid summary rollup, and QA flags."""
    cl = _build_centerline(extraction if isinstance(extraction, dict) else {})
    text_segs = _segments_from_texts(extraction, cl)
    geo_segs = _segments_from_geometry(extraction, cl)
    segments = _merge_segments(text_segs + geo_segs)

    labels = collect_location_labels(list(extraction.get("texts") or []))
    pipe_ends = collect_pipe_ends(extraction)
    # After linear stationing, copy side/offset onto pipe ends that only had stations
    for end in pipe_ends:
        if end.get("station") and (not end.get("side") or end.get("offset_ft") is None):
            inf_side, inf_off, _ = _infer_side_offset_from_segments(
                str(end.get("station") or ""),
                str(end.get("network") or "") or None,
                segments,
            )
            if not end.get("side") and inf_side:
                end["side"] = inf_side
            if end.get("offset_ft") is None and inf_off is not None:
                end["offset_ft"] = inf_off

    connections = _connections_from_blocks(
        extraction, cl, segments=segments, labels=labels, pipe_ends=pipe_ends
    )
    connections.extend(_bends_from_polylines(extraction, cl))

    seen: set[str] = set()
    uniq_conn: list[dict[str, Any]] = []
    for c in connections:
        key = (
            f"{c.get('utility')}|{c.get('type')}|{c.get('station')}|"
            f"{c.get('size')}|{c.get('angle')}|{c.get('name')}"
        ).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq_conn.append(c)

    def conn_key(c: dict[str, Any]) -> tuple:
        ft = station_to_feet(str(c.get("station") or "")) or 0.0
        return (str(c.get("utility") or ""), ft, str(c.get("type") or ""))

    uniq_conn.sort(key=conn_key)

    # Linear rows often have length only (APS pipes). Station them from Civil
    # start/end structures or fittings — same association Civil 3D uses.
    _fill_linear_from_connections(segments, uniq_conn)

    bid_summary = build_bid_summary_from_detail(segments, uniq_conn, eoq_items=eoq_items)
    qa_flags = build_qa_flags(segments, uniq_conn, cl)

    networks = sorted(
        {str(s.get("utility")) for s in segments} | {str(c.get("utility")) for c in uniq_conn}
    )
    return {
        "alignment": {
            "name": cl.get("name"),
            "layer": cl.get("layer"),
            "length": round(float(cl.get("length") or 0), 2),
            "sta_start": feet_to_station(float(cl.get("sta_start") or 0)),
            "source": cl.get("source"),
            "is_centerline": bool(cl.get("is_centerline")),
            "has_geometry": len(cl.get("points") or []) >= 2,
        },
        "segments": segments,
        "connections": uniq_conn,
        "bid_summary": bid_summary,
        "qa_flags": qa_flags,
        "summary": {
            "segment_count": len(segments),
            "connection_count": len(uniq_conn),
            "bid_item_count": len(bid_summary),
            "qa_flag_count": len(qa_flags),
            "utilities": networks,
            "total_lf": round(sum(float(s.get("quantity_lf") or 0) for s in segments), 2),
            "centerline": cl.get("name"),
        },
    }
