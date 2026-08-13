from sqlalchemy.orm import Session

from app.models.activity import ActivityLog


def log_activity(
    db: Session,
    *,
    user_id: int | None,
    project_id: int | None,
    action: str,
    message: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        user_id=user_id,
        project_id=project_id,
        action=action,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
