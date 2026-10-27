"""Calculation results survive API calls and keep the existing trace contract."""

import json

from tests.test_api import client, fake_model  # noqa: F401  reuse API fixtures
from tests.test_loop import item, response


def test_calculation_chain_is_serializable_reusable_and_traced(client, fake_model):
    fake_model([
        response([item(type="function_call", call_id="join", name="spatial_join", arguments=json.dumps({
            "left": "sites", "right": "incident:flood_test", "predicate": "covered_by",
        }))]),
        response([item(type="function_call", call_id="distinct", name="distinct_rows", arguments=json.dumps({
            "source": "r_0001", "columns": ["site_id"],
        }))]),
        response([item(type="function_call", call_id="total", name="aggregate", arguments=json.dumps({
            "source": "r_0002", "measures": [{"function": "sum", "column": "tiv_eur", "output": "tiv_eur"}],
        }))]),
        response([item(type="function_call", call_id="answer", name="suggest_follow_ups", arguments=json.dumps({
            "answer": "Six sites represent EUR 14M.", "questions": ["Which companies own them?"],
        }))]),
    ])
    result = client.post("/api/chat", json={"session_id": "calculation-api", "message": "Screen the flood."})
    assert result.status_code == 200
    turn = result.json()
    assert turn["reply"] == "Six sites represent EUR 14M."
    assert turn["results"][2]["table"]["rows"] == [{"tiv_eur": 14_000_000}]
    assert all("_frame" not in result for result in turn["results"])
    calls = {event["payload"]["call_id"]: event for event in turn["trace"] if event["type"] == "tool_call"}
    for event in turn["trace"]:
        if event["type"] != "tool_result":
            continue
        assert event["payload"]["call_id"] in calls
        assert event["duration_ms"] >= 0 and event["turn_id"] == turn["turn_id"]
    # A subsequent direct map call uses the private spatial frame from the chat.
    highlighted = client.post("/api/tools/highlight_sites", json={
        "session_id": "calculation-api", "args": {"result_id": "r_0002"},
    }).json()
    assert highlighted["status"] == "ok" and highlighted["data"]["n_sites"] == 6
