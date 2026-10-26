import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.agent.baseline import (baseline_footprint, baseline_footprint_info, baseline_instructions,
                                        footprint_geojson)
from backend.app.agent.loop import run_turn
from backend.app.data import get_bundle
from backend.app.store import SessionStore
from backend.app.tools import core  # noqa: F401  registers the tools
from backend.app.tools.registry import TOOLS, dispatch, tool_definitions
from backend.app.tools.result import ToolResult

router = APIRouter(prefix="/api")
sessions = SessionStore()

SITE_PROPERTIES = ["site_id", "company_id", "company_name", "address", "city", "district_name",
                   "property_type", "tiv_eur"]


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    turn_id: str
    mode: Literal["llm_only", "tools"]
    reply: str
    results: list[ToolResult]
    trace: list[dict]


class ToolCallRequest(BaseModel):
    session_id: str
    args: dict[str, Any] = Field(default_factory=dict)


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """With no tools registered (step-00) the model answers from the data in its prompt; otherwise it uses tools."""
    bundle = get_bundle()
    session = sessions.get(req.session_id, bundle)
    turn_id = session.next_turn_id()
    tools = tool_definitions()
    if tools:
        mode = "tools"
        turn = run_turn(req.message, session.ctx, session.history, turn_id, tools=tools, mode=mode)
    else:
        mode = "llm_only"
        turn = run_turn(req.message, session.ctx, session.history, turn_id, tools=[],
                        instructions=baseline_instructions(bundle), mode=mode)
    session.history = turn.items
    response = ChatResponse(turn_id=turn_id, mode=mode, reply=turn.reply, results=turn.results, trace=turn.trace)
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
def list_layers():
    bundle = get_bundle()
    layers = [{"id": "sites", "name": "Portfolio sites", "kind": "sites"},
              {"id": "districts", "name": "Districts", "kind": "districts"}]
    layers += [{"id": f"incident:{i.id}", "name": i.meta.get("name", i.id), "kind": "incident",
                "peril": i.meta.get("peril"), "incident_id": i.id} for i in bundle.incidents.values()]
    layers += [{"id": f"baseline:{i}", "name": f"{bundle.incidents[i].meta.get('name', i)} (as given to the model, simplified)",
                "kind": "baseline_footprint", "incident_id": i, "simplification": info}
               for i, info in baseline_footprint_info(bundle).items()]
    if bundle.buildings is not None:
        layers.append({"id": "buildings", "name": "Buildings", "kind": "buildings"})
    if bundle.parcels is not None:
        layers.append({"id": "parcels", "name": "Parcels", "kind": "parcels"})
    for layer in layers:
        layer["url"] = f"/api/layers/{layer['id']}"
    return layers


@router.get("/layers/{layer_id}")
def get_layer(layer_id: str):
    bundle = get_bundle()
    if layer_id == "sites":
        sites = bundle.sites.join(bundle.companies.company_name, on="company_id")
        gdf = sites[SITE_PROPERTIES + ["geometry"]]
    elif layer_id == "districts":
        gdf = bundle.districts[["district_code", "district_name", "geometry"]]
    elif layer_id.startswith("incident:") and layer_id.split(":", 1)[1] in bundle.incidents:
        incident = bundle.incidents[layer_id.split(":", 1)[1]]
        gdf = incident.polygons[["geometry"]].assign(incident_id=incident.id, peril=incident.meta.get("peril"))
    elif layer_id.startswith("baseline:") and layer_id.split(":", 1)[1] in bundle.incidents:
        incident_id = layer_id.split(":", 1)[1]
        geom, info = baseline_footprint(bundle, incident_id)
        return {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": footprint_geojson(geom),
            "properties": {"incident_id": incident_id, "label": info.label()}}]}
    elif layer_id == "buildings" and bundle.buildings is not None:
        gdf = bundle.buildings
    elif layer_id == "parcels" and bundle.parcels is not None:
        gdf = bundle.parcels
    else:
        raise HTTPException(404, f"Unknown layer '{layer_id}'")
    return json.loads(gdf.to_json(drop_id=True))
