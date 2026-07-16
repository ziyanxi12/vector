from pydantic import BaseModel


class IngestResponse(BaseModel):
    succeeded: list[str]
    failed: list[dict]


class SearchHit(BaseModel):
    data_id: str
    text: str
    score: float
    metadata: dict


class SearchResponse(BaseModel):
    results: list[SearchHit]


class SearchBatchResponse(BaseModel):
    results: list[list[SearchHit]]


class ItemResponse(BaseModel):
    data_id: str
    text: str
    metadata: dict


class ListIdsResponse(BaseModel):
    type: str
    total: int
    limit: int
    offset: int
    ids: list[str]
    has_more: bool


class CheckIdsResponse(BaseModel):
    type: str
    total_checked: int
    exists: list[str]
    missing: list[str]
    exists_count: int
    missing_count: int


class DeleteBatchResponse(BaseModel):
    deleted: list[str]
    not_found: list[str]
    total_deleted: int
    total_not_found: int
