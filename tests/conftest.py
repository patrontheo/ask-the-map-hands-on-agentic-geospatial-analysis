from pathlib import Path

import pytest

from backend.app.data import load_bundle

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bundle"


@pytest.fixture(scope="session")
def bundle():
    return load_bundle(FIXTURE_DIR)
