from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int = Field(ge=1)
    limit: int = Field(ge=1)
    total: int = Field(ge=0)
