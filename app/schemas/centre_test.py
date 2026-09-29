import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CentreTestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_id: uuid.UUID
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class CentreTestPublic(BaseModel):
    id: uuid.UUID
    centre_id: uuid.UUID
    test_id: uuid.UUID
    test_name: str
    price: Decimal
    created_at: datetime
