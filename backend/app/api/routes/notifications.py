from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User

router = APIRouter()


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    project_id: int | None
    title: str
    message: str
    category: str
    is_read: bool
    created_at: str

    @classmethod
    def from_row(cls, row: Notification) -> "NotificationOut":
        return cls(
            id=row.id,
            user_id=row.user_id,
            project_id=row.project_id,
            title=row.title,
            message=row.message,
            category=row.category,
            is_read=row.is_read,
            created_at=row.created_at.isoformat(),
        )


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).limit(50)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return [NotificationOut.from_row(n) for n in db.scalars(stmt).all()]


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    count = db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
    ) or 0
    return {"count": count}


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationOut:
    row = db.get(Notification, notification_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.is_read = True
    db.commit()
    db.refresh(row)
    return NotificationOut.from_row(row)


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    rows = db.scalars(select(Notification).where(Notification.user_id == current_user.id, Notification.is_read.is_(False))).all()
    for row in rows:
        row.is_read = True
    db.commit()
    return {"updated": len(list(rows))}
