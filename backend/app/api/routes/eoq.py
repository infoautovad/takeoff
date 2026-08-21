from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.projects import _get_accessible_project
from app.database import get_db
from app.models.document import Document
from app.models.eoq import EOQItemStatus, EOQStatus
from app.models.project import ProjectStatus
from app.models.user import User
from app.schemas.eoq import EOQItemOut, EOQItemUpdate, EOQOut
from app.services.activity import log_activity
from app.services.eoq_service import (
    export_eoq_csv,
    export_eoq_excel,
    generate_eoq_for_project,
    get_eoq,
    get_eoq_item,
    list_project_eoqs,
    load_project_utilities_detail,
    update_eoq_item,
)
from app.services.notifications import notify

router = APIRouter()


class ApprovalIn(BaseModel):
    action: str  # submit | approve | reject
    note: str | None = None


class GenerateEoqIn(BaseModel):
    """Optional document scope — omit or empty = all analyzed files in the project."""
    document_ids: list[int] | None = Field(default=None)


@router.get("/projects/{project_id}", response_model=list[EOQOut])
def list_eoqs(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EOQOut]:
    _get_accessible_project(db, project_id, current_user)
    return [EOQOut.model_validate(e) for e in list_project_eoqs(db, project_id)]


@router.post("/projects/{project_id}/generate", response_model=EOQOut)
def generate_eoq(
    project_id: int,
    payload: GenerateEoqIn = GenerateEoqIn(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EOQOut:
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
        eoq = generate_eoq_for_project(
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
        action="eoq_generated",
        message=f"Generated Estimate Of Quantities v{eoq.version}{scope_msg}",
        entity_type="eoq",
        entity_id=eoq.id,
    )
    notify(
        db,
        user_id=current_user.id,
        project_id=project_id,
        title="Estimate Of Quantities generated",
        message=f"{eoq.title} is ready for review",
        category="eoq",
    )
    return EOQOut.model_validate(eoq)


@router.get("/{eoq_id}", response_model=EOQOut)
def get_eoq_detail(
    eoq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EOQOut:
    eoq = get_eoq(db, eoq_id)
    if not eoq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    _get_accessible_project(db, eoq.project_id, current_user)
    return EOQOut.model_validate(eoq)


@router.patch("/items/{item_id}", response_model=EOQItemOut)
def patch_eoq_item(
    item_id: int,
    payload: EOQItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EOQItemOut:
    item = get_eoq_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities item not found")
    eoq = get_eoq(db, item.eoq_id)
    if not eoq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    _get_accessible_project(db, eoq.project_id, current_user)

    if payload.status is not None and payload.status not in set(EOQItemStatus):
        raise HTTPException(status_code=400, detail="Invalid item status")

    updated = update_eoq_item(
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
        project_id=eoq.project_id,
        action="eoq_item_updated",
        message=f"Updated Estimate Of Quantities item {updated.item_number}: {updated.description[:80]}",
        entity_type="eoq_item",
        entity_id=updated.id,
    )
    return EOQItemOut.model_validate(updated)


@router.get("/{eoq_id}/export/excel")
def download_eoq_excel(
    eoq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    eoq = get_eoq(db, eoq_id)
    if not eoq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    _get_accessible_project(db, eoq.project_id, current_user)

    content = export_eoq_excel(
        eoq,
        utilities_detail=load_project_utilities_detail(db, eoq.project_id),
    )
    filename = f"AutoVAD_Estimate_Of_Quantities_v{eoq.version}_{eoq.project_id}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{eoq_id}/export/csv")
def download_eoq_csv(
    eoq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    eoq = get_eoq(db, eoq_id)
    if not eoq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    _get_accessible_project(db, eoq.project_id, current_user)

    content = export_eoq_csv(eoq)
    filename = f"AutoVAD_Estimate_Of_Quantities_v{eoq.version}_{eoq.project_id}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{eoq_id}/approval", response_model=EOQOut)
def update_eoq_approval(
    eoq_id: int,
    payload: ApprovalIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EOQOut:
    eoq = get_eoq(db, eoq_id)
    if not eoq:
        raise HTTPException(status_code=404, detail="Estimate Of Quantities not found")
    project = _get_accessible_project(db, eoq.project_id, current_user)

    action = payload.action.lower().strip()
    if action == "submit":
        eoq.status = EOQStatus.IN_REVIEW
        project.status = ProjectStatus.IN_REVIEW
        title = "Review requested"
        message = f"{eoq.title} submitted for review"
    elif action == "approve":
        eoq.status = EOQStatus.APPROVED
        project.status = ProjectStatus.APPROVED
        title = "Estimate Of Quantities approved"
        message = f"{eoq.title} approved"
    elif action == "reject":
        eoq.status = EOQStatus.REJECTED
        title = "Estimate Of Quantities rejected"
        message = f"{eoq.title} rejected" + (f": {payload.note}" if payload.note else "")
    else:
        raise HTTPException(status_code=400, detail="action must be submit, approve, or reject")

    if payload.note:
        eoq.notes = ((eoq.notes or "") + f"\n[{action}] {payload.note}").strip()

    db.commit()
    db.refresh(eoq)
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
        action=f"eoq_{action}",
        message=message,
        entity_type="eoq",
        entity_id=eoq.id,
    )
    return EOQOut.model_validate(eoq)
