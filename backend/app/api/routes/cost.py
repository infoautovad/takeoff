import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.projects import _get_accessible_project
from app.database import get_db
from app.models.cost import CostEstimate, SORItem
from app.models.user import User
from app.services.activity import log_activity
from app.services.cost_service import generate_cost_estimate, import_sor_file, list_sor
from app.services.notifications import notify

router = APIRouter()


class SOROut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    item_code: str | None
    description: str
    unit: str
    rate: float


class CostEstimateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    eoq_id: int
    title: str
    currency: str
    total_amount: float
    breakdown: dict
    created_at: str


def _estimate_out(row: CostEstimate) -> CostEstimateOut:
    breakdown = {}
    if row.breakdown_json:
        try:
            breakdown = json.loads(row.breakdown_json)
        except json.JSONDecodeError:
            breakdown = {}
    return CostEstimateOut(
        id=row.id,
        project_id=row.project_id,
        eoq_id=row.eoq_id,
        title=row.title,
        currency=row.currency,
        total_amount=float(row.total_amount),
        breakdown=breakdown,
        created_at=row.created_at.isoformat(),
    )


@router.get("/projects/{project_id}/sor", response_model=list[SOROut])
def get_sor(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[SOROut]:
    _get_accessible_project(db, project_id, current_user)
    items = list_sor(db, project_id)
    return [
        SOROut(
            id=i.id,
            project_id=i.project_id,
            item_code=i.item_code,
            description=i.description,
            unit=i.unit,
            rate=float(i.rate),
        )
        for i in items
    ]


@router.post("/projects/{project_id}/sor/upload", response_model=list[SOROut])
async def upload_sor(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SOROut]:
    _get_accessible_project(db, project_id, current_user)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="Upload CSV or Excel SOR file")

    data = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        items = import_sor_file(db, project_id, tmp_path, file.filename)
    finally:
        tmp_path.unlink(missing_ok=True)

    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="SOR uploaded",
        message=f"Imported {len(items)} SOR rate item(s) from {file.filename}",
        category="cost",
    )
    return [
        SOROut(
            id=i.id,
            project_id=i.project_id,
            item_code=i.item_code,
            description=i.description,
            unit=i.unit,
            rate=float(i.rate),
        )
        for i in items
    ]


@router.post("/projects/{project_id}/estimate/{eoq_id}", response_model=CostEstimateOut)
def create_estimate(
    project_id: int,
    eoq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CostEstimateOut:
    _get_accessible_project(db, project_id, current_user)
    try:
        estimate = generate_cost_estimate(db, project_id=project_id, eoq_id=eoq_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_activity(
        db,
        user_id=current_user.id,
        project_id=project_id,
        action="cost_estimated",
        message=f"Generated cost estimate total {estimate.total_amount} {estimate.currency}",
        entity_type="cost_estimate",
        entity_id=estimate.id,
    )
    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="Cost estimate ready",
        message=f"Estimated total: {estimate.total_amount} {estimate.currency}",
        category="cost",
    )
    return _estimate_out(estimate)


@router.get("/projects/{project_id}/estimates", response_model=list[CostEstimateOut])
def list_estimates(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CostEstimateOut]:
    _get_accessible_project(db, project_id, current_user)
    rows = db.scalars(
        select(CostEstimate).where(CostEstimate.project_id == project_id).order_by(CostEstimate.created_at.desc())
    ).all()
    return [_estimate_out(r) for r in rows]
