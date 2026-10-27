import pytest

from backend.app.tools.registry import ToolContext, dispatch
from backend.app.tools.result import to_llm_payload


@pytest.fixture
def ctx(bundle):
    return ToolContext(bundle)


def test_get_sites_returns_rows_without_map_changes(ctx):
    r = dispatch("get_dataset", {"dataset_id": "sites"}, ctx)
    assert r.status == "ok" and r.table.total_rows == 13
    assert r.table.id_field == "site_id"
    assert {"site_id", "company_name", "lon", "lat", "tiv_eur"} <= {c.name for c in r.table.columns}
    assert r.map_actions == []
    assert len(to_llm_payload(r)["table"]["rows"]) == 13  # the model gets the full table


def test_get_incident_can_return_readable_geometry_without_map_changes(ctx):
    r = dispatch("get_dataset", {"dataset_id": "incident:flood_test", "include_geometry": True}, ctx)
    assert r.status == "ok"
    assert r.map_actions == []
    assert r.data["crs"] == "EPSG:4326"
    assert r.data["geometry"]["type"] == "FeatureCollection"
    assert len(r.data["geometry"]["features"]) == 2
    assert r.data["n_rows"] == 2
    assert "site_ids" not in r.data  # loading does not select anything


def test_unknown_dataset_hints_valid_ids(ctx):
    r = dispatch("get_dataset", {"dataset_id": "incident:earthquake"}, ctx)
    assert r.error.code == "unknown_dataset" and "incident:flood_test" in r.error.hint


def test_get_districts(ctx):
    r = dispatch("get_dataset", {"dataset_id": "districts"}, ctx)
    assert r.table.total_rows == 2
    assert r.map_actions == []


def test_highlight_sites_is_display_only(ctx):
    r = dispatch("highlight_sites", {"site_ids": ["S01", "S01", "S03"]}, ctx)
    assert r.data == {"site_ids": ["S01", "S03"], "n_sites": 2}
    assert r.map_actions == [{"type": "highlight_sites", "site_ids": ["S01", "S03"]}]
    assert dispatch("highlight_sites", {"site_ids": ["NOPE"]}, ctx).error.code == "unknown_site_ids"
    assert dispatch("highlight_sites", {"site_ids": []}, ctx).map_actions == [{"type": "clear_highlight"}]


def test_zoom_map_and_hide_layer(ctx):
    shown = dispatch("show_layer", {"layer_id": "sites"}, ctx)
    assert shown.map_actions == [{"type": "show_layer", "layer_id": "sites"}]
    assert dispatch("show_layer", {"layer_id": "nope"}, ctx).error.code == "unknown_layer"
    r = dispatch("zoom_map", {"layer_id": "incident:wildfire_test"}, ctx)
    assert r.map_actions[0]["type"] == "fit_bounds"
    assert dispatch("zoom_map", {"site_ids": ["S01"]}, ctx).status == "ok"
    both = dispatch("zoom_map", {"layer_id": "incident:flood_test", "site_ids": ["S08"]}, ctx)
    flood = dispatch("zoom_map", {"layer_id": "incident:flood_test"}, ctx).map_actions[0]["bbox"]
    assert both.status == "ok" and both.map_actions[0]["bbox"][2] > flood[2]  # extended east to the wildfire site
    assert dispatch("zoom_map", {}, ctx).error.code == "invalid_arguments"
    assert dispatch("zoom_map", {"layer_id": None, "site_ids": []}, ctx).error.code == "invalid_arguments"
    assert dispatch("zoom_map", {"layer_id": "nope"}, ctx).error.code == "unknown_layer"
    hide = dispatch("hide_layer", {"layer_id": "sites"}, ctx)
    assert hide.map_actions == [{"type": "hide_layer", "layer_id": "sites"}]


def test_suggest_follow_ups_returns_questions_only(ctx):
    r = dispatch("suggest_follow_ups", {"questions": ["Which of those sites are near the edge?", "  "]}, ctx)
    assert r.status == "ok"
    assert r.data["follow_ups"] == ["Which of those sites are near the edge?"]
    assert not r.map_actions and r.table is None


def test_suggest_follow_ups_rejects_too_many(ctx):
    r = dispatch("suggest_follow_ups", {"questions": ["a?", "b?", "c?"]}, ctx)
    assert r.status == "error"
