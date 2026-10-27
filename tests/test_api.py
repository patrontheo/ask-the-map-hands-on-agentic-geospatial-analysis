import json

import pytest
from fastapi.testclient import TestClient

from backend.app.agent import loop
from backend.app.data import get_bundle
from backend.app.main import app
from tests.conftest import FIXTURE_DIR
from tests.test_loop import item, response


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(FIXTURE_DIR))  # never the real bundle in data/
    get_bundle.cache_clear()
    with TestClient(app) as c:
        yield c
    get_bundle.cache_clear()


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
    assert not any(l["id"].startswith("simplified:") for l in layers.values())


STARTER_TOOLS = {"describe_data", "get_dataset", "show_layer", "highlight_sites",
                 "zoom_map", "hide_layer", "suggest_follow_ups"}
REMOVED_TOOLS = {"select_sites_in_incident", "summarize_sites", "distance_between_sites",
                 "load_portfolio", "load_incident", "load_districts"}


def test_starter_tools_available_without_prebuilt_computation_tools(client):
    tools = {t["name"]: t["registered"] for t in client.get("/api/tools").json()}
    assert STARTER_TOOLS <= {name for name, registered in tools.items() if registered}
    assert REMOVED_TOOLS.isdisjoint(tools)


def test_unregistered_tool_is_directly_callable(client, monkeypatch):
    from backend.app.tools.registry import TOOLS

    monkeypatch.setattr(TOOLS["get_dataset"], "registered", False)
    r = client.post("/api/tools/get_dataset", json={"session_id": "s1", "args": {"dataset_id": "districts"}}).json()
    assert r["status"] == "ok" and r["data"]["n_rows"] == 2
    bad = client.post("/api/tools/get_dataset", json={"session_id": "s1", "args": {}}).json()
    assert bad["error"]["code"] == "invalid_arguments"


@pytest.mark.parametrize("name", sorted(REMOVED_TOOLS))
def test_removed_tools_cannot_be_called_directly(client, name):
    result = client.post(f"/api/tools/{name}", json={"session_id": "removed-tools", "args": {}}).json()
    assert result["status"] == "error"
    assert result["error"]["code"] == "unknown_tool"


def test_chat_offers_registered_tools(client, fake_model):
    calls = fake_model([
        response([item(type="function_call", call_id="c1", name="show_layer",
                       arguments=json.dumps({"layer_id": "incident:flood_test"}))]),
        response([item(type="message")], text="Showing the flood."),
    ])
    r = client.post("/api/chat", json={"session_id": "s2", "message": "show the flood"}).json()
    available = {t["name"] for t in client.get("/api/tools").json() if t["registered"]}
    assert {t["name"] for t in calls[0]["tools"]} == available
    assert STARTER_TOOLS <= available
    assert r["reply"] == "Showing the flood."
    assert r["results"][0]["map_actions"][0] == {"type": "show_layer", "layer_id": "incident:flood_test"}


def test_dataset_results_survive_between_api_calls_without_serializing_frames(client):
    loaded = client.post("/api/tools/get_dataset", json={
        "session_id": "datasets", "args": {"dataset_id": "sites"},
    }).json()
    assert loaded["status"] == "ok" and loaded["map_actions"] == []
    assert "_frame" not in loaded
    highlighted = client.post("/api/tools/highlight_sites", json={
        "session_id": "datasets", "args": {"result_id": loaded["result_id"]},
    }).json()
    assert highlighted["status"] == "ok" and highlighted["data"]["n_sites"] == 13
    assert [action["type"] for action in highlighted["map_actions"]] == ["highlight_sites"]
    other = client.post("/api/tools/get_dataset", json={
        "session_id": "different-session", "args": {"dataset_id": loaded["result_id"]},
    }).json()
    assert other["error"]["code"] == "unknown_result"


def test_model_cannot_call_removed_computation_tool(client, fake_model):
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
