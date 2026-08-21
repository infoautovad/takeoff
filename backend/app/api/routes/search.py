from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.eoq import EOQ, EOQItem
from app.models.document import Document
from app.models.project import Project, ProjectMember
from app.models.user import User

router = APIRouter()


@router.get("")
def global_search(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    like = f"%{q.strip()}%"
    accessible = select(Project.id).where(
        or_(
            Project.owner_id == current_user.id,
            Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == current_user.id)),
        )
    )

    projects = db.scalars(
        select(Project).where(Project.id.in_(accessible), or_(Project.name.ilike(like), Project.location.ilike(like), Project.client_name.ilike(like))).limit(20)
    ).all()
    documents = db.scalars(
        select(Document).where(Document.project_id.in_(accessible), Document.original_filename.ilike(like)).limit(20)
    ).all()
    items = db.scalars(
        select(EOQItem)
        .join(EOQ, EOQ.id == EOQItem.eoq_id)
        .where(
            EOQ.project_id.in_(accessible),
            or_(EOQItem.description.ilike(like), EOQItem.category.ilike(like), EOQItem.item_code.ilike(like)),
        )
        .limit(30)
    ).all()

    return {
        "query": q,
        "projects": [{"id": p.id, "name": p.name, "status": p.status.value, "location": p.location} for p in projects],
        "documents": [
            {"id": d.id, "project_id": d.project_id, "filename": d.original_filename, "status": d.processing_status.value}
            for d in documents
        ],
        "eoq_items": [
            {
                "id": i.id,
                "eoq_id": i.eoq_id,
                "description": i.description,
                "quantity": float(i.quantity),
                "unit": i.unit,
                "category": i.category,
            }
            for i in items
        ],
    }
