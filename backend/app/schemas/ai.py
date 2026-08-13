from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    project_id: int
    engine: str
    summary: str | None
    findings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ProcessResultOut(BaseModel):
    document_id: int
    status: str
    analysis: AnalysisOut | None = None
    error: str | None = None


class ChatAskIn(BaseModel):
    question: str = Field(min_length=2, max_length=4000)


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    user_id: int
    role: str
    content: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
