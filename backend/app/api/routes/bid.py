from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
import tempfile
from pathlib import Path

from app.api.deps import get_current_user
from app.api.routes.projects import _get_accessible_project
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.services.activity import log_activity
from app.services.bid_service import (
    delete_template,
    import_bid_template,
    list_templates,
    map_eoq_to_template,
    set_active_template,
)
from app.services.csi_mapper import list_csi_catalog
from app.services.notifications import notify

router = APIRouter()
settings = get_settings()


class BidLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_number: str
    csi_code: str | None
    item_code: str | None
    description: str
    unit: str
    default_rate: float | None
    sort_order: int


class BidTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    source_filename: str | None
    is_active: bool
    notes: str | None
    created_by: int
    created_at: str
    lines: list[BidLineOut] = Field(default_factory=list)


def _template_out(t) -> BidTemplateOut:
    return BidTemplateOut(
        id=t.id,
        project_id=t.project_id,
        name=t.name,
        source_filename=t.source_filename,
        is_active=t.is_active,
        notes=t.notes,
        created_by=t.created_by,
        created_at=t.created_at.isoformat(),
        lines=[
            BidLineOut(
                id=ln.id,
                line_number=ln.line_number,
                csi_code=ln.csi_code,
                item_code=ln.item_code,
                description=ln.description,
                unit=ln.unit,
                default_rate=ln.default_rate,
                sort_order=ln.sort_order,
            )
            for ln in sorted(t.lines or [], key=lambda x: x.sort_order)
        ],
    )


@router.get("/csi-catalog")
def csi_catalog(current_user: User = Depends(get_current_user)) -> dict:
    return {"division_focus": "31 / 32 / 33 (+ related civil)", "items": list_csi_catalog()}


@router.get("/projects/{project_id}/templates", response_model=list[BidTemplateOut])
def get_templates(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BidTemplateOut]:
    _get_accessible_project(db, project_id, current_user)
    return [_template_out(t) for t in list_templates(db, project_id)]


@router.post("/projects/{project_id}/templates/upload", response_model=BidTemplateOut)
async def upload_template(
    project_id: int,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BidTemplateOut:
    _get_accessible_project(db, project_id, current_user)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".xlsx", ".xls", ".csv"}:
        raise HTTPException(status_code=400, detail="Upload PDF, Excel, or CSV bid template")

    data = await file.read()
    # max_upload_size_mb <= 0 means unlimited (no size rejection).
    if settings.max_upload_size_mb > 0:
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
            )

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        template = import_bid_template(
            db,
            project_id=project_id,
            user_id=current_user.id,
            path=tmp_path,
            filename=file.filename,
            name=name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    log_activity(
        db,
        user_id=current_user.id,
        project_id=project_id,
        action="bid_template_upload",
        message=f"Uploaded bid template '{template.name}' ({len(template.lines)} lines)",
    )
    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="Bid template uploaded",
        message=f"Imported {len(template.lines)} bid line(s) from {file.filename}",
        category="eoq",
    )
    return _template_out(template)


@router.post("/projects/{project_id}/templates/{template_id}/activate", response_model=BidTemplateOut)
def activate_template(
    project_id: int,
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BidTemplateOut:
    _get_accessible_project(db, project_id, current_user)
    try:
        template = set_active_template(db, project_id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _template_out(template)


@router.delete("/projects/{project_id}/templates/{template_id}", status_code=204)
def remove_template(
    project_id: int,
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _get_accessible_project(db, project_id, current_user)
    try:
        delete_template(db, project_id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/eoq/{eoq_id}/map")
def map_eoq(
    project_id: int,
    eoq_id: int,
    template_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _get_accessible_project(db, project_id, current_user)
    try:
        result = map_eoq_to_template(db, eoq_id=eoq_id, template_id=template_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_activity(
        db,
        user_id=current_user.id,
        project_id=project_id,
        action="bid_map",
        message=f"Mapped Estimate Of Quantities {eoq_id} to bid template ({result['matched']}/{result['total']} matched)",
    )
    return result
