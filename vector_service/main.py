from contextlib import asynccontextmanager
from fastapi import FastAPI
from .api.router import router
from .config import settings
from .logger import get_logger, setup_logging

setup_logging(settings.log_dir)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .dependencies import get_es_repository, get_texttovec_client
    logger.info("service starting: es_mock=%s log_dir=%s", settings.es_mock, settings.log_dir)
    if not settings.es_mock:
        from .client.es_real import ElasticsearchRepository
        repo: ElasticsearchRepository = get_es_repository()
        await repo.ensure_template()
    logger.info("service started")
    yield
    await get_texttovec_client().close()
    if not settings.es_mock:
        await get_es_repository().close()
    logger.info("service stopped")


app = FastAPI(title="Vector Management Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
