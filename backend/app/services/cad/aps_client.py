"""Autodesk Platform Services (APS) client for DWG / Civil 3D Model Derivative."""

from __future__ import annotations

import base64
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

APS_BASE = "https://developer.api.autodesk.com"


class AutodeskAPSError(RuntimeError):
    pass


def aps_configured() -> bool:
    settings = get_settings()
    return bool((settings.autodesk_client_id or "").strip() and (settings.autodesk_client_secret or "").strip())


def aps_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "configured": aps_configured(),
        "bucket": _bucket_key(),
        "client_id_set": bool((settings.autodesk_client_id or "").strip()),
    }


def _bucket_key() -> str:
    settings = get_settings()
    raw = (settings.autodesk_bucket_key or f"autovad{settings.app_env}{settings.autodesk_client_id or 'local'}").lower()
    # APS bucket keys: lowercase letters, numbers, `-`
    cleaned = re.sub(r"[^a-z0-9\-]", "", raw)[:128]
    return cleaned or "autovadlocal"


def get_access_token() -> str:
    settings = get_settings()
    if not aps_configured():
        raise AutodeskAPSError("Autodesk APS credentials are not configured")

    data = {
        "grant_type": "client_credentials",
        # Include code:all so the same token can call Design Automation when needed
        "scope": "data:read data:write data:create bucket:create bucket:read viewables:read code:all",
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{APS_BASE}/authentication/v2/token",
            data=data,
            auth=(settings.autodesk_client_id.strip(), settings.autodesk_client_secret.strip()),
        )
        if resp.status_code >= 400:
            raise AutodeskAPSError(f"APS auth failed ({resp.status_code}): {resp.text[:400]}")
        token = resp.json().get("access_token")
        if not token:
            raise AutodeskAPSError("APS auth response missing access_token")
        return token


def ensure_bucket(token: str) -> str:
    bucket = _bucket_key()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        # Check existing
        check = client.get(f"{APS_BASE}/oss/v2/buckets/{bucket}/details", headers=headers)
        if check.status_code == 200:
            return bucket

        create = client.post(
            f"{APS_BASE}/oss/v2/buckets",
            headers=headers,
            json={"bucketKey": bucket, "policyKey": "temporary"},
        )
        if create.status_code in {200, 409}:
            return bucket
        if create.status_code >= 400:
            raise AutodeskAPSError(f"APS bucket create failed ({create.status_code}): {create.text[:400]}")
        return bucket


def upload_object(token: str, bucket: str, path: Path) -> dict[str, Any]:
    """Upload via Autodesk OSS Direct-to-S3 (legacy PUT object is deprecated)."""
    from urllib.parse import quote

    object_key = f"{uuid.uuid4().hex}_{re.sub(r'[^A-Za-z0-9._-]', '_', path.name)}"
    data = path.read_bytes()
    size = len(data)
    # Non-final parts must be at least 5 MiB for multipart uploads.
    chunk_size = 5 * 1024 * 1024
    parts = max(1, (size + chunk_size - 1) // chunk_size)
    encoded_key = quote(object_key, safe="")
    auth_headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=3600.0) as client:
        upload_key: str | None = None
        urls: list[str] = []
        first_part = 1
        while first_part <= parts:
            batch = min(25, parts - first_part + 1)
            params = {
                "parts": str(batch),
                "firstPart": str(first_part),
                "minutesExpiration": "60",
            }
            if upload_key:
                params["uploadKey"] = upload_key
            signed = client.get(
                f"{APS_BASE}/oss/v2/buckets/{bucket}/objects/{encoded_key}/signeds3upload",
                headers=auth_headers,
                params=params,
            )
            if signed.status_code >= 400:
                raise AutodeskAPSError(
                    f"APS signed upload URL failed ({signed.status_code}): {signed.text[:400]}"
                )
            body = signed.json()
            upload_key = body.get("uploadKey") or upload_key
            batch_urls = body.get("urls") or []
            if not batch_urls:
                raise AutodeskAPSError("APS signed upload response missing urls")
            urls.extend(batch_urls)
            first_part += batch

        if not upload_key:
            raise AutodeskAPSError("APS signed upload response missing uploadKey")
        if len(urls) < parts:
            raise AutodeskAPSError(f"APS returned {len(urls)} upload URLs for {parts} parts")

        for index, url in enumerate(urls[:parts]):
            start = index * chunk_size
            end = min(start + chunk_size, size)
            put = client.put(url, content=data[start:end])
            # Retry once on transient S3 responses
            if put.status_code in {429} or 500 <= put.status_code <= 599:
                time.sleep(1.5)
                put = client.put(url, content=data[start:end])
            if put.status_code == 403:
                raise AutodeskAPSError(
                    "APS S3 upload URL expired or was rejected (403). Retry CAD processing."
                )
            if put.status_code >= 400:
                raise AutodeskAPSError(
                    f"APS S3 part upload failed ({put.status_code}): {put.text[:400]}"
                )

        complete = client.post(
            f"{APS_BASE}/oss/v2/buckets/{bucket}/objects/{encoded_key}/signeds3upload",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"uploadKey": upload_key},
        )
        if complete.status_code >= 400:
            raise AutodeskAPSError(
                f"APS complete upload failed ({complete.status_code}): {complete.text[:400]}"
            )
        body = complete.json() if complete.content else {}
        object_id = body.get("objectId") or f"urn:adsk.objects:os.object:{bucket}/{object_key}"
        return {
            "bucket": bucket,
            "object_key": object_key,
            "object_id": object_id,
            "size": body.get("size") or size,
        }


def to_urn(object_id: str) -> str:
    # URL-safe base64 without padding
    encoded = base64.urlsafe_b64encode(object_id.encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def start_translation(token: str, urn: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-ads-force": "true",
    }
    payload = {
        "input": {"urn": urn},
        "output": {
            "formats": [
                {"type": "svf2", "views": ["2d", "3d"]},
            ]
        },
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{APS_BASE}/modelderivative/v2/designdata/job",
            headers=headers,
            json=payload,
        )
        if resp.status_code >= 400:
            raise AutodeskAPSError(f"APS translation job failed ({resp.status_code}): {resp.text[:500]}")
        return resp.json()


def wait_for_manifest(token: str, urn: str, *, timeout_s: int = 3600, interval_s: int = 5) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    with httpx.Client(timeout=60.0) as client:
        while time.time() < deadline:
            resp = client.get(
                f"{APS_BASE}/modelderivative/v2/designdata/{urn}/manifest",
                headers=headers,
            )
            if resp.status_code == 200:
                last = resp.json()
                status = (last.get("status") or "").lower()
                if status == "success":
                    return last
                if status in {"failed", "timeout"}:
                    raise AutodeskAPSError(f"APS translation {status}: {last.get('progress')}")
            elif resp.status_code not in {404, 202}:
                raise AutodeskAPSError(f"APS manifest error ({resp.status_code}): {resp.text[:400]}")
            time.sleep(interval_s)
    raise AutodeskAPSError(f"APS translation timed out after {timeout_s}s")


def fetch_metadata_guids(token: str, urn: str) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(
            f"{APS_BASE}/modelderivative/v2/designdata/{urn}/metadata",
            headers=headers,
        )
        if resp.status_code >= 400:
            raise AutodeskAPSError(f"APS metadata failed ({resp.status_code}): {resp.text[:400]}")
        data = resp.json().get("data") or {}
        return data.get("metadata") or []


def fetch_properties(token: str, urn: str, guid: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(
            f"{APS_BASE}/modelderivative/v2/designdata/{urn}/metadata/{guid}/properties",
            headers=headers,
        )
        if resp.status_code >= 400:
            raise AutodeskAPSError(f"APS properties failed ({resp.status_code}): {resp.text[:400]}")
        return resp.json()


def fetch_object_tree(token: str, urn: str, guid: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(
            f"{APS_BASE}/modelderivative/v2/designdata/{urn}/metadata/{guid}",
            headers=headers,
        )
        if resp.status_code >= 400:
            raise AutodeskAPSError(f"APS object tree failed ({resp.status_code}): {resp.text[:400]}")
        return resp.json()


def map_aps_properties_to_extraction(properties_payload: dict[str, Any], *, filename: str) -> dict[str, Any]:
    """Map APS REST property collection into AutoVAD CAD extraction schema."""
    collection = ((properties_payload.get("data") or {}).get("collection")) or []

    layers: dict[str, dict[str, Any]] = {}
    lines: list[dict[str, Any]] = []
    polylines: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    hatches: list[dict[str, Any]] = []
    circles: list[dict[str, Any]] = []
    pipes: list[dict[str, Any]] = []
    surfaces: list[dict[str, Any]] = []
    volumes: list[dict[str, Any]] = []

    for obj in collection[:8000]:
        props = obj.get("properties") or {}
        name = obj.get("name") or props.get("Name") or "Object"
        flat: dict[str, Any] = {}
        for group, values in props.items():
            if isinstance(values, dict):
                for k, v in values.items():
                    flat[str(k)] = v
            else:
                flat[str(group)] = values

        layer = str(
            flat.get("Layer")
            or flat.get("layer")
            or flat.get("Layer Name")
            or flat.get("Level")
            or "0"
        )
        layers[layer] = {"name": layer}

        entity = str(flat.get("Entity") or flat.get("Type") or flat.get("Category") or name)
        length = _to_float(flat.get("Length") or flat.get("length") or flat.get("Perimeter") or flat.get("3D Length"))
        area = _to_float(flat.get("Area") or flat.get("area"))
        radius = _to_float(flat.get("Radius") or flat.get("radius") or flat.get("Pipe Radius"))
        diameter = _to_float(
            flat.get("Diameter")
            or flat.get("Inner Pipe Diameter")
            or flat.get("Outer Pipe Diameter")
            or flat.get("Nominal Diameter")
        )
        if diameter is not None and 0 < diameter < 8:
            diameter = diameter * 12.0
        part_size = flat.get("Part Size Name") or flat.get("Part Size") or flat.get("Description")
        network = flat.get("Network Name") or flat.get("Pipe Network Name") or flat.get("Network")
        cut_vol = _to_float(flat.get("Cut") or flat.get("Cut Volume"))
        fill_vol = _to_float(flat.get("Fill") or flat.get("Fill Volume"))

        lower_entity = entity.lower()
        blob = f"{entity} {name} {layer} {part_size or ''} {network or ''}".lower()

        if cut_vol or fill_vol:
            surfaces.append({"name": name, "cut": cut_vol, "fill": fill_vol})
            if cut_vol:
                volumes.append({"type": "cut", "quantity": cut_vol, "name": name})
            if fill_vol:
                volumes.append({"type": "fill", "quantity": fill_vol, "name": name})

        if "pipe" in lower_entity or "pipe" in blob:
            if length:
                pipes.append(
                    {
                        "name": name,
                        "layer": layer,
                        "length": length,
                        "radius": radius,
                        "diameter": diameter,
                        "part_size": part_size,
                        "network": network,
                        "description": part_size or name,
                    }
                )
            continue

        if any(k in blob for k in ("structure", "manhole", "inlet", "catch", "valve", "bend", "tee", "hydrant")):
            blocks.append(
                {
                    "name": str(part_size or name),
                    "layer": layer,
                    "type": entity,
                    "description": part_size or name,
                    "size": diameter,
                }
            )
        elif "block" in lower_entity or "insert" in lower_entity or "ref" in lower_entity:
            blocks.append({"name": name, "layer": layer, "type": entity, "description": part_size})
        elif "text" in lower_entity or "mtext" in lower_entity:
            texts.append({"layer": layer, "text": name})
        elif "dimension" in lower_entity or "dim" in lower_entity:
            dimensions.append({"layer": layer, "measurement": length, "text": name})
        elif "hatch" in lower_entity:
            hatches.append({"layer": layer, "area": area})
        elif "circle" in lower_entity or "arc" in lower_entity:
            circles.append(
                {
                    "layer": layer,
                    "radius": radius,
                    "arc_length": length,
                    "area": area,
                    "type": entity,
                }
            )
        elif length is not None and (area is None or "line" in lower_entity or "polyline" in lower_entity):
            if "poly" in lower_entity:
                polylines.append({"layer": layer, "length": length, "area": area, "closed": bool(area)})
            else:
                lines.append({"layer": layer, "length": length})
        elif area is not None:
            hatches.append({"layer": layer, "area": area})
        else:
            blocks.append({"name": name, "layer": layer, "type": entity})

    stats = {
        "aps_objects": len(collection),
        "layer_count": len(layers),
        "line_count": len(lines),
        "polyline_count": len(polylines),
        "block_insert_count": len(blocks),
        "text_count": len(texts),
        "dimension_count": len(dimensions),
        "hatch_count": len(hatches),
        "circle_arc_count": len(circles),
        "pipe_count": len(pipes),
        "surface_count": len(surfaces),
    }
    return {
        "format": "dwg",
        "engine": "autodesk_aps",
        "status": "extracted",
        "units": None,
        "layers": list(layers.values()),
        "lines": lines[:5000],
        "polylines": polylines[:5000],
        "blocks": blocks[:5000],
        "texts": texts[:2000],
        "dimensions": dimensions[:2000],
        "tables": [],
        "hatches": hatches[:2000],
        "circles": circles[:2000],
        "pipes": pipes[:5000],
        "surfaces": surfaces[:500],
        "volumes": volumes[:500],
        "stats": stats,
        "summary": (
            f"APS DWG processed '{filename}': {stats['aps_objects']} objects, "
            f"{stats['layer_count']} layers, {stats['pipe_count']} pipes, "
            f"{stats['block_insert_count']} blocks/structures."
        ),
        "aps": {"configured": True, "urn_processed": True},
    }


def find_properties_db_urn(manifest: dict[str, Any]) -> str | None:
    def walk(node: Any) -> str | None:
        if isinstance(node, dict):
            if node.get("role") == "Autodesk.CloudPlatform.PropertyDatabase" and node.get("urn"):
                return str(node["urn"])
            for child in node.get("children") or []:
                found = walk(child)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found:
                    return found
        return None

    return walk(manifest.get("derivatives") or [])


def download_derivative(token: str, derivative_urn: str) -> bytes:
    from urllib.parse import quote

    url = (
        "https://developer.api.autodesk.com/derivativeservice/v2/derivatives/"
        f"{quote(derivative_urn, safe='')}"
    )
    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code >= 400:
            raise AutodeskAPSError(
                f"APS derivative download failed ({resp.status_code}): {resp.text[:400]}"
            )
        return resp.content


def parse_properties_db(db_path: Path, *, filename: str) -> dict[str, Any]:
    """Parse Autodesk SVF properties.db (SQLite) into CAD extraction schema.

    The Model Derivative REST properties endpoint is often empty for 2D DWG /
    Civil plan-profile sheets, while properties.db still contains layers,
    lengths, pipes, structures, and areas.
    """
    import sqlite3

    layers: dict[str, dict[str, Any]] = {}
    lines: list[dict[str, Any]] = []
    polylines: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    hatches: list[dict[str, Any]] = []
    circles: list[dict[str, Any]] = []
    pipes: list[dict[str, Any]] = []
    alignments: list[dict[str, Any]] = []
    surfaces: list[dict[str, Any]] = []
    volumes: list[dict[str, Any]] = []

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    attrs = cur.execute(
        "SELECT id, name, category, display_name FROM _objects_attr"
    ).fetchall()
    useful_ids: set[int] = set()
    for attr_id, name, category, display_name in attrs:
        label = f"{name or ''} {category or ''} {display_name or ''}".lower()
        if any(
            key in label
            for key in (
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
            )
        ):
            useful_ids.add(int(attr_id))

    if not useful_ids:
        con.close()
        return map_aps_properties_to_extraction({"data": {"collection": []}}, filename=filename)

    placeholders = ",".join("?" for _ in useful_ids)
    rows = cur.execute(
        f"""
        SELECT e.entity_id, a.name, a.category, v.value
        FROM _objects_eav e
        JOIN _objects_attr a ON a.id = e.attribute_id
        JOIN _objects_val v ON v.id = e.value_id
        WHERE e.attribute_id IN ({placeholders})
        """,
        tuple(useful_ids),
    ).fetchall()
    con.close()

    by_entity: dict[int, dict[str, Any]] = {}
    for entity_id, name, category, value in rows:
        props = by_entity.setdefault(int(entity_id), {})
        key = str(name or "").strip()
        if not key:
            continue
        # Prefer Geometry-category values when duplicates exist
        cat = str(category or "")
        if key in props and cat and "geometry" not in cat.lower() and "general" not in cat.lower():
            continue
        props[key] = value

    for props in by_entity.values():
        entity = str(props.get("type") or props.get("General Object Type") or props.get("Name ") or "")
        name = str(
            props.get("Name")
            or props.get("name")
            or props.get("Part Size Name")
            or props.get("Alignment Name")
            or entity
            or "Object"
        )
        layer = str(props.get("Layer") or props.get("Layer name") or "0")
        layers[layer] = {"name": layer}

        length = _first_float(
            props,
            (
                "2D Length",
                "3D Length",
                "Pipe Length 3D",
                "General Overall Length",
                "Length",
                "Segment Length",
                "Parcel Perimeter",
                "Tangent Horizontal Length",
            ),
        )
        area = _first_float(
            props,
            ("Area", "Parcel Area", "2D surface area", "2D surface area "),
        )
        radius = _first_float(props, ("Pipe Radius", "Major radius", "Radius"))
        diameter = _first_float(
            props,
            (
                "Inner Pipe Diameter",
                "Outer Pipe Diameter",
                "Pipe Diameter",
                "Nominal Diameter",
                "Diameter",
                "Inside Diameter",
                "Outside Diameter",
            ),
        )
        # Normalize diameter to inches when value looks like feet
        if diameter is not None and 0 < diameter < 8:
            diameter = diameter * 12.0
        part_size = (
            props.get("Part Size Name")
            or props.get("Part Size")
            or props.get("Size Name")
            or props.get("Description")
        )
        network = (
            props.get("Network Name")
            or props.get("Pipe Network Name")
            or props.get("Network")
            or props.get("System Name")
        )
        material = props.get("Material") or props.get("Pipe Material")
        text_value = props.get("Contents") or props.get("textContent") or props.get("Text override")
        measurement = _to_float(props.get("Measurement"))
        cut_vol = _first_float(props, ("Cut", "Cut Volume", "Cut volume", "Volume Cut"))
        fill_vol = _first_float(props, ("Fill", "Fill Volume", "Fill volume", "Volume Fill"))
        net_vol = _first_float(props, ("Net", "Net Volume", "Net volume", "Composite Volume"))

        lower_entity = entity.lower()
        lower_name = name.lower()
        lower_layer = layer.lower()
        blob = " ".join(str(x) for x in (entity, name, layer, part_size, network, material) if x).lower()

        if cut_vol or fill_vol or net_vol:
            surfaces.append(
                {
                    "name": name or layer or "Surface",
                    "cut": cut_vol,
                    "fill": fill_vol,
                    "net": net_vol,
                    "type": entity or "Surface",
                }
            )
            if cut_vol:
                volumes.append({"type": "cut", "quantity": cut_vol, "name": name})
            if fill_vol:
                volumes.append({"type": "fill", "quantity": fill_vol, "name": name})

        if (
            "pipe" in lower_entity
            or "pipe" in lower_name
            or "aeccdbpipe" in lower_entity
            or "pipe network" in blob
        ):
            pipe_row = {
                "name": name,
                "layer": layer,
                "length": length,
                "radius": radius,
                "diameter": diameter,
                "part_size": part_size,
                "network": network,
                "material": material,
                "description": part_size or name,
            }
            if length:
                pipes.append(pipe_row)
            else:
                blocks.append(
                    {
                        "name": str(part_size or name),
                        "layer": layer,
                        "type": entity or "Pipe",
                        "size": diameter,
                        "description": part_size,
                    }
                )
            continue

        if (
            "structure" in lower_entity
            or "manhole" in lower_name
            or "catch" in lower_name
            or "inlet" in lower_name
            or "aeccdbstructure" in lower_entity
            or ("structure" in blob and "infrastructure" not in blob)
        ):
            blocks.append(
                {
                    "name": str(part_size or name),
                    "layer": layer or str(network or "Structure"),
                    "type": entity or "Structure",
                    "description": part_size or name,
                    "size": diameter,
                }
            )
            continue

        # Fittings often appear as Civil parts / blocks with size in the name
        if any(k in blob for k in ("valve", "bend", "elbow", "tee", "reducer", "hydrant", "fitting", "wye")):
            blocks.append(
                {
                    "name": str(part_size or name),
                    "layer": layer or str(network or ""),
                    "type": entity or "Fitting",
                    "description": part_size or name,
                    "size": diameter,
                }
            )
            continue

        if "alignment" in lower_entity or "alignment" in lower_name:
            if length:
                alignments.append({"name": name, "layer": layer, "length": length})
            continue

        if "surface" in lower_entity or "tin" in lower_entity or "tin surface" in blob:
            surfaces.append(
                {
                    "name": name,
                    "type": entity or "Surface",
                    "cut": cut_vol,
                    "fill": fill_vol,
                    "net": net_vol,
                }
            )
            continue

        if "text" in lower_entity or "mtext" in lower_entity:
            texts.append({"layer": layer, "text": str(text_value or name)})
            continue

        if "dimension" in lower_entity or "dim" in lower_entity:
            dimensions.append({"layer": layer, "measurement": measurement or length, "text": name})
            continue

        if "hatch" in lower_entity or "face" in lower_entity:
            if area:
                hatches.append({"layer": layer, "area": area})
            continue

        if "circle" in lower_entity or "arc" in lower_entity or "ellipse" in lower_entity:
            circles.append(
                {
                    "layer": layer,
                    "radius": radius,
                    "arc_length": length,
                    "area": area,
                    "type": entity,
                }
            )
            continue

        if "polyline" in lower_entity or "lwpolyline" in lower_entity:
            if length or area:
                polylines.append(
                    {
                        "layer": layer,
                        "length": length,
                        "area": area,
                        "closed": bool(area and not length),
                    }
                )
            continue

        if "line" in lower_entity and "polyline" not in lower_entity:
            if length:
                lines.append({"layer": layer, "length": length})
            continue

        if "block" in lower_entity or "reference" in lower_entity or "insert" in lower_entity:
            # Skip viewport / sheet framing noise
            if any(skip in lower_name for skip in ("mview", "viewport", "sheet", "logo", "title")):
                continue
            if any(skip in lower_layer for skip in ("vport", "defpoints", "viewport")):
                continue
            blocks.append({"name": name, "layer": layer, "type": entity or "Block"})
            continue

        # Geometry-bearing unknowns
        if length and area:
            polylines.append({"layer": layer, "length": length, "area": area, "closed": True})
        elif length:
            lines.append({"layer": layer, "length": length})
        elif area:
            hatches.append({"layer": layer, "area": area})
        elif entity and not entity.startswith("AcDb") and "table" not in lower_entity:
            blocks.append({"name": name, "layer": layer, "type": entity})

    stats = {
        "aps_objects": len(by_entity),
        "layer_count": len(layers),
        "line_count": len(lines),
        "polyline_count": len(polylines),
        "block_insert_count": len(blocks),
        "text_count": len(texts),
        "dimension_count": len(dimensions),
        "hatch_count": len(hatches),
        "circle_arc_count": len(circles),
        "pipe_count": len(pipes),
        "alignment_count": len(alignments),
        "surface_count": len(surfaces),
        "volume_signals": len(volumes),
        "source": "properties.db",
    }
    return {
        "format": "dwg",
        "engine": "autodesk_aps",
        "status": "extracted",
        "units": "ft",  # Civil plan/profile DWGs via APS are commonly imperial drawing units
        "layers": list(layers.values()),
        "lines": lines[:5000],
        "polylines": polylines[:5000],
        "blocks": blocks[:5000],
        "texts": texts[:2000],
        "dimensions": dimensions[:2000],
        "tables": [],
        "hatches": hatches[:2000],
        "circles": circles[:2000],
        "pipes": pipes[:5000],
        "alignments": alignments[:2000],
        "surfaces": surfaces[:500],
        "volumes": volumes[:500],
        "stats": stats,
        "summary": (
            f"APS DWG processed '{filename}' via properties.db: {stats['aps_objects']} objects, "
            f"{stats['layer_count']} layers, {stats['line_count']} lines, "
            f"{stats['polyline_count']} polylines, {stats['pipe_count']} pipes, "
            f"{stats['block_insert_count']} blocks/structures, "
            f"{stats['surface_count']} surfaces/volume signals."
        ),
        "aps": {"configured": True, "urn_processed": True, "property_source": "properties.db"},
    }


def process_dwg_with_aps(path: Path) -> dict[str, Any]:
    """Full DWG pipeline: auth → bucket → upload → translate → properties → CAD schema."""
    import tempfile

    settings = get_settings()
    token = get_access_token()
    bucket = ensure_bucket(token)
    uploaded = upload_object(token, bucket, path)
    urn = to_urn(uploaded["object_id"])
    start_translation(token, urn)
    manifest = wait_for_manifest(
        token,
        urn,
        timeout_s=int(getattr(settings, "autodesk_poll_timeout_seconds", 3600) or 3600),
        interval_s=int(getattr(settings, "autodesk_poll_interval_seconds", 5) or 5),
    )
    metadata = fetch_metadata_guids(token, urn)
    if not metadata:
        raise AutodeskAPSError("APS translation succeeded but no metadata views were returned")

    extraction: dict[str, Any] | None = None
    property_source = "rest"

    # Prefer properties.db — REST /metadata/{guid}/properties is often empty for 2D DWG sheets.
    db_urn = find_properties_db_urn(manifest)
    if db_urn:
        try:
            raw = download_derivative(token, db_urn)
            with tempfile.TemporaryDirectory(prefix="aps_props_") as tmp:
                db_path = Path(tmp) / "properties.db"
                db_path.write_bytes(raw)
                extraction = parse_properties_db(db_path, filename=path.name)
                property_source = "properties.db"
        except Exception as exc:
            # Fall through to REST properties aggregation
            extraction = None
            property_source = f"properties.db_failed:{exc}"

    if extraction is None or int((extraction.get("stats") or {}).get("aps_objects") or 0) == 0:
        merged_collection: list[dict[str, Any]] = []
        for item in metadata:
            guid = item.get("guid")
            if not guid:
                continue
            try:
                props = fetch_properties(token, urn, str(guid))
            except AutodeskAPSError:
                continue
            merged_collection.extend(((props.get("data") or {}).get("collection")) or [])
        extraction = map_aps_properties_to_extraction(
            {"data": {"collection": merged_collection}},
            filename=path.name,
        )
        if property_source == "properties.db":
            property_source = "rest_fallback"
        elif not property_source.startswith("properties.db"):
            property_source = "rest"

    extraction["aps"] = {
        "configured": True,
        "bucket": bucket,
        "object_key": uploaded["object_key"],
        "object_id": uploaded["object_id"],
        "urn": urn,
        "metadata_views": len(metadata),
        "property_source": property_source,
        "sheet_names": [m.get("name") for m in metadata],
    }
    return extraction


def _first_float(props: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _to_float(props.get(key))
        if value is not None:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
