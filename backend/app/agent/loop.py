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
             tools: list[dict] | None = None, instructions: str = SYSTEM_PROMPT, mode: str = "tools") -> TurnResult:
    """Bounded tool loop: the model asks, the dispatcher executes, results go back, until a text answer."""
    tools = tool_definitions() if tools is None else tools
    trace = Trace(turn_id)
    trace.emit("user_message", {"text": message, "mode": mode})
    items = [*history, {"role": "user", "content": message}]
    results: list[ToolResult] = []

    for _ in range(config.MAX_MODEL_CALLS):
        trace.emit("llm_request", {"model": config.LLM_MODEL, "n_items": len(items),
                                   "tools": [t["name"] for t in tools]})
        try:
            with Timer() as t:
                response = llm_client.create_response(instructions, items, tools)
        except Exception as e:
            trace.emit("error", {"where": "model", "message": f"{type(e).__name__}: {e}"})
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

        for call in calls:
            trace.emit("tool_call", {"call_id": call.call_id, "tool": call.name, "args": _parse(call.arguments)})
            with Timer() as t:
                result = dispatch(call.name, call.arguments, ctx)
            results.append(result)
            trace.emit("tool_result", {"call_id": call.call_id, "result_id": result.result_id,
                                       "status": result.status, "summary": result.summary,
                                       "error": result.error.model_dump() if result.error else None}, t.ms)
            items.append({"type": "function_call_output", "call_id": call.call_id,
                          "output": json.dumps(to_llm_payload(result), default=str)})

    trace.emit("error", {"where": "loop", "message": f"Stopped after {config.MAX_MODEL_CALLS} model calls."})
    return TurnResult("I stopped before finishing: too many steps. Try a more specific question.",
                      results, trace.events, items)


def _parse(arguments: str):
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
