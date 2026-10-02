import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.payment import PaymentStatus


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking_id: uuid.UUID


class PaymentWebhookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_reference: str = Field(min_length=1, max_length=64)
    status: PaymentStatus
    provider_transaction_id: str = Field(min_length=1, max_length=64)

    @field_validator("status")
    @classmethod
    def terminal_status(cls, value: PaymentStatus) -> PaymentStatus:
        if value == PaymentStatus.PENDING:
            raise ValueError("status must be SUCCESS or FAILED")
        return value


class PaymentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    payment_reference: str
    amount: Decimal
    status: PaymentStatus
    created_at: datetime
