from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.boq import BOQItemStatus, BOQStatus


class BOQItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    boq_id: int
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
    status: BOQItemStatus
    created_at: datetime
    updated_at: datetime


class BOQOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    version: int
    status: BOQStatus
    currency: str
    notes: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime
    items: list[BOQItemOut] = []
