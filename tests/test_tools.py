import json

import pytest

from backend.app.tools.registry import TOOLS, ToolContext, dispatch, tool_definitions
from backend.app.tools.result import to_llm_payload


@pytest.fixture
def ctx(bundle):
    return ToolContext(bundle)


def test_definitions_have_responses_api_shape():
    defs = {d["name"]: d for d in tool_definitions()}
    assert set(defs) >= {"describe_data", "get_dataset", "show_layer", "highlight_sites"}
    for d in defs.values():
        assert d["type"] == "function" and d["description"] and d["parameters"]["type"] == "object"
    assert defs["get_dataset"]["parameters"]["required"] == ["dataset_id"]


def test_results_are_stored_with_unique_ids(ctx):
    loaded = dispatch("get_dataset", {"dataset_id": "sites"}, ctx)
    assert loaded.status == "ok" and loaded.result_id == "r_0001"
    assert loaded.table.total_rows == 13
    highlighted = dispatch("highlight_sites", {"site_ids": ["S01", "S02"]}, ctx)
    assert highlighted.status == "ok" and highlighted.result_id == "r_0002"
    assert ctx.store.get(loaded.result_id) is loaded
    assert ctx.store.get(highlighted.result_id) is highlighted
    assert ctx.store.get("r_9999") is None


def test_errors_are_results_with_hints(ctx):
    r = dispatch("get_dataset", {"dataset_id": "incident:earthquake"}, ctx)
    assert r.status == "error" and r.error.code == "unknown_dataset" and "flood_test" in r.error.hint

    assert dispatch("get_dataset", {}, ctx).error.code == "invalid_arguments"
    assert dispatch("get_dataset", "{not json", ctx).error.code == "invalid_arguments"
    assert dispatch("no_such_tool", {}, ctx).error.code == "unknown_tool"
    assert dispatch("highlight_sites", {"site_ids": ["NOPE"]}, ctx).error.code == "unknown_site_ids"


def test_unregistered_tool_is_not_dispatchable(ctx, monkeypatch):
    monkeypatch.setattr(TOOLS["show_layer"], "registered", False)
    assert "show_layer" not in {d["name"] for d in tool_definitions()}
    args = {"layer_id": "sites"}
    assert dispatch("show_layer", args, ctx).error.code == "unknown_tool"
    assert dispatch("show_layer", args, ctx, allow_unregistered=True).status == "ok"


def test_llm_payload_has_no_map_actions(ctx):
    r = dispatch("show_layer", {"layer_id": "incident:flood_test"}, ctx)
    payload = to_llm_payload(r)
    assert set(payload) == {"result_id", "status", "summary", "data"}
    json.dumps(payload)


def test_describe_data(ctx):
    d = dispatch("describe_data", {}, ctx)
    assert [i["id"] for i in d.data["incidents"]] == ["flood_test", "wildfire_test"]
