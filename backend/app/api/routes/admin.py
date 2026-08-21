from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.config import get_settings
from app.database import get_db
from app.models.activity import ActivityLog
from app.models.analysis import DocumentAnalysis
from app.models.eoq import EOQ
from app.models.document import Document, ProcessingStatus
from app.models.project import Project
from app.models.user import User, UserRole
from app.core.security import hash_password

router = APIRouter()


class AdminUserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    plan: str = "starter"
    is_active: bool
    is_blocked: bool
    created_at: str


class UserUpdateIn(BaseModel):
    role: UserRole | None = None
    is_blocked: bool | None = None
    is_active: bool | None = None


@router.get("/overview")
def admin_overview(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)

    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    active_users = db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True), User.is_blocked.is_(False))) or 0
    total_projects = db.scalar(select(func.count()).select_from(Project)) or 0
    total_docs = db.scalar(select(func.count()).select_from(Document)) or 0
    completed_jobs = db.scalar(select(func.count()).select_from(Document).where(Document.processing_status == ProcessingStatus.COMPLETED)) or 0
    failed_jobs = db.scalar(select(func.count()).select_from(Document).where(Document.processing_status == ProcessingStatus.FAILED)) or 0
    processing_jobs = db.scalar(
        select(func.count()).select_from(Document).where(
            Document.processing_status.in_([ProcessingStatus.PROCESSING, ProcessingStatus.QUEUED])
        )
    ) or 0
    eoqs = db.scalar(select(func.count()).select_from(EOQ)) or 0
    analyses = db.scalar(select(func.count()).select_from(DocumentAnalysis)) or 0
    recent_errors = db.scalars(
        select(Document).where(Document.processing_status == ProcessingStatus.FAILED).order_by(Document.updated_at.desc()).limit(10)
    ).all()
    recent_activity = db.scalars(select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(15)).all()
    storage_path = settings.storage_path
    storage_bytes = sum(f.stat().st_size for f in storage_path.rglob("*") if f.is_file())

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_projects": total_projects,
        "documents_uploaded": total_docs,
        "eoqs_generated": eoqs,
        "analyses_completed": analyses,
        "pdf_processing_queue": processing_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "storage_usage_mb": round(storage_bytes / (1024 * 1024), 2),
        "database": "sqlite" if settings.database_url.startswith("sqlite") else "postgresql",
        "openai_configured": bool(settings.openai_api_key),
        "ai_mode": "openai" if settings.openai_api_key else "heuristic",
        "system_health": "healthy" if failed_jobs < max(3, completed_jobs) else "degraded",
        "activity_last_24h": db.scalar(select(func.count()).select_from(ActivityLog).where(ActivityLog.created_at >= day_ago)) or 0,
        "error_logs": [
            {
                "document_id": d.id,
                "filename": d.original_filename,
                "error": d.error_message,
                "updated_at": d.updated_at.isoformat(),
            }
            for d in recent_errors
        ],
        "recent_activity": [
            {
                "id": a.id,
                "action": a.action,
                "message": a.message,
                "created_at": a.created_at.isoformat(),
            }
            for a in recent_activity
        ],
    }


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(get_current_admin)) -> list[AdminUserOut]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [
        AdminUserOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role.value,
            plan=getattr(u.plan, "value", None) or "starter",
            is_active=u.is_active,
            is_blocked=u.is_blocked,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    payload: UserUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return AdminUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        plan=getattr(user.plan, "value", None) or "starter",
        is_active=user.is_active,
        is_blocked=user.is_blocked,
        created_at=user.created_at.isoformat(),
    )


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    temp = "AutoVAD@123"
    user.hashed_password = hash_password(temp)
    db.commit()
    return {"message": "Password reset", "temporary_password": temp}
