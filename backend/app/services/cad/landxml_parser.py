"""LandXML extraction for alignments, surfaces, pipes, and cross-sections."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_landxml(path: Path) -> dict[str, Any]:
    tree = ET.parse(path)
    root = tree.getroot()

    alignments: list[dict[str, Any]] = []
    surfaces: list[dict[str, Any]] = []
    pipes: list[dict[str, Any]] = []
    structures: list[dict[str, Any]] = []
    cross_sections: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    layers: list[dict[str, Any]] = []
    volumes: list[dict[str, Any]] = []

    def _fattr(elem: ET.Element, *keys: str) -> float | None:
        for key in keys:
            raw = elem.attrib.get(key)
            if raw is None:
                continue
            try:
                return float(raw)
            except ValueError:
                continue
        return None

    for elem in root.iter():
        name = _local(elem.tag)

        if name == "Alignment":
            length = elem.attrib.get("length") or elem.attrib.get("Length")
            alignments.append(
                {
                    "name": elem.attrib.get("name") or elem.attrib.get("Name"),
                    "length": float(length) if length else None,
                    "sta_start": elem.attrib.get("staStart") or elem.attrib.get("StaStart"),
                }
            )
            layers.append({"name": f"Alignment:{alignments[-1]['name']}"})

        elif name in {"Surface", "SurfaceSource"}:
            surf = {
                "name": elem.attrib.get("name") or elem.attrib.get("Name"),
                "type": elem.attrib.get("desc") or elem.attrib.get("surfaceType"),
            }
            # Pull cut/fill from child Volume / Volume2D if present
            for child in elem:
                cname = _local(child.tag)
                if cname in {"Volume", "Volume2D", "SurfaceVolume"}:
                    cut = _fattr(child, "cut", "Cut", "cutVol", "earthworkCut")
                    fill = _fattr(child, "fill", "Fill", "fillVol", "earthworkFill")
                    net = _fattr(child, "net", "Net", "vol", "volume")
                    if cut is not None:
                        surf["cut"] = cut
                    if fill is not None:
                        surf["fill"] = fill
                    if net is not None:
                        surf["net"] = net
            surfaces.append(surf)
            layers.append({"name": f"Surface:{surfaces[-1]['name']}"})

        elif name == "Pipe":
            length = elem.attrib.get("length") or elem.attrib.get("Length")
            diam_raw = elem.attrib.get("oDiam") or elem.attrib.get("diam") or elem.attrib.get("Diameter")
            try:
                diam_f = float(diam_raw) if diam_raw else None
            except ValueError:
                diam_f = None
            pipes.append(
                {
                    "name": elem.attrib.get("name") or elem.attrib.get("Name"),
                    "length": float(length) if length else None,
                    "diameter": diam_f,
                    "part_size": diam_raw,
                    "material": elem.attrib.get("material") or elem.attrib.get("Material"),
                    "network": elem.attrib.get("refPipeNetwork") or elem.attrib.get("network"),
                }
            )

        elif name in {"Struct", "Structure"}:
            structures.append(
                {
                    "name": elem.attrib.get("name") or elem.attrib.get("Name"),
                    "type": elem.attrib.get("desc") or elem.attrib.get("Type") or "Structure",
                }
            )

        elif name in {"Volume", "Volume2D", "SurfaceVolume"}:
            cut = _fattr(elem, "cut", "Cut", "cutVol", "earthworkCut")
            fill = _fattr(elem, "fill", "Fill", "fillVol", "earthworkFill")
            net = _fattr(elem, "net", "Net", "vol", "volume")
            label = elem.attrib.get("name") or elem.attrib.get("desc") or "Volume"
            if cut is not None:
                volumes.append({"type": "cut", "name": label, "quantity": cut, "method": "LandXML Volume"})
            if fill is not None:
                volumes.append({"type": "fill", "name": label, "quantity": fill, "method": "LandXML Volume"})
            if cut is None and fill is None and net is not None:
                volumes.append({"type": "net", "name": label, "quantity": net, "method": "LandXML Volume"})

        elif name in {"CrossSect", "CrossSection"}:
            cross_sections.append(
                {
                    "sta": elem.attrib.get("sta") or elem.attrib.get("Sta"),
                    "name": elem.attrib.get("name") or elem.attrib.get("Name"),
                }
            )

        elif name in {"Feature", "Parcel"}:
            texts.append({"text": elem.attrib.get("name") or elem.attrib.get("Name") or name, "layer": name})

    seen: set[str] = set()
    uniq_layers = []
    for layer in layers:
        if layer["name"] not in seen and layer["name"]:
            seen.add(layer["name"])
            uniq_layers.append(layer)

    total_align = round(sum(a["length"] or 0 for a in alignments), 3)
    total_pipe = round(sum(p["length"] or 0 for p in pipes), 3)

    stats = {
        "alignment_count": len(alignments),
        "surface_count": len(surfaces),
        "pipe_count": len(pipes),
        "structure_count": len(structures),
        "cross_section_count": len(cross_sections),
        "volume_count": len(volumes),
        "total_alignment_length": total_align,
        "total_pipe_length": total_pipe,
    }

    return {
        "format": "landxml",
        "engine": "autovad_landxml",
        "units": root.attrib.get("units") or "unknown",
        "layers": uniq_layers,
        "lines": [],
        "polylines": [],
        "blocks": [
            {
                "name": s.get("name") or s.get("type") or "Structure",
                "layer": str(s.get("type") or "Structure"),
                "type": s.get("type") or "Structure",
                "description": s.get("type"),
            }
            for s in structures
        ],
        "texts": texts[:2000],
        "dimensions": [],
        "tables": [],
        "alignments": alignments,
        "surfaces": surfaces,
        "pipes": pipes,
        "volumes": volumes,
        "cross_sections": cross_sections,
        "stats": stats,
        "summary": (
            f"LandXML parsed: {stats['alignment_count']} alignments ({total_align} length units), "
            f"{stats['surface_count']} surfaces, {stats['pipe_count']} pipes ({total_pipe}), "
            f"{stats['structure_count']} structures, {stats['volume_count']} volumes, "
            f"{stats['cross_section_count']} cross-sections."
        ),
    }
