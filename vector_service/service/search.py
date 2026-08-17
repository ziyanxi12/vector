import asyncio
import time

from client.es_repository import EsRepository, SearchResult
from client.texttovec import TextItem, TextToVecClient
from handler.base import BaseHandler
from logger import get_logger
from model.request import SearchBatchRequest, SearchRequest
from model.response import SearchBatchResponse, SearchHit, SearchResponse

logger = get_logger(__name__)

_ES_SEARCH_CONCURRENCY = 10


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
    t0 = time.monotonic()
    queries = request.queries
    n = len(queries)

    # Phase 1: batch encode all queries at once (vector/hybrid modes)
    encode_ms = 0.0
    if request.mode in ("vector", "hybrid"):
        text_items = [TextItem(text=q, text_id=f"query_{i}") for i, q in enumerate(queries)]
        t_enc = time.monotonic()
        vec_results = await texttovec.encode(text_items)
        encode_ms = (time.monotonic() - t_enc) * 1000
        vec_map = {v.text_id: v.vector for v in vec_results}
        query_vectors = [vec_map[f"query_{i}"] for i in range(n)]
    else:
        query_vectors = None

    # Phase 2: concurrent ES searches (with concurrency limit)
    sem = asyncio.Semaphore(_ES_SEARCH_CONCURRENCY)

    async def _search_one(i: int) -> list[SearchResult]:
        async with sem:
            if request.mode == "vector":
                return await es.knn_search(handler.index_name, query_vectors[i], request.top_k, request.filters)
            elif request.mode == "text":
                return await es.text_search(handler.index_name, queries[i], request.top_k, request.filters)
            else:  # hybrid
                knn_res, text_res = await asyncio.gather(
                    es.knn_search(handler.index_name, query_vectors[i], request.top_k, request.filters),
                    es.text_search(handler.index_name, queries[i], request.top_k, request.filters),
                )
                return _merge_hybrid(knn_res, text_res, request.top_k, request.hybrid_weight)

    t_es = time.monotonic()
    all_raw = await asyncio.gather(*[_search_one(i) for i in range(n)])
    es_ms = (time.monotonic() - t_es) * 1000

    total_ms = (time.monotonic() - t0) * 1000
    logger.info("search_batch phases: mode=%s queries=%d encode=%.0fms es=%.0fms total=%.0fms",
                request.mode, n, encode_ms, es_ms, total_ms)

    return SearchBatchResponse(
        results=[
            [SearchHit(data_id=r.data_id, text=r.text, score=r.score, metadata=r.metadata) for r in raw]
            for raw in all_raw
        ]
    )


async def _vector_search(request, handler, texttovec, es) -> list[SearchResult]:
    vectors = await texttovec.encode([TextItem(text=request.query, text_id="query")])
    results = await es.knn_search(handler.index_name, vectors[0].vector, request.top_k, request.filters)
    return results


async def _text_search(request, handler, es) -> list[SearchResult]:
    results = await es.text_search(handler.index_name, request.query, request.top_k, request.filters)
    return results


def _merge_hybrid(
    vector_results: list[SearchResult],
    text_results: list[SearchResult],
    top_k: int,
    hybrid_weight: float,
) -> list[SearchResult]:
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
        data_id: hybrid_weight * vector_score_map.get(data_id, 0.0)
        + (1 - hybrid_weight) * text_score_map.get(data_id, 0.0)
        for data_id in all_ids
    }

    doc_map = {r.data_id: r for r in [*text_results, *vector_results]}
    sorted_ids = sorted(merged_scores, key=lambda x: merged_scores[x], reverse=True)[:top_k]

    return [
        SearchResult(
            data_id=data_id,
            text=doc_map[data_id].text,
            score=merged_scores[data_id],
            metadata=doc_map[data_id].metadata,
        )
        for data_id in sorted_ids
    ]


async def _hybrid_search(request, handler, texttovec, es) -> list[SearchResult]:
    vectors = await texttovec.encode([TextItem(text=request.query, text_id="query")])
    vector_results, text_results = await asyncio.gather(
        es.knn_search(handler.index_name, vectors[0].vector, request.top_k, request.filters),
        es.text_search(handler.index_name, request.query, request.top_k, request.filters),
    )
    return _merge_hybrid(vector_results, text_results, request.top_k, request.hybrid_weight)
