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
    async def bulk_delete(self, index: str, data_ids: list[str]) -> tuple[list[str], list[str]]:
        """批量删除，返回 (deleted_ids, not_found_ids)"""
        ...

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
        """分页获取 data_id 列表，返回"""
        ...

    @abstractmethod
    async def check_ids_exists(self, index: str, ids: list[str]) -> tuple[list[str], list[str]]:
        """批量检查 ID 是否存在，返回"""
        ...
