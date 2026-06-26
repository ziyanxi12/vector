import respx
from tests.conftest import COMPONENT_META, make_texttovec_response
from vector_service.client.es_repository import EsDoc


async def _seed(mock_es):
    docs = [
        EsDoc(data_id="comp_001", text="蓝色按钮", vector=[1.0] + [0.0] * 127, metadata={**COMPONENT_META, "domain": "basic"}),
        EsDoc(data_id="comp_002", text="红色按钮", vector=[0.9] + [0.1] * 127, metadata={**COMPONENT_META, "domain": "danger"}),
        EsDoc(data_id="comp_003", text="输入框组件", vector=[0.0, 1.0] + [0.0] * 126, metadata={**COMPONENT_META, "domain": "form"}),
    ]
    await mock_es.bulk_upsert("vec_component", docs)


@respx.mock
async def test_vector_search(client, mock_es):
    await _seed(mock_es)
    respx.post("http://localhost:8099/textToVec").mock(side_effect=make_texttovec_response)

    resp = await client.post("/api/v1/search", json={
        "type": "component",
        "query": "按钮",
        "mode": "vector",
        "top_k": 2,
    })

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    assert all("score" in r for r in results)


async def test_text_search(client, mock_es):
    await _seed(mock_es)

    resp = await client.post("/api/v1/search", json={
        "type": "component",
        "query": "按钮",
        "mode": "text",
        "top_k": 10,
    })

    assert resp.status_code == 200
    results = resp.json()["results"]
    ids = [r["data_id"] for r in results]
    assert "comp_001" in ids
    assert "comp_002" in ids
    assert "comp_003" not in ids


@respx.mock
async def test_hybrid_search(client, mock_es):
    await _seed(mock_es)
    respx.post("http://localhost:8099/textToVec").mock(side_effect=make_texttovec_response)

    resp = await client.post("/api/v1/search", json={
        "type": "component",
        "query": "按钮",
        "mode": "hybrid",
        "top_k": 3,
        "hybrid_weight": 0.7,
    })

    assert resp.status_code == 200
    assert len(resp.json()["results"]) > 0


async def test_search_with_filter(client, mock_es):
    await _seed(mock_es)

    resp = await client.post("/api/v1/search", json={
        "type": "component",
        "query": "按钮",
        "mode": "text",
        "filters": {"metadata.domain": "basic"},
    })

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert all(r["metadata"]["domain"] == "basic" for r in results)


async def test_get_item(client, mock_es):
    await _seed(mock_es)

    resp = await client.get("/api/v1/item", params={"type": "component", "data_id": "comp_001"})

    assert resp.status_code == 200
    assert resp.json()["data_id"] == "comp_001"


async def test_get_item_not_found(client, mock_es):
    resp = await client.get("/api/v1/item", params={"type": "component", "data_id": "not_exist"})
    assert resp.status_code == 404
