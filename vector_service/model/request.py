from typing import Literal, Optional, Union
from pydantic import BaseModel, field_validator, model_validator


class IngestItem(BaseModel):
    data_id: str
    text: str
    metadata: dict

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text cannot be empty")
        return v


class IngestRequest(BaseModel):
    type: str
    items: list[IngestItem]

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("items cannot be empty")
        return v


class UpdateRequest(BaseModel):
    type: str
    data_id: str
    text: Optional[str] = None
    metadata: Optional[dict] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateRequest":
        if self.text is None and self.metadata is None:
            raise ValueError("at least one of text or metadata must be provided")
        return self

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("text cannot be empty")
        return v


class SearchRequest(BaseModel):
    type: str
    query: str
    mode: Literal["vector", "text", "hybrid"] = "vector"
    top_k: int = 10
    filters: dict = {}
    hybrid_weight: float = 0.7


class SearchBatchRequest(BaseModel):
    type: str
    queries: list[str]
    mode: Literal["vector", "text", "hybrid"] = "vector"
    top_k: int = 10
    filters: dict = {}
    hybrid_weight: float = 0.7

    @field_validator("queries")
    @classmethod
    def queries_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("queries cannot be empty")
        return v


class DeleteRequest(BaseModel):
    type: str
    data_id: str


class CheckIdsRequest(BaseModel):
    type: str
    ids: list[str]

    @field_validator("ids")
    @classmethod
    def ids_validate(cls, v: list) -> list:
        if not v:
            raise ValueError("ids cannot be empty")
        if len(v) > 1000:
            raise ValueError("ids cannot exceed 1000")
        return v
