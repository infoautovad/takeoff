from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.projects import _get_accessible_project
from app.database import get_db
from app.models.boq import BOQItemStatus, BOQStatus
from app.models.document import Document
from app.models.project import ProjectStatus
from app.models.user import User
from app.schemas.boq import BOQItemOut, BOQItemUpdate, BOQOut
from app.services.activity import log_activity
from app.services.boq_service import (
    export_boq_csv,
    export_boq_excel,
    generate_boq_for_project,
    get_boq,
    get_boq_item,
    list_project_boqs,
    update_boq_item,
)
from app.services.notifications import notify

router = APIRouter()


class ApprovalIn(BaseModel):
    action: str  # submit | approve | reject
    note: str | None = None


class GenerateBoqIn(BaseModel):
    """Optional document scope — omit or empty = all analyzed files in the project."""
    document_ids: list[int] | None = Field(default=None)


@router.get("/projects/{project_id}", response_model=list[BOQOut])
def list_boqs(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BOQOut]:
    _get_accessible_project(db, project_id, current_user)
    return [BOQOut.model_validate(b) for b in list_project_boqs(db, project_id)]


@router.post("/projects/{project_id}/generate", response_model=BOQOut)
def generate_boq(
    project_id: int,
    payload: GenerateBoqIn = GenerateBoqIn(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BOQOut:
    project = _get_accessible_project(db, project_id, current_user)
    document_ids = payload.document_ids or None
    if document_ids:
        docs = list(
            db.scalars(
                select(Document).where(
                    Document.project_id == project_id,
                    Document.id.in_(document_ids),
                )
            ).all()
        )
        found = {d.id for d in docs}
        missing = [i for i in document_ids if i not in found]
        if missing:
            raise HTTPException(status_code=400, detail=f"Document(s) not in this project: {missing}")

    try:
        boq = generate_boq_for_project(
            db,
            project,
            current_user.id,
            document_ids=document_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scope_msg = (
        f" from {len(document_ids)} file(s)" if document_ids else " from all analyzed files"
    )
    log_activity(
        db,
        user_id=current_user.id,
        project_id=project_id,
        action="boq_generated",
        message=f"Generated Estimate Of Quantities v{boq.version}{scope_msg}",
        entity_type="boq",
        entity_id=boq.id,
    )
    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="Estimate Of Quantities generated",
        message=f"{boq.title} is ready for review",
        category="boq",
    )
    return BOQOut.model_validate(boq)


@router.get("/{boq_id}", response_model=BOQOut)
def get_boq_detail(
    boq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BOQOut:
    boq = get_boq(db, boq_id)
    if not boq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    _get_accessible_project(db, boq.project_id, current_user)
    return BOQOut.model_validate(boq)


@router.patch("/items/{item_id}", response_model=BOQItemOut)
def patch_boq_item(
    item_id: int,
    payload: BOQItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BOQItemOut:
    item = get_boq_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities item not found")
    boq = get_boq(db, item.boq_id)
    if not boq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    _get_accessible_project(db, boq.project_id, current_user)

    if payload.status is not None and payload.status not in set(BOQItemStatus):
        raise HTTPException(status_code=400, detail="Invalid item status")

    updated = update_boq_item(
        db,
        item,
        status=payload.status,
        quantity=payload.quantity,
        description=payload.description,
        unit=payload.unit,
        item_code=payload.item_code,
        review_note=payload.notes,
    )
    log_activity(
        db,
        user_id=current_user.id,
        project_id=boq.project_id,
        action="boq_item_updated",
        message=f"Updated Estimate Of Quantities item {updated.item_number}: {updated.description[:80]}",
        entity_type="boq_item",
        entity_id=updated.id,
    )
    return BOQItemOut.model_validate(updated)


@router.get("/{boq_id}/export/excel")
def download_boq_excel(
    boq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    boq = get_boq(db, boq_id)
    if not boq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    _get_accessible_project(db, boq.project_id, current_user)

    content = export_boq_excel(boq)
    filename = f"AutoVAD_Estimate_Of_Quantities_v{boq.version}_{boq.project_id}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{boq_id}/export/csv")
def download_boq_csv(
    boq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    boq = get_boq(db, boq_id)
    if not boq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    _get_accessible_project(db, boq.project_id, current_user)

    content = export_boq_csv(boq)
    filename = f"AutoVAD_Estimate_Of_Quantities_v{boq.version}_{boq.project_id}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{boq_id}/approval", response_model=BOQOut)
def update_boq_approval(
    boq_id: int,
    payload: ApprovalIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BOQOut:
    boq = get_boq(db, boq_id)
    if not boq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    project = _get_accessible_project(db, boq.project_id, current_user)

    action = payload.action.lower().strip()
    if action == "submit":
        boq.status = BOQStatus.IN_REVIEW
        project.status = ProjectStatus.IN_REVIEW
        title = "Review requested"
        message = f"{boq.title} submitted for review"
    elif action == "approve":
        boq.status = BOQStatus.APPROVED
        project.status = ProjectStatus.APPROVED
        title = "Estimate Of Quantities approved"
        message = f"{boq.title} approved"
    elif action == "reject":
        boq.status = BOQStatus.REJECTED
        title = "Estimate Of Quantities rejected"
        message = f"{boq.title} rejected" + (f": {payload.note}" if payload.note else "")
    else:
        raise HTTPException(status_code=400, detail="action must be submit, approve, or reject")

    if payload.note:
        boq.notes = ((boq.notes or "") + f"\n[{action}] {payload.note}").strip()

    db.commit()
    db.refresh(boq)
    notify(
        db,
        user_id=current_user.id,
        project_id=project.id,
        title=title,
        message=message,
        category="approval",
    )
    log_activity(
        db,
        user_id=current_user.id,
        project_id=project.id,
        action=f"boq_{action}",
        message=message,
        entity_type="boq",
        entity_id=boq.id,
    )
    return BOQOut.model_validate(boq)
