from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CadSourceFormat(str, Enum):
    DXF = "dxf"
    DWG = "dwg"
    LANDXML = "landxml"
    CIVIL3D = "civil3d"


class CadJobStatus(str, Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    EXTRACTED = "extracted"
    QUANTIFIED = "quantified"
    FAILED = "failed"
    NEEDS_AUTODESK = "needs_autodesk"


class CadModel(Base):
    """CAD / Civil 3D Intelligence Engine — one parsed model per uploaded CAD document."""

    __tablename__ = "cad_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True, nullable=False)
    source_format: Mapped[CadSourceFormat] = mapped_column(
        SAEnum(CadSourceFormat, name="cad_source_format", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status: Mapped[CadJobStatus] = mapped_column(
        SAEnum(CadJobStatus, name="cad_job_status", values_callable=lambda x: [e.value for e in x]),
        default=CadJobStatus.QUEUED,
        nullable=False,
    )
    engine: Mapped[str] = mapped_column(String(50), default="autovad_cad", nullable=False)
    units: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    layers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimensions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    texts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tables_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_stats_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    quantities = relationship("CadQuantity", back_populates="cad_model", cascade="all, delete-orphan")


class CadQuantity(Base):
    __tablename__ = "cad_quantities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cad_model_id: Mapped[int] = mapped_column(ForeignKey("cad_models.id", ondelete="CASCADE"), nullable=False, index=True)
    item_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    layer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    calculation_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    cad_model = relationship("CadModel", back_populates="quantities")
