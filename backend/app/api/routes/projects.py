from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.eoq import EOQ
from app.models.document import Document
from app.models.project import Project, ProjectMember, ProjectMemberRole, ProjectStatus
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services.activity import log_activity
from app.services.notifications import notify


class ShareProjectIn(BaseModel):
    email: EmailStr
    role: ProjectMemberRole = ProjectMemberRole.ENGINEER

router = APIRouter()


def _project_access_filter(user: User):
    return or_(
        Project.owner_id == user.id,
        Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)),
    )


def _to_project_out(db: Session, project: Project) -> ProjectOut:
    doc_count = db.scalar(select(func.count()).select_from(Document).where(Document.project_id == project.id)) or 0
    eoq_count = db.scalar(select(func.count()).select_from(EOQ).where(EOQ.project_id == project.id)) or 0
    data = ProjectOut.model_validate(project)
    data.document_count = doc_count
    data.eoq_count = eoq_count
    return data


def _get_accessible_project(db: Session, project_id: int, user: User) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, _project_access_filter(user)))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(
    status_filter: ProjectStatus | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectOut]:
    stmt = select(Project).where(_project_access_filter(current_user)).order_by(Project.updated_at.desc())
    if status_filter:
        stmt = stmt.where(Project.status == status_filter)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Project.name.ilike(like),
                Project.location.ilike(like),
                Project.client_name.ilike(like),
            )
        )
    projects = db.scalars(stmt).all()
    return [_to_project_out(db, p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectOut:
    project = Project(
        name=payload.name.strip(),
        description=payload.description,
        location=payload.location,
        client_name=payload.client_name,
        country=payload.country or "USA",
        state=payload.state,
        status=payload.status,
        owner_id=current_user.id,
    )
    db.add(project)
    db.flush()

    membership = ProjectMember(
        project_id=project.id,
        user_id=current_user.id,
        role=ProjectMemberRole.OWNER,
    )
    db.add(membership)
    db.commit()
    db.refresh(project)

    log_activity(
        db,
        user_id=current_user.id,
        project_id=project.id,
        action="project_created",
        message=f"Created project '{project.name}'",
        entity_type="project",
        entity_id=project.id,
    )
    return _to_project_out(db, project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectOut:
    project = _get_accessible_project(db, project_id, current_user)
    return _to_project_out(db, project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectOut:
    project = _get_accessible_project(db, project_id, current_user)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(project, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(project)

    log_activity(
        db,
        user_id=current_user.id,
        project_id=project.id,
        action="project_updated",
        message=f"Updated project '{project.name}'",
        entity_type="project",
        entity_id=project.id,
    )
    return _to_project_out(db, project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_project(
    project_id: int,
    hard_delete: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    project = _get_accessible_project(db, project_id, current_user)

    if hard_delete:
        name = project.name
        db.delete(project)
        db.commit()
        log_activity(
            db,
            user_id=current_user.id,
            project_id=None,
            action="project_deleted",
            message=f"Deleted project '{name}'",
            entity_type="project",
            entity_id=project_id,
        )
        return

    project.status = ProjectStatus.ARCHIVED
    db.commit()
    log_activity(
        db,
        user_id=current_user.id,
        project_id=project.id,
        action="project_archived",
        message=f"Archived project '{project.name}'",
        entity_type="project",
        entity_id=project.id,
    )


@router.get("/{project_id}/members")
def list_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    _get_accessible_project(db, project_id, current_user)
    members = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id)).all()
    out = []
    for m in members:
        user = db.get(User, m.user_id)
        out.append(
            {
                "id": m.id,
                "user_id": m.user_id,
                "email": user.email if user else None,
                "full_name": user.full_name if user else None,
                "role": m.role.value,
            }
        )
    return out


@router.post("/{project_id}/share", status_code=status.HTTP_201_CREATED)
def share_project(
    project_id: int,
    payload: ShareProjectIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    project = _get_accessible_project(db, project_id, current_user)
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can share this project")

    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user:
        raise HTTPException(status_code=404, detail="User with this email is not registered")

    existing = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
    )
    if existing:
        existing.role = payload.role
        db.commit()
        member = existing
    else:
        member = ProjectMember(project_id=project_id, user_id=user.id, role=payload.role)
        db.add(member)
        db.commit()
        db.refresh(member)

    notify(
        db,
        user_id=user.id,
        project_id=project_id,
        title="Project shared with you",
        message=f"{current_user.full_name} shared '{project.name}' ({payload.role.value})",
        category="share",
    )
    return {
        "id": member.id,
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": member.role.value,
    }
