import respx
from tests.conftest import COMPONENT_META, ICON_META, make_texttovec_response


@respx.mock
async def test_ingest_component_success(client, mock_es):
    respx.post("http://localhost:8099/textToVec").mock(side_effect=make_texttovec_response)

    resp = await client.post("/api/v1/ingest", json={
        "type": "component",
        "items": [{"data_id": "comp_001", "text": "蓝色主按钮", "metadata": COMPONENT_META}],
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["succeeded"] == ["comp_001"]
    assert body["failed"] == []


@respx.mock
async def test_ingest_icon_success(client, mock_es):
    respx.post("http://localhost:8099/textToVec").mock(side_effect=make_texttovec_response)

    resp = await client.post("/api/v1/ingest", json={
        "type": "icon",
        "items": [{"data_id": "icon_001", "text": "搜索图标", "metadata": ICON_META}],
    })

    assert resp.status_code == 200
    assert resp.json()["succeeded"] == ["icon_001"]


@respx.mock
async def test_ingest_batch(client, mock_es):
    respx.post("http://localhost:8099/textToVec").mock(side_effect=make_texttovec_response)

    items = [
        {"data_id": f"comp_{i:03d}", "text": f"组件{i}", "metadata": COMPONENT_META}
        for i in range(5)
    ]
    resp = await client.post("/api/v1/ingest", json={"type": "component", "items": items})

    assert resp.status_code == 200
    assert len(resp.json()["succeeded"]) == 5


async def test_ingest_empty_text(client):
    resp = await client.post("/api/v1/ingest", json={
        "type": "component",
        "items": [{"data_id": "comp_001", "text": "", "metadata": COMPONENT_META}],
    })
    assert resp.status_code == 422


async def test_ingest_missing_metadata_field(client):
    resp = await client.post("/api/v1/ingest", json={
        "type": "component",
        "items": [{"data_id": "comp_001", "text": "按钮", "metadata": {"name": "只有name"}}],
    })
    assert resp.status_code == 200
    assert resp.json()["failed"][0]["data_id"] == "comp_001"


async def test_ingest_unknown_type(client):
    resp = await client.post("/api/v1/ingest", json={
        "type": "unknown",
        "items": [{"data_id": "x", "text": "test", "metadata": {}}],
    })
    assert resp.status_code == 400
