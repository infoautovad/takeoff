from datetime import datetime, timezone
from enum import Enum
from decimal import Decimal

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BOQStatus(str, Enum):
    DRAFT = "draft"
    AI_GENERATED = "ai_generated"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class BOQItemStatus(str, Enum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    VERIFIED = "verified"
    APPROVED = "approved"
    REJECTED = "rejected"


class BOQ(Base):
    __tablename__ = "boqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[BOQStatus] = mapped_column(
        SAEnum(BOQStatus, name="boq_status", values_callable=lambda x: [e.value for e in x]),
        default=BOQStatus.DRAFT,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
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

    project = relationship("Project", back_populates="boqs")
    items = relationship("BOQItem", back_populates="boq", cascade="all, delete-orphan")


class BOQItem(Base):
    __tablename__ = "boq_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    boq_id: Mapped[int] = mapped_column(ForeignKey("boqs.id", ondelete="CASCADE"), nullable=False, index=True)
    item_number: Mapped[str] = mapped_column(String(50), nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    csi_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calculation_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    bid_template_line_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bid_match_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[BOQItemStatus] = mapped_column(
        SAEnum(BOQItemStatus, name="boq_item_status", values_callable=lambda x: [e.value for e in x]),
        default=BOQItemStatus.DRAFT,
        nullable=False,
    )
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

    boq = relationship("BOQ", back_populates="items")
