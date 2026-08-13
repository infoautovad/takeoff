from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentType(str, Enum):
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    IMAGE = "image"
    ZIP = "zip"
    DXF = "dxf"
    DWG = "dwg"
    LANDXML = "landxml"
    CIVIL3D = "civil3d"
    OTHER = "other"


class ProcessingStatus(str, Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    document_type: Mapped[DocumentType] = mapped_column(
        SAEnum(DocumentType, name="document_type", values_callable=lambda x: [e.value for e in x]),
        default=DocumentType.OTHER,
        nullable=False,
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, name="processing_status", values_callable=lambda x: [e.value for e in x]),
        default=ProcessingStatus.UPLOADED,
        nullable=False,
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship("Project", back_populates="documents")
    uploaded_by_user = relationship("User", back_populates="uploaded_documents")
    analysis = relationship("DocumentAnalysis", back_populates="document", uselist=False, cascade="all, delete-orphan")
