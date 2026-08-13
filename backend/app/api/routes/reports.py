import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.projects import _get_accessible_project
from app.database import get_db
from app.models.report import Report
from app.models.user import User
from app.services.notifications import notify
from app.services.report_service import generate_project_reports

router = APIRouter()


class ReportOut(BaseModel):
    id: int
    project_id: int
    report_type: str
    title: str
    summary: str | None
    content: dict
    created_at: str


def _out(row: Report) -> ReportOut:
    content = {}
    if row.content_json:
        try:
            content = json.loads(row.content_json)
        except json.JSONDecodeError:
            content = {}
    return ReportOut(
        id=row.id,
        project_id=row.project_id,
        report_type=row.report_type,
        title=row.title,
        summary=row.summary,
        content=content,
        created_at=row.created_at.isoformat(),
    )


@router.get("/projects/{project_id}", response_model=list[ReportOut])
def list_reports(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReportOut]:
    _get_accessible_project(db, project_id, current_user)
    rows = db.scalars(select(Report).where(Report.project_id == project_id).order_by(Report.created_at.desc())).all()
    return [_out(r) for r in rows]


@router.post("/projects/{project_id}/generate", response_model=list[ReportOut])
def generate_reports(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReportOut]:
    project = _get_accessible_project(db, project_id, current_user)
    rows = generate_project_reports(db, project, current_user.id)
    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="Reports generated",
        message=f"{len(rows)} project report(s) are ready",
        category="report",
    )
    return [_out(r) for r in rows]
