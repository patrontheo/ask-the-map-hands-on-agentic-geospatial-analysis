import json

import pytest

from backend.app.tools.registry import TOOLS, ToolContext, dispatch, tool_definitions
from backend.app.tools.result import to_llm_payload

pytestmark = pytest.mark.usefixtures("registered_tools")


@pytest.fixture
def ctx(bundle):
    return ToolContext(bundle)


def test_definitions_have_responses_api_shape():
    defs = {d["name"]: d for d in tool_definitions()}
    assert set(defs) >= {"describe_data", "select_sites_in_incident", "summarize_sites", "distance_between_sites"}
    for d in defs.values():
        assert d["type"] == "function" and d["description"] and d["parameters"]["type"] == "object"
    assert defs["select_sites_in_incident"]["parameters"]["required"] == ["incident_id"]


def test_select_then_summarize_by_result_id(ctx):
    sel = dispatch("select_sites_in_incident", json.dumps({"incident_id": "flood_test"}), ctx)
    assert sel.status == "ok" and sel.result_id == "r_0001"
    assert sel.data["n_sites"] == 6
    assert sel.map_actions[0] == {"type": "highlight_sites", "site_ids": sel.data["site_ids"]}

    summ = dispatch("summarize_sites", {"result_id": sel.result_id, "group_by": "company"}, ctx)
    assert summ.status == "ok"
    assert [r["group"] for r in summ.table.rows] == ["C01", "C03", "C02", "C04"]
    assert "EUR 14.0M" in summ.summary


def test_errors_are_results_with_hints(ctx):
    r = dispatch("select_sites_in_incident", {"incident_id": "earthquake"}, ctx)
    assert r.status == "error" and r.error.code == "unknown_incident" and "flood_test" in r.error.hint

    assert dispatch("select_sites_in_incident", {}, ctx).error.code == "invalid_arguments"
    assert dispatch("select_sites_in_incident", "{not json", ctx).error.code == "invalid_arguments"
    assert dispatch("no_such_tool", {}, ctx).error.code == "unknown_tool"
    assert dispatch("summarize_sites", {"result_id": "r_9999"}, ctx).error.code == "unknown_result"
    both = dispatch("summarize_sites", {"result_id": "r_0001", "site_ids": ["S01"]}, ctx)
    assert both.error.code == "invalid_arguments"


def test_unregistered_tool_is_not_dispatchable(ctx, monkeypatch):
    monkeypatch.setattr(TOOLS["summarize_sites"], "registered", False)
    assert "summarize_sites" not in {d["name"] for d in tool_definitions()}
    assert dispatch("summarize_sites", {}, ctx).error.code == "unknown_tool"
    assert dispatch("summarize_sites", {}, ctx, allow_unregistered=True).status == "ok"


def test_llm_payload_has_no_map_actions(ctx):
    r = dispatch("select_sites_in_incident", {"incident_id": "flood_test"}, ctx)
    payload = to_llm_payload(r)
    assert set(payload) == {"result_id", "status", "summary", "data"}
    json.dumps(payload)


def test_describe_and_distance(ctx):
    d = dispatch("describe_data", {}, ctx)
    assert [i["id"] for i in d.data["incidents"]] == ["flood_test", "wildfire_test"]
    dist = dispatch("distance_between_sites", {"site_a": "S01", "site_b": "S03"}, ctx)
    assert dist.data["distance_m"] == pytest.approx(3500, abs=1)
