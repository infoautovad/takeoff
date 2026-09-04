"""CAD & Civil 3D Intelligence Engine orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.cad import CadJobStatus, CadModel, CadQuantity, CadSourceFormat
from app.models.document import Document, DocumentType, ProcessingStatus
from app.services.cad.autodesk_aps import parse_civil3d_package, parse_dwg
from app.services.cad.dxf_parser import parse_dxf
from app.services.cad.landxml_parser import parse_landxml
from app.services.cad.quantity_engine import build_quantities
from app.services.openai_client import enrich_cad_quantities_with_openai, openai_configured
from app.services.storage import storage_service
from app.config import get_settings


def _clip_rows(rows: list[dict[str, Any]] | list[Any], limit: int) -> tuple[list[Any], int]:
    if limit <= 0:
        return list(rows), 0
    total = len(rows)
    if total <= limit:
        return list(rows), 0
    return list(rows)[:limit], total - limit


def detect_cad_format(document: Document) -> CadSourceFormat | None:
    name = document.original_filename.lower()
    ext = Path(name).suffix.lower().lstrip(".")
    if document.document_type == DocumentType.DXF or ext == "dxf":
        return CadSourceFormat.DXF
    if document.document_type == DocumentType.DWG or ext == "dwg":
        return CadSourceFormat.DWG
    if document.document_type == DocumentType.LANDXML or ext in {"landxml"} or (
        ext == "xml" and "land" in name
    ):
        return CadSourceFormat.LANDXML
    if document.document_type == DocumentType.CIVIL3D or ext == "json" or "civil" in name:
        return CadSourceFormat.CIVIL3D
    if ext == "xml":
        return CadSourceFormat.LANDXML
    return None


def process_cad_document(db: Session, document: Document) -> CadModel:
    fmt = detect_cad_format(document)
    if not fmt:
        raise ValueError("Document is not a supported CAD/Civil format")

    model = db.scalar(select(CadModel).where(CadModel.document_id == document.id))
    if not model:
        model = CadModel(
            project_id=document.project_id,
            document_id=document.id,
            source_format=fmt,
        )
        db.add(model)

    model.status = CadJobStatus.PARSING
    model.error_message = None
    document.processing_status = ProcessingStatus.PROCESSING
    db.commit()

    try:
        path = storage_service.resolve_local_path(document.storage_key)
        if not path.exists():
            raise FileNotFoundError("CAD file missing from storage")

        if fmt == CadSourceFormat.DXF:
            extraction = parse_dxf(path)
        elif fmt == CadSourceFormat.LANDXML:
            extraction = parse_landxml(path)
        elif fmt == CadSourceFormat.CIVIL3D:
            extraction = parse_civil3d_package(path)
        else:
            extraction = parse_dwg(path)

        settings = get_settings()
        model.engine = extraction.get("engine") or "autovad_cad"
        model.units = str(extraction.get("units")) if extraction.get("units") is not None else None
        model.summary = extraction.get("summary")
        model.layers_json = json.dumps(extraction.get("layers") or [], ensure_ascii=True)

        lines_raw = extraction.get("lines") or []
        polys_raw = extraction.get("polylines") or []
        circles_raw = extraction.get("circles") or []
        hatches_raw = extraction.get("hatches") or []
        lines_kept, lines_dropped = _clip_rows(lines_raw, settings.cad_store_lines_limit)
        polys_kept, polys_dropped = _clip_rows(polys_raw, settings.cad_store_polylines_limit)
        circles_kept, circles_dropped = _clip_rows(circles_raw, settings.cad_store_circles_limit)
        hatches_kept, hatches_dropped = _clip_rows(hatches_raw, settings.cad_store_hatches_limit)
        truncation = {
            "lines_dropped": lines_dropped,
            "polylines_dropped": polys_dropped,
            "circles_dropped": circles_dropped,
            "hatches_dropped": hatches_dropped,
        }
        has_truncation = any(int(v) > 0 for v in truncation.values())

        model.entities_json = json.dumps(
            {
                "lines": lines_kept,
                "polylines": polys_kept,
                "circles": circles_kept,
                "hatches": hatches_kept,
                "alignments": extraction.get("alignments") or [],
                "pipes": extraction.get("pipes") or [],
                "surfaces": extraction.get("surfaces") or [],
                "volumes": extraction.get("volumes") or [],
                "cross_sections": extraction.get("cross_sections") or [],
                "_meta": {
                    "store_limits": {
                        "lines": settings.cad_store_lines_limit,
                        "polylines": settings.cad_store_polylines_limit,
                        "circles": settings.cad_store_circles_limit,
                        "hatches": settings.cad_store_hatches_limit,
                    },
                    "truncated": truncation,
                },
            },
            ensure_ascii=True,
        )
        model.blocks_json = json.dumps(extraction.get("blocks") or [], ensure_ascii=True)
        model.dimensions_json = json.dumps(extraction.get("dimensions") or [], ensure_ascii=True)
        model.texts_json = json.dumps(extraction.get("texts") or [], ensure_ascii=True)
        model.tables_json = json.dumps(extraction.get("tables") or [], ensure_ascii=True)
        raw_stats = dict(extraction.get("stats") or {})
        if has_truncation:
            raw_stats["entity_store_truncation"] = truncation
            model.summary = (
                f"{model.summary or ''} "
                "Stored entity payload was capped for database size; quantity takeoff used full parsed geometry."
            ).strip()
        model.raw_stats_json = json.dumps(raw_stats, ensure_ascii=True)

        status = extraction.get("status")
        if status == "needs_autodesk":
            model.status = CadJobStatus.NEEDS_AUTODESK
            document.processing_status = ProcessingStatus.COMPLETED
            model.quantities_json = json.dumps([], ensure_ascii=True)
            db.execute(delete(CadQuantity).where(CadQuantity.cad_model_id == model.id))
            db.commit()
            db.refresh(model)
            return model

        if status == "failed":
            model.status = CadJobStatus.FAILED
            model.error_message = extraction.get("error") or extraction.get("summary")
            document.processing_status = ProcessingStatus.FAILED
            document.error_message = model.error_message
            db.commit()
            db.refresh(model)
            return model

        quantities = build_quantities(extraction, source_label=document.original_filename)
        # Plugin / Design Automation may already emit quantity candidates
        for hint in extraction.get("quantities_hint") or []:
            if hint.get("description") and hint.get("quantity") is not None:
                quantities.append(dict(hint))
        if settings.cad_openai_enrichment and openai_configured():
            quantities = enrich_cad_quantities_with_openai(
                filename=document.original_filename,
                extraction_summary=extraction.get("summary") or "",
                stats=extraction.get("stats") or {},
                quantities=quantities,
                layers=extraction.get("layers") or [],
                blocks=extraction.get("blocks") or [],
                pipes=extraction.get("pipes") or [],
                texts=extraction.get("texts") or [],
            )
            model.engine = f"{model.engine}+openai"

        from app.services.traffic_control import consolidate_traffic_control_signs

        quantities, _tc_meta = consolidate_traffic_control_signs(
            quantities, allow_online_refresh=True
        )

        from app.services.cad.utility_stationing import build_utilities_detail

        try:
            utilities_detail = build_utilities_detail(extraction)
        except Exception as exc:  # noqa: BLE001
            utilities_detail = {
                "segments": [],
                "connections": [],
                "summary": {"error": str(exc)[:240]},
                "alignment": {"name": None, "source": "error"},
            }
        model.utilities_detail_json = json.dumps(utilities_detail, ensure_ascii=True)

        model.quantities_json = json.dumps(quantities, ensure_ascii=True)
        model.status = CadJobStatus.QUANTIFIED

        db.execute(delete(CadQuantity).where(CadQuantity.cad_model_id == model.id))
        db.flush()
        for q in quantities:
            db.add(
                CadQuantity(
                    cad_model_id=model.id,
                    item_code=q.get("item_code"),
                    description=q["description"],
                    category=q.get("category"),
                    unit=q["unit"],
                    quantity=float(q["quantity"]),
                    layer=q.get("layer"),
                    entity_type=q.get("entity_type"),
                    calculation_method=q.get("calculation_method"),
                    source_reference=q.get("source_reference"),
                    confidence=q.get("confidence"),
                )
            )

        document.processing_status = ProcessingStatus.COMPLETED
        document.error_message = None
        db.commit()
        return db.scalar(
            select(CadModel).options(selectinload(CadModel.quantities)).where(CadModel.id == model.id)
        )  # type: ignore[return-value]
    except Exception as exc:
        # Persist failure without re-raising so Analyze can return a CAD-specific error
        # instead of a generic client timeout / PDF tip message.
        model.status = CadJobStatus.FAILED
        model.error_message = str(exc)
        document.processing_status = ProcessingStatus.FAILED
        document.error_message = str(exc)
        db.commit()
        db.refresh(model)
        return model


def list_project_cad_models(db: Session, project_id: int) -> list[CadModel]:
    return list(
        db.scalars(
            select(CadModel)
            .options(selectinload(CadModel.quantities))
            .where(CadModel.project_id == project_id)
            .order_by(CadModel.created_at.desc())
        ).all()
    )
