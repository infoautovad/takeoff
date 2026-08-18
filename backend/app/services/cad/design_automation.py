"""Autodesk Design Automation (cloud AutoCAD / Civil 3D) for DWG takeoff.

Two modes:
1) Script activity (no custom plugin): cloud AutoCAD opens DWG → DXFOUT → local ezdxf parse
2) AppBundle activity (optional): cloud plugin writes result.json with richer takeoff

Falls back to Model Derivative when DA is disabled or fails.
"""

from __future__ import annotations

import io
import json
import re
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.services.cad.aps_client import (
    APS_BASE,
    AutodeskAPSError,
    aps_configured,
    ensure_bucket,
    get_access_token,
    upload_object,
)

DA_BASE = f"{APS_BASE}/da/us-east/v3"
DEFAULT_ALIAS = "prod"
APPBUNDLE_ID = "AutoVadCivilTakeoff"
ACTIVITY_DXF_ID = "AutoVadDwgToDxf"
ACTIVITY_PLUGIN_ID = "AutoVadCivilTakeoff"


def design_automation_enabled() -> bool:
    settings = get_settings()
    return bool(aps_configured() and settings.design_automation_enabled)


def design_automation_status() -> dict[str, Any]:
    settings = get_settings()
    bundle_path = _appbundle_zip_path()
    return {
        "enabled": settings.design_automation_enabled,
        "configured": design_automation_enabled(),
        "nickname": (settings.design_automation_nickname or "").strip() or None,
        "engine": settings.design_automation_engine or "auto",
        "modes": {
            "dwg_to_dxf_script": True,
            "civil_takeoff_appbundle": bundle_path.exists(),
        },
        "appbundle_zip": str(bundle_path) if bundle_path.exists() else None,
        "preferred": (
            "civil_takeoff_appbundle"
            if bundle_path.exists() and settings.design_automation_prefer_plugin
            else "dwg_to_dxf_script"
        ),
        "setup_hint": (
            "Set DESIGN_AUTOMATION_ENABLED=true (and APS credentials). "
            "Optional: build cad_plugins/AutoVadCivilTakeoff into appbundle.zip for richer Civil takeoff."
        ),
    }


def get_da_token() -> str:
    """Token with Design Automation scope (code:all)."""
    settings = get_settings()
    if not aps_configured():
        raise AutodeskAPSError("Autodesk APS credentials are not configured")
    data = {
        "grant_type": "client_credentials",
        "scope": (
            "data:read data:write data:create bucket:create bucket:read "
            "viewables:read code:all"
        ),
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{APS_BASE}/authentication/v2/token",
            data=data,
            auth=(settings.autodesk_client_id.strip(), settings.autodesk_client_secret.strip()),
        )
        if resp.status_code >= 400:
            raise AutodeskAPSError(f"APS DA auth failed ({resp.status_code}): {resp.text[:400]}")
        token = resp.json().get("access_token")
        if not token:
            raise AutodeskAPSError("APS DA auth response missing access_token")
        return token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _nickname(token: str | None = None) -> str:
    settings = get_settings()
    configured = (settings.design_automation_nickname or "").strip()
    if configured:
        return configured
    tok = token or get_da_token()
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(f"{DA_BASE}/forgeapps/me", headers=_headers(tok))
        if resp.status_code == 200:
            nick = (resp.json() or {}).get("nickname") or (resp.json() or {}).get("id")
            if nick:
                return str(nick)
        # Create / set nickname from client id fragment
        nick = re.sub(r"[^A-Za-z0-9]", "", (settings.autodesk_client_id or "autovad")[:20]) or "autovad"
        patch = client.patch(
            f"{DA_BASE}/forgeapps/me",
            headers=_headers(tok),
            json={"nickname": nick},
        )
        if patch.status_code >= 400 and patch.status_code != 409:
            # Some apps already have a nickname; retry GET
            again = client.get(f"{DA_BASE}/forgeapps/me", headers=_headers(tok))
            if again.status_code == 200:
                data = again.json() or {}
                return str(data.get("nickname") or data.get("id") or nick)
            raise AutodeskAPSError(f"DA nickname setup failed ({patch.status_code}): {patch.text[:400]}")
        return nick


def _pick_engine(token: str) -> str:
    settings = get_settings()
    configured = (settings.design_automation_engine or "").strip()
    if configured and configured.lower() != "auto":
        return configured
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(f"{DA_BASE}/engines", headers=_headers(token))
        if resp.status_code >= 400:
            return "Autodesk.AutoCAD+25_0"
        data = resp.json() or {}
        engines = data.get("data") or []
        # Prefer newest AutoCAD engine (Civil 3D DA rides on AutoCAD engines)
        autocad = [e for e in engines if isinstance(e, str) and "AutoCAD+" in e]
        if not autocad:
            return "Autodesk.AutoCAD+25_0"
        autocad.sort(reverse=True)
        return autocad[0]


def _qualified(nickname: str, local_id: str, alias: str = DEFAULT_ALIAS) -> str:
    return f"{nickname}.{local_id}+{alias}"


def _appbundle_zip_path() -> Path:
    settings = get_settings()
    custom = (settings.design_automation_appbundle_path or "").strip()
    if custom:
        return Path(custom)
    # backend/cad_plugins/AutoVadCivilTakeoff/appbundle.zip
    return Path(__file__).resolve().parents[3] / "cad_plugins" / "AutoVadCivilTakeoff" / "appbundle.zip"


def ensure_activity_dwg_to_dxf(token: str | None = None) -> str:
    """Register (or reuse) script-only DWG→DXF Design Automation activity."""
    tok = token or get_da_token()
    nick = _nickname(tok)
    engine = _pick_engine(tok)
    activity_id = ACTIVITY_DXF_ID
    qualified = _qualified(nick, activity_id)

    body = {
        "id": activity_id,
        "engine": engine,
        "commandLine": [
            '$(engine.path)\\accoreconsole.exe /i "$(args[inputFile].path)" '
            '/s "$(settings[script].path)"'
        ],
        "parameters": {
            "inputFile": {
                "verb": "get",
                "description": "Input DWG",
                "required": True,
                "localName": "input.dwg",
            },
            "outputFile": {
                "verb": "put",
                "description": "Output DXF from Design Automation",
                "required": True,
                "localName": "result.dxf",
            },
        },
        "settings": {
            # AccoreConsole script: export DXF (R2018 / AC1027 = 16 is common)
            "script": "._-DXFOUT\nresult.dxf\n16\n",
        },
        "description": "AutoVAD: DWG → DXF via Design Automation (cloud AutoCAD)",
    }

    with httpx.Client(timeout=120.0) as client:
        # Create activity if missing
        get = client.get(f"{DA_BASE}/activities/{quote(qualified, safe='')}", headers=_headers(tok))
        if get.status_code == 404:
            create = client.post(f"{DA_BASE}/activities", headers=_headers(tok), json=body)
            if create.status_code >= 400 and create.status_code != 409:
                raise AutodeskAPSError(
                    f"DA activity create failed ({create.status_code}): {create.text[:500]}"
                )
            version = 1
            if create.status_code < 400:
                version = int((create.json() or {}).get("version") or 1)
            alias = client.post(
                f"{DA_BASE}/activities/{activity_id}/aliases",
                headers=_headers(tok),
                json={"id": DEFAULT_ALIAS, "version": version},
            )
            if alias.status_code >= 400 and alias.status_code != 409:
                client.patch(
                    f"{DA_BASE}/activities/{activity_id}/aliases/{DEFAULT_ALIAS}",
                    headers=_headers(tok),
                    json={"version": version},
                )
        elif get.status_code >= 400:
            raise AutodeskAPSError(f"DA activity get failed ({get.status_code}): {get.text[:400]}")

    return qualified


def ensure_appbundle_and_activity(token: str | None = None) -> str | None:
    """Upload optional Civil takeoff AppBundle and register activity. Returns qualified activity id."""
    zip_path = _appbundle_zip_path()
    if not zip_path.exists():
        return None

    tok = token or get_da_token()
    nick = _nickname(tok)
    engine = _pick_engine(tok)
    qualified_bundle = _qualified(nick, APPBUNDLE_ID)
    qualified_activity = _qualified(nick, ACTIVITY_PLUGIN_ID)

    with httpx.Client(timeout=180.0) as client:
        # AppBundle create / new version
        get_b = client.get(
            f"{DA_BASE}/appbundles/{quote(qualified_bundle, safe='')}",
            headers=_headers(tok),
        )
        if get_b.status_code == 404:
            create_b = client.post(
                f"{DA_BASE}/appbundles",
                headers=_headers(tok),
                json={
                    "id": APPBUNDLE_ID,
                    "engine": engine,
                    "description": "AutoVAD Civil/AutoCAD takeoff plugin",
                },
            )
            if create_b.status_code >= 400:
                raise AutodeskAPSError(
                    f"DA appbundle create failed ({create_b.status_code}): {create_b.text[:500]}"
                )
            upload = create_b.json()
        else:
            # New version
            ver = client.post(
                f"{DA_BASE}/appbundles/{APPBUNDLE_ID}/versions",
                headers=_headers(tok),
                json={"engine": engine, "description": "AutoVAD Civil takeoff plugin update"},
            )
            if ver.status_code >= 400:
                raise AutodeskAPSError(
                    f"DA appbundle version failed ({ver.status_code}): {ver.text[:500]}"
                )
            upload = ver.json()

        upload_url = upload.get("uploadParameters", {}).get("endpointURL") or upload.get("uploadUrl")
        form_data = upload.get("uploadParameters", {}).get("formData") or {}
        if not upload_url:
            raise AutodeskAPSError("DA appbundle response missing upload URL")

        files = {"file": ("appbundle.zip", zip_path.read_bytes(), "application/octet-stream")}
        # S3 form upload
        up = client.post(upload_url, data=form_data, files=files)
        if up.status_code >= 400:
            raise AutodeskAPSError(f"DA appbundle upload failed ({up.status_code}): {up.text[:400]}")

        # Alias
        client.post(
            f"{DA_BASE}/appbundles/{APPBUNDLE_ID}/aliases",
            headers=_headers(tok),
            json={"id": DEFAULT_ALIAS, "version": upload.get("version") or 1},
        )
        client.patch(
            f"{DA_BASE}/appbundles/{APPBUNDLE_ID}/aliases/{DEFAULT_ALIAS}",
            headers=_headers(tok),
            json={"version": upload.get("version") or 1},
        )

        activity_body = {
            "id": ACTIVITY_PLUGIN_ID,
            "engine": engine,
            "commandLine": [
                '$(engine.path)\\accoreconsole.exe /i "$(args[inputFile].path)" '
                '/al "$(appbundles[AutoVadCivilTakeoff].path)" '
                '/s "$(settings[script].path)"'
            ],
            "appbundles": [qualified_bundle],
            "parameters": {
                "inputFile": {
                    "verb": "get",
                    "required": True,
                    "localName": "input.dwg",
                },
                "outputFile": {
                    "verb": "put",
                    "required": True,
                    "localName": "result.json",
                },
            },
            "settings": {"script": "AutoVadTakeoff\n"},
            "description": "AutoVAD Design Automation Civil takeoff → result.json",
        }

        get_a = client.get(
            f"{DA_BASE}/activities/{quote(qualified_activity, safe='')}",
            headers=_headers(tok),
        )
        if get_a.status_code == 404:
            create_a = client.post(f"{DA_BASE}/activities", headers=_headers(tok), json=activity_body)
            if create_a.status_code >= 400:
                raise AutodeskAPSError(
                    f"DA plugin activity create failed ({create_a.status_code}): {create_a.text[:500]}"
                )
            client.post(
                f"{DA_BASE}/activities/{ACTIVITY_PLUGIN_ID}/aliases",
                headers=_headers(tok),
                json={"id": DEFAULT_ALIAS, "version": 1},
            )
        else:
            # Update via new version
            client.post(
                f"{DA_BASE}/activities/{ACTIVITY_PLUGIN_ID}/versions",
                headers=_headers(tok),
                json={k: v for k, v in activity_body.items() if k != "id"},
            )

    return qualified_activity


def setup_design_automation() -> dict[str, Any]:
    """Ensure nickname + activities are registered in the APS account."""
    if not design_automation_enabled():
        raise AutodeskAPSError("Design Automation is disabled or APS credentials missing")
    tok = get_da_token()
    nick = _nickname(tok)
    engine = _pick_engine(tok)
    dxf_activity = ensure_activity_dwg_to_dxf(tok)
    plugin_activity = None
    plugin_error = None
    try:
        plugin_activity = ensure_appbundle_and_activity(tok)
    except Exception as exc:
        plugin_error = str(exc)
    return {
        "nickname": nick,
        "engine": engine,
        "dxf_activity": dxf_activity,
        "plugin_activity": plugin_activity,
        "plugin_error": plugin_error,
        "status": design_automation_status(),
    }


def _oss_object_url(bucket: str, object_key: str) -> str:
    return f"{APS_BASE}/oss/v2/buckets/{bucket}/objects/{quote(object_key, safe='')}"


def _create_empty_oss_object(token: str, bucket: str, object_key: str) -> None:
    """Ensure output object key exists (some APS flows prefer signed put on existing keys)."""
    # Direct-to-S3 empty upload via existing helper pattern — write 1 byte placeholder then overwrite
    pass


def _signed_download_url(token: str, bucket: str, object_key: str, minutes: int = 60) -> str:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    encoded = quote(object_key, safe="")
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{APS_BASE}/oss/v2/buckets/{bucket}/objects/{encoded}/signed",
            headers=headers,
            json={"minutesExpiration": minutes, "singleUse": False},
            params={"access": "read"},
        )
        if resp.status_code >= 400:
            # Fallback: authenticated OSS URL (DA accepts Authorization header)
            return _oss_object_url(bucket, object_key)
        data = resp.json() or {}
        return data.get("signedUrl") or data.get("url") or _oss_object_url(bucket, object_key)


def _signed_upload_url(token: str, bucket: str, object_key: str, minutes: int = 60) -> str:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    encoded = quote(object_key, safe="")
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{APS_BASE}/oss/v2/buckets/{bucket}/objects/{encoded}/signed",
            headers=headers,
            json={"minutesExpiration": minutes, "singleUse": False},
            params={"access": "write"},
        )
        if resp.status_code >= 400:
            return _oss_object_url(bucket, object_key)
        data = resp.json() or {}
        return data.get("signedUrl") or data.get("url") or _oss_object_url(bucket, object_key)


def _download_oss_object(token: str, bucket: str, object_key: str) -> bytes:
    headers = {"Authorization": f"Bearer {token}"}
    encoded = quote(object_key, safe="")
    with httpx.Client(timeout=3600.0) as client:
        resp = client.get(
            f"{APS_BASE}/oss/v2/buckets/{bucket}/objects/{encoded}",
            headers=headers,
        )
        if resp.status_code >= 400:
            raise AutodeskAPSError(
                f"OSS download failed ({resp.status_code}): {resp.text[:400]}"
            )
        return resp.content


def _submit_and_wait(
    token: str,
    activity_id: str,
    arguments: dict[str, Any],
    *,
    timeout_s: int,
    interval_s: int,
) -> dict[str, Any]:
    with httpx.Client(timeout=120.0) as client:
        create = client.post(
            f"{DA_BASE}/workitems",
            headers=_headers(token),
            json={"activityId": activity_id, "arguments": arguments},
        )
        if create.status_code >= 400:
            raise AutodeskAPSError(
                f"DA workitem create failed ({create.status_code}): {create.text[:600]}"
            )
        work = create.json() or {}
        work_id = work.get("id")
        if not work_id:
            raise AutodeskAPSError("DA workitem response missing id")

        deadline = time.time() + timeout_s
        last: dict[str, Any] = work
        while time.time() < deadline:
            status_resp = client.get(f"{DA_BASE}/workitems/{work_id}", headers=_headers(token))
            if status_resp.status_code >= 400:
                raise AutodeskAPSError(
                    f"DA workitem status failed ({status_resp.status_code}): {status_resp.text[:400]}"
                )
            last = status_resp.json() or {}
            st = (last.get("status") or "").lower()
            if st in {"success", "failed", "cancelled", "timeout"}:
                if st != "success":
                    report = last.get("reportUrl")
                    raise AutodeskAPSError(
                        f"DA workitem {st}"
                        + (f" — report: {report}" if report else "")
                        + f" — {json.dumps(last.get('stats') or {})[:200]}"
                    )
                return last
            time.sleep(interval_s)
        raise AutodeskAPSError(f"DA workitem timed out after {timeout_s}s (id={work_id})")


def process_dwg_with_design_automation(path: Path) -> dict[str, Any]:
    """Run Design Automation on a DWG and return CAD extraction dict."""
    if not design_automation_enabled():
        raise AutodeskAPSError("Design Automation is not enabled")

    settings = get_settings()
    token = get_da_token()
    # Also need OSS token for upload (same token with data scopes — DA token has them)
    bucket = ensure_bucket(token)
    uploaded = upload_object(token, bucket, path)
    input_key = uploaded["object_key"]
    output_key = f"da_out/{uuid.uuid4().hex}_{path.stem}.out"

    timeout_s = int(settings.design_automation_timeout_seconds or 540)
    interval_s = int(settings.autodesk_poll_interval_seconds or 5)

    prefer_plugin = bool(settings.design_automation_prefer_plugin)
    plugin_activity = None
    if prefer_plugin and _appbundle_zip_path().exists():
        try:
            plugin_activity = ensure_appbundle_and_activity(token)
        except Exception:
            plugin_activity = None

    input_arg = {
        "url": _oss_object_url(bucket, input_key),
        "verb": "get",
        "headers": {"Authorization": f"Bearer {token}"},
    }
    output_arg = {
        "url": _oss_object_url(bucket, output_key),
        "verb": "put",
        "headers": {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        },
    }

    if plugin_activity:
        _submit_and_wait(
            token,
            plugin_activity,
            {"inputFile": input_arg, "outputFile": {**output_arg, "localName": "result.json"}},
            timeout_s=timeout_s,
            interval_s=interval_s,
        )
        raw = _download_oss_object(token, bucket, output_key)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise AutodeskAPSError(f"DA plugin result.json invalid: {exc}") from exc
        return _normalize_plugin_result(payload, filename=path.name, activity=plugin_activity)

    # Default: DWG → DXF via cloud AutoCAD script, then local ezdxf
    activity = ensure_activity_dwg_to_dxf(token)
    # Output key should end with .dxf for clarity
    output_key = f"da_out/{uuid.uuid4().hex}_{path.stem}.dxf"
    output_arg["url"] = _oss_object_url(bucket, output_key)

    _submit_and_wait(
        token,
        activity,
        {
            "inputFile": input_arg,
            "outputFile": {**output_arg, "localName": "result.dxf"},
        },
        timeout_s=timeout_s,
        interval_s=interval_s,
    )
    dxf_bytes = _download_oss_object(token, bucket, output_key)
    if len(dxf_bytes) < 64:
        raise AutodeskAPSError("DA DXF output was empty — check AccoreConsole DXFOUT script / engine")

    with tempfile.TemporaryDirectory(prefix="da_dxf_") as tmp:
        dxf_path = Path(tmp) / "result.dxf"
        dxf_path.write_bytes(dxf_bytes)
        from app.services.cad.dxf_parser import parse_dxf

        extraction = parse_dxf(dxf_path)

    extraction["format"] = "dwg"
    extraction["engine"] = "design_automation_dxf"
    extraction["status"] = "extracted"
    extraction["summary"] = (
        f"Design Automation (cloud AutoCAD) converted '{path.name}' → DXF, "
        f"then local geometry takeoff. "
        + (extraction.get("summary") or "")
    )
    extraction["aps"] = {
        "configured": True,
        "design_automation": True,
        "mode": "dwg_to_dxf_script",
        "activity": activity,
        "bucket": bucket,
        "input_object": input_key,
        "output_object": output_key,
    }
    return extraction


def _normalize_plugin_result(payload: dict[str, Any], *, filename: str, activity: str) -> dict[str, Any]:
    """Map plugin JSON into the shared CAD extraction schema."""
    stats = payload.get("stats") or {}
    return {
        "format": "dwg",
        "engine": "design_automation_civil",
        "status": "extracted",
        "units": payload.get("units"),
        "layers": payload.get("layers") or [],
        "lines": payload.get("lines") or [],
        "polylines": payload.get("polylines") or [],
        "blocks": payload.get("blocks") or [],
        "texts": payload.get("texts") or [],
        "dimensions": payload.get("dimensions") or [],
        "tables": payload.get("tables") or [],
        "hatches": payload.get("hatches") or [],
        "circles": payload.get("circles") or [],
        "alignments": payload.get("alignments") or [],
        "pipes": payload.get("pipes") or [],
        "surfaces": payload.get("surfaces") or [],
        "stats": {**stats, "file": filename},
        "summary": payload.get("summary")
        or (
            f"Design Automation Civil takeoff for '{filename}': "
            f"{stats.get('entity_count', '?')} entities."
        ),
        "aps": {
            "configured": True,
            "design_automation": True,
            "mode": "civil_takeoff_appbundle",
            "activity": activity,
        },
        "quantities_hint": payload.get("quantities") or [],
    }


def package_appbundle_from_folder(plugin_dir: Path, out_zip: Path | None = None) -> Path:
    """Zip a PackageContents.xml + Contents folder into appbundle.zip (helper for builds)."""
    out = out_zip or (plugin_dir / "appbundle.zip")
    package_xml = plugin_dir / "PackageContents.xml"
    contents = plugin_dir / "Contents"
    if not package_xml.exists():
        raise FileNotFoundError("PackageContents.xml missing")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(package_xml, arcname="PackageContents.xml")
        if contents.exists():
            for f in contents.rglob("*"):
                if f.is_file():
                    zf.write(f, arcname=str(Path("Contents") / f.relative_to(contents)))
    out.write_bytes(buf.getvalue())
    return out
