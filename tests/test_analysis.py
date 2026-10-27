from dataclasses import replace

import geopandas as gpd
import pytest
from shapely.geometry import MultiPolygon, box

from backend.app.analysis import (AnalysisError, distance_between_sites, incident_footprint,
                                  select_sites_in_incident, summarize_sites)

FLOOD_SITES = ["S01", "S02", "S04", "S05", "S07", "S12"]


def test_flood_selection_counts_overlap_once_and_includes_boundary(bundle):
    sel = select_sites_in_incident(bundle, "flood_test")
    assert sel.site_ids == FLOOD_SITES
    assert sel.n_sites == 6
    assert sel.metadata["n_footprint_polygons"] == 2


def test_wildfire_selection(bundle):
    assert select_sites_in_incident(bundle, "wildfire_test").site_ids == ["S08", "S11"]


def test_any_building_intersection_overrides_pinpoint_and_counts_site_once(bundle):
    outside = box(704400, 7059000, 704500, 7059100)
    inside = box(701000, 7059000, 701100, 7059100)
    buildings = gpd.GeoDataFrame({"site_id": ["S03", "S03", "S01"]},
                                geometry=[MultiPolygon([outside, inside]), inside, outside], crs=2154)
    result = select_sites_in_incident(replace(bundle, buildings=buildings), "flood_test")
    assert result.site_ids == ["S03"]  # outside point, but one building part is inside
    assert result.n_sites == 1  # repeated building rows do not count twice
    assert result.metadata["selection_basis"] == "building_intersection"
    # S01's pinpoint is inside, but its supplied building is outside: the point is not used.


def test_building_boundary_contact_counts_as_affected(bundle):
    footprint = incident_footprint(bundle, "flood_test").union_projected
    east = footprint.bounds[2]
    buildings = gpd.GeoDataFrame({"site_id": ["S03"]},
                                geometry=[box(east, 7059000, east + 50, 7059050)], crs=2154)
    assert select_sites_in_incident(replace(bundle, buildings=buildings), "flood_test").site_ids == ["S03"]


def test_bundles_without_buildings_use_explicit_point_fallback(bundle):
    result = select_sites_in_incident(bundle, "flood_test")
    assert result.metadata["selection_basis"] == "point_fallback"


def test_unknown_incident_lists_valid_ids(bundle):
    with pytest.raises(AnalysisError) as e:
        select_sites_in_incident(bundle, "earthquake")
    assert e.value.code == "unknown_incident"
    assert "flood_test" in e.value.hint


def test_exposed_tiv_by_company_with_tie_rule(bundle):
    s = summarize_sites(bundle, FLOOD_SITES, group_by="company", metric="tiv")
    assert s.table.group.tolist() == ["C01", "C03", "C02", "C04"]
    assert s.table.tiv_eur.tolist() == [8_000_000, 4_000_000, 1_000_000, 1_000_000]
    assert s.table.group_name.iloc[0] == "Alder Logistics"
    assert s.metadata["total_tiv_eur"] == 14_000_000


def test_zero_tiv_site_counts_as_site(bundle):
    s = summarize_sites(bundle, ["S05"], group_by="none", metric="n_sites")
    assert s.table.n_sites.iloc[0] == 1
    assert s.table.tiv_eur.iloc[0] == 0


def test_duplicates_removed(bundle):
    s = summarize_sites(bundle, ["S01", "S01", "S02"])
    assert s.metadata["duplicates_removed"] == 1
    assert s.metadata["total_tiv_eur"] == 8_000_000


def test_whole_portfolio_when_no_ids(bundle):
    s = summarize_sites(bundle, None, group_by="company")
    totals = dict(zip(s.table.group, s.table.tiv_eur))
    assert totals == {"C01": 32_000_000, "C03": 11_000_000, "C04": 11_000_000, "C02": 5_000_000}


def test_share_ranking_differs_from_absolute(bundle):
    exposed = summarize_sites(bundle, FLOOD_SITES, group_by="company").table.set_index("group").tiv_eur
    total = summarize_sites(bundle, None, group_by="company").table.set_index("group").tiv_eur
    share = (exposed / total[exposed.index] * 100).round(1).sort_values(ascending=False)
    assert share.to_dict() == {"C03": 36.4, "C01": 25.0, "C02": 20.0, "C04": 9.1}
    assert share.index[0] != exposed.index[0]


def test_unknown_site_ids(bundle):
    with pytest.raises(AnalysisError) as e:
        summarize_sites(bundle, ["S01", "NOPE"])
    assert e.value.code == "unknown_site_ids"


def test_group_by_district(bundle):
    s = summarize_sites(bundle, FLOOD_SITES, group_by="district")
    assert s.table.group.tolist() == ["D1"]
    assert s.table.group_name.tolist() == ["West District"]


def test_naive_per_polygon_count_double_counts(bundle):
    fp_parts = bundle.incidents["flood_test"].polygons.to_crs(bundle.crs_projected).geometry
    naive = sum(int(bundle.sites_projected.map(p.covers).sum()) for p in fp_parts)
    assert naive == 7
    assert incident_footprint(bundle, "flood_test").n_polygons == 2


def test_distance_in_metres(bundle):
    d = distance_between_sites(bundle, "S01", "S03")
    assert d.distance_m == pytest.approx(3500, abs=1)
    assert d.crs == "EPSG:2154"
