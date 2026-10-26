import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from backend.app.analysis import AnalysisError
from backend.app.data import Bundle
from backend.app.tools.result import ToolResult

log = logging.getLogger(__name__)


class ResultStore:
    def __init__(self):
        self._results: dict[str, ToolResult] = {}

    def next_id(self) -> str:
        return f"r_{len(self._results) + 1:04d}"

    def add(self, result: ToolResult) -> None:
        self._results[result.result_id] = result

    def get(self, result_id: str) -> ToolResult | None:
        return self._results.get(result_id)


@dataclass
class ToolContext:
    bundle: Bundle
    store: ResultStore = field(default_factory=ResultStore)


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[[Bundle, BaseModel, ToolContext], ToolResult]
    registered: bool = True

    def definition(self) -> dict:
        """Function definition in the shape the Responses API expects."""
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {"type": "function", "name": self.name, "description": self.description, "parameters": schema}


TOOLS: dict[str, ToolSpec] = {}


def tool(args: type[BaseModel], description: str = "", registered: bool = True):
    def decorator(fn):
        TOOLS[fn.__name__] = ToolSpec(fn.__name__, description.strip(), args, fn, registered)
        return fn
    return decorator


def registered_tools() -> list[ToolSpec]:
    return [t for t in TOOLS.values() if t.registered]


def tool_definitions() -> list[dict]:
    return [t.definition() for t in registered_tools()]


def dispatch(name: str, arguments: str | dict[str, Any], ctx: ToolContext,
             allow_unregistered: bool = False) -> ToolResult:
    """The only place where tools run. Always returns a ToolResult, never raises.

    The model may only call registered tools; direct calls (allow_unregistered) can run any implemented tool.
    """
    raw_args: dict[str, Any] = {}
    spec = TOOLS.get(name)
    try:
        raw_args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
        if spec is None or not (spec.registered or allow_unregistered):
            names = ", ".join(t.name for t in registered_tools())
            result = ToolResult.fail("unknown_tool", f"No tool named '{name}' is available.",
                                     f"Available tools: {names}.")
        else:
            result = spec.fn(ctx.bundle, spec.args_model.model_validate(raw_args), ctx)
    except json.JSONDecodeError as e:
        result = ToolResult.fail("invalid_arguments", "Arguments are not valid JSON.", str(e))
    except ValidationError as e:
        hint = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'args'}: {err['msg']}" for err in e.errors())
        result = ToolResult.fail("invalid_arguments", f"Invalid arguments for '{name}'.", hint)
    except AnalysisError as e:
        result = ToolResult.fail(e.code, e.message, e.hint)
    except Exception:
        log.exception("tool %s failed", name)
        result = ToolResult.fail("internal_error", f"Tool '{name}' failed unexpectedly.",
                                 "This is a bug in the tool, not in your request.")

    result.result_id = ctx.store.next_id()
    result.tool = name
    result.args = raw_args
    ctx.store.add(result)
    return result
