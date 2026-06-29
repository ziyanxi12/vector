import asyncio
import time

from ..client.es_repository import EsRepository, SearchResult
from ..client.texttovec import TextItem, TextToVecClient
from ..handler.base import BaseHandler
from ..logger import get_logger
from ..model.request import SearchBatchRequest, SearchRequest
from ..model.response import SearchBatchResponse, SearchHit, SearchResponse

logger = get_logger(__name__)


async def search(
    request: SearchRequest,
    handler: BaseHandler,
    texttovec: TextToVecClient,
    es: EsRepository,
) -> SearchResponse:
    if request.mode == "vector":
        results = await _vector_search(request, handler, texttovec, es)
    elif request.mode == "text":
        results = await _text_search(request, handler, es)
    else:
        results = await _hybrid_search(request, handler, texttovec, es)

    return SearchResponse(
        results=[
            SearchHit(data_id=r.data_id, text=r.text, score=r.score, metadata=r.metadata)
            for r in results
        ]
    )


async def search_batch(
    request: SearchBatchRequest,
    handler: BaseHandler,
    texttovec: TextToVecClient,
    es: EsRepository,
) -> SearchBatchResponse:
    single = SearchRequest(
        type=request.type,
        mode=request.mode,
        top_k=request.top_k,
        filters=request.filters,
        hybrid_weight=request.hybrid_weight,
        query="",
    )
    tasks = []
    for q in request.queries:
        single.query = q
        tasks.append(search(SearchRequest(**single.model_dump()), handler, texttovec, es))

    responses = await asyncio.gather(*tasks)
    return SearchBatchResponse(results=[r.results for r in responses])


async def _vector_search(request, handler, texttovec, es) -> list[SearchResult]:
    t0 = time.monotonic()
    vectors = await texttovec.encode([TextItem(text=request.query, text_id="query")])
    logger.debug("vectorize done [%.0fms]", (time.monotonic() - t0) * 1000)

    t1 = time.monotonic()
    results = await es.knn_search(handler.index_name, vectors[0].vector, request.top_k, request.filters)
    logger.debug("knn_search done: hits=%d [%.0fms]", len(results), (time.monotonic() - t1) * 1000)
    return results


async def _text_search(request, handler, es) -> list[SearchResult]:
    t0 = time.monotonic()
    results = await es.text_search(handler.index_name, request.query, request.top_k, request.filters)
    logger.debug("text_search done: hits=%d [%.0fms]", len(results), (time.monotonic() - t0) * 1000)
    return results


async def _hybrid_search(request, handler, texttovec, es) -> list[SearchResult]:
    t0 = time.monotonic()
    vectors = await texttovec.encode([TextItem(text=request.query, text_id="query")])
    logger.debug("vectorize done [%.0fms]", (time.monotonic() - t0) * 1000)

    t1 = time.monotonic()
    vector_results, text_results = await asyncio.gather(
        es.knn_search(handler.index_name, vectors[0].vector, request.top_k, request.filters),
        es.text_search(handler.index_name, request.query, request.top_k, request.filters),
    )
    logger.debug("hybrid es query done: knn=%d text=%d [%.0fms]",
                 len(vector_results), len(text_results), (time.monotonic() - t1) * 1000)

    vector_score_map = {r.data_id: r.score for r in vector_results}

    if text_results:
        scores = [r.score for r in text_results]
        min_s, max_s = min(scores), max(scores)
        score_range = max_s - min_s or 1.0
        text_score_map = {r.data_id: (r.score - min_s) / score_range for r in text_results}
    else:
        text_score_map = {}

    all_ids = set(vector_score_map) | set(text_score_map)
    merged_scores = {
        data_id: request.hybrid_weight * vector_score_map.get(data_id, 0.0)
        + (1 - request.hybrid_weight) * text_score_map.get(data_id, 0.0)
        for data_id in all_ids
    }

    doc_map = {r.data_id: r for r in [*text_results, *vector_results]}
    sorted_ids = sorted(merged_scores, key=lambda x: merged_scores[x], reverse=True)[: request.top_k]

    return [
        SearchResult(
            data_id=data_id,
            text=doc_map[data_id].text,
            score=merged_scores[data_id],
            metadata=doc_map[data_id].metadata,
        )
        for data_id in sorted_ids
    ]
