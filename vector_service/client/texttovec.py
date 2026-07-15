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
        logger.debug("texttovec request: url=%s items=%d dimension=%d", 
                    self.base_url, len(items), self.dimension)
        t0 = time.monotonic()
        
        max_retries = 3
        retry_statuses = {502, 503, 504}
        
        for attempt in range(max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self.base_url}/embedding/text2vector",
                    json={
                        "dimension": self.dimension,
                        "text_value": [item.model_dump() for item in items],
                    },
                )
                response.raise_for_status()
                data = response.json()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code in retry_statuses and attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning("texttovec retryable error: status=%d attempt=%d/%d waiting=%.1fs",
                                  e.response.status_code, attempt + 1, max_retries, wait_time)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error("texttovec failed: status=%d url=%s reason=%s [%.0fms]",
                                e.response.status_code, e.request.url, 
                                e.response.text[:200] if e.response.text else "N/A",
                                (time.monotonic() - t0) * 1000)
                    raise
            except httpx.ConnectError as e:
                logger.error("texttovec connection failed: url=%s error=%s [%.0fms]", 
                            self.base_url, e, (time.monotonic() - t0) * 1000)
                raise
            except httpx.TimeoutException as e:
                logger.error("texttovec timeout: url=%s error=%s [%.0fms]", 
                            self.base_url, e, (time.monotonic() - t0) * 1000)
                raise
            except Exception as e:
                logger.error("texttovec request failed: %s [%.0fms]", 
                            e, (time.monotonic() - t0) * 1000, exc_info=True)
                raise

        elapsed = (time.monotonic() - t0) * 1000
        if "content" not in data:
            logger.error("texttovec unexpected response shape: keys=%s body=%s", list(data.keys()), str(data)[:500])
            raise KeyError(f"texttovec response missing 'content' key, got: {list(data.keys())}")
        results = [VectorResult(**v) for v in data["content"]]
        logger.debug("texttovec response: status=200 vectors=%d [%.0fms]", len(results), elapsed)
        return results
