import asyncio
import time

import httpx
from pydantic import BaseModel

from logger import get_logger

logger = get_logger(__name__)


class TextItem(BaseModel):
    text: str
    text_id: str


class VectorResult(BaseModel):
    text_id: str
    vector: list[float]


class TextToVecClient:
    def __init__(self, base_url: str, dimension: int, timeout: float = 60.0):
        self.base_url = base_url
        self.dimension = dimension
        self._client = httpx.AsyncClient(timeout=timeout, trust_env=False)

    async def close(self) -> None:
        await self._client.aclose()

    async def encode(self, items: list[TextItem]) -> list[VectorResult]:
        logger.debug("texttovec encode: items=%d dimension=%d", len(items), self.dimension)
        t0 = time.monotonic()
        
        max_retries = 3
        retry_statuses = {502, 503, 504}
        
        for attempt in range(max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self.base_url}/textToVec",
                    json={
                        "dimension": self.dimension,
                        "text_value": [item.model_dump() for item in items],
                    },
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in retry_statuses and attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning("texttovec retryable error: status=%d attempt=%d/%d waiting=%.1fs",
                                  e.response.status_code, attempt + 1, max_retries, wait_time)
                    await asyncio.sleep(wait_time)
                    continue
                else:
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
