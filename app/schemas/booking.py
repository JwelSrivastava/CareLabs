import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    """Amount is accepted and ignored. The stored price comes from the centre offering."""

    model_config = ConfigDict(extra="forbid")

    centre_id: uuid.UUID
    test_id: uuid.UUID
    appointment_at: datetime
    amount: Decimal | None = Field(default=None)


class BookingPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    centre_id: uuid.UUID
    test_id: uuid.UUID
    appointment_at: datetime
    amount: Decimal
    status: BookingStatus
    created_at: datetime
    updated_at: datetime
