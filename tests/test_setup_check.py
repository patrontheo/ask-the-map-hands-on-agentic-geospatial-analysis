import json

import pytest

from backend.app import config
from backend.app.data import get_bundle
from scripts.setup_check import main
from tests.conftest import FIXTURE_DIR


@pytest.fixture
def setup_environment(monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(FIXTURE_DIR))
    get_bundle.cache_clear()
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.setattr(config, name, f"private-{name.lower()}")
    yield
    get_bundle.cache_clear()


def test_offline_setup_succeeds_without_model_requests(setup_environment, monkeypatch, capsys):
    from backend.app.agent import llm_client

    def unexpected_request(*args, **kwargs):
        pytest.fail("Offline setup must not call the model")

    monkeypatch.setattr(llm_client, "create_response", unexpected_request)
    assert main(["--json"]) == 0
    output = capsys.readouterr().out
    assert "private-" not in output
    checks = {check["check"]: check for check in json.loads(output)}
    assert checks["Data"]["ok"] and "fixture fallback" in checks["Data"]["message"]
    assert checks["Backend"]["ok"]


def test_missing_configuration_fails_without_exposing_values(setup_environment, monkeypatch, capsys):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    assert main(["--json"]) == 1
    output = capsys.readouterr().out
    assert "private-" not in output
    failed = [check for check in json.loads(output) if not check["ok"]]
    assert len(failed) == 1 and failed[0]["check"] == "Model configuration"
    assert "LLM_API_KEY" in failed[0]["message"]
