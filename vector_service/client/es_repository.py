import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EsDoc:
    data_id: str
    text: str
    vector: list[float]
    metadata: dict


@dataclass
class SearchResult:
    data_id: str
    text: str
    score: float
    metadata: dict


@dataclass
class BulkResult:
    succeeded: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)


class EsRepository(ABC):
    async def close(self) -> None:
        pass

    async def ensure_index(self, index: str) -> None:
        pass

    @abstractmethod
    async def bulk_upsert(self, index: str, docs: list[EsDoc]) -> BulkResult: ...

    @abstractmethod
    async def get(self, index: str, data_id: str) -> Optional[EsDoc]: ...

    @abstractmethod
    async def update(self, index: str, data_id: str, fields: dict) -> None: ...

    @abstractmethod
    async def delete(self, index: str, data_id: str) -> bool: ...

    @abstractmethod
    async def knn_search(
        self, index: str, query_vector: list[float], top_k: int, filters: dict
    ) -> list[SearchResult]: ...

    @abstractmethod
    async def text_search(
        self, index: str, query: str, top_k: int, filters: dict
    ) -> list[SearchResult]: ...

    @abstractmethod
    async def count(self, index: str) -> int:
        """获取索引文档总数"""
        ...

    @abstractmethod
    async def list_ids(self, index: str, limit: int, offset: int) -> tuple[list[str], int]:
        """分页获取 data_id 列表，返回 (ids, total)"""
        ...

    @abstractmethod
    async def check_ids_exists(self, index: str, ids: list[str]) -> tuple[list[str], list[str]]:
        """批量检查 ID 是否存在，返回 (exists, missing)"""
        ...


class MockEsRepository(EsRepository):
    def __init__(self):
        # index -> data_id -> raw doc dict
        self._store: dict[str, dict[str, dict]] = {}

    def _get_index(self, index: str) -> dict[str, dict]:
        if index not in self._store:
            self._store[index] = {}
        return self._store[index]

    def _matches_filters(self, doc: dict, filters: dict) -> bool:
        for key, value in filters.items():
            parts = f"metadata.{key}".split(".")
            obj = doc
            for part in parts:
                obj = obj.get(part) if isinstance(obj, dict) else None
            if obj != value:
                return False
        return True

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def bulk_upsert(self, index: str, docs: list[EsDoc]) -> BulkResult:
        store = self._get_index(index)
        result = BulkResult()
        for doc in docs:
            try:
                store[doc.data_id] = {
                    "data_id": doc.data_id,
                    "text": doc.text,
                    "vector": doc.vector,
                    "metadata": doc.metadata,
                }
                result.succeeded.append(doc.data_id)
            except Exception as e:
                result.failed.append({"data_id": doc.data_id, "error": str(e)})
        return result

    async def get(self, index: str, data_id: str) -> Optional[EsDoc]:
        doc = self._get_index(index).get(data_id)
        if doc is None:
            return None
        return EsDoc(**doc)

    async def update(self, index: str, data_id: str, fields: dict) -> None:
        store = self._get_index(index)
        if data_id not in store:
            raise KeyError(f"{data_id} not found in {index}")
        store[data_id].update(fields)

    async def delete(self, index: str, data_id: str) -> bool:
        store = self._get_index(index)
        if data_id in store:
            del store[data_id]
            return True
        return False

    async def knn_search(
        self, index: str, query_vector: list[float], top_k: int, filters: dict
    ) -> list[SearchResult]:
        results = []
        for doc in self._get_index(index).values():
            if not self._matches_filters(doc, filters):
                continue
            if not doc.get("vector"):
                continue
            score = self._cosine_similarity(query_vector, doc["vector"])
            results.append(
                SearchResult(
                    data_id=doc["data_id"],
                    text=doc["text"],
                    score=score,
                    metadata=doc["metadata"],
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def text_search(
        self, index: str, query: str, top_k: int, filters: dict
    ) -> list[SearchResult]:
        results = []
        for doc in self._get_index(index).values():
            if not self._matches_filters(doc, filters):
                continue
            score = 1.0 if query in doc["text"] else 0.0
            if score == 0.0:
                continue
            results.append(
                SearchResult(
                    data_id=doc["data_id"],
                    text=doc["text"],
                    score=score,
                    metadata=doc["metadata"],
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def count(self, index: str) -> int:
        return len(self._get_index(index))

    async def list_ids(self, index: str, limit: int, offset: int) -> tuple[list[str], int]:
        store = self._get_index(index)
        total = len(store)
        ids = list(store.keys())[offset:offset + limit]
        return ids, total

    async def check_ids_exists(self, index: str, ids: list[str]) -> tuple[list[str], list[str]]:
        store = self._get_index(index)
        exists = [id for id in ids if id in store]
        missing = list(set(ids) - set(exists))
        return exists, missing
