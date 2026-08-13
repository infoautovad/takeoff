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
            surfaces.append(
                {
                    "name": elem.attrib.get("name") or elem.attrib.get("Name"),
                    "type": elem.attrib.get("desc") or elem.attrib.get("surfaceType"),
                }
            )
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

        elif name in {"Volume", "CgPoints"}:
            pass

        elif name == "Surface":
            # already handled above; also look for Volume children later
            pass

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
        "cross_sections": cross_sections,
        "stats": stats,
        "summary": (
            f"LandXML parsed: {stats['alignment_count']} alignments ({total_align} length units), "
            f"{stats['surface_count']} surfaces, {stats['pipe_count']} pipes ({total_pipe}), "
            f"{stats['structure_count']} structures, {stats['cross_section_count']} cross-sections."
        ),
    }
