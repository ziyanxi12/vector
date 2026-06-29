import time

import httpx
from pydantic import BaseModel

from ..logger import get_logger

logger = get_logger(__name__)


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
        logger.debug("texttovec encode: items=%d dimension=%d", len(items), self.dimension)
        t0 = time.monotonic()
        try:
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
        except httpx.HTTPStatusError as e:
            logger.error("texttovec HTTP error [%.0fms]: status=%d url=%s",
                         (time.monotonic() - t0) * 1000, e.response.status_code, e.request.url)
            raise
        except Exception as e:
            logger.error("texttovec request failed [%.0fms]: %s", (time.monotonic() - t0) * 1000, e, exc_info=True)
            raise

        elapsed = (time.monotonic() - t0) * 1000
        results = [VectorResult(**v) for v in data["vectors"]]
        logger.debug("texttovec encode done: returned=%d [%.0fms]", len(results), elapsed)
        return results
