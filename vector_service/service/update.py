from fastapi import HTTPException
from ..client.es_repository import EsRepository
from ..client.texttovec import TextItem, TextToVecClient
from ..handler.base import BaseHandler
from ..model.request import UpdateRequest


async def update(
    request: UpdateRequest,
    handler: BaseHandler,
    texttovec: TextToVecClient,
    es: EsRepository,
) -> None:
    existing = await es.get(handler.index_name, request.data_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"{request.data_id} not found")

    fields: dict = {}

    if request.text is not None:
        vectors = await texttovec.encode([TextItem(text=request.text, text_id=request.data_id)])
        fields["text"] = request.text
        fields["vector"] = vectors[0].vector

    if request.metadata is not None:
        fields["metadata"] = handler.validate_metadata(request.metadata)

    await es.update(handler.index_name, request.data_id, fields)
