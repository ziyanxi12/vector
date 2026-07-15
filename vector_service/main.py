from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.router import router
from config import settings
from logger import get_logger, setup_logging
from version import __version__

setup_logging(settings.log_dir, verbose_http=settings.log_verbose_http)
logger = get_logger(__name__)


async def check_texttovec_connection() -> bool:
    try:
        from dependencies import get_texttovec_client
        from client.texttovec import TextItem
        client = get_texttovec_client()
        await client.encode([TextItem(text="test", text_id="test")])
        return True
    except Exception as e:
        logger.error("texttovec health check failed: %s", e, exc_info=True)
        return False


async def check_es_connection() -> bool:
    if settings.es_mock:
        return True
    try:
        from dependencies import get_es_repository
        repo = get_es_repository()
        await repo.ensure_template()
        return True
    except Exception as e:
        logger.error("es health check failed: %s", e, exc_info=True)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    from dependencies import get_es_repository, get_texttovec_client
    logger.info("service starting: version=%s es_mock=%s log_dir=%s", __version__, settings.es_mock, settings.log_dir)
    
    texttovec_ok = await check_texttovec_connection()
    es_ok = await check_es_connection()
    
    if not texttovec_ok:
        logger.error("texttovec connection check failed, service may not work properly")
    if not es_ok:
        logger.error("es connection check failed, service may not work properly")
    
    logger.info("service started: texttovec=%s es=%s", 
                "ok" if texttovec_ok else "FAILED", 
                "ok" if es_ok else "FAILED")
    yield
    await get_texttovec_client().close()
    if not settings.es_mock:
        await get_es_repository().close()
    logger.info("service stopped")


app = FastAPI(title="Vector Management Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": __version__}
