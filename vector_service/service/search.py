import asyncio
from ..client.es_repository import EsRepository, SearchResult
from ..client.texttovec import TextItem, TextToVecClient
from ..handler.base import BaseHandler
from ..model.request import SearchRequest
from ..model.response import SearchHit, SearchResponse


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


async def _vector_search(request, handler, texttovec, es) -> list[SearchResult]:
    vectors = await texttovec.encode([TextItem(text=request.query, text_id="query")])
    return await es.knn_search(handler.index_name, vectors[0].vector, request.top_k, request.filters)


async def _text_search(request, handler, es) -> list[SearchResult]:
    return await es.text_search(handler.index_name, request.query, request.top_k, request.filters)


async def _hybrid_search(request, handler, texttovec, es) -> list[SearchResult]:
    vectors = await texttovec.encode([TextItem(text=request.query, text_id="query")])

    vector_results, text_results = await asyncio.gather(
        es.knn_search(handler.index_name, vectors[0].vector, request.top_k, request.filters),
        es.text_search(handler.index_name, request.query, request.top_k, request.filters),
    )

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
