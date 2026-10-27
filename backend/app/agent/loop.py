import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.app import config
from backend.app.agent import llm_client
from backend.app.agent.trace import Timer, Trace
from backend.app.tools.registry import ToolContext, dispatch, tool_definitions
from backend.app.tools.result import ToolResult, to_llm_payload

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text()


@dataclass
class TurnResult:
    reply: str
    results: list[ToolResult]
    trace: list[dict]
    items: list = field(default_factory=list)


def run_turn(message: str, ctx: ToolContext, history: list, turn_id: str,
             tools: list[dict] | None = None) -> TurnResult:
    """Bounded tool loop: the model asks, the dispatcher executes, results go back, until a text answer."""
    tools = tool_definitions() if tools is None else tools
    trace = Trace(turn_id)
    trace.emit("user_message", {"text": message})
    items = [*_without_past_geometry(history), {"role": "user", "content": message}]
    results: list[ToolResult] = []

    for _ in range(config.MAX_MODEL_CALLS):
        trace.emit("llm_request", {"model": config.LLM_MODEL, "n_items": len(items),
                                   "reasoning_effort": config.LLM_REASONING_EFFORT or None,
                                   "tools": [t["name"] for t in tools]})
        try:
            with Timer() as t:
                response = llm_client.create_response(SYSTEM_PROMPT, items, tools)
        except Exception as e:
            trace.emit("error", {"where": "model", "message": f"{type(e).__name__}: {e}"}, t.ms)
            return TurnResult("The model request failed; see the trace for details.", results, trace.events, items)

        calls = [o for o in response.output if o.type == "function_call"]
        usage = response.usage
        trace.emit("llm_response", {
            "text": response.output_text,
            "function_calls": [{"call_id": c.call_id, "name": c.name, "arguments": c.arguments} for c in calls],
            "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens} if usage else None,
        }, t.ms)
        items += [o.model_dump(exclude_none=True) for o in response.output]

        if not calls:
            trace.emit("assistant_message", {"text": response.output_text})
            return TurnResult(response.output_text, results, trace.events, items)

        batch: list[ToolResult] = []
        for call in calls:
            trace.emit("tool_call", {"call_id": call.call_id, "tool": call.name, "args": _parse(call.arguments)})
            with Timer() as t:
                result = dispatch(call.name, call.arguments, ctx)
            results.append(result)
            batch.append(result)
            trace.emit("tool_result", {"call_id": call.call_id, "result_id": result.result_id,
                                       "status": result.status, "summary": result.summary,
                                       "error": result.error.model_dump() if result.error else None}, t.ms)
            items.append({"type": "function_call_output", "call_id": call.call_id,
                          "output": json.dumps(to_llm_payload(result), default=str)})

        answer = next((r.data.get("answer") for r in reversed(batch) if r.tool == "suggest_follow_ups"), None)
        if answer and all(r.status == "ok" for r in batch):
            items.append({"role": "assistant", "content": answer})
            trace.emit("assistant_message", {"text": answer})
            return TurnResult(answer, results, trace.events, items)

    trace.emit("error", {"where": "loop", "message": f"Stopped after {config.MAX_MODEL_CALLS} model calls."})
    return TurnResult("I stopped before finishing: too many steps. Try a more specific question.",
                      results, trace.events, items)


def _without_past_geometry(history: list[dict]) -> list[dict]:
    """Keep earlier tables and result IDs, but load their GeoJSON only on demand."""
    items = []
    for item in history:
        if item.get("type") == "function_call_output":
            payload = json.loads(item["output"])
            data = payload.get("data", {})
            if "geometry" in data:
                data = {k: v for k, v in data.items() if k != "geometry"}
                data["geometry_note"] = (
                    "Coordinates omitted from an earlier turn. If needed, reload with "
                    f"get_dataset(dataset_id='{payload['result_id']}', include_geometry=true)."
                )
                item = {**item, "output": json.dumps({**payload, "data": data})}
        items.append(item)
    return items


def _parse(arguments: str):
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
