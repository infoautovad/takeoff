import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.api.routes.projects import _get_accessible_project
from app.config import get_settings
from app.database import get_db
from app.models.cad import CadModel
from app.models.document import Document
from app.models.user import User
from app.services.activity import log_activity
from app.services.cad.aps_client import aps_configured, aps_status
from app.services.cad.design_automation import (
    design_automation_status,
    setup_design_automation,
)
from app.services.cad.engine import detect_cad_format, list_project_cad_models
from app.services.notifications import notify
from app.services.openai_client import openai_status
from app.services.processing import process_document

router = APIRouter()


class CadQuantityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    category: str | None
    unit: str
    quantity: float
    layer: str | None
    entity_type: str | None
    calculation_method: str | None
    source_reference: str | None
    confidence: float | None


class CadModelOut(BaseModel):
    id: int
    project_id: int
    document_id: int
    source_format: str
    status: str
    engine: str
    units: str | None
    summary: str | None
    layers: list
    entities: dict
    blocks: list
    dimensions: list
    texts: list
    tables: list
    stats: dict
    quantities: list[CadQuantityOut] = Field(default_factory=list)
    error_message: str | None
    created_at: str


def _model_out(model) -> CadModelOut:
    def loads(raw, default):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    return CadModelOut(
        id=model.id,
        project_id=model.project_id,
        document_id=model.document_id,
        source_format=model.source_format.value,
        status=model.status.value,
        engine=model.engine,
        units=model.units,
        summary=model.summary,
        layers=loads(model.layers_json, []),
        entities=loads(model.entities_json, {}),
        blocks=loads(model.blocks_json, []),
        dimensions=loads(model.dimensions_json, []),
        texts=loads(model.texts_json, []),
        tables=loads(model.tables_json, []),
        stats=loads(model.raw_stats_json, {}),
        quantities=[CadQuantityOut.model_validate(q) for q in (model.quantities or [])],
        error_message=model.error_message,
        created_at=model.created_at.isoformat(),
    )


@router.get("/capabilities")
def cad_capabilities() -> dict:
    settings = get_settings()
    oai = openai_status()
    aps = aps_status()
    da = design_automation_status()
    return {
        "module": "CAD & Civil 3D Intelligence Engine",
        "enabled": settings.cad_engine_enabled,
        "supported_now": {
            "dxf": "Local geometry parser (layers, lines, polylines, blocks, dimensions, text, hatches)",
            "landxml": "Alignments, surfaces, pipes, structures, cross-sections",
            "civil3d_json": "Civil 3D / APS JSON export ingestion",
            "dwg_design_automation": (
                "Cloud AutoCAD Design Automation (DWG→DXF script, optional Civil AppBundle)"
            ),
            "dwg_model_derivative": "APS Model Derivative properties fallback",
        },
        "pipeline": [
            "Upload DXF / DWG / LandXML / Civil 3D export",
            "Design Automation (cloud AutoCAD) when enabled",
            "Model Derivative fallback for DWG properties",
            "Extract layers, lines, polylines, blocks, dimensions, text, tables",
            "Quantity engine (length / area / count)",
            "Optional OpenAI enrichment (when key configured)",
            "Generate Estimate Of Quantities + material summary + Excel + confidence + source refs",
        ],
        "autodesk_aps_configured": aps_configured(),
        "autodesk_aps": aps,
        "design_automation": da,
        "openai": oai,
        "cad_openai_enrichment": settings.cad_openai_enrichment,
        "ready": {
            "dxf_landxml_local": True,
            "dwg_via_design_automation": da["configured"],
            "dwg_via_aps": aps["configured"],
            "openai_enrichment": oai["configured"] and settings.cad_openai_enrichment,
        },
        "setup_hints": {
            "design_automation": da.get("setup_hint"),
            "aps_app": (
                "In APS app settings enable Design Automation API + Model Derivative + Data Management. "
                "Then call POST /api/cad/design-automation/setup once."
            ),
        },
    }


@router.post("/design-automation/setup")
def design_automation_setup(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Register Design Automation nickname + activities on this APS account."""
    _ = current_user
    settings = get_settings()
    if not settings.cad_engine_enabled:
        raise HTTPException(status_code=503, detail="CAD engine is disabled")
    try:
        return setup_design_automation()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/design-automation/status")
def design_automation_status_route(
    current_user: User = Depends(get_current_user),
) -> dict:
    _ = current_user
    return design_automation_status()


@router.get("/projects/{project_id}", response_model=list[CadModelOut])
def list_cad_models(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CadModelOut]:
    _get_accessible_project(db, project_id, current_user)
    return [_model_out(m) for m in list_project_cad_models(db, project_id)]


@router.post("/documents/{document_id}/process", response_model=CadModelOut)
def process_cad(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CadModelOut:
    settings = get_settings()
    if not settings.cad_engine_enabled:
        raise HTTPException(status_code=503, detail="CAD engine is disabled")

    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    _get_accessible_project(db, document.project_id, current_user)

    if not detect_cad_format(document):
        raise HTTPException(status_code=400, detail="File is not a CAD/Civil format (DXF/DWG/LandXML/Civil3D)")

    try:
        # Mirrors CAD quantities into DocumentAnalysis for EOQ / chat.
        process_document(db, document)
        model = db.scalar(
            select(CadModel)
            .options(selectinload(CadModel.quantities))
            .where(CadModel.document_id == document.id)
        )
        if not model:
            raise RuntimeError("CAD model was not created")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CAD processing failed: {exc}") from exc

    log_activity(
        db,
        user_id=current_user.id,
        project_id=document.project_id,
        action="cad_processed",
        message=f"CAD engine processed '{document.original_filename}' ({model.status.value})",
        entity_type="cad_model",
        entity_id=model.id,
    )
    notify(
        db,
        user_id=current_user.id,
        project_id=document.project_id,
        title="CAD processing finished",
        message=model.summary or f"{document.original_filename} processed",
        category="cad",
    )
    return _model_out(model)


@router.post("/projects/{project_id}/process-all", response_model=list[CadModelOut])
def process_all_cad(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CadModelOut]:
    _get_accessible_project(db, project_id, current_user)

    docs = db.scalars(select(Document).where(Document.project_id == project_id)).all()
    results: list[CadModelOut] = []
    for doc in docs:
        if not detect_cad_format(doc):
            continue
        try:
            process_document(db, doc)
            model = db.scalar(
                select(CadModel)
                .options(selectinload(CadModel.quantities))
                .where(CadModel.document_id == doc.id)
            )
            if model:
                results.append(_model_out(model))
        except Exception:
            continue
    if not results:
        raise HTTPException(status_code=400, detail="No CAD/Civil documents found to process")
    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="CAD batch processing finished",
        message=f"Processed {len(results)} CAD/Civil file(s)",
        category="cad",
    )
    return results
