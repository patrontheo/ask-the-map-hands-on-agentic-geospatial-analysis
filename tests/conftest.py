from pathlib import Path

import pytest

from backend.app.data import load_bundle

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bundle"


@pytest.fixture(scope="session")
def bundle():
    return load_bundle(FIXTURE_DIR)


@pytest.fixture
def registered_tools(monkeypatch):
    """Register every core tool, as after step-01 (in step-00 they are implemented but unregistered)."""
    import backend.app.tools.core  # noqa: F401
    from backend.app.tools.registry import TOOLS

    for spec in TOOLS.values():
        monkeypatch.setattr(spec, "registered", True)
