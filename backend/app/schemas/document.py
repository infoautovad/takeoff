from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentType, ProcessingStatus


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    uploaded_by: int
    original_filename: str
    content_type: str
    file_size: int
    document_type: DocumentType
    processing_status: ProcessingStatus
    page_count: int | None
    revision_label: str | None
    notes: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
