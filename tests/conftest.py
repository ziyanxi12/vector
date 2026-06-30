import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "vector_service"))

import json
import pytest
import httpx
import respx
from httpx import AsyncClient, ASGITransport
from main import app
from client.es_repository import MockEsRepository
from dependencies import get_es_repository


COMPONENT_META = {
    "name": "主按钮",
    "canvas_name": "Button",
    "component_name": "PrimaryButton",
    "domain": "basic",
}

ICON_META = {
    "name": "搜索图标",
    "description": "放大镜搜索",
    "english_name": "search",
    "category": "action",
}


def make_texttovec_response(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    vectors = [{"vector": [0.1] * 128, "text_id": item["text_id"]} for item in body["text_value"]]
    return httpx.Response(200, json={"vectors": vectors})


@pytest.fixture
def mock_es():
    return MockEsRepository()


@pytest.fixture
def override_es(mock_es):
    app.dependency_overrides[get_es_repository] = lambda: mock_es
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(override_es):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
