import time

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_es_repository, get_texttovec_client
from handler.registry import get_handler
from logger import get_logger
from model.request import DeleteRequest, IngestRequest, SearchBatchRequest, SearchRequest, UpdateRequest, CheckIdsRequest
from model.response import IngestResponse, ItemResponse, SearchBatchResponse, SearchResponse, ListIdsResponse, CheckIdsResponse
from service import ingest as ingest_svc
from service import search as search_svc
from service import update as update_svc

router = APIRouter(prefix="/api/v1")
logger = get_logger(__name__)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: IngestRequest,
    texttovec=Depends(get_texttovec_client),
    es=Depends(get_es_repository),
):
    logger.debug("ingest request: type=%s items=%d", request.type, len(request.items))
    t0 = time.monotonic()
    try:
        handler = get_handler(request.type)
        result = await ingest_svc.ingest(request, handler, texttovec, es)
    except Exception as e:
        logger.error("ingest error [%.0fms]: %s", _ms(t0), e, exc_info=True)
        raise
    elapsed = _ms(t0)
    if result.failed:
        logger.warning("ingest partial failure: type=%s succeeded=%d failed=%d [%.0fms]",
                       request.type, len(result.succeeded), len(result.failed), elapsed)
    else:
        logger.info("ingest ok: type=%s succeeded=%d [%.0fms]",
                    request.type, len(result.succeeded), elapsed)
    return result


@router.put("/update")
async def update(
    request: UpdateRequest,
    texttovec=Depends(get_texttovec_client),
    es=Depends(get_es_repository),
):
    logger.debug("update request: type=%s data_id=%s text=%s metadata=%s",
                 request.type, request.data_id,
                 request.text is not None, request.metadata is not None)
    t0 = time.monotonic()
    try:
        handler = get_handler(request.type)
        await update_svc.update(request, handler, texttovec, es)
    except HTTPException:
        logger.warning("update not found: type=%s data_id=%s [%.0fms]",
                       request.type, request.data_id, _ms(t0))
        raise
    except Exception as e:
        logger.error("update error [%.0fms]: %s", _ms(t0), e, exc_info=True)
        raise
    logger.info("update ok: type=%s data_id=%s [%.0fms]",
                request.type, request.data_id, _ms(t0))
    return {"status": "ok"}


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    texttovec=Depends(get_texttovec_client),
    es=Depends(get_es_repository),
):
    logger.debug("search request: type=%s mode=%s query=%r top_k=%d filters=%s",
                 request.type, request.mode, request.query, request.top_k, request.filters)
    t0 = time.monotonic()
    try:
        handler = get_handler(request.type)
        result = await search_svc.search(request, handler, texttovec, es)
    except Exception as e:
        logger.error("search error [%.0fms]: %s", _ms(t0), e, exc_info=True)
        raise
    elapsed = _ms(t0)
    logger.info("search ok: type=%s mode=%s hits=%d [%.0fms]",
                request.type, request.mode, len(result.results), elapsed)
    logger.debug("search scores: %s", [round(r.score, 4) for r in result.results])
    return result


@router.post("/search/batch", response_model=SearchBatchResponse)
async def search_batch(
    request: SearchBatchRequest,
    texttovec=Depends(get_texttovec_client),
    es=Depends(get_es_repository),
):
    logger.debug("search_batch request: type=%s mode=%s queries=%d top_k=%d",
                 request.type, request.mode, len(request.queries), request.top_k)
    t0 = time.monotonic()
    try:
        handler = get_handler(request.type)
        result = await search_svc.search_batch(request, handler, texttovec, es)
    except Exception as e:
        logger.error("search_batch error [%.0fms]: %s", _ms(t0), e, exc_info=True)
        raise
    logger.info("search_batch ok: type=%s mode=%s queries=%d [%.0fms]",
                request.type, request.mode, len(request.queries), _ms(t0))
    return result


@router.get("/item", response_model=ItemResponse)
async def get_item(
    type: str,
    data_id: str,
    es=Depends(get_es_repository),
):
    logger.debug("get_item request: type=%s data_id=%s", type, data_id)
    t0 = time.monotonic()
    handler = get_handler(type)
    doc = await es.get(handler.index_name, data_id)
    if doc is None:
        logger.warning("get_item not found: type=%s data_id=%s [%.0fms]", type, data_id, _ms(t0))
        raise HTTPException(status_code=404, detail=f"{data_id} not found")
    logger.info("get_item ok: type=%s data_id=%s [%.0fms]", type, data_id, _ms(t0))
    return ItemResponse(data_id=doc.data_id, text=doc.text, metadata=doc.metadata)


@router.delete("/item")
async def delete_item(
    request: DeleteRequest,
    es=Depends(get_es_repository),
):
    logger.debug("delete_item request: type=%s data_id=%s", request.type, request.data_id)
    t0 = time.monotonic()
    handler = get_handler(request.type)
    deleted = await es.delete(handler.index_name, request.data_id)
    if not deleted:
        logger.warning("delete_item not found: type=%s data_id=%s [%.0fms]",
                       request.type, request.data_id, _ms(t0))
        raise HTTPException(status_code=404, detail=f"{request.data_id} not found")
    logger.info("delete_item ok: type=%s data_id=%s [%.0fms]",
                request.type, request.data_id, _ms(t0))
    return {"status": "ok"}


def _ms(t0: float) -> float:
    return (time.monotonic() - t0) * 1000


@router.get("/ids", response_model=ListIdsResponse)
async def list_ids(
    type: str,
    limit: int = 1000,
    offset: int = 0,
    es=Depends(get_es_repository),
):
    logger.debug("list_ids request: type=%s limit=%d offset=%d", type, limit, offset)
    t0 = time.monotonic()
    if limit > 5000:
        raise HTTPException(status_code=400, detail="limit cannot exceed 5000")
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be at least 1")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be at least 0")
    try:
        handler = get_handler(type)
        ids, total = await es.list_ids(handler.index_name, limit, offset)
        has_more = (offset + limit) < total
    except Exception as e:
        logger.error("list_ids error [%.0fms]: %s", _ms(t0), e, exc_info=True)
        raise
    logger.info("list_ids ok: type=%s total=%d returned=%d [%.0fms]", 
                type, total, len(ids), _ms(t0))
    return ListIdsResponse(
        type=type, total=total, limit=limit, 
        offset=offset, ids=ids, has_more=has_more
    )


@router.post("/ids/check", response_model=CheckIdsResponse)
async def check_ids(
    request: CheckIdsRequest,
    es=Depends(get_es_repository),
):
    logger.debug("check_ids request: type=%s count=%d", request.type, len(request.ids))
    t0 = time.monotonic()
    try:
        handler = get_handler(request.type)
        exists, missing = await es.check_ids_exists(handler.index_name, request.ids)
    except Exception as e:
        logger.error("check_ids error [%.0fms]: %s", _ms(t0), e, exc_info=True)
        raise
    logger.info("check_ids ok: type=%s exists=%d missing=%d [%.0fms]",
                request.type, len(exists), len(missing), _ms(t0))
    return CheckIdsResponse(
        type=request.type, total_checked=len(request.ids),
        exists=exists, missing=missing,
        exists_count=len(exists), missing_count=len(missing)
    )
