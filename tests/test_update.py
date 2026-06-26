import respx
from tests.conftest import COMPONENT_META, make_texttovec_response
from vector_service.client.es_repository import EsDoc


async def _seed(mock_es, data_id="comp_001"):
    await mock_es.bulk_upsert("vec_component", [
        EsDoc(data_id=data_id, text="原始文本", vector=[0.1] * 128, metadata=COMPONENT_META)
    ])


@respx.mock
async def test_update_text_regenerates_vector(client, mock_es):
    await _seed(mock_es)
    respx.post("http://localhost:8099/textToVec").mock(side_effect=make_texttovec_response)

    resp = await client.put("/api/v1/update", json={
        "type": "component",
        "data_id": "comp_001",
        "text": "更新后的文本",
    })

    assert resp.status_code == 200
    doc = await mock_es.get("vec_component", "comp_001")
    assert doc.text == "更新后的文本"


async def test_update_metadata_only_no_texttovec(client, mock_es):
    await _seed(mock_es)
    new_meta = {**COMPONENT_META, "domain": "form"}

    resp = await client.put("/api/v1/update", json={
        "type": "component",
        "data_id": "comp_001",
        "metadata": new_meta,
    })

    assert resp.status_code == 200
    doc = await mock_es.get("vec_component", "comp_001")
    assert doc.metadata["domain"] == "form"
    assert doc.text == "原始文本"


async def test_update_not_found(client, mock_es):
    resp = await client.put("/api/v1/update", json={
        "type": "component",
        "data_id": "not_exist",
        "text": "新文本",
    })
    assert resp.status_code == 404


async def test_update_no_fields(client):
    resp = await client.put("/api/v1/update", json={
        "type": "component",
        "data_id": "comp_001",
    })
    assert resp.status_code == 422
