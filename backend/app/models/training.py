"""Agent / model training lab — gold cases, AutoVAD runs, and diff reports."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TrainingCaseStatus(str, Enum):
    DRAFT = "draft"  # sample not analyzed yet
    ANALYZED = "analyzed"  # stage 1 done — AutoVAD EOQ ready
    READY = "ready"  # stage 1 + original EOQ uploaded
    ARCHIVED = "archived"


class TrainingRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrainingCase(Base):
    """A gold-set style case: sample plan file + expected (original) bid/takeoff items."""

    __tablename__ = "training_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TrainingCaseStatus] = mapped_column(
        SAEnum(TrainingCaseStatus, name="training_case_status", values_callable=lambda x: [e.value for e in x]),
        default=TrainingCaseStatus.DRAFT,
        nullable=False,
    )
    sample_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sample_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sample_content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sample_file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Original Estimate Of Quantities source file (PDF / Excel / CSV / image)
    expected_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expected_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Parsed expected / original items JSON: { "items": [ { description, unit, quantity, ... } ] }
    expected_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stage 1: AutoVAD Estimate Of Quantities from the sample plan
    actual_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optional bid catalog for matcher training: list of { item_code, description, unit }
    bid_catalog_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    runs: Mapped[list[TrainingRun]] = relationship(
        "TrainingRun", back_populates="case", cascade="all, delete-orphan", order_by="TrainingRun.id.desc()"
    )


class TrainingRun(Base):
    """One AutoVAD inference pass on a training case."""

    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("training_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[TrainingRunStatus] = mapped_column(
        SAEnum(TrainingRunStatus, name="training_run_status", values_callable=lambda x: [e.value for e in x]),
        default=TrainingRunStatus.QUEUED,
        nullable=False,
    )
    engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Actual AutoVAD items JSON list
    actual_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    case: Mapped[TrainingCase] = relationship("TrainingCase", back_populates="runs")
    report: Mapped[TrainingReport | None] = relationship(
        "TrainingReport", back_populates="run", uselist=False, cascade="all, delete-orphan"
    )


class TrainingReport(Base):
    """Diff + training guidance comparing AutoVAD output vs original expected items."""

    __tablename__ = "training_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("training_runs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # Full compare_eoq.to_dict() plus extras
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    diffs_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Human/AI narrative for fine-tuning: mistakes, patterns, suggested fixes
    training_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    recall: Mapped[str | None] = mapped_column(String(32), nullable=True)
    precision_proxy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    run: Mapped[TrainingRun] = relationship("TrainingRun", back_populates="report")
