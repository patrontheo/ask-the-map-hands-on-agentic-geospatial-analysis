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
    assert layers["baseline:flood_test"]["kind"] == "baseline_footprint"
    baseline = client.get("/api/layers/baseline:flood_test").json()
    assert baseline["features"][0]["properties"]["label"]


def test_step00_tools_listed_unregistered_but_directly_callable(client):
    tools = {t["name"]: t for t in client.get("/api/tools").json()}
    assert "select_sites_in_incident" in tools
    assert not any(t["registered"] for t in tools.values())
    r = client.post("/api/tools/select_sites_in_incident",
                    json={"session_id": "s1", "args": {"incident_id": "flood_test"}}).json()
    assert r["status"] == "ok" and r["data"]["n_sites"] == 6
    bad = client.post("/api/tools/select_sites_in_incident", json={"session_id": "s1", "args": {}}).json()
    assert bad["error"]["code"] == "invalid_arguments"


def test_step00_chat_is_llm_only_with_data_in_prompt(client, fake_model):
    calls = fake_model([response([item(type="message")], text="I count 6 sites.")])
    r = client.post("/api/chat", json={"session_id": "s3", "message": "flood?"}).json()
    assert r["mode"] == "llm_only" and r["results"] == []
    assert calls[0]["tools"] == []
    instructions = calls[0]["instructions"]
    assert all(f"S{n:02d}" in instructions for n in range(1, 14))
    assert '"type":"Polygon"' in instructions and "flood_test" in instructions
    assert r["trace"][0]["payload"]["mode"] == "llm_only"


@pytest.mark.usefixtures("registered_tools")
def test_chat_uses_tools_once_registered(client, fake_model):
    calls = fake_model([
        response([item(type="function_call", call_id="c1", name="select_sites_in_incident",
                       arguments=json.dumps({"incident_id": "flood_test"}))]),
        response([item(type="message")], text="6 sites."),
    ])
    r = client.post("/api/chat", json={"session_id": "s2", "message": "flood?"}).json()
    assert r["mode"] == "tools" and r["reply"] == "6 sites."
    assert calls[0]["tools"] and "## Sites" not in calls[0]["instructions"]
    assert r["results"][0]["map_actions"][0]["type"] == "highlight_sites"


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
