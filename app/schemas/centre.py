import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CentreWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    location: str = Field(min_length=1, max_length=255)

    @field_validator("name", "location")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("This field is required")
        return stripped


class CentrePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    location: str
    created_at: datetime
    updated_at: datetime
