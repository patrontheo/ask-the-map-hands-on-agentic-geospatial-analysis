"""Composed tool workflows checked against frozen answers and source geometry/CSV."""

import csv
import json

import numpy as np
import pandas as pd
import pytest
from pyproj import Transformer
from shapely import transform, union_all
from shapely.geometry import shape

from backend.app.data import REPO_ROOT, load_bundle
from backend.app.tools.registry import ToolContext, dispatch
from tests.test_table_tools import run


@pytest.fixture(scope="module")
def real_bundle():
    return load_bundle(REPO_ROOT / "data")


def selection(ctx, incident):
    joined = run(ctx, "spatial_join", left="sites", right=f"incident:{incident}", predicate="covered_by")
    return run(ctx, "distinct_rows", source=joined.result_id, columns=["site_id"])


def company_shares(ctx, selected):
    exposed = run(ctx, "aggregate", source=selected.result_id, group_by=["company_id"], measures=[
        {"function": "sum", "column": "tiv_eur", "output": "exposed_tiv_eur"},
        {"function": "count", "output": "n_exposed_sites"},
    ])
    portfolio = run(ctx, "aggregate", source="sites", group_by=["company_id", "company_name"], measures=[
        {"function": "sum", "column": "tiv_eur", "output": "portfolio_tiv_eur"},
    ])
    joined = run(ctx, "join_tables", left=portfolio.result_id, right=exposed.result_id, on=["company_id"])
    calculated = run(ctx, "calculate", source=joined.result_id, output_column="exposure_pct",
                     expression="exposed_tiv_eur / portfolio_tiv_eur * 100",
                     fill_nulls={"exposed_tiv_eur": 0, "n_exposed_sites": 0})
    return run(ctx, "sort_rows", source=calculated.result_id,
               columns=["exposed_tiv_eur", "company_id"], descending=[True, False])


def test_fixture_company_shares_use_full_portfolio(bundle):
    ctx = ToolContext(bundle)
    out = company_shares(ctx, selection(ctx, "flood_test"))
    expected = {"C01": (8_000_000, 32_000_000), "C02": (1_000_000, 5_000_000),
                "C03": (4_000_000, 11_000_000), "C04": (1_000_000, 11_000_000)}
    for row in out.table.rows:
        exposed, portfolio = expected[row["company_id"]]
        assert row["exposed_tiv_eur"] == exposed
        assert row["portfolio_tiv_eur"] == portfolio
        assert row["exposure_pct"] == pytest.approx(100 * exposed / portfolio)


def test_real_selection_totals_rankings_and_company_shares(real_bundle):
    ctx = ToolContext(real_bundle)
    incident = "wildfire_leporge_2026"
    expected = json.loads((REPO_ROOT / "tests/expected.json").read_text())["incidents"][incident]
    selected = selection(ctx, incident)
    assert sorted(row["site_id"] for row in selected.table.rows) == expected["site_ids"]
    assert selected.table.total_rows == expected["n_sites"] == 40
    total = run(ctx, "aggregate", source=selected.result_id, measures=[
        {"function": "count", "output": "n_sites"},
        {"function": "sum", "column": "tiv_eur", "output": "tiv_eur"},
    ])
    assert total.table.rows == [{"n_sites": 40, "tiv_eur": expected["tiv_eur"]}]
    shares = company_shares(ctx, selected)
    exposed_rows = [row for row in shares.table.rows if row["n_exposed_sites"] > 0]
    assert [{"group": row["company_id"], "group_name": row["company_name"],
             "n_sites": row["n_exposed_sites"], "tiv_eur": row["exposed_tiv_eur"]}
            for row in exposed_rows] == expected["by_company"]
    # Denominators are checked separately from the source CSV, not tool outputs.
    raw = pd.read_csv(REPO_ROOT / "data/portfolio/sites.csv")
    totals = raw.groupby("company_id").tiv_eur.sum().to_dict()
    for row in shares.table.rows:
        assert row["portfolio_tiv_eur"] == totals[row["company_id"]]
        assert row["exposure_pct"] == pytest.approx(100 * row["exposed_tiv_eur"] / totals[row["company_id"]])
    by_id = {row["company_id"]: row for row in shares.table.rows}
    assert len(by_id) == 15 and by_id["C14"]["exposed_tiv_eur"] == by_id["C14"]["exposure_pct"] == 0
    assert by_id["C15"]["exposure_pct"] == 100
    highlighted = dispatch("highlight_sites", {"result_id": selected.result_id}, ctx)
    assert highlighted.data["n_sites"] == 40
    assert dispatch("zoom_map", {"result_id": highlighted.result_id}, ctx).status == "ok"


def test_company_filter_commune_counts_and_portfolio_total(real_bundle):
    ctx = ToolContext(real_bundle)
    with (REPO_ROOT / "data/portfolio/sites.csv").open() as file:
        sites = list(csv.DictReader(file))
    filtered = run(ctx, "filter_rows", source="sites", column="company_name", value="Halvorne Logistics")
    assert sorted(row["site_id"] for row in filtered.table.rows) == sorted(s["site_id"] for s in sites if s["company_id"] == "C01")
    communes = run(ctx, "aggregate", source="sites", group_by=["district_code"],
                   measures=[{"function": "count_distinct", "column": "site_id", "output": "n_sites"}])
    for row in communes.table.rows:
        assert row["n_sites"] == sum(s["district_code"] == row["district_code"] for s in sites)
    total = run(ctx, "aggregate", source="sites", measures=[{"function": "sum", "column": "tiv_eur", "output": "tiv_eur"}])
    assert total.table.rows[0]["tiv_eur"] == sum(int(s["tiv_eur"]) for s in sites)


def test_real_commune_burnt_shares_and_ares(real_bundle):
    ctx = ToolContext(real_bundle)
    clipped = run(ctx, "intersect_geometries", left="districts", right="incident:wildfire_leporge_2026")
    burnt = run(ctx, "measure_area", source=clipped.result_id, output_column="burnt_area_ha")
    full = run(ctx, "measure_area", source="districts", output_column="total_area_ha")
    joined = run(ctx, "join_tables", left=full.result_id, right=burnt.result_id, on=["district_code"])
    shares = run(ctx, "calculate", source=joined.result_id, output_column="burnt_pct",
                 expression="burnt_area_ha / total_area_ha * 100", fill_nulls={"burnt_area_ha": 0})
    ranked = run(ctx, "sort_rows", source=shares.result_id, columns=["burnt_pct", "district_code"], descending=[True, False])
    # Independent geometry path: raw GeoJSON, pyproj and Shapely, no tool helpers.
    project = Transformer.from_crs(4326, 2154, always_xy=True).transform

    def projected(geometry):
        return transform(shape(geometry), lambda coords: np.column_stack(project(coords[:, 0], coords[:, 1])))

    fire = json.loads((REPO_ROOT / "data/events/wildfire_leporge_2026.geojson").read_text())
    mask = union_all([projected(feature["geometry"]) for feature in fire["features"]])
    districts = json.loads((REPO_ROOT / "data/admin/districts.geojson").read_text())
    references = {}
    for feature in districts["features"]:
        geometry = projected(feature["geometry"])
        references[feature["properties"]["district_code"]] = (geometry.area, geometry.intersection(mask).area)
    for row in ranked.table.rows:
        total, overlap = references[row["district_code"]]
        assert row["total_area_ha"] == pytest.approx(total / 10_000)
        assert row["burnt_area_ha"] == pytest.approx(overlap / 10_000)
        assert row["burnt_pct"] == pytest.approx(100 * overlap / total)
        assert 0 <= row["burnt_pct"] <= 100
    ares = run(ctx, "filter_rows", source=ranked.result_id, column="district_name", value="Arès")
    assert ares.table.total_rows == 1 and ares.table.rows[0]["burnt_pct"] > 0
