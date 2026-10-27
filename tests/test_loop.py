import json
from types import SimpleNamespace

import pytest

from backend.app.agent import loop
from backend.app.tools.registry import ToolContext


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
        response([item(type="function_call", call_id="c1", name="get_dataset", arguments='{"dataset_id":"sites"}')]),
        response([item(type="function_call", call_id="c2", name="highlight_sites",
                       arguments=json.dumps({"result_id": "r_0001"}))]),
        response([item(type="message", content="Highlighted the portfolio.")], text="Highlighted the portfolio."),
    ])
    turn = loop.run_turn("q", ToolContext(bundle), history=[], turn_id="t1")

    assert turn.reply == "Highlighted the portfolio."
    assert [r.tool for r in turn.results] == ["get_dataset", "highlight_sites"]
    assert turn.results[1].data["n_sites"] == 13
    types = [e["type"] for e in turn.trace]
    assert types == ["user_message", "llm_request", "llm_response", "tool_call", "tool_result",
                     "llm_request", "llm_response", "tool_call", "tool_result",
                     "llm_request", "llm_response", "assistant_message"]
    outputs = [i for i in seen[1] if isinstance(i, dict) and i.get("type") == "function_call_output"]
    assert outputs[0]["call_id"] == "c1" and json.loads(outputs[0]["output"])["data"]["n_rows"] == 13
    assert len(json.loads(outputs[0]["output"])["table"]["rows"]) == 13


def test_tool_error_goes_back_to_model(bundle, scripted):
    scripted([
        response([item(type="function_call", call_id="c1", name="get_dataset",
                       arguments=json.dumps({"dataset_id": "incident:earthquake"}))]),
        response([item(type="message", content="No such incident.")], text="No such incident."),
    ])
    turn = loop.run_turn("q", ToolContext(bundle), history=[], turn_id="t1")
    result_event = next(e for e in turn.trace if e["type"] == "tool_result")
    assert result_event["payload"]["status"] == "error"
    assert result_event["payload"]["error"]["code"] == "unknown_dataset"


def test_loop_stops_at_limit(bundle, scripted, monkeypatch):
    monkeypatch.setattr(loop.config, "MAX_MODEL_CALLS", 2)
    call = item(type="function_call", call_id="c", name="describe_data", arguments="{}")
    scripted([response([call]), response([call])])
    turn = loop.run_turn("q", ToolContext(bundle), history=[], turn_id="t1")
    assert turn.trace[-1]["type"] == "error"
