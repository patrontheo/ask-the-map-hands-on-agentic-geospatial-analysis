"""Independent source checks, available before participants implement analysis tools."""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal

from backend.app.data import REPO_ROOT

DATA_DIR = REPO_ROOT / "data"
EXPECTED = json.loads((REPO_ROOT / "tests/expected.json").read_text())


def test_frozen_reference_inputs_have_not_changed():
    for relative_path, expected_hash in EXPECTED["input_sha256"].items():
        actual = hashlib.sha256((DATA_DIR / relative_path).read_bytes()).hexdigest()
        assert actual == expected_hash, f"Reference data changed: {relative_path}"


def test_frozen_totals_and_company_ranking_match_source_rows():
    catalog = json.loads((DATA_DIR / "catalog.json").read_text())
    with (DATA_DIR / catalog["portfolio"]["sites"]).open() as file:
        sites = list(csv.DictReader(file))
    with (DATA_DIR / catalog["portfolio"]["companies"]).open() as file:
        names = {row["company_id"]: row["company_name"] for row in csv.DictReader(file)}

    for expected in EXPECTED["incidents"].values():
        selected = set(expected["site_ids"])
        assert len(selected) == expected["n_sites"]
        counts, totals = Counter(), defaultdict(Decimal)
        for row in sites:
            if row["site_id"] in selected:
                counts[row["company_id"]] += 1
                totals[row["company_id"]] += Decimal(row["tiv_eur"])
        assert sum(counts.values()) == expected["n_sites"]
        assert sum(totals.values()) == expected["tiv_eur"]
        ranking = sorted(counts, key=lambda company_id: (-totals[company_id], company_id))
        rows = [{"group": company_id, "group_name": names[company_id],
                 "n_sites": counts[company_id], "tiv_eur": totals[company_id]} for company_id in ranking]
        assert rows == expected["by_company"]
