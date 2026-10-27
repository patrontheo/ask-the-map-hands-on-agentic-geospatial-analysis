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


def test_follow_up_omits_geometry_and_can_reload_it(bundle, scripted):
    ctx = ToolContext(bundle)
    reasoning = item(type="reasoning", encrypted_content="opaque reasoning")
    answer = item(type="message", role="assistant", phase="final_answer", content="S01 and S03.")
    seen = scripted([
        response([
            item(type="function_call", call_id="sites", name="get_dataset",
                 arguments=json.dumps({"dataset_id": "sites", "include_geometry": True})),
            item(type="function_call", call_id="footprint", name="get_dataset",
                 arguments=json.dumps({"dataset_id": "incident:flood_test", "include_geometry": True})),
        ]),
        response([item(type="function_call", call_id="selection", name="highlight_sites",
                       arguments=json.dumps({"site_ids": ["S01", "S03"]}))]),
        response([reasoning, answer], text="S01 and S03."),
        response([item(type="message", content="Follow-up answer.")], text="Follow-up answer."),
        response([item(type="function_call", call_id="reload", name="get_dataset",
                       arguments=json.dumps({"dataset_id": "r_0002", "include_geometry": True}))]),
        response([item(type="message", content="Checked again.")], text="Checked again."),
    ])

    def outputs(items):
        return {i["call_id"]: json.loads(i["output"]) for i in items if i.get("type") == "function_call_output"}

    first = loop.run_turn("Which sites?", ctx, history=[], turn_id="t1")
    original = outputs(first.items)
    for call_id in ("sites", "footprint"):
        # Geometry remains available through every model call within the spatial question.
        assert outputs(seen[1])[call_id]["data"]["geometry"] == original[call_id]["data"]["geometry"]
        assert outputs(seen[2])[call_id]["data"]["geometry"] == original[call_id]["data"]["geometry"]

    second = loop.run_turn("What TIV do those sites represent?", ctx, first.items, turn_id="t2")
    compact = outputs(seen[3])
    for call_id in ("sites", "footprint"):
        assert "geometry" not in compact[call_id]["data"]
        assert compact[call_id]["table"] == original[call_id]["table"]
        assert compact[call_id]["result_id"] == original[call_id]["result_id"]
        assert "get_dataset" in compact[call_id]["data"]["geometry_note"]
    assert compact["selection"]["data"]["site_ids"] == ["S01", "S03"]
    assert reasoning.model_dump() in seen[3] and answer.model_dump() in seen[3]
    # The original transcript, stored results and backend geometry are untouched.
    assert outputs(first.items) == original
    assert ctx.store.get("r_0002").data["geometry"] == original["footprint"]["data"]["geometry"]
    assert len(ctx.get_frame("r_0002")) == 2

    third = loop.run_turn("Check the footprint geometry again.", ctx, second.items, turn_id="t3")
    assert third.results[0].status == "ok"
    assert "geometry" not in outputs(seen[4])["footprint"]["data"]
    assert outputs(seen[5])["reload"]["data"]["geometry"] == original["footprint"]["data"]["geometry"]


def test_final_answer_executes_entire_map_batch_without_another_model_call(bundle, scripted, monkeypatch):
    monkeypatch.setattr(loop.config, "MAX_MODEL_CALLS", 1)
    seen = scripted([response([
        # Finishing must still run the later map calls before returning.
        item(type="function_call", call_id="finish", name="suggest_follow_ups",
             arguments=json.dumps({"questions": ["What is their TIV?"], "answer": "**S01 and S03.**"})),
        item(type="function_call", call_id="show", name="show_layer",
             arguments=json.dumps({"layer_id": "incident:flood_test"})),
        item(type="function_call", call_id="highlight", name="highlight_sites",
             arguments=json.dumps({"site_ids": ["S01", "S03"]})),
        item(type="function_call", call_id="zoom", name="zoom_map",
             arguments=json.dumps({"site_ids": ["S01", "S03"]})),
    ])])

    turn = loop.run_turn("Which sites?", ToolContext(bundle), history=[], turn_id="t1")
    assert len(seen) == 1
    assert turn.reply == "**S01 and S03.**"
    assert len(turn.results) == 4 and all(r.status == "ok" for r in turn.results)
    assert [action["type"] for r in turn.results for action in r.map_actions] == [
        "show_layer", "highlight_sites", "fit_bounds",
    ]
    assert turn.results[0].data["follow_ups"] == ["What is their TIV?"]
    assert turn.items[-1] == {"role": "assistant", "content": turn.reply}
    assert turn.trace[-1]["type"] == "assistant_message"


def test_failed_map_batch_reaches_model_before_final_answer(bundle, scripted):
    seen = scripted([
        response([
            item(type="function_call", call_id="bad", name="show_layer",
                 arguments=json.dumps({"layer_id": "missing"})),
            item(type="function_call", call_id="premature", name="suggest_follow_ups",
                 arguments=json.dumps({"questions": ["What next?"], "answer": "Shown."})),
        ]),
        response([
            item(type="function_call", call_id="retry", name="show_layer",
                 arguments=json.dumps({"layer_id": "sites"})),
            item(type="function_call", call_id="finish", name="suggest_follow_ups",
                 arguments=json.dumps({"questions": ["Which sites?"], "answer": "Now shown."})),
        ]),
    ])

    turn = loop.run_turn("Show sites.", ToolContext(bundle), history=[], turn_id="t1")
    assert len(seen) == 2 and turn.reply == "Now shown."
    errors = [json.loads(i["output"]) for i in seen[1] if i.get("type") == "function_call_output"]
    assert errors[0]["error"]["code"] == "unknown_layer"
    assert turn.results[2].map_actions == [{"type": "show_layer", "layer_id": "sites"}]
    assert [e["payload"]["text"] for e in turn.trace if e["type"] == "assistant_message"] == ["Now shown."]
