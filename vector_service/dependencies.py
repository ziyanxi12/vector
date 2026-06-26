from .config import settings
from .client.texttovec import TextToVecClient
from .client.es_repository import EsRepository, MockEsRepository

_texttovec_client = TextToVecClient(settings.texttovec_base_url, settings.texttovec_dimension)
_mock_es = MockEsRepository()


def get_es_repository() -> EsRepository:
    if settings.es_mock:
        return _mock_es
    from .client.es_real import ElasticsearchRepository
    return ElasticsearchRepository(settings.es_url)


def get_texttovec_client() -> TextToVecClient:
    return _texttovec_client
