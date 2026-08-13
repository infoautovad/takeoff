import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.projects import _get_accessible_project
from app.database import get_db
from app.models.comparison import ComparisonResult
from app.models.user import User
from app.services.compare_service import compare_boqs, compare_drawings
from app.services.notifications import notify

router = APIRouter()


class BoqCompareIn(BaseModel):
    left_boq_id: int
    right_boq_id: int


class DrawingCompareIn(BaseModel):
    left_document_id: int
    right_document_id: int


class ComparisonOut(BaseModel):
    id: int
    project_id: int
    comparison_type: str
    left_label: str
    right_label: str
    summary: str | None
    result: dict
    created_at: str


def _out(row: ComparisonResult) -> ComparisonOut:
    result = {}
    if row.result_json:
        try:
            result = json.loads(row.result_json)
        except json.JSONDecodeError:
            result = {}
    return ComparisonOut(
        id=row.id,
        project_id=row.project_id,
        comparison_type=row.comparison_type,
        left_label=row.left_label,
        right_label=row.right_label,
        summary=row.summary,
        result=result,
        created_at=row.created_at.isoformat(),
    )


@router.post("/projects/{project_id}/boq", response_model=ComparisonOut)
def boq_compare(
    project_id: int,
    payload: BoqCompareIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComparisonOut:
    _get_accessible_project(db, project_id, current_user)
    try:
        row = compare_boqs(
            db,
            project_id=project_id,
            left_boq_id=payload.left_boq_id,
            right_boq_id=payload.right_boq_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="BOQ comparison ready",
        message=row.summary or "BOQ comparison completed",
        category="comparison",
    )
    return _out(row)


@router.post("/projects/{project_id}/drawings", response_model=ComparisonOut)
def drawing_compare(
    project_id: int,
    payload: DrawingCompareIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComparisonOut:
    _get_accessible_project(db, project_id, current_user)
    try:
        row = compare_drawings(
            db,
            project_id=project_id,
            left_document_id=payload.left_document_id,
            right_document_id=payload.right_document_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="Drawing comparison ready",
        message=row.summary or "Drawing comparison completed",
        category="comparison",
    )
    return _out(row)


@router.get("/projects/{project_id}", response_model=list[ComparisonOut])
def list_comparisons(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ComparisonOut]:
    _get_accessible_project(db, project_id, current_user)
    rows = db.scalars(
        select(ComparisonResult).where(ComparisonResult.project_id == project_id).order_by(ComparisonResult.created_at.desc())
    ).all()
    return [_out(r) for r in rows]
