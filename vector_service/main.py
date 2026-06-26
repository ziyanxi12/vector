from fastapi import FastAPI
from .api.router import router

app = FastAPI(title="Vector Management Service")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
