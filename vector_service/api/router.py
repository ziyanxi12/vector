from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import get_es_repository, get_texttovec_client
from ..handler.registry import get_handler
from ..model.request import DeleteRequest, IngestRequest, SearchRequest, UpdateRequest
from ..model.response import IngestResponse, ItemResponse, SearchResponse
from ..service import ingest as ingest_svc
from ..service import search as search_svc
from ..service import update as update_svc

router = APIRouter(prefix="/api/v1")


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: IngestRequest,
    texttovec=Depends(get_texttovec_client),
    es=Depends(get_es_repository),
):
    handler = get_handler(request.type)
    return await ingest_svc.ingest(request, handler, texttovec, es)


@router.put("/update")
async def update(
    request: UpdateRequest,
    texttovec=Depends(get_texttovec_client),
    es=Depends(get_es_repository),
):
    handler = get_handler(request.type)
    await update_svc.update(request, handler, texttovec, es)
    return {"status": "ok"}


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    texttovec=Depends(get_texttovec_client),
    es=Depends(get_es_repository),
):
    handler = get_handler(request.type)
    return await search_svc.search(request, handler, texttovec, es)


@router.get("/item", response_model=ItemResponse)
async def get_item(
    type: str,
    data_id: str,
    es=Depends(get_es_repository),
):
    handler = get_handler(type)
    doc = await es.get(handler.index_name, data_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"{data_id} not found")
    return ItemResponse(data_id=doc.data_id, text=doc.text, metadata=doc.metadata)


@router.delete("/item")
async def delete_item(
    request: DeleteRequest,
    es=Depends(get_es_repository),
):
    handler = get_handler(request.type)
    deleted = await es.delete(handler.index_name, request.data_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"{request.data_id} not found")
    return {"status": "ok"}
