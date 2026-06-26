from contextlib import asynccontextmanager
from fastapi import FastAPI
from .api.router import router
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.es_mock:
        from .client.es_real import ElasticsearchRepository
        from .dependencies import get_es_repository
        repo: ElasticsearchRepository = get_es_repository()
        await repo.ensure_template()
    yield


app = FastAPI(title="Vector Management Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
