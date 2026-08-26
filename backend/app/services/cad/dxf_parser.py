"""DXF geometry extraction via ezdxf (CAD & Civil 3D Intelligence Engine)."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


def parse_dxf(path: Path) -> dict[str, Any]:
    import ezdxf

    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()

    layers = []
    for layer in doc.layers:
        layers.append(
            {
                "name": layer.dxf.name,
                "color": getattr(layer.dxf, "color", None),
            }
        )

    lines: list[dict[str, Any]] = []
    polylines: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    hatches: list[dict[str, Any]] = []
    circles: list[dict[str, Any]] = []

    def _len_points(pts: list[tuple[float, float]]) -> float:
        total = 0.0
        for i in range(1, len(pts)):
            x1, y1 = pts[i - 1]
            x2, y2 = pts[i]
            total += math.hypot(x2 - x1, y2 - y1)
        return total

    for entity in msp:
        dxftype = entity.dxftype()
        layer = getattr(entity.dxf, "layer", "0")

        if dxftype == "LINE":
            start = (float(entity.dxf.start.x), float(entity.dxf.start.y))
            end = (float(entity.dxf.end.x), float(entity.dxf.end.y))
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            lines.append({"layer": layer, "length": length, "start": start, "end": end})

        elif dxftype in {"LWPOLYLINE", "POLYLINE"}:
            pts: list[tuple[float, float]] = []
            try:
                pts = [(float(p[0]), float(p[1])) for p in entity.get_points("xy")]
            except Exception:
                try:
                    pts = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in entity.vertices]  # type: ignore[attr-defined]
                except Exception:
                    pts = []
            closed = bool(getattr(entity, "closed", False))
            length = _len_points(pts)
            if closed and pts:
                length += math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
            area = None
            if closed and len(pts) >= 3:
                a = 0.0
                for i in range(len(pts)):
                    x1, y1 = pts[i]
                    x2, y2 = pts[(i + 1) % len(pts)]
                    a += x1 * y2 - x2 * y1
                area = abs(a) / 2.0
            polylines.append(
                {
                    "layer": layer,
                    "length": length,
                    "area": area,
                    "closed": closed,
                    "vertices": len(pts),
                    # Keep geometry for station projection (cap vertices)
                    "points": [[round(p[0], 4), round(p[1], 4)] for p in pts[:800]],
                    "name": layer,
                }
            )

        elif dxftype == "CIRCLE":
            r = float(entity.dxf.radius)
            center = None
            try:
                center = [float(entity.dxf.center.x), float(entity.dxf.center.y)]
            except Exception:
                center = None
            circles.append(
                {
                    "layer": layer,
                    "radius": r,
                    "center": center,
                    "circumference": 2 * math.pi * r,
                    "area": math.pi * r * r,
                }
            )

        elif dxftype == "ARC":
            r = float(entity.dxf.radius)
            start_angle = math.radians(float(entity.dxf.start_angle))
            end_angle = math.radians(float(entity.dxf.end_angle))
            sweep = end_angle - start_angle
            if sweep < 0:
                sweep += 2 * math.pi
            circles.append({"layer": layer, "radius": r, "arc_length": r * sweep, "type": "ARC"})

        elif dxftype == "INSERT":
            insert = [float(entity.dxf.insert.x), float(entity.dxf.insert.y)]
            attribs: dict[str, str] = {}
            try:
                if getattr(entity, "attribs", None):
                    for att in entity.attribs:
                        tag = str(getattr(att.dxf, "tag", "") or "")
                        val = str(getattr(att.dxf, "text", "") or "")
                        if tag:
                            attribs[tag] = val
                            attribs[tag.upper()] = val
                elif getattr(entity, "has_attrib", False):
                    for att in entity.attribs:
                        tag = str(att.dxf.tag or "")
                        val = str(att.dxf.text or "")
                        if tag:
                            attribs[tag] = val
                            attribs[tag.upper()] = val
            except Exception:
                attribs = {}
            sta = attribs.get("STATION") or attribs.get("STA") or attribs.get("STN")
            side = attribs.get("SIDE") or attribs.get("DIR")
            offset = attribs.get("OFFSET") or attribs.get("OFF")
            blocks.append(
                {
                    "layer": layer,
                    "name": entity.dxf.name,
                    "insert": insert,
                    "position": insert,
                    "attributes": attribs,
                    "station": sta,
                    "side": side,
                    "offset": offset,
                    "type": "INSERT",
                }
            )

        elif dxftype == "TEXT":
            insert = None
            try:
                insert = [float(entity.dxf.insert.x), float(entity.dxf.insert.y)]
            except Exception:
                insert = None
            texts.append({"layer": layer, "text": entity.dxf.text, "insert": insert, "space": "model"})
        elif dxftype == "MTEXT":
            insert = None
            try:
                insert = [float(entity.dxf.insert.x), float(entity.dxf.insert.y)]
            except Exception:
                insert = None
            texts.append({"layer": layer, "text": entity.text, "insert": insert, "space": "model"})

        elif "DIMENSION" in dxftype:
            measurement = None
            try:
                measurement = float(entity.get_measurement())
            except Exception:
                measurement = None
            dimensions.append({"layer": layer, "measurement": measurement})

        elif dxftype == "HATCH":
            area = None
            try:
                area = float(entity.area)
            except Exception:
                area = None
            hatches.append({"layer": layer, "area": area})

    # Paper-space sheet callouts (STA / offset labels) — content only; XY is not model
    try:
        for layout in doc.layouts:
            if str(layout.name).upper() in {"MODEL", "MODE"}:
                continue
            for entity in layout:
                dxftype = entity.dxftype()
                layer = getattr(entity.dxf, "layer", "0")
                if dxftype == "TEXT":
                    texts.append(
                        {
                            "layer": layer,
                            "text": entity.dxf.text,
                            "space": "paper",
                            "layout": layout.name,
                        }
                    )
                elif dxftype == "MTEXT":
                    texts.append(
                        {
                            "layer": layer,
                            "text": entity.text,
                            "space": "paper",
                            "layout": layout.name,
                        }
                    )
    except Exception:
        pass

    tables: list[dict[str, Any]] = []
    for block in doc.blocks:
        upper = block.name.upper()
        if any(k in upper for k in ("TABLE", "QTY", "EOQ", "BOQ", "SCHEDULE")):
            tables.append({"name": block.name, "entity_count": len(block)})

    units = None
    try:
        units = str(doc.units)
    except Exception:
        units = str(doc.header.get("$INSUNITS", "unknown"))

    stats = {
        "layer_count": len(layers),
        "line_count": len(lines),
        "polyline_count": len(polylines),
        "block_insert_count": len(blocks),
        "text_count": len(texts),
        "dimension_count": len(dimensions),
        "hatch_count": len(hatches),
        "circle_arc_count": len(circles),
        "total_line_length": round(sum(i["length"] for i in lines), 3),
        "total_polyline_length": round(sum(i["length"] for i in polylines), 3),
    }

    # Promote centerline-like polylines to alignments (for stationing)
    alignments: list[dict[str, Any]] = []
    for pl in polylines:
        layer = str(pl.get("layer") or "")
        low = layer.lower().replace("_", " ")
        if (
            "centerline" in low
            or "centreline" in low
            or "p cl" in low
            or re.search(r"(?:^|[^a-z0-9])cl(?:[^a-z0-9]|$)", low)
            or layer.lower().startswith("p_cl")
            or "_cl" in layer.lower()
        ):
            alignments.append(
                {
                    "name": layer,
                    "layer": layer,
                    "length": pl.get("length"),
                    "points": pl.get("points") or [],
                    "sta_start": "0+00",
                }
            )

    return {
        "format": "dxf",
        "engine": "ezdxf",
        "status": "extracted",
        "units": units,
        "layers": layers,
        "lines": lines[:5000],
        "polylines": polylines[:5000],
        "blocks": blocks[:5000],
        "texts": texts[:2000],
        "dimensions": dimensions[:2000],
        "tables": tables,
        "hatches": hatches[:2000],
        "circles": circles[:2000],
        "alignments": alignments[:200],
        "stats": stats,
        "summary": (
            f"DXF parsed: {stats['layer_count']} layers, {stats['line_count']} lines, "
            f"{stats['polyline_count']} polylines, {stats['block_insert_count']} blocks, "
            f"{stats['dimension_count']} dimensions, {stats['text_count']} text entities, "
            f"{len(alignments)} CL/alignment candidates."
        ),
    }
