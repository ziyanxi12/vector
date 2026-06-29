import time

from fastapi import HTTPException
from ..client.es_repository import EsDoc, EsRepository
from ..client.texttovec import TextItem, TextToVecClient
from ..handler.base import BaseHandler
from ..logger import get_logger
from ..model.request import IngestRequest
from ..model.response import IngestResponse

logger = get_logger(__name__)

BATCH_SIZE = 50


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

    succeeded = []
    total_batches = (len(validated_items) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(validated_items), BATCH_SIZE):
        batch = validated_items[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        text_items = [TextItem(text=item.text, text_id=item.data_id) for item, _ in batch]

        logger.debug("ingest batch %d/%d: encoding %d items", batch_num, total_batches, len(batch))
        t0 = time.monotonic()
        try:
            vectors = await texttovec.encode(text_items)
        except Exception as e:
            logger.error("vectorize failed for batch %d/%d: %s", batch_num, total_batches, e, exc_info=True)
            failed.extend({"data_id": item.data_id, "error": str(e)} for item, _ in batch)
            continue
        logger.debug("vectorize batch %d/%d done [%.0fms]", batch_num, total_batches, (time.monotonic() - t0) * 1000)

        vector_map = {v.text_id: v.vector for v in vectors}

        docs = []
        for item, metadata in batch:
            vector = vector_map.get(item.data_id)
            if vector is None:
                logger.warning("vector not returned for data_id=%s", item.data_id)
                failed.append({"data_id": item.data_id, "error": "vector not returned"})
                continue
            docs.append(EsDoc(data_id=item.data_id, text=item.text, vector=vector, metadata=metadata))

        t1 = time.monotonic()
        result = await es.bulk_upsert(handler.index_name, docs)
        logger.debug("es bulk_upsert batch %d/%d: succeeded=%d failed=%d [%.0fms]",
                     batch_num, total_batches, len(result.succeeded), len(result.failed),
                     (time.monotonic() - t1) * 1000)

        if result.failed:
            for f in result.failed:
                logger.warning("es upsert failed: data_id=%s error=%s", f.get("data_id"), f.get("error"))

        succeeded.extend(result.succeeded)
        failed.extend(result.failed)

    return IngestResponse(succeeded=succeeded, failed=failed)
