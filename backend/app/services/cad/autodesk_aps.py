"""Autodesk Platform Services (APS) adapter for native DWG / Civil 3D models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.cad.aps_client import (
    AutodeskAPSError,
    aps_configured,
    aps_status,
    process_dwg_with_aps,
)
from app.services.cad.design_automation import (
    design_automation_enabled,
    design_automation_status,
    process_dwg_with_design_automation,
)


def parse_dwg(path: Path) -> dict[str, Any]:
    if not aps_configured():
        return {
            "format": "dwg",
            "engine": "autodesk_aps_pending",
            "status": "needs_autodesk",
            "units": None,
            "layers": [],
            "lines": [],
            "polylines": [],
            "blocks": [],
            "texts": [],
            "dimensions": [],
            "tables": [],
            "stats": {"file": path.name, "bytes": path.stat().st_size},
            "summary": (
                "DWG uploaded. Native DWG processing requires Autodesk Platform Services "
                "(Design Automation and/or Model Derivative). Set AUTODESK_CLIENT_ID and "
                "AUTODESK_CLIENT_SECRET in backend/.env, or export DWG to DXF/LandXML for local parsing."
            ),
            "next_steps": [
                "Create an APS app at https://aps.autodesk.com and copy Client ID/Secret",
                "Enable Design Automation API on the app, put credentials in backend/.env, restart backend",
                "Or export DWG → DXF and re-upload for immediate local extraction",
            ],
            "aps": aps_status(),
            "design_automation": design_automation_status(),
        }

    settings = get_settings()
    errors: list[str] = []

    # 1) Prefer Design Automation (cloud AutoCAD) when enabled
    if design_automation_enabled():
        try:
            result = process_dwg_with_design_automation(path)
            result.setdefault("aps", {})["model_derivative_fallback"] = False
            result["design_automation"] = design_automation_status()
            return result
        except Exception as exc:
            errors.append(f"Design Automation: {exc}")
            if not settings.design_automation_fallback_model_derivative:
                return {
                    "format": "dwg",
                    "engine": "design_automation",
                    "status": "failed",
                    "units": None,
                    "layers": [],
                    "lines": [],
                    "polylines": [],
                    "blocks": [],
                    "texts": [],
                    "dimensions": [],
                    "tables": [],
                    "stats": {"file": path.name},
                    "summary": f"Design Automation DWG processing failed: {exc}",
                    "error": str(exc),
                    "aps": aps_status(),
                    "design_automation": design_automation_status(),
                }

    # 2) Fallback: Model Derivative properties.db / REST
    try:
        result = process_dwg_with_aps(path)
        if errors:
            result["summary"] = (
                (result.get("summary") or "")
                + f" (Design Automation unavailable → Model Derivative. {errors[0][:180]})"
            )
            result.setdefault("aps", {})["design_automation_error"] = errors[0]
        result["design_automation"] = design_automation_status()
        return result
    except AutodeskAPSError as exc:
        errors.append(f"Model Derivative: {exc}")
        return {
            "format": "dwg",
            "engine": "autodesk_aps",
            "status": "failed",
            "units": None,
            "layers": [],
            "lines": [],
            "polylines": [],
            "blocks": [],
            "texts": [],
            "dimensions": [],
            "tables": [],
            "stats": {"file": path.name},
            "summary": "APS DWG processing failed: " + " | ".join(errors),
            "error": " | ".join(errors),
            "aps": aps_status(),
            "design_automation": design_automation_status(),
        }


def parse_civil3d_package(path: Path) -> dict[str, Any]:
    """Civil 3D integration entrypoint (exports / APS / Design Automation)."""
    suffix = path.suffix.lower()
    if suffix in {".xml", ".landxml"}:
        from app.services.cad.landxml_parser import parse_landxml

        result = parse_landxml(path)
        result["format"] = "civil3d"
        result["engine"] = "civil3d_via_landxml"
        result["status"] = "extracted"
        result["summary"] = "Civil 3D data ingested via LandXML export. " + (result.get("summary") or "")
        return result

    if suffix == ".json":
        import json

        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        return {
            "format": "civil3d",
            "engine": "civil3d_json_export",
            "status": "extracted",
            "units": data.get("units"),
            "layers": data.get("layers") or [],
            "lines": data.get("lines") or [],
            "polylines": data.get("polylines") or [],
            "blocks": data.get("blocks") or [],
            "texts": data.get("texts") or [],
            "dimensions": data.get("dimensions") or [],
            "tables": data.get("tables") or [],
            "stats": data.get("stats") or {"keys": list(data.keys())[:40]},
            "summary": "Civil 3D JSON export ingested into CAD Intelligence Engine.",
        }

    # Native Civil 3D/DWG package → Design Automation / APS
    result = parse_dwg(path)
    result["format"] = "civil3d"
    engine = result.get("engine") or ""
    if "design_automation" in engine:
        result["summary"] = "Civil 3D/DWG via Design Automation. " + (result.get("summary") or "")
    elif engine.startswith("autodesk_aps") or engine == "autodesk_aps":
        result["engine"] = "civil3d_via_aps"
        result["summary"] = "Civil 3D/DWG via APS Model Derivative. " + (result.get("summary") or "")
    return result
