from pydantic import BaseModel, Field


class AttentionItem(BaseModel):
    kind: str
    severity: str = "warning"
    title: str
    detail: str
    project_id: int
    project_name: str
    entity_id: int | None = None
    action_label: str = "Open"


class WeekSnapshot(BaseModel):
    documents_uploaded: int = 0
    boqs_generated: int = 0
    projects_touched: int = 0
    failed_uploads: int = 0


class DashboardStats(BaseModel):
    total_projects: int
    active_projects: int
    documents_uploaded: int
    boqs_generated: int
    pending_reviews: int
    recent_activity: list[dict]
    needs_attention: list[AttentionItem] = Field(default_factory=list)
    week: WeekSnapshot = Field(default_factory=WeekSnapshot)
