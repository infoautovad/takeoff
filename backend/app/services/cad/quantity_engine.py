"""Map CAD extractions to size-aware civil quantity takeoff candidates.

Goals vs generic layer sums:
- Pipe lengths split by size + network (water / sanitary / storm)
- Count bends, valves, tees, reducers, hydrants by type (+ size when named)
- Storm/sanitary structures: manholes, inlets, catch basins, junction boxes
- Earthwork cut / fill volumes when surfaces expose them
"""

from __future__ import annotations

import re
from typing import Any

from app.services.csi_mapper import enrich_quantity_item

# inch sizes: 8", 8 in, 8-inch, 8IN, Ø8, DIA 8, DN200 (approx mm→in when large)
_SIZE_RE = re.compile(
    r"(?:"
    r"(?:Ø|ø|dia\.?|diam\.?|diameter|dn|nps)?\s*"
    r"(\d{1,2}(?:\.\d+)?)\s*(?:\"|''|in(?:ch(?:es)?)?|mm)?\b"
    r"|"
    r"\b(\d{1,2}(?:\.\d+)?)(?:\"|''|in)\b"
    r")",
    re.I,
)

_MM_SIZE_RE = re.compile(r"\b(\d{2,4})\s*mm\b", re.I)

_NOISE_LAYERS = {
    "0",
    "defpoints",
    "view",
    "textm",
    "psplan_vport",
    "psprof_vport",
    "viewport",
    "vport",
    "title",
    "border",
    "legend",
}

_NOISE_NAME_BITS = (
    "mview",
    "viewport",
    "logo",
    "title",
    "border",
    "legend",
    "model_space",
    "paper_space",
    "crowsfoot",
    "*model",
    "*paper",
    "north arrow",
    "barscale",
    "sheet",
)


def _is_noise_layer(name: str) -> bool:
    low = (name or "").strip().lower()
    if not low or low in _NOISE_LAYERS:
        return True
    return any(token in low for token in ("vport", "viewport", "defpoints", "title block"))


def _is_noise_name(name: str) -> bool:
    low = (name or "").lower()
    return any(bit in low for bit in _NOISE_NAME_BITS)


def _is_paper_space(entity: dict[str, Any]) -> bool:
    space = str(entity.get("space") or entity.get("layout") or "").lower()
    layer = str(entity.get("layer") or "").lower()
    return "paper" in space or layer.startswith("ps") or "paper_space" in layer


def _length_scale_to_feet(units: Any) -> float:
    """Convert drawing length units to feet for LF takeoff."""
    if units is None:
        return 1.0
    raw = str(units).strip().lower()
    # ezdxf / INSUNITS common values
    mapping = {
        "0": 1.0,  # unitless — assume feet for US civil
        "1": 1.0 / 12.0,  # inches
        "2": 1.0,  # feet
        "4": 1.0 / 25.4 / 12.0,  # mm
        "5": 1.0 / 2.54 / 12.0,  # cm
        "6": 3.280839895,  # meters
        "inch": 1.0 / 12.0,
        "inches": 1.0 / 12.0,
        "in": 1.0 / 12.0,
        "ft": 1.0,
        "feet": 1.0,
        "foot": 1.0,
        "mm": 1.0 / 25.4 / 12.0,
        "cm": 1.0 / 2.54 / 12.0,
        "m": 3.280839895,
        "meter": 3.280839895,
        "meters": 3.280839895,
        "metre": 3.280839895,
        "metres": 3.280839895,
    }
    if raw in mapping:
        return mapping[raw]
    # strings like "InsertionUnits.Feet"
    for key, scale in mapping.items():
        if key.isalpha() and key in raw:
            return scale
    return 1.0


def _size_hints_from_texts(extraction: dict[str, Any]) -> dict[str, str]:
    """Map layer → most common size label found in TEXT/MTEXT on that layer."""
    counts: dict[str, dict[str, int]] = {}
    for text in extraction.get("texts") or []:
        layer = str(text.get("layer") or "").strip()
        body = str(text.get("text") or text.get("content") or "")
        size = extract_size_label(body, layer)
        if not layer or not size:
            continue
        bucket = counts.setdefault(layer.lower(), {})
        bucket[size] = bucket.get(size, 0) + 1
    # Also scan dimension text-like measurement if present as inches
    for dim in extraction.get("dimensions") or []:
        layer = str(dim.get("layer") or "").strip()
        measurement = dim.get("measurement")
        size = extract_size_label(measurement, layer, dim.get("text"))
        if not layer or not size:
            continue
        # Only trust small civil pipe diameters from dimensions
        try:
            inches = float(re.sub(r"[^0-9.]", "", size.split("-")[0]))
        except ValueError:
            continue
        if inches < 1 or inches > 72:
            continue
        bucket = counts.setdefault(layer.lower(), {})
        bucket[size] = bucket.get(size, 0) + 1

    out: dict[str, str] = {}
    for layer, bucket in counts.items():
        best = max(bucket.items(), key=lambda kv: kv[1])
        out[layer] = best[0]
    return out


def extract_size_label(*parts: Any) -> str | None:
    """Return normalized size like '8-Inch' from layer/name/props text."""
    text = " ".join(str(p) for p in parts if p)
    if not text:
        return None

    mm = _MM_SIZE_RE.search(text)
    if mm:
        try:
            inches = float(mm.group(1)) / 25.4
            # Civil pipe sizes are usually whole/half inches
            if inches >= 2:
                rounded = round(inches * 2) / 2
                if abs(rounded - int(rounded)) < 0.01:
                    return f"{int(rounded)}-Inch"
                return f"{rounded:g}-Inch"
        except ValueError:
            pass

    # Prefer patterns near pipe/water keywords
    low_all = text.lower()
    # Structure tags like SSMH-2 / CB-12 are indices, not diameters (unless "12\"")
    structure_index = bool(
        re.search(r"\b(?:ssmh|smh|mh|cb|inlet|str|jbox|jh|dmh)[-_ ]?\d+\b", low_all)
        and not re.search(r"\d+\s*(?:\"|''|in(?:ch)?|mm)\b", low_all)
    )
    for match in _SIZE_RE.finditer(text):
        raw = match.group(1) or match.group(2)
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        # Skip stationing-like numbers and tiny/huge junk
        if val < 1 or val > 120:
            continue
        matched = match.group(0)
        span = text[max(0, match.start() - 12) : match.end() + 12].lower()
        common = {2, 3, 4, 6, 8, 10, 12, 14, 15, 16, 18, 20, 21, 24, 27, 30, 36, 42, 48, 54, 60}
        has_unit = bool(re.search(r"[\"'']|in(?:ch(?:es)?)?|mm", matched, re.I))
        has_cue = any(c in span for c in ('"', "in", "dia", "ø", "dn", "nps", "pipe", "casing", "wm"))
        civil_context = any(
            c in low_all
            for c in ("pipe", "water", "main", "sewer", "storm", "valve", "hydrant", "casing", "ductile", "pvc", "wm")
        )
        if structure_index and not has_unit and not has_cue:
            continue
        if has_unit or has_cue or (val in common and civil_context):
            if abs(val - int(val)) < 0.01:
                return f"{int(val)}-Inch"
            return f"{val:g}-Inch"
    return None


def detect_network(*parts: Any) -> str | None:
    text = " ".join(str(p) for p in parts if p).lower()
    if "casing" in text:
        return "casing"
    if any(k in text for k in ("storm", "st-", "p_storm", "sd-", "inlet", "catch basin", "catchbasin", "cb-")):
        return "storm"
    if any(k in text for k in ("sanitary", "san-", "p_san", "e_san", "ss-", "ssmh", "smh")):
        return "sanitary"
    if "sewer" in text and "storm" not in text:
        return "sanitary"
    if any(k in text for k in ("water", "watermain", "wm-", "p_water", "e_water", "potable", "hydrant")):
        return "water"
    # Cautious short tokens
    if re.search(r"(^|[^a-z])w[-_]", text) or " water " in f" {text} ":
        return "water"
    return None


def classify_fitting(name: str, layer: str = "") -> tuple[str, str, str] | None:
    """Return (description_prefix, category, unit) for countable fittings/structures."""
    text = f"{name} {layer}".lower()
    if _is_noise_name(name) or _is_noise_layer(layer):
        return None

    # Structures first (storm/sanitary)
    structure_map = [
        (["smh", "sanitary manhole", "sanhole", "ss mh", "ssmh"], "Sanitary Sewer Manhole", "Drainage"),
        (["manhole", " mh", "mh_", "mh-", "junc"], "Manhole", "Drainage"),
        (["inlet", "catch basin", "catchbasin", "cb-", "cb_", "sf_b", "curb inlet", "grate"], "Storm Drainage Inlet", "Drainage"),
        (["junction box", "jbox", "j-box", "drop structure"], "Storm Drainage Junction Box", "Drainage"),
        (["headwall", "endwall", "outlet structure"], "Drainage Headwall / Outlet", "Drainage"),
        (["structure"], "Drainage Structure", "Drainage"),
        (["hydrant", "fh-", "fh_"], "Fire Hydrant", "Utilities"),
        (["valve", "gv-", "bv-", "wv-", "gate valve", "butterfly"], "Valve", "Utilities"),
        (["bend", "elbow", "ell-", "90deg", "45deg", "22.5"], "Bend / Elbow", "Utilities"),
        (["tee", "wye", "branch"], "Tee / Wye Fitting", "Utilities"),
        (["reducer", "increaser", "coupling", "adapter"], "Reducer / Coupling", "Utilities"),
        (["cross fitting", "cross-"], "Cross Fitting", "Utilities"),
        (["cap", "plug", "blind"], "Cap / Plug", "Utilities"),
        (["sleeve", "casing"], "Casing / Sleeve", "Utilities"),
        (["meter"], "Water Meter", "Utilities"),
        (["blowoff", "blow-off", "air release", "arv"], "Blowoff / Air Release", "Utilities"),
    ]
    for keys, desc, cat in structure_map:
        if any(k in text for k in keys):
            return desc, cat, "EA"
    return None


def _pipe_description(network: str | None, size: str | None, fallback_name: str) -> tuple[str, str]:
    size_bit = f"{size} " if size else ""
    if network == "water":
        return f"{size_bit}Water Main".strip(), "Utilities"
    if network == "sanitary":
        return f"{size_bit}Sanitary Sewer Pipe".strip(), "Drainage"
    if network == "storm":
        return f"{size_bit}Storm Drain Pipe".strip(), "Drainage"
    if network == "casing":
        return f"{size_bit}Casing Pipe".strip(), "Utilities"
    # Try size-only civil pipe
    if size:
        return f"{size} Utility Pipe", "Utilities"
    low = fallback_name.lower()
    if "casing" in low:
        return "Casing Pipe", "Utilities"
    return "Utility Pipe, Type and Size Unidentified", "Utilities"


def build_quantities(extraction: dict[str, Any], source_label: str) -> list[dict[str, Any]]:
    length_by_key: dict[str, dict[str, Any]] = {}
    area_by_key: dict[str, dict[str, Any]] = {}
    count_by_key: dict[str, dict[str, Any]] = {}
    volume_by_key: dict[str, dict[str, Any]] = {}
    length_scale = _length_scale_to_feet(extraction.get("units"))
    size_by_layer = _size_hints_from_texts(extraction)

    def add_length(
        *,
        description: str,
        category: str,
        quantity: float,
        layer: str,
        entity_type: str,
        method: str,
        confidence: float = 88.0,
        size: str | None = None,
    ):
        if quantity <= 0:
            return
        if _is_noise_layer(layer) and "pipe" not in description.lower():
            return
        scaled = float(quantity) * length_scale
        unit = "LF"
        # Aggregate by description+size+unit (not layer) so LINE/POLYLINE/PIPE merge
        key = f"{description.lower()}|{unit}|{(size or '').lower()}"
        row = length_by_key.setdefault(
            key,
            {
                "description": description,
                "category": category,
                "unit": unit,
                "quantity": 0.0,
                "layer": layer,
                "entity_type": entity_type,
                "calculation_method": method,
                "source_reference": source_label,
                "confidence": confidence,
                "size": size,
            },
        )
        row["quantity"] += scaled
        row["confidence"] = max(float(row["confidence"]), confidence)
        if size and (not row.get("size")):
            row["size"] = size

    def add_count_item(
        *,
        description: str,
        category: str,
        layer: str,
        entity_type: str,
        method: str,
        confidence: float = 90.0,
        size: str | None = None,
        name: str = "",
    ):
        unit = "EA"
        key = f"{description.lower()}|{unit}|{(size or '').lower()}|{(name or layer).lower()}"
        row = count_by_key.setdefault(
            key,
            {
                "description": description if not size else f"{size} {description}",
                "category": category,
                "unit": unit,
                "quantity": 0.0,
                "layer": layer,
                "entity_type": entity_type,
                "calculation_method": method,
                "source_reference": source_label,
                "confidence": confidence,
                "size": size,
            },
        )
        # Avoid double-prefixing size on merge
        if size and size.lower() not in row["description"].lower():
            row["description"] = f"{size} {description}"
        row["quantity"] += 1
        row["confidence"] = max(float(row["confidence"]), confidence)

    def add_volume(*, description: str, quantity: float, method: str, layer: str = "Surface"):
        if quantity is None or float(quantity) <= 0:
            return
        key = description.lower()
        row = volume_by_key.setdefault(
            key,
            {
                "description": description,
                "category": "Earthwork",
                "unit": "CY",
                "quantity": 0.0,
                "layer": layer,
                "entity_type": "SURFACE",
                "calculation_method": method,
                "source_reference": source_label,
                "confidence": 86.0,
            },
        )
        row["quantity"] += float(quantity)

    def add_area(name: str, value: float, entity_type: str):
        if not value or value <= 0 or _is_noise_layer(name):
            return
        low = name.lower()
        if any(k in low for k in ("pave", "asphalt", "sidewalk", "gsb", "wmm", "row", "easement")):
            desc = f"Area - {name}"
            cat = "Pavement" if any(k in low for k in ("pave", "asphalt", "gsb", "wmm")) else "Geometry"
        else:
            return  # skip random closed polys as BOQ area noise
        key = f"{desc}|SF|{name}"
        row = area_by_key.setdefault(
            key,
            {
                "description": desc,
                "category": cat,
                "unit": "SF",
                "quantity": 0.0,
                "layer": name,
                "entity_type": entity_type,
                "calculation_method": f"Sum of {entity_type} areas on '{name}'",
                "source_reference": source_label,
                "confidence": 78.0,
            },
        )
        row["quantity"] += value

    # --- Civil 3D / APS pipes (best source for size) ---
    for pipe in extraction.get("pipes") or []:
        name = str(pipe.get("name") or "Pipe")
        layer = str(pipe.get("layer") or name)
        length = float(pipe.get("length") or 0)
        diameter = pipe.get("diameter") or pipe.get("inner_diameter") or pipe.get("outer_diameter")
        size = extract_size_label(name, layer, diameter, pipe.get("part_size"), pipe.get("description"))
        if not size:
            size = size_by_layer.get(layer.lower())
        if not size and pipe.get("radius"):
            try:
                # radius often in drawing units (ft) → diameter inches if small
                r = float(pipe["radius"])
                if r < 5:  # feet
                    size = extract_size_label(f'{r * 2 * 12}"')
                elif r < 60:  # already inches radius unlikely; treat as inches diameter/2
                    size = extract_size_label(f'{r * 2}"')
            except (TypeError, ValueError):
                pass
        network = detect_network(name, layer, pipe.get("network"), pipe.get("description")) or detect_network(
            pipe.get("part_size") or ""
        )
        desc, cat = _pipe_description(network, size, name)
        conf = 94.0 if size and network else 88.0 if size or network else 80.0
        add_length(
            description=desc,
            category=cat,
            quantity=length,
            layer=layer,
            entity_type="PIPE",
            method=f"Sum of PIPE lengths ({name})" + (f", size {size}" if size else ""),
            confidence=conf,
            size=size,
        )

    # --- Alignments (often sanitary/storm centerlines) ---
    for align in extraction.get("alignments") or []:
        name = str(align.get("name") or "Alignment")
        layer = str(align.get("layer") or name)
        length = float(align.get("length") or 0)
        size = extract_size_label(name, layer)
        network = detect_network(name, layer)
        if network in {"sanitary", "storm", "water"} or size:
            desc, cat = _pipe_description(network, size, name)
            add_length(
                description=desc,
                category=cat,
                quantity=length,
                layer=layer,
                entity_type="ALIGNMENT",
                method=f"Sum of ALIGNMENT lengths '{name}'",
                confidence=90.0 if network else 82.0,
                size=size,
            )

    # --- Polylines / lines: size-aware by layer/name ---
    for line in extraction.get("lines") or []:
        if _is_paper_space(line):
            continue
        layer = str(line.get("layer") or "0")
        length = float(line.get("length") or 0)
        size = extract_size_label(layer, line.get("name")) or size_by_layer.get(layer.lower())
        network = detect_network(layer, line.get("name"))
        # Require network or size or explicit pipe-ish layer — avoid random linework
        if network or size or any(k in layer.lower() for k in ("pipe", "water", "sewer", "storm", "san", "casing")):
            desc, cat = _pipe_description(network, size, layer)
            add_length(
                description=desc,
                category=cat,
                quantity=length,
                layer=layer,
                entity_type="LINE",
                method=f"Sum of LINE lengths on layer '{layer}'",
                confidence=86.0 if size and network else 80.0 if size or network else 74.0,
                size=size,
            )

    for pl in extraction.get("polylines") or []:
        if _is_paper_space(pl):
            continue
        layer = str(pl.get("layer") or "0")
        length = float(pl.get("length") or 0)
        size = extract_size_label(layer, pl.get("name")) or size_by_layer.get(layer.lower())
        network = detect_network(layer, pl.get("name"))
        if network or size or any(
            k in layer.lower() for k in ("pipe", "water", "sewer", "storm", "san", "casing", "main")
        ):
            desc, cat = _pipe_description(network, size, layer)
            add_length(
                description=desc,
                category=cat,
                quantity=length,
                layer=layer,
                entity_type="POLYLINE",
                method=f"Sum of POLYLINE lengths on layer '{layer}'",
                confidence=87.0 if size and network else 81.0 if size or network else 75.0,
                size=size,
            )
        if pl.get("area"):
            add_area(layer, float(pl.get("area") or 0) * (length_scale**2), "POLYLINE")

    for hatch in extraction.get("hatches") or []:
        add_area(str(hatch.get("layer") or "0"), float(hatch.get("area") or 0), "HATCH")

    # --- Blocks / inserts: fittings + structures (do not lump) ---
    for block in extraction.get("blocks") or []:
        if _is_paper_space(block):
            continue
        name = str(block.get("name") or "BLOCK")
        layer = str(block.get("layer") or "")
        btype = str(block.get("type") or "")
        if _is_noise_name(name):
            continue
        size = extract_size_label(name, layer, block.get("size"), block.get("description"), btype)
        if not size:
            size = size_by_layer.get(layer.lower())
        network = detect_network(name, layer, btype)
        classified = classify_fitting(name, layer) or classify_fitting(name, btype)
        if classified:
            desc, cat, _unit = classified
            # Specialize manhole/inlet by network
            if desc == "Manhole" and network == "sanitary":
                desc = "Sanitary Sewer Manhole"
            elif desc == "Manhole" and network == "storm":
                desc = "Storm Sewer Manhole"
            elif desc == "Drainage Structure" and network == "storm":
                desc = "Storm Drainage Structure"
            elif desc in {"Valve", "Bend / Elbow", "Tee / Wye Fitting", "Reducer / Coupling"} and network == "water":
                desc = f"Water {desc}"
            elif desc in {"Valve", "Bend / Elbow"} and network == "sanitary":
                desc = f"Sanitary {desc}"
            add_count_item(
                description=desc,
                category=cat,
                layer=layer or name,
                entity_type="INSERT",
                method=f"Count of INSERT '{name}'",
                confidence=92.0 if size else 89.0,
                size=size,
                name=name,
            )
            continue

        # Layer-implied utility insert without clear fitting keyword
        if network in {"water", "storm", "sanitary"}:
            if network == "water":
                desc, cat = "Water Appurtenance (Unclassified)", "Utilities"
            elif network == "storm":
                desc, cat = "Storm Drainage Structure", "Drainage"
            else:
                desc, cat = "Sanitary Sewer Structure", "Drainage"
            add_count_item(
                description=desc,
                category=cat,
                layer=layer or name,
                entity_type="INSERT",
                method=f"Count of INSERT '{name}' on {network} layer",
                confidence=78.0,
                size=size,
                name=name,
            )

    # --- Surfaces / cut-fill ---
    for surf in extraction.get("surfaces") or []:
        name = str(surf.get("name") or "Surface")
        cut = surf.get("cut") or surf.get("cut_volume") or surf.get("Cut Volume")
        fill = surf.get("fill") or surf.get("fill_volume") or surf.get("Fill Volume")
        net = surf.get("net") or surf.get("net_volume")
        # Convert CF→CY if values look like cubic feet (very large)
        def as_cy(val: Any) -> float | None:
            try:
                v = float(val)
            except (TypeError, ValueError):
                return None
            if v <= 0:
                return None
            # Heuristic: if huge, treat as CF
            if v > 50000:
                v = v / 27.0
            return v

        cut_cy = as_cy(cut)
        fill_cy = as_cy(fill)
        if cut_cy:
            add_volume(
                description="Earthwork Cut",
                quantity=cut_cy,
                method=f"Surface '{name}' cut volume",
                layer=name,
            )
        if fill_cy:
            add_volume(
                description="Earthwork Fill",
                quantity=fill_cy,
                method=f"Surface '{name}' fill volume",
                layer=name,
            )
        if not cut_cy and not fill_cy:
            net_cy = as_cy(net)
            if net_cy:
                # Net alone — put under cut if positive convention unknown; split note
                add_volume(
                    description="Earthwork Net Volume (verify cut/fill)",
                    quantity=abs(net_cy),
                    method=f"Surface '{name}' net volume (sign/convention needs engineer check)",
                    layer=name,
                )

    for vol in extraction.get("volumes") or []:
        kind = str(vol.get("type") or vol.get("name") or "").lower()
        qty = vol.get("quantity") or vol.get("volume")
        try:
            q = float(qty)
        except (TypeError, ValueError):
            continue
        if q > 50000:
            q = q / 27.0
        if "cut" in kind:
            add_volume(description="Earthwork Cut", quantity=q, method=vol.get("method") or "Volume property")
        elif "fill" in kind:
            add_volume(description="Earthwork Fill", quantity=q, method=vol.get("method") or "Volume property")
        elif "net" in kind:
            add_volume(
                description="Earthwork Net Volume (verify cut/fill)",
                quantity=abs(q),
                method=vol.get("method") or "Volume property (net)",
            )

    # Merge pipe length rows that are identical after size detection from text near layers
    items: list[dict[str, Any]] = []
    for row in (
        list(length_by_key.values())
        + list(area_by_key.values())
        + list(count_by_key.values())
        + list(volume_by_key.values())
    ):
        row["quantity"] = round(float(row["quantity"]), 2)
        row["unit"] = str(row.get("unit") or "UNIT").upper()
        # Drop tiny junk lengths
        if row["unit"] in {"LF", "SF"} and row["quantity"] < 0.05:
            continue
        items.append(enrich_quantity_item(row))

    items = _dedupe_prefer_sized(items)
    items = _collapse_count_duplicates(items)
    return items[:300]


def _dedupe_prefer_sized(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """If we have sized water/sanitary/storm pipes, drop generic unidentified duplicates."""
    has_sized = {
        "water": False,
        "sanitary": False,
        "storm": False,
    }
    for i in items:
        d = (i.get("description") or "").lower()
        if "-inch" in d and "unidentified" not in d:
            if "water" in d:
                has_sized["water"] = True
            if "sanitary" in d:
                has_sized["sanitary"] = True
            if "storm" in d:
                has_sized["storm"] = True

    out: list[dict[str, Any]] = []
    for i in items:
        d = (i.get("description") or "").lower()
        if "unidentified" in d or d == "utility pipe, type and size unidentified":
            if has_sized["water"] and ("water" in d or "utility pipe" in d):
                # Drop bare unidentified when sized water exists
                if "water" not in d or "-inch" not in d:
                    if has_sized["water"] and "utility pipe" in d:
                        continue
            if has_sized["sanitary"] and "sanitary" in d and "-inch" not in d:
                continue
            if has_sized["storm"] and "storm" in d and "-inch" not in d:
                continue
            if all(has_sized.values()) and "unidentified" in d:
                continue
        out.append(i)
    return out


def _collapse_count_duplicates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge EA rows that differ only by block name but share description+size+unit."""
    merged: dict[str, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []
    for item in items:
        unit = str(item.get("unit") or "").upper()
        if unit != "EA":
            passthrough.append(item)
            continue
        key = (
            f"{(item.get('description') or '').strip().lower()}|"
            f"{unit}|{(item.get('size') or '')}".lower()
        )
        if key not in merged:
            merged[key] = dict(item)
            continue
        try:
            merged[key]["quantity"] = round(
                float(merged[key].get("quantity") or 0) + float(item.get("quantity") or 0),
                2,
            )
            merged[key]["confidence"] = max(
                float(merged[key].get("confidence") or 0),
                float(item.get("confidence") or 0),
            )
        except (TypeError, ValueError):
            passthrough.append(item)
    return passthrough + list(merged.values())
