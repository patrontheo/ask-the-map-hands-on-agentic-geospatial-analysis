import pytest

from backend.app.tools.registry import ToolContext, dispatch
from backend.app.tools.result import to_llm_payload


@pytest.fixture
def ctx(bundle):
    return ToolContext(bundle)


def test_load_portfolio_returns_rows_and_shows_sites(ctx):
    r = dispatch("load_portfolio", {}, ctx)
    assert r.status == "ok" and r.table.total_rows == 13
    assert r.table.id_field == "site_id"
    assert {"site_id", "company_name", "lon", "lat", "tiv_eur"} <= {c.name for c in r.table.columns}
    assert r.map_actions[0] == {"type": "show_layer", "layer_id": "sites"}
    assert r.map_actions[1]["type"] == "fit_bounds"
    assert len(to_llm_payload(r)["table"]["rows"]) == 13  # the model gets the full table


def test_load_incident_shows_footprint_and_gives_readable_geometry(ctx):
    r = dispatch("load_incident", {"incident_id": "flood_test"}, ctx)
    assert r.status == "ok"
    assert r.map_actions[0] == {"type": "show_layer", "layer_id": "incident:flood_test"}
    reading = r.data["footprint_for_reading"]
    assert reading["crs"] == "EPSG:4326" and reading["geometry"]["type"] in {"Polygon", "MultiPolygon"}
    assert reading["label"]
    assert r.data["n_polygons"] == 2
    assert "site_ids" not in r.data  # loading does not select anything


def test_load_incident_unknown_id_hints_valid_ids(ctx):
    r = dispatch("load_incident", {"incident_id": "earthquake"}, ctx)
    assert r.error.code == "unknown_incident" and "flood_test" in r.error.hint


def test_load_districts(ctx):
    r = dispatch("load_districts", {}, ctx)
    assert r.table.total_rows == 2
    assert r.map_actions[0] == {"type": "show_layer", "layer_id": "districts"}


def test_highlight_sites_is_display_only(ctx):
    r = dispatch("highlight_sites", {"site_ids": ["S01", "S01", "S03"]}, ctx)
    assert r.data == {"site_ids": ["S01", "S03"], "n_sites": 2}
    assert {"type": "highlight_sites", "site_ids": ["S01", "S03"]} in r.map_actions
    assert dispatch("highlight_sites", {"site_ids": ["NOPE"]}, ctx).error.code == "unknown_site_ids"
    assert dispatch("highlight_sites", {"site_ids": []}, ctx).map_actions == [{"type": "clear_highlight"}]


def test_zoom_map_and_hide_layer(ctx):
    r = dispatch("zoom_map", {"layer_id": "incident:wildfire_test"}, ctx)
    assert r.map_actions[0]["type"] == "fit_bounds"
    assert dispatch("zoom_map", {"site_ids": ["S01"]}, ctx).status == "ok"
    assert dispatch("zoom_map", {}, ctx).error.code == "invalid_arguments"
    assert dispatch("zoom_map", {"layer_id": "nope"}, ctx).error.code == "unknown_layer"
    hide = dispatch("hide_layer", {"layer_id": "sites"}, ctx)
    assert hide.map_actions == [{"type": "hide_layer", "layer_id": "sites"}]
