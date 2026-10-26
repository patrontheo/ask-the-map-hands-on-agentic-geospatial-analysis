import json
from types import SimpleNamespace

import pytest

from backend.app.agent import loop
from backend.app.tools.registry import ToolContext

pytestmark = pytest.mark.usefixtures("registered_tools")


def item(**kw):
    return SimpleNamespace(**kw, model_dump=lambda exclude_none=True: dict(kw))


def response(output, text=""):
    return SimpleNamespace(output=output, output_text=text,
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5))


@pytest.fixture
def scripted(monkeypatch):
    def install(responses):
        seen = []

        def fake(instructions, items, tools):
            seen.append(list(items))
            return responses.pop(0)
        monkeypatch.setattr(loop.llm_client, "create_response", fake)
        return seen
    return install


def test_two_tool_turn_feeds_results_back(bundle, scripted):
    seen = scripted([
        response([item(type="function_call", call_id="c1", name="select_sites_in_incident",
                       arguments=json.dumps({"incident_id": "flood_test"}))]),
        response([item(type="function_call", call_id="c2", name="summarize_sites",
                       arguments=json.dumps({"result_id": "r_0001", "group_by": "company"}))]),
        response([item(type="message", content="6 sites, EUR 14.0M.")], text="6 sites, EUR 14.0M."),
    ])
    turn = loop.run_turn("q", ToolContext(bundle), history=[], turn_id="t1")

    assert turn.reply == "6 sites, EUR 14.0M."
    assert [r.tool for r in turn.results] == ["select_sites_in_incident", "summarize_sites"]
    types = [e["type"] for e in turn.trace]
    assert types == ["user_message", "llm_request", "llm_response", "tool_call", "tool_result",
                     "llm_request", "llm_response", "tool_call", "tool_result",
                     "llm_request", "llm_response", "assistant_message"]
    outputs = [i for i in seen[1] if isinstance(i, dict) and i.get("type") == "function_call_output"]
    assert outputs[0]["call_id"] == "c1" and json.loads(outputs[0]["output"])["data"]["n_sites"] == 6


def test_tool_error_goes_back_to_model(bundle, scripted):
    scripted([
        response([item(type="function_call", call_id="c1", name="select_sites_in_incident",
                       arguments=json.dumps({"incident_id": "earthquake"}))]),
        response([item(type="message", content="No such incident.")], text="No such incident."),
    ])
    turn = loop.run_turn("q", ToolContext(bundle), history=[], turn_id="t1")
    result_event = next(e for e in turn.trace if e["type"] == "tool_result")
    assert result_event["payload"]["status"] == "error"
    assert result_event["payload"]["error"]["code"] == "unknown_incident"


def test_loop_stops_at_limit(bundle, scripted, monkeypatch):
    monkeypatch.setattr(loop.config, "MAX_MODEL_CALLS", 2)
    call = item(type="function_call", call_id="c", name="describe_data", arguments="{}")
    scripted([response([call]), response([call])])
    turn = loop.run_turn("q", ToolContext(bundle), history=[], turn_id="t1")
    assert turn.trace[-1]["type"] == "error"
