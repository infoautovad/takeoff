"""Underground utility stationing & connection tables from CAD takeoff.

Builds two detail tables for Excel export:
1. Station-to-station pipe runs (utility, from/to station, direction vs alignment, LF)
2. Bends / fittings / connections located along the alignment

Works from:
- Plan/DWG text callouts with STA ranges
- Pipe / polyline geometry projected onto a reference alignment
- Fitting / bend block inserts projected to station + left/right of CL
"""

from __future__ import annotations

import math
import re
from typing import Any

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
_SIZE = re.compile(r"(?P<size>\d{1,2}(?:\.\d+)?)\s*(?:\"|''|in(?:ch(?:es)?)?|-?\s*inch)", re.I)

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

_ALIGN_NAME_HINTS = (
    "alignment",
    "centerline",
    "centreline",
    "cl-",
    " cl",
    "roadway",
    "baseline",
    "profile",
)


def station_to_feet(sta: str | None) -> float | None:
    if not sta:
        return None
    m = re.match(r"(\d+)\+(\d+(?:\.\d+)?)", str(sta).strip())
    if not m:
        return None
    return float(m.group(1)) * 100.0 + float(m.group(2))


def feet_to_station(feet: float | None) -> str:
    if feet is None or not math.isfinite(feet):
        return ""
    feet = max(0.0, float(feet))
    plus = int(feet // 100)
    rem = feet - plus * 100
    if abs(rem - round(rem)) < 0.05:
        return f"{plus}+{int(round(rem)):02d}"
    return f"{plus}+{rem:05.2f}"


def _network_label(network: str | None) -> str:
    return {
        "water": "Water",
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


def _project_point_on_polyline(
    point: tuple[float, float],
    chain: list[tuple[float, float]],
) -> tuple[float, float, str] | None:
    """Return (station_feet_along, signed_offset, side) where side is Left/Right/On."""
    if len(chain) < 2:
        return None
    best_d = float("inf")
    best_sta = 0.0
    best_side = "On"
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
        # 2D cross for side: positive = left of direction of travel
        cross = dx * (point[1] - y1) - dy * (point[0] - x1)
        side = "On" if abs(cross) < 1e-6 * seg_len else ("Left" if cross > 0 else "Right")
        if d < best_d:
            best_d = d
            best_sta = cum + t_clamped * seg_len
            best_side = side
            best_off = d
        cum += seg_len
    if best_d == float("inf"):
        return None
    return best_sta, best_off, best_side


def _build_alignment_chain(extraction: dict[str, Any]) -> dict[str, Any]:
    """Pick a reference alignment polyline and starting station."""
    alignments = list(extraction.get("alignments") or [])
    polylines = list(extraction.get("polylines") or [])
    lines = list(extraction.get("lines") or [])

    candidates: list[dict[str, Any]] = []

    for a in alignments:
        pts = _as_points(a.get("points") or a.get("vertices") or a.get("coords"))
        length = float(a.get("length") or (_polyline_length(pts) if pts else 0) or 0)
        name = str(a.get("name") or a.get("layer") or "Alignment")
        sta0 = station_to_feet(str(a.get("sta_start") or a.get("staStart") or "") or None) or 0.0
        score = length
        low = name.lower()
        if any(h in low for h in _ALIGN_NAME_HINTS):
            score += 10_000
        candidates.append(
            {
                "name": name,
                "layer": a.get("layer"),
                "points": pts,
                "length": length,
                "sta_start": sta0,
                "score": score,
                "source": "alignment",
            }
        )

    for pl in polylines:
        layer = str(pl.get("layer") or "")
        name = str(pl.get("name") or layer)
        low = f"{layer} {name}".lower()
        if not any(h.strip() in low for h in _ALIGN_NAME_HINTS if h.strip()):
            # Also accept layers that look like CL without "alignment"
            if not re.search(r"\bcl\b|center\s*line|centre\s*line|baseline", low):
                continue
        pts = _as_points(pl.get("points") or pl.get("vertices") or pl.get("coords"))
        length = float(pl.get("length") or (_polyline_length(pts) if pts else 0) or 0)
        candidates.append(
            {
                "name": name or layer,
                "layer": layer,
                "points": pts,
                "length": length,
                "sta_start": 0.0,
                "score": length + 5_000,
                "source": "polyline",
            }
        )

    # Fallback: longest non-utility polyline with points
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
            candidates.append(
                {
                    "name": layer or "Reference alignment",
                    "layer": layer,
                    "points": pts,
                    "length": length,
                    "sta_start": 0.0,
                    "score": length,
                    "source": "longest_polyline",
                }
            )

    if not candidates and lines:
        # Synthetic chain from longest line
        best = max(lines, key=lambda L: float(L.get("length") or 0), default=None)
        if best and best.get("start") and best.get("end"):
            pts = [_as_point(best["start"]), _as_point(best["end"])]
            pts = [p for p in pts if p]
            if len(pts) == 2:
                candidates.append(
                    {
                        "name": str(best.get("layer") or "Line alignment"),
                        "layer": best.get("layer"),
                        "points": pts,
                        "length": float(best.get("length") or _dist(pts[0], pts[1])),
                        "sta_start": 0.0,
                        "score": float(best.get("length") or 0),
                        "source": "line",
                    }
                )

    if not candidates:
        return {
            "name": "Assumed 0+00 (no alignment geometry)",
            "layer": None,
            "points": [],
            "length": 0.0,
            "sta_start": 0.0,
            "source": "none",
        }

    best = max(candidates, key=lambda c: float(c.get("score") or 0))
    return best


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
    if not raw:
        return []
    if isinstance(raw, list):
        out: list[tuple[float, float]] = []
        for p in raw:
            pt = _as_point(p)
            if pt:
                out.append(pt)
        return out
    return []


def _segments_from_texts(extraction: dict[str, Any]) -> list[dict[str, Any]]:
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
        direction = "Increasing station" if b >= a else "Decreasing station"
        rows.append(
            {
                "utility": _network_label(network),
                "network": network or "utility",
                "size": size or "",
                "description": f"{size + ' ' if size else ''}{_network_label(network)}".strip(),
                "from_station": feet_to_station(min(a, b) if b >= a else a),
                "to_station": feet_to_station(max(a, b) if b >= a else b),
                "from_station_raw": feet_to_station(a),
                "to_station_raw": feet_to_station(b),
                "direction": direction,
                "side_of_alignment": "",
                "quantity_lf": round(length, 2),
                "unit": "LF",
                "layer": t.get("layer") or "",
                "alignment": "",
                "source": "plan/DWG text callout",
                "method": f"Station range from text: '{text[:100]}'",
            }
        )
    return rows


def _segments_from_geometry(
    extraction: dict[str, Any],
    alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    chain = list(alignment.get("points") or [])
    sta0 = float(alignment.get("sta_start") or 0.0)
    align_name = str(alignment.get("name") or "")

    def add_run(
        *,
        network: str | None,
        size: str | None,
        length: float,
        layer: str,
        pts: list[tuple[float, float]],
        entity: str,
        name: str = "",
    ) -> None:
        if length <= 0.05:
            return
        from_sta = ""
        to_sta = ""
        direction = "Along alignment"
        side = ""
        method = f"{entity} length on layer '{layer}'"
        if len(pts) >= 2 and len(chain) >= 2:
            p0 = _project_point_on_polyline(pts[0], chain)
            p1 = _project_point_on_polyline(pts[-1], chain)
            if p0 and p1:
                s0 = sta0 + p0[0]
                s1 = sta0 + p1[0]
                from_sta = feet_to_station(s0)
                to_sta = feet_to_station(s1)
                direction = "Increasing station" if s1 >= s0 else "Decreasing station"
                # Dominant side from mid-point if available
                mid = pts[len(pts) // 2]
                pm = _project_point_on_polyline(mid, chain)
                if pm:
                    side = pm[2]
                method = (
                    f"Projected {entity} endpoints onto alignment '{align_name}' "
                    f"({from_sta} → {to_sta})"
                )
        elif extraction.get("pipes"):
            # Attribute stations on pipe objects when present
            pass

        rows.append(
            {
                "utility": _network_label(network),
                "network": network or "utility",
                "size": size or "",
                "description": f"{(size + ' ') if size else ''}{_network_label(network)}".strip(),
                "from_station": from_sta,
                "to_station": to_sta,
                "from_station_raw": from_sta,
                "to_station_raw": to_sta,
                "direction": direction,
                "side_of_alignment": side,
                "quantity_lf": round(length, 2),
                "unit": "LF",
                "layer": layer,
                "alignment": align_name,
                "source": f"CAD {entity}",
                "method": method,
                "name": name,
            }
        )

    for pipe in extraction.get("pipes") or []:
        layer = str(pipe.get("layer") or "")
        name = str(pipe.get("name") or "")
        network = detect_network(name, layer, pipe.get("network"), pipe.get("description"))
        if not network and not any(
            k in f"{layer} {name}".lower() for k in ("pipe", "water", "sewer", "storm", "san", "main")
        ):
            continue
        size = extract_size_label(name, layer, pipe.get("diameter"), pipe.get("part_size"), pipe.get("description"))
        length = float(pipe.get("length") or 0)
        pts = _as_points(pipe.get("points") or pipe.get("coords"))
        # Optional start/end station attributes from Civil 3D / LandXML
        sta_s = pipe.get("sta_start") or pipe.get("start_station") or pipe.get("refStart")
        sta_e = pipe.get("sta_end") or pipe.get("end_station") or pipe.get("refEnd")
        if sta_s and sta_e and length <= 0:
            a = station_to_feet(str(sta_s))
            b = station_to_feet(str(sta_e))
            if a is not None and b is not None:
                length = abs(b - a)
        row_before = len(rows)
        add_run(
            network=network,
            size=size,
            length=length,
            layer=layer or name,
            pts=pts,
            entity="PIPE",
            name=name,
        )
        if sta_s and sta_e and rows and len(rows) > row_before:
            rows[-1]["from_station"] = str(sta_s)
            rows[-1]["to_station"] = str(sta_e)
            rows[-1]["from_station_raw"] = str(sta_s)
            rows[-1]["to_station_raw"] = str(sta_e)
            a = station_to_feet(str(sta_s))
            b = station_to_feet(str(sta_e))
            if a is not None and b is not None:
                rows[-1]["direction"] = "Increasing station" if b >= a else "Decreasing station"
                rows[-1]["method"] = f"Pipe start/end station attributes ({sta_s} → {sta_e})"

    for pl in extraction.get("polylines") or []:
        layer = str(pl.get("layer") or "")
        network = detect_network(layer, pl.get("name"))
        if not network and not any(
            k in layer.lower() for k in ("pipe", "water", "sewer", "storm", "san", "casing", "main")
        ):
            continue
        # Skip alignment-like polylines already used as CL
        if any(h in layer.lower() for h in ("centerline", "centreline", "alignment")) and not network:
            continue
        size = extract_size_label(layer, pl.get("name"))
        length = float(pl.get("length") or 0)
        pts = _as_points(pl.get("points") or pl.get("vertices") or pl.get("coords"))
        if length <= 0 and pts:
            length = _polyline_length(pts)
        add_run(
            network=network,
            size=size,
            length=length,
            layer=layer,
            pts=pts,
            entity="POLYLINE",
        )

    for line in extraction.get("lines") or []:
        layer = str(line.get("layer") or "")
        network = detect_network(layer, line.get("name"))
        if not network and not any(
            k in layer.lower() for k in ("pipe", "water", "sewer", "storm", "san", "casing", "main")
        ):
            continue
        size = extract_size_label(layer, line.get("name"))
        length = float(line.get("length") or 0)
        pts: list[tuple[float, float]] = []
        s = _as_point(line.get("start"))
        e = _as_point(line.get("end"))
        if s and e:
            pts = [s, e]
        add_run(
            network=network,
            size=size,
            length=length,
            layer=layer,
            pts=pts,
            entity="LINE",
        )

    return rows


def _connections_from_blocks(
    extraction: dict[str, Any],
    alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    chain = list(alignment.get("points") or [])
    sta0 = float(alignment.get("sta_start") or 0.0)
    align_name = str(alignment.get("name") or "")

    for block in extraction.get("blocks") or []:
        name = str(block.get("name") or "BLOCK")
        layer = str(block.get("layer") or "")
        btype = str(block.get("type") or "")
        classified = classify_fitting(name, layer) or classify_fitting(name, btype)
        blob = f"{name} {layer} {btype} {block.get('description') or ''}".lower()
        is_conn = bool(classified) or any(
            k in blob for k in ("bend", "elbow", "tee", "wye", "valve", "hydrant", "fitting", "reducer", "cross")
        )
        if not is_conn:
            continue
        # Prefer underground utility context
        network = detect_network(name, layer, btype, block.get("description"))
        if not network and classified:
            cat = classified[1].lower()
            if "util" in cat:
                network = "water"
            elif "drain" in cat:
                network = detect_network(layer) or "storm"
        if not network and not any(
            k in blob for k in ("water", "sewer", "storm", "san", "wm", "ss", "pipe", "main")
        ):
            # Still include clear fittings; mark utility unknown
            network = network or None

        size = extract_size_label(name, layer, block.get("size"), block.get("description"), btype)
        desc = classified[0] if classified else name
        insert = _as_point(block.get("insert") or block.get("position") or block.get("location"))
        station = ""
        side = ""
        offset = ""
        method = f"Block insert '{name}'"
        if insert and len(chain) >= 2:
            proj = _project_point_on_polyline(insert, chain)
            if proj:
                station = feet_to_station(sta0 + proj[0])
                side = proj[2]
                offset = f"{proj[1]:.2f}"
                method = (
                    f"Projected '{name}' onto alignment '{align_name}' "
                    f"@ {station} ({side})"
                )
        else:
            # Text near label station
            for t in extraction.get("texts") or []:
                txt = str(t.get("text") or "")
                if name.lower()[:8] and name.lower()[:8] in txt.lower():
                    m = _STA_ONE.search(txt)
                    if m:
                        station = m.group("sta")
                        method = f"Station from nearby text for '{name}'"
                        break

        rows.append(
            {
                "utility": _network_label(network),
                "network": network or "utility",
                "connection_type": desc,
                "size": size or "",
                "station": station,
                "direction_from_alignment": side,
                "offset_ft": offset,
                "quantity": 1,
                "unit": "EA",
                "layer": layer,
                "alignment": align_name,
                "source": "CAD block / fitting",
                "method": method,
                "name": name,
            }
        )
    return rows


def _bends_from_polylines(
    extraction: dict[str, Any],
    alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detect horizontal bends where utility polyline deflection is significant."""
    rows: list[dict[str, Any]] = []
    chain = list(alignment.get("points") or [])
    sta0 = float(alignment.get("sta_start") or 0.0)
    align_name = str(alignment.get("name") or "")
    min_deflection_deg = 12.0

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
            if deflection < min_deflection_deg:
                continue
            station = ""
            side = ""
            if len(chain) >= 2:
                proj = _project_point_on_polyline(b, chain)
                if proj:
                    station = feet_to_station(sta0 + proj[0])
                    side = proj[2]
            rows.append(
                {
                    "utility": _network_label(network),
                    "network": network or "utility",
                    "connection_type": f"Bend ({deflection:.0f}°)",
                    "size": size or "",
                    "station": station,
                    "direction_from_alignment": side,
                    "offset_ft": "",
                    "quantity": 1,
                    "unit": "EA",
                    "layer": layer,
                    "alignment": align_name,
                    "source": "Polyline deflection",
                    "method": f"Vertex deflection {deflection:.1f}° on layer '{layer}'",
                    "name": f"BEND@{station or i}",
                }
            )
    return rows


def _merge_segment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer text station rows; keep geometry rows that add new coverage."""
    if not rows:
        return []
    text_rows = [r for r in rows if "text" in str(r.get("source") or "").lower()]
    geo_rows = [r for r in rows if r not in text_rows]
    # If text has good station ranges, keep them and add geometry rows missing stations overlap
    out = list(text_rows)
    for g in geo_rows:
        # Skip tiny duplicates of same utility+size+length within 2%
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
    # Sort by utility then from station feet
    def sort_key(r: dict[str, Any]) -> tuple:
        ft = station_to_feet(str(r.get("from_station_raw") or r.get("from_station") or "")) or 0.0
        return (str(r.get("utility") or ""), ft, str(r.get("size") or ""))

    out.sort(key=sort_key)
    return out


def build_utilities_detail(extraction: dict[str, Any]) -> dict[str, Any]:
    """Build stationing + connection tables for all underground utilities."""
    alignment = _build_alignment_chain(extraction if isinstance(extraction, dict) else {})
    text_segs = _segments_from_texts(extraction)
    geo_segs = _segments_from_geometry(extraction, alignment)
    segments = _merge_segment_rows(text_segs + geo_segs)

    connections = _connections_from_blocks(extraction, alignment)
    connections.extend(_bends_from_polylines(extraction, alignment))

    # Dedupe connections by type+station+utility
    seen: set[str] = set()
    uniq_conn: list[dict[str, Any]] = []
    for c in connections:
        key = (
            f"{c.get('utility')}|{c.get('connection_type')}|{c.get('station')}|"
            f"{c.get('size')}|{c.get('name')}"
        ).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq_conn.append(c)

    def conn_key(c: dict[str, Any]) -> tuple:
        ft = station_to_feet(str(c.get("station") or "")) or 0.0
        return (str(c.get("utility") or ""), ft, str(c.get("connection_type") or ""))

    uniq_conn.sort(key=conn_key)

    networks = sorted({str(s.get("utility")) for s in segments} | {str(c.get("utility")) for c in uniq_conn})
    return {
        "alignment": {
            "name": alignment.get("name"),
            "layer": alignment.get("layer"),
            "length": round(float(alignment.get("length") or 0), 2),
            "sta_start": feet_to_station(float(alignment.get("sta_start") or 0)),
            "source": alignment.get("source"),
            "has_geometry": len(alignment.get("points") or []) >= 2,
        },
        "segments": segments,
        "connections": uniq_conn,
        "summary": {
            "segment_count": len(segments),
            "connection_count": len(uniq_conn),
            "utilities": networks,
            "total_lf": round(sum(float(s.get("quantity_lf") or 0) for s in segments), 2),
        },
    }
