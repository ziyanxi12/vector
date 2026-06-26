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


class ItemResponse(BaseModel):
    data_id: str
    text: str
    metadata: dict
