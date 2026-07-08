import asyncio
import time

from fastapi import HTTPException
from client.es_repository import EsDoc, EsRepository
from client.texttovec import TextItem, TextToVecClient
from handler.base import BaseHandler
from logger import get_logger
from model.request import IngestRequest
from model.response import IngestResponse

logger = get_logger(__name__)

BATCH_SIZE = 20


async def ingest(
    request: IngestRequest,
    handler: BaseHandler,
    texttovec: TextToVecClient,
    es: EsRepository,
) -> IngestResponse:
    validated_items = []
    failed = []

    for item in request.items:
        try:
            validated_metadata = handler.validate_metadata(item.metadata)
            validated_items.append((item, validated_metadata))
        except Exception as e:
            logger.warning("metadata validation failed: data_id=%s error=%s", item.data_id, e)
            failed.append({"data_id": item.data_id, "error": str(e)})

    logger.debug("ingest validation done: valid=%d invalid=%d", len(validated_items), len(failed))

    if not validated_items:
        return IngestResponse(succeeded=[], failed=failed)

    batches = [validated_items[i:i + BATCH_SIZE] for i in range(0, len(validated_items), BATCH_SIZE)]
    total_batches = len(batches)
    succeeded = []

    async def _vectorize(batch: list, batch_num: int) -> list:
        text_items = [TextItem(text=item.text, text_id=item.data_id) for item, _ in batch]
        logger.debug("ingest batch %d/%d: encoding %d items", batch_num, total_batches, len(batch))
        vectors = await texttovec.encode(text_items)
        return vectors

    # 提前启动第一个 batch 的向量化
    next_vec_task: asyncio.Task = asyncio.create_task(_vectorize(batches[0], 1))

    for idx, batch in enumerate(batches):
        batch_num = idx + 1

        try:
            vectors = await next_vec_task
        except Exception as e:
            logger.error("vectorize failed for batch %d/%d: %s", batch_num, total_batches, e, exc_info=True)
            failed.extend({"data_id": item.data_id, "error": str(e)} for item, _ in batch)
            if idx + 1 < total_batches:
                next_vec_task = asyncio.create_task(_vectorize(batches[idx + 1], batch_num + 1))
            continue

        # 立刻启动下一 batch 向量化，与 ES 写入并发
        if idx + 1 < total_batches:
            next_vec_task = asyncio.create_task(_vectorize(batches[idx + 1], batch_num + 1))

        vector_map = {v.text_id: v.vector for v in vectors}
        docs = []
        for item, metadata in batch:
            vector = vector_map.get(item.data_id)
            if vector is None:
                logger.warning("vector not returned for data_id=%s", item.data_id)
                failed.append({"data_id": item.data_id, "error": "vector not returned"})
                continue
            docs.append(EsDoc(data_id=item.data_id, text=item.text, vector=vector, metadata=metadata))

        result = await es.bulk_upsert(handler.index_name, docs)

        if result.failed:
            for f in result.failed:
                logger.warning("es upsert failed: data_id=%s error=%s", f.get("data_id"), f.get("error"))

        succeeded.extend(result.succeeded)
        failed.extend(result.failed)

    return IngestResponse(succeeded=succeeded, failed=failed)
