from __future__ import annotations

from config import settings
from client.texttovec import TextToVecClient
from client.es_repository import EsRepository

_texttovec_client = TextToVecClient(
    settings.texttovec_base_url,
    settings.texttovec_dimension,
    timeout=settings.texttovec_timeout,
)
_es_real: EsRepository | None = None


def get_es_repository() -> EsRepository:
    global _es_real
    if _es_real is None:
        from client.es_real import ElasticsearchRepository
        _es_real = ElasticsearchRepository(
            settings.es_url, settings.es_username,
            settings.es_password, settings.es_verify_certs,
        )
    return _es_real


def get_texttovec_client() -> TextToVecClient:
    return _texttovec_client
