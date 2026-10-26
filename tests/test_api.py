import json

import pytest
from fastapi.testclient import TestClient

from backend.app.agent import loop
from backend.app.main import app
from tests.test_loop import item, response


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_model(monkeypatch):
    calls = []

    def install(responses):
        def fake(instructions, items, tools):
            calls.append({"instructions": instructions, "items": list(items), "tools": tools})
            return responses.pop(0)
        monkeypatch.setattr(loop.llm_client, "create_response", fake)
        return calls
    return install


def test_layers_and_geojson(client):
    layers = {l["id"]: l for l in client.get("/api/layers").json()}
    assert {"sites", "districts", "incident:flood_test", "incident:wildfire_test"} <= set(layers)
    sites = client.get(layers["sites"]["url"]).json()
    assert len(sites["features"]) == 13
    assert sites["features"][0]["properties"]["company_name"]
    assert client.get("/api/layers/incident:flood_test").json()["features"][0]["properties"]["peril"] == "flood"
    assert client.get("/api/layers/nope").status_code == 404
    assert layers["simplified:flood_test"]["kind"] == "simplified_footprint"
    simplified = client.get("/api/layers/simplified:flood_test").json()
    assert simplified["features"][0]["properties"]["label"]


STEP00_TOOLS = {"describe_data", "load_portfolio", "load_incident", "load_districts", "highlight_sites",
                "zoom_map", "hide_layer"}
COMPUTATION_TOOLS = {"select_sites_in_incident", "summarize_sites", "distance_between_sites"}


def test_step00_registers_data_and_map_tools_only(client):
    tools = {t["name"]: t["registered"] for t in client.get("/api/tools").json()}
    assert {name for name, registered in tools.items() if registered} == STEP00_TOOLS
    assert COMPUTATION_TOOLS <= {name for name, registered in tools.items() if not registered}


def test_unregistered_tool_is_directly_callable(client):
    r = client.post("/api/tools/select_sites_in_incident",
                    json={"session_id": "s1", "args": {"incident_id": "flood_test"}}).json()
    assert r["status"] == "ok" and r["data"]["n_sites"] == 6
    bad = client.post("/api/tools/select_sites_in_incident", json={"session_id": "s1", "args": {}}).json()
    assert bad["error"]["code"] == "invalid_arguments"


def test_step00_chat_offers_only_data_and_map_tools(client, fake_model):
    calls = fake_model([
        response([item(type="function_call", call_id="c1", name="load_incident",
                       arguments=json.dumps({"incident_id": "flood_test"}))]),
        response([item(type="message")], text="Showing the flood."),
    ])
    r = client.post("/api/chat", json={"session_id": "s2", "message": "show the flood"}).json()
    assert {t["name"] for t in calls[0]["tools"]} == STEP00_TOOLS
    assert r["reply"] == "Showing the flood."
    assert r["results"][0]["map_actions"][0] == {"type": "show_layer", "layer_id": "incident:flood_test"}


def test_model_cannot_call_unregistered_computation_tool(client, fake_model):
    fake_model([
        response([item(type="function_call", call_id="c1", name="select_sites_in_incident",
                       arguments=json.dumps({"incident_id": "flood_test"}))]),
        response([item(type="message")], text="I can't compute that."),
    ])
    r = client.post("/api/chat", json={"session_id": "s5", "message": "flood?"}).json()
    assert r["results"][0]["error"]["code"] == "unknown_tool"


def test_history_kept_and_reset(client, fake_model):
    calls = fake_model([response([item(type="message")], text="a"), response([item(type="message")], text="b")])
    client.post("/api/chat", json={"session_id": "s4", "message": "one"})
    client.post("/api/chat", json={"session_id": "s4", "message": "two"})
    assert len(calls[1]["items"]) > 1
    assert len(client.get("/api/session/s4").json()["turns"]) == 2
    client.post("/api/session/s4/reset")
    assert client.get("/api/session/s4").json()["turns"] == []


def test_frontend_is_served(client):
    assert "Ask the Map" in client.get("/").text
