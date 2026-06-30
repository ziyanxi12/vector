from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_bulk
from .es_repository import BulkResult, EsDoc, EsRepository, SearchResult

INDEX_TEMPLATE = {
    "index_patterns": ["vec_*"],
    "template": {
        "mappings": {
            "properties": {
                "data_id": {"type": "keyword"},
                "text": {"type": "text"},
                "vector": {
                    "type": "dense_vector",
                    "dims": 128,
                    "index": True,
                    "similarity": "cosine",
                },
                "metadata": {"type": "object", "dynamic": True},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
    },
}


class ElasticsearchRepository(EsRepository):
    def __init__(self, url: str, username: str = "", password: str = "", verify_certs: bool = True):
        kwargs = {}
        if username and password:
            kwargs["basic_auth"] = (username, password)
        self._es = AsyncElasticsearch(hosts=[url], verify_certs=verify_certs, **kwargs)

    async def close(self) -> None:
        await self._es.close()

    async def ensure_template(self) -> None:
        await self._es.indices.put_index_template(name="vec_template", body=INDEX_TEMPLATE)

    async def ensure_index(self, index: str) -> None:
        if not await self._es.indices.exists(index=index):
            await self._es.indices.create(index=index)

    async def bulk_upsert(self, index: str, docs: list[EsDoc]) -> BulkResult:
        actions = [
            {
                "_op_type": "index",
                "_index": index,
                "_id": doc.data_id,
                "data_id": doc.data_id,
                "text": doc.text,
                "vector": doc.vector,
                "metadata": doc.metadata,
            }
            for doc in docs
        ]
        succeeded = []
        failed = []
        async for ok, info in async_bulk(self._es, actions, raise_on_error=False):
            if ok:
                succeeded.append(info["index"]["_id"])
            else:
                failed.append({"data_id": info["index"]["_id"], "error": str(info["index"].get("error"))})
        return BulkResult(succeeded=succeeded, failed=failed)

    async def get(self, index: str, data_id: str) -> EsDoc | None:
        try:
            resp = await self._es.get(index=index, id=data_id)
            src = resp["_source"]
            return EsDoc(
                data_id=src["data_id"],
                text=src["text"],
                vector=src["vector"],
                metadata=src["metadata"],
            )
        except NotFoundError:
            return None

    async def update(self, index: str, data_id: str, fields: dict) -> None:
        await self._es.update(index=index, id=data_id, doc=fields)

    async def delete(self, index: str, data_id: str) -> bool:
        try:
            await self._es.delete(index=index, id=data_id)
            return True
        except NotFoundError:
            return False

    async def knn_search(
        self, index: str, query_vector: list[float], top_k: int, filters: dict
    ) -> list[SearchResult]:
        knn = {
            "field": "vector",
            "query_vector": query_vector,
            "k": top_k,
            "num_candidates": top_k * 10,
        }
        if filters:
            knn["filter"] = _build_filters(filters)

        resp = await self._es.search(index=index, knn=knn, size=top_k)
        return _parse_hits(resp)

    async def text_search(
        self, index: str, query: str, top_k: int, filters: dict
    ) -> list[SearchResult]:
        must = {"match": {"text": query}}
        if filters:
            body = {"query": {"bool": {"must": must, "filter": _build_filters(filters)}}}
        else:
            body = {"query": must}

        resp = await self._es.search(index=index, body=body, size=top_k)
        return _parse_hits(resp)


def _build_filters(filters: dict) -> list[dict]:
    return [{"term": {k: v}} for k, v in filters.items()]


def _parse_hits(resp: dict) -> list[SearchResult]:
    return [
        SearchResult(
            data_id=hit["_source"]["data_id"],
            text=hit["_source"]["text"],
            score=hit["_score"],
            metadata=hit["_source"]["metadata"],
        )
        for hit in resp["hits"]["hits"]
    ]
