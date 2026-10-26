from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.agent.loop import run_turn
from backend.app.data import get_bundle
from backend.app.layers import UnknownLayer, layer_geojson, list_layers
from backend.app.store import SessionStore
import backend.app.tools  # noqa: F401  declares the tools
from backend.app.tools.registry import TOOLS, dispatch
from backend.app.tools.result import ToolResult

router = APIRouter(prefix="/api")
sessions = SessionStore()


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    turn_id: str
    reply: str
    results: list[ToolResult]
    trace: list[dict]


class ToolCallRequest(BaseModel):
    session_id: str
    args: dict[str, Any] = Field(default_factory=dict)


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session = sessions.get(req.session_id, get_bundle())
    turn_id = session.next_turn_id()
    turn = run_turn(req.message, session.ctx, session.history, turn_id)
    session.history = turn.items
    response = ChatResponse(turn_id=turn_id, reply=turn.reply, results=turn.results, trace=turn.trace)
    session.turns.append({"message": req.message, **response.model_dump()})
    return response


@router.post("/session/{session_id}/reset")
def reset_session(session_id: str):
    sessions.reset(session_id)
    return {"ok": True}


@router.get("/session/{session_id}")
def get_session(session_id: str):
    return {"session_id": session_id, "turns": sessions.get(session_id, get_bundle()).turns}


@router.get("/tools")
def list_tools():
    return [{"name": t.name, "description": t.description, "schema": t.args_model.model_json_schema(),
             "registered": t.registered} for t in TOOLS.values()]


@router.post("/tools/{name}", response_model=ToolResult)
def call_tool(name: str, req: ToolCallRequest):
    session = sessions.get(req.session_id, get_bundle())
    return dispatch(name, req.args, session.ctx, allow_unregistered=True)


@router.get("/layers")
def get_layers():
    return list_layers(get_bundle())


@router.get("/layers/{layer_id}")
def get_layer(layer_id: str):
    try:
        return layer_geojson(get_bundle(), layer_id)
    except UnknownLayer:
        raise HTTPException(404, f"Unknown layer '{layer_id}'")
