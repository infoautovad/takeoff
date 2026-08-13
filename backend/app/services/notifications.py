from sqlalchemy.orm import Session

from app.models.notification import Notification


def notify(
    db: Session,
    *,
    user_id: int,
    title: str,
    message: str,
    category: str = "general",
    project_id: int | None = None,
) -> Notification:
    row = Notification(
        user_id=user_id,
        project_id=project_id,
        title=title,
        message=message,
        category=category,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
