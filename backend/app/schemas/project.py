from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    location: str | None = None
    client_name: str | None = None
    country: str = "USA"
    state: str | None = None
    status: ProjectStatus = ProjectStatus.DRAFT


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    location: str | None = None
    client_name: str | None = None
    country: str | None = None
    state: str | None = None
    status: ProjectStatus | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    location: str | None
    client_name: str | None
    country: str
    state: str | None
    status: ProjectStatus
    owner_id: int
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    eoq_count: int = 0
