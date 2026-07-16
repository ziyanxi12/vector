from __future__ import annotations

import time

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_streaming_bulk

from logger import get_logger
from .es_repository import BulkResult, EsDoc, EsRepository, SearchResult

logger = get_logger(__name__)

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
        self._url = url

    async def close(self) -> None:
        await self._es.close()

    async def ensure_template(self) -> None:
        try:
            await self._es.indices.put_index_template(name="vec_template", body=INDEX_TEMPLATE)
            logger.info("es template created: name=vec_template")
        except Exception as e:
            logger.error("es connection failed: url=%s error=%s", self._url, e, exc_info=True)
            raise

    async def ensure_index(self, index: str) -> None:
        try:
            if not await self._es.indices.exists(index=index):
                await self._es.indices.create(index=index)
                logger.info("es index created: index=%s", index)
        except Exception as e:
            logger.error("es index operation failed: index=%s error=%s", index, e, exc_info=True)
            raise

    async def bulk_upsert(self, index: str, docs: list[EsDoc]) -> BulkResult:
        logger.debug("es bulk_upsert: index=%s docs=%d", index, len(docs))
        t0 = time.monotonic()
        
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
        async for ok, info in async_streaming_bulk(self._es, actions, raise_on_error=False):
            if ok:
                succeeded.append(info["index"]["_id"])
            else:
                failed.append({"data_id": info["index"]["_id"], "error": str(info["index"].get("error"))})
        
        elapsed = (time.monotonic() - t0) * 1000
        if failed:
            logger.warning("es bulk_upsert partial failure: index=%s succeeded=%d failed=%d [%.0fms]",
                          index, len(succeeded), len(failed), elapsed)
        else:
            logger.debug("es bulk_upsert done: succeeded=%d [%.0fms]", len(succeeded), elapsed)
        
        return BulkResult(succeeded=succeeded, failed=failed)

    async def get(self, index: str, data_id: str) -> EsDoc | None:
        logger.debug("es get: index=%s data_id=%s", index, data_id)
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
            logger.debug("es get not found: index=%s data_id=%s", index, data_id)
            return None

    async def update(self, index: str, data_id: str, fields: dict) -> None:
        logger.debug("es update: index=%s data_id=%s fields=%s", index, data_id, list(fields.keys()))
        await self._es.update(index=index, id=data_id, doc=fields)

    async def delete(self, index: str, data_id: str) -> bool:
        logger.debug("es delete: index=%s data_id=%s", index, data_id)
        try:
            await self._es.delete(index=index, id=data_id)
            return True
        except NotFoundError:
            logger.debug("es delete not found: index=%s data_id=%s", index, data_id)
            return False

    async def bulk_delete(self, index: str, data_ids: list[str]) -> tuple[list[str], list[str]]:
        logger.debug("es bulk_delete: index=%s ids=%d", index, len(data_ids))
        t0 = time.monotonic()
        
        deleted = []
        not_found = []
        
        actions = [
            {"_op_type": "delete", "_index": index, "_id": data_id}
            for data_id in data_ids
        ]
        
        async for ok, info in async_streaming_bulk(self._es, actions, raise_on_error=False):
            if ok:
                deleted.append(info["delete"]["_id"])
            else:
                error_info = info.get("delete", {})
                data_id = error_info.get("_id", "")
                status = error_info.get("status", 0)
                if status == 404 or "not found" in str(error_info.get("error", "")).lower():
                    not_found.append(data_id)
                else:
                    logger.warning("es bulk_delete unexpected error: data_id=%s error=%s", 
                                  data_id, error_info.get("error"))
        
        elapsed = (time.monotonic() - t0) * 1000
        logger.info("es bulk_delete done: index=%s deleted=%d not_found=%d [%.0fms]",
                    index, len(deleted), len(not_found), elapsed)
        return deleted, not_found

    async def knn_search(
        self, index: str, query_vector: list[float], top_k: int, filters: dict
    ) -> list[SearchResult]:
        logger.debug("es knn_search: index=%s top_k=%d filters=%s", index, top_k, filters or "none")
        t0 = time.monotonic()
        
        knn = {
            "field": "vector",
            "query_vector": query_vector,
            "k": top_k,
            "num_candidates": top_k * 10,
        }
        if filters:
            knn["filter"] = _build_filters(filters)

        resp = await self._es.search(index=index, knn=knn, size=top_k)
        results = _parse_hits(resp)
        logger.debug("es knn_search done: hits=%d [%.0fms]", len(results), (time.monotonic() - t0) * 1000)
        return results

    async def text_search(
        self, index: str, query: str, top_k: int, filters: dict
    ) -> list[SearchResult]:
        logger.debug("es text_search: index=%s query=%r top_k=%d filters=%s", 
                    index, query[:50], top_k, filters or "none")
        t0 = time.monotonic()
        
        must = {"match": {"text": query}}
        if filters:
            body = {"query": {"bool": {"must": must, "filter": _build_filters(filters)}}}
        else:
            body = {"query": must}

        resp = await self._es.search(index=index, body=body, size=top_k)
        results = _parse_hits(resp)
        logger.debug("es text_search done: hits=%d [%.0fms]", len(results), (time.monotonic() - t0) * 1000)
        return results

    async def count(self, index: str) -> int:
        logger.debug("es count: index=%s", index)
        try:
            resp = await self._es.count(index=index)
            logger.debug("es count done: count=%d", resp["count"])
            return resp["count"]
        except NotFoundError:
            logger.debug("es count: index=%s not found", index)
            return 0

    async def list_ids(self, index: str, limit: int, offset: int) -> tuple[list[str], int]:
        logger.debug("es list_ids: index=%s limit=%d offset=%d", index, limit, offset)
        total = await self.count(index)
        if total == 0:
            return [], 0
        resp = await self._es.search(
            index=index,
            query={"match_all": {}},
            _source=["data_id"],
            size=limit,
            from_=offset
        )
        ids = [hit["_source"]["data_id"] for hit in resp["hits"]["hits"]]
        logger.debug("es list_ids done: total=%d returned=%d", total, len(ids))
        return ids, total

    async def check_ids_exists(self, index: str, ids: list[str]) -> tuple[list[str], list[str]]:
        logger.debug("es check_ids_exists: index=%s ids_count=%d", index, len(ids))
        try:
            resp = await self._es.mget(index=index, body={"ids": ids})
            exists = [doc["_id"] for doc in resp["docs"] if doc["found"]]
            missing = list(set(ids) - set(exists))
            logger.debug("es check_ids_exists done: exists=%d missing=%d", len(exists), len(missing))
            return exists, missing
        except NotFoundError:
            logger.debug("es check_ids_exists: index=%s not found", index)
            return [], ids


def _build_filters(filters: dict) -> list[dict]:
    result = []
    for k, v in filters.items():
        # 多值：使用 terms 查询（OR 逻辑）
        if isinstance(v, list):
            if not v:  # 空数组跳过
                continue
            if isinstance(v[0], str):
                result.append({"terms": {f"metadata.{k}.keyword": v}})
            else:
                result.append({"terms": {f"metadata.{k}": v}})
        # 单值字符串：使用 term + .keyword
        elif isinstance(v, str):
            result.append({"term": {f"metadata.{k}.keyword": v}})
        # 单值其他类型：使用 term
        else:
            result.append({"term": {f"metadata.{k}": v}})
    return result


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
