from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.eoq import EOQItemStatus, EOQStatus


class EOQItemUpdate(BaseModel):
    """Engineer review edits for a single EOQ line."""

    status: EOQItemStatus | None = None
    quantity: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    item_code: str | None = None
    notes: str | None = None


class EOQItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    eoq_id: int
    item_number: str
    item_code: str | None
    csi_code: str | None = None
    description: str
    category: str | None
    unit: str
    quantity: Decimal
    rate: Decimal | None
    amount: Decimal | None
    source_document_id: int | None
    source_page: int | None
    source_reference: str | None
    calculation_method: str | None
    confidence: Decimal | None
    bid_template_line_id: int | None = None
    bid_match_confidence: float | None = None
    status: EOQItemStatus
    created_at: datetime
    updated_at: datetime


class EOQOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    version: int
    status: EOQStatus
    currency: str
    notes: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime
    items: list[EOQItemOut] = []
