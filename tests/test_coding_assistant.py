"""Exercise the launchers with dummy CLIs and temporary, synthetic credentials."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tomllib

from dotenv import dotenv_values
import pytest


BIN = Path(__file__).resolve().parents[1] / "coding-assistant" / "bin"
TEMPLATE = BIN.parents[1] / ".example.env"
SETTINGS = (
    "LLM_API_KEY", "LLM_BASE_URL", "AZURE_FOUNDRY_API_KEY",
    "LUNA_OPENAI_BASE_URL", "LUNA_DEPLOYMENT",
    "HAIKU_ANTHROPIC_BASE_URL", "HAIKU_DEPLOYMENT",
)


@pytest.fixture
def launch(tmp_path):
    repo = tmp_path / "workshop with spaces"
    shutil.copytree(BIN, repo / "coding-assistant" / "bin")
    stub_dir = tmp_path / "cli"
    stub_dir.mkdir()
    stub_code = f"settings = {SETTINGS!r}\n" + """
import json, os, sys
environment = {key: value for key, value in os.environ.items()
               if key in settings or key.startswith(("FILE_", "ANTHROPIC_", "CLAUDE_"))}
print(json.dumps({"args": sys.argv[1:], "env": environment, "cwd": os.getcwd()}))
"""
    stub = f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -c {shlex.quote(stub_code)} "$@"\n'
    for cli in ("codex", "claude"):
        path = stub_dir / cli
        path.write_text(stub)
        path.chmod(0o755)

    def run(script, config=None, *, overrides=None, args=()):
        # This .env exists only under pytest's temporary directory, never in the checkout.
        if config is not None:
            (repo / ".env").write_text(config)
        environment = {
            key: value for key, value in os.environ.items()
            if key not in SETTINGS and not key.startswith(("FILE_", "ANTHROPIC_", "CLAUDE_"))
        }
        environment["PATH"] = f"{stub_dir}:/usr/bin:/bin"
        environment.update(overrides or {})
        return subprocess.run(
            [str(repo / "coding-assistant" / "bin" / script), *args],
            cwd=tmp_path, env=environment, text=True, capture_output=True,
        )

    return run, repo


def test_codex_reuses_app_settings_and_passes_arguments(launch):
    run, repo = launch
    result = run("codex-luna", """
# No separate coding-assistant endpoint or key needed.
LLM_BASE_URL=https://example.invalid/openai/v1
LLM_API_KEY='dummy key=with equals'
LUNA_DEPLOYMENT=luna-test
""", args=("exec", "Reply with exactly: OK"))
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    assert child["cwd"] == str(repo)
    assert child["args"][-4:] == ["-m", "luna-test", "exec", "Reply with exactly: OK"]
    provider = tomllib.loads(child["args"][3])["model_providers"]["luna"]
    assert provider["base_url"] == "https://example.invalid/openai/v1"
    assert provider["wire_api"] == "responses"
    assert provider["requires_openai_auth"] is False
    assert child["env"][provider["env_key"]] == "dummy key=with equals"
    assert all("dummy key" not in arg for arg in child["args"])
    assert not any(key.startswith("FILE_") for key in child["env"])


def test_haiku_selects_foundry_and_pins_models(launch):
    run, _ = launch
    result = run("claude-haiku", """
LLM_API_KEY=dummy-app-key
AZURE_FOUNDRY_API_KEY=dummy-assistant-key
HAIKU_ANTHROPIC_BASE_URL=https://example.invalid/anthropic
HAIKU_DEPLOYMENT=haiku-test
""", overrides={
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "ANTHROPIC_API_KEY": "dummy-other-key",
        "ANTHROPIC_BASE_URL": "https://other.invalid",
        "ANTHROPIC_FOUNDRY_AUTH_TOKEN": "dummy-token",
        "ANTHROPIC_FOUNDRY_RESOURCE": "other",
    }, args=("-p", "Reply with exactly: OK"))
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    assert child["args"] == ["-p", "Reply with exactly: OK"]
    environment = child["env"]
    assert environment["CLAUDE_CODE_USE_FOUNDRY"] == "1"
    assert environment["ANTHROPIC_FOUNDRY_BASE_URL"] == "https://example.invalid/anthropic"
    assert environment["ANTHROPIC_FOUNDRY_API_KEY"] == "dummy-assistant-key"
    for key in (
        "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        assert environment[key] == "haiku-test"
    for key in (
        "CLAUDE_CODE_USE_BEDROCK", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
        "ANTHROPIC_FOUNDRY_AUTH_TOKEN", "ANTHROPIC_FOUNDRY_RESOURCE", "AZURE_FOUNDRY_API_KEY",
    ):
        assert key not in environment


def test_exported_values_override_file_and_shell_text_is_literal(launch):
    run, repo = launch
    marker = repo / "must-not-exist"
    result = run("codex-luna", (
        f'export LLM_API_KEY = "$(touch {marker})"\r\n'
        "LUNA_OPENAI_BASE_URL=https://file.invalid/openai/v1 # optional comment\r\n"
        "LUNA_DEPLOYMENT=file-model"  # No trailing newline.
    ), overrides={
        "LUNA_OPENAI_BASE_URL": "https://exported.invalid/openai/v1",
        "LUNA_DEPLOYMENT": "exported-model",
    })
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    assert child["env"]["AZURE_FOUNDRY_API_KEY"] == f"$(touch {marker})"
    assert child["args"][-1] == "exported-model"
    assert "https://exported.invalid/openai/v1" in child["args"][3]
    assert not marker.exists()


@pytest.mark.parametrize("script, setting", [
    ("codex-luna", "LUNA_OPENAI_BASE_URL"),
    ("claude-haiku", "HAIKU_ANTHROPIC_BASE_URL"),
])
def test_missing_configuration_stops_before_launch_without_exposing_key(launch, script, setting):
    run, _ = launch
    result = run(script, "LLM_API_KEY=dummy-private-key\n")
    assert result.returncode != 0
    assert not result.stdout
    assert setting in result.stderr
    assert ".example.env" in result.stderr
    assert "dummy-private-key" not in result.stderr


def test_exported_configuration_works_without_env_file(launch):
    run, _ = launch
    result = run("claude-haiku", overrides={
        "LLM_API_KEY": "dummy-exported-key",
        "HAIKU_ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
        "HAIKU_DEPLOYMENT": "haiku-test",
    })
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["env"]["ANTHROPIC_FOUNDRY_API_KEY"] == "dummy-exported-key"


@pytest.mark.parametrize("script", ["codex-luna", "claude-haiku"])
def test_participant_setup_from_current_template(launch, script):
    run, _ = launch
    template = TEMPLATE.read_text()
    defaults = dotenv_values(TEMPLATE, interpolate=False)
    config = template.replace("LLM_API_KEY=", "LLM_API_KEY=dummy-template-key", 1)
    if script == "codex-luna":
        config = config.replace("LLM_BASE_URL=", "LLM_BASE_URL=https://example.invalid/openai/v1", 1)
    else:
        # Haiku doesn't require the app or Luna endpoint to be configured.
        config = config.replace(
            "HAIKU_ANTHROPIC_BASE_URL=",
            "HAIKU_ANTHROPIC_BASE_URL=https://example.invalid/anthropic", 1,
        )
    result = run(script, config)
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    if script == "codex-luna":
        provider = tomllib.loads(child["args"][3])["model_providers"]["luna"]
        assert provider["base_url"] == "https://example.invalid/openai/v1"
        assert child["env"][provider["env_key"]] == "dummy-template-key"
        assert child["args"][-1] == defaults["LUNA_DEPLOYMENT"]
    else:
        assert child["env"]["ANTHROPIC_FOUNDRY_API_KEY"] == "dummy-template-key"
        assert child["env"]["ANTHROPIC_MODEL"] == defaults["HAIKU_DEPLOYMENT"]


def test_codex_uses_explicit_assistant_endpoint_and_key(launch):
    run, _ = launch
    result = run("codex-luna", """
LLM_BASE_URL=https://app.invalid/openai/v1
LLM_API_KEY=dummy-app-key
AZURE_FOUNDRY_API_KEY=dummy-assistant-key
LUNA_OPENAI_BASE_URL=https://assistant.invalid/openai/v1
LUNA_DEPLOYMENT=assistant-deployment
""")
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    provider = tomllib.loads(child["args"][3])["model_providers"]["luna"]
    assert provider["base_url"] == "https://assistant.invalid/openai/v1"
    assert child["env"][provider["env_key"]] == "dummy-assistant-key"
    assert child["args"][-1] == "assistant-deployment"


@pytest.mark.parametrize("script, cli", [("codex-luna", "codex"), ("claude-haiku", "claude")])
def test_missing_cli_has_actionable_error(launch, script, cli):
    run, repo = launch
    (repo.parent / "cli" / cli).unlink()
    result = run(script, """
LLM_API_KEY=dummy-private-key
LLM_BASE_URL=https://example.invalid/openai/v1
LUNA_DEPLOYMENT=luna-test
HAIKU_ANTHROPIC_BASE_URL=https://example.invalid/anthropic
HAIKU_DEPLOYMENT=haiku-test
""")
    assert result.returncode != 0
    assert not result.stdout
    assert f"{cli} CLI not found" in result.stderr
    assert "coding-assistant/README.md" in result.stderr
    assert "dummy-private-key" not in result.stderr
