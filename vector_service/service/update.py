import time

from fastapi import HTTPException
from client.es_repository import EsRepository
from client.texttovec import TextItem, TextToVecClient
from handler.base import BaseHandler
from logger import get_logger
from model.request import UpdateRequest

logger = get_logger(__name__)


async def update(
    request: UpdateRequest,
    handler: BaseHandler,
    texttovec: TextToVecClient,
    es: EsRepository,
) -> None:
    t0 = time.monotonic()
    existing = await es.get(handler.index_name, request.data_id)
    if existing is None:
        logger.warning("update target not found: index=%s data_id=%s", handler.index_name, request.data_id)
        raise HTTPException(status_code=404, detail=f"{request.data_id} not found")

    fields: dict = {}

    if request.text is not None:
        vectors = await texttovec.encode([TextItem(text=request.text, text_id=request.data_id)])
        fields["text"] = request.text
        fields["vector"] = vectors[0].vector

    if request.metadata is not None:
        fields["metadata"] = handler.validate_metadata(request.metadata)

    logger.debug("update fields: %s", list(fields.keys()))
    await es.update(handler.index_name, request.data_id, fields)
