import httpx
from pydantic import BaseModel


class TextItem(BaseModel):
    text: str
    text_id: str


class VectorResult(BaseModel):
    text_id: str
    vector: list[float]


class TextToVecClient:
    def __init__(self, base_url: str, dimension: int):
        self.base_url = base_url
        self.dimension = dimension

    async def encode(self, items: list[TextItem]) -> list[VectorResult]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/textToVec",
                json={
                    "dimension": self.dimension,
                    "text_value": [item.model_dump() for item in items],
                },
            )
            response.raise_for_status()
            data = response.json()
            return [VectorResult(**v) for v in data["vectors"]]
