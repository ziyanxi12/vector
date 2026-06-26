from fastapi import HTTPException
from ..client.es_repository import EsDoc, EsRepository
from ..client.texttovec import TextItem, TextToVecClient
from ..handler.base import BaseHandler
from ..model.request import IngestRequest
from ..model.response import IngestResponse

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
            failed.append({"data_id": item.data_id, "error": str(e)})

    succeeded = []

    for i in range(0, len(validated_items), BATCH_SIZE):
        batch = validated_items[i : i + BATCH_SIZE]
        text_items = [TextItem(text=item.text, text_id=item.data_id) for item, _ in batch]

        try:
            vectors = await texttovec.encode(text_items)
        except Exception as e:
            failed.extend({"data_id": item.data_id, "error": str(e)} for item, _ in batch)
            continue

        vector_map = {v.text_id: v.vector for v in vectors}

        docs = []
        for item, metadata in batch:
            vector = vector_map.get(item.data_id)
            if vector is None:
                failed.append({"data_id": item.data_id, "error": "vector not returned"})
                continue
            docs.append(EsDoc(data_id=item.data_id, text=item.text, vector=vector, metadata=metadata))

        result = await es.bulk_upsert(handler.index_name, docs)
        succeeded.extend(result.succeeded)
        failed.extend(result.failed)

    return IngestResponse(succeeded=succeeded, failed=failed)
