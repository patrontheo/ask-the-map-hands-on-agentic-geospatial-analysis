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
from pathlib import Path
arguments = sys.argv[2:]
if arguments == ["--version"]:
    print(Path(sys.argv[1]).with_name("version.txt").read_text().strip())
    raise SystemExit(0)
if arguments == ["--help"]:
    print(Path(sys.argv[1]).with_name(Path(sys.argv[1]).name + "-help.txt").read_text())
    raise SystemExit(0)
environment = {key: value for key, value in os.environ.items()
               if key in settings or key.startswith(("FILE_", "ANTHROPIC_", "CLAUDE_", "OPENCODE_"))}
print(json.dumps({"args": arguments, "env": environment, "cwd": os.getcwd(), "executable": sys.argv[1]}))
"""
    stub = f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -c {shlex.quote(stub_code)} "$0" "$@"\n'
    (stub_dir / "version.txt").write_text("2.1.308 (Claude Code)\n")
    (stub_dir / "opencode-help.txt").write_text("opencode [project]\n--model string\n")
    (stub_dir / "claude-help.txt").write_text('--permission-mode <mode> (choices: "acceptEdits", "auto")\n')
    for cli in ("codex", "claude", "opencode"):
        path = stub_dir / cli
        path.write_text(stub)
        path.chmod(0o755)

    def run(script, config=None, *, overrides=None, args=()):
        # This .env exists only under pytest's temporary directory, never in the checkout.
        if config is not None:
            (repo / ".env").write_text(config)
        environment = {
            key: value for key, value in os.environ.items()
            if key not in SETTINGS and not key.startswith(("FILE_", "ANTHROPIC_", "CLAUDE_", "OPENCODE_"))
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
    assert child["args"][-8:] == ["--sandbox", "workspace-write", "--ask-for-approval", "never",
                                  "-m", "luna-test", "exec", "Reply with exactly: OK"]
    assert tomllib.loads(child["args"][5])["model_reasoning_effort"] == "medium"
    provider = tomllib.loads(child["args"][3])["model_providers"]["luna"]
    assert provider["base_url"] == "https://example.invalid/openai/v1"
    assert provider["wire_api"] == "responses"
    assert provider["requires_openai_auth"] is False
    assert child["env"][provider["env_key"]] == "dummy key=with equals"
    assert all("dummy key" not in arg for arg in child["args"])
    assert not any(key.startswith("FILE_") for key in child["env"])


@pytest.mark.parametrize("interface", ["v1", "v2"])
def test_opencode_reuses_luna_settings_without_putting_credentials_in_config(launch, interface):
    run, repo = launch
    if interface == "v2":
        (repo.parent / "cli" / "opencode-help.txt").write_text("opencode [directory]\n--standalone\n")
    result = run("opencode-luna", """
LLM_BASE_URL=https://example.invalid/openai/v1
LLM_API_KEY='dummy key="quoted" with equals='
LUNA_DEPLOYMENT=workshop-deployment
""", overrides={"OPENCODE_CONFIG_CONTENT": '{"model":"other/model"}'},
        args=("run", "Reply with exactly: OK"))
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    assert child["cwd"] == str(repo)
    prefix = ["--model", "workshop-luna/luna"] if interface == "v1" else ["--standalone"]
    assert child["args"] == [*prefix, "run", "Reply with exactly: OK"]
    raw_config = child["env"]["OPENCODE_CONFIG_CONTENT"]
    config = json.loads(raw_config)
    assert config["model"] == "workshop-luna/luna"
    if interface == "v1":
        assert config["small_model"] == "workshop-luna/luna"
        assert config["enabled_providers"] == ["workshop-luna"]
        provider = config["provider"]["workshop-luna"]
        assert provider["npm"] == "@ai-sdk/openai"
        options = provider["options"]
        model = provider["models"]["luna"]
        assert model["id"] == "{env:LUNA_DEPLOYMENT}"
        model_options = model["options"]
        assert model_options["store"] is False
    else:
        assert "--model" not in child["args"]
        provider = config["providers"]["workshop-luna"]
        assert provider["package"] == "@opencode/ai/providers/openai/responses"
        options = provider["settings"]
        model = provider["models"]["luna"]
        assert model["modelID"] == "{env:LUNA_DEPLOYMENT}"
        model_options = model["settings"]
        assert model["body"]["store"] is False
        assert config["policies"] == [
            {"action": "provider.use", "resource": "*", "effect": "deny"},
            {"action": "provider.use", "resource": "workshop-luna", "effect": "allow"},
        ]
    assert options["baseURL"] == "{env:LUNA_OPENAI_BASE_URL}"
    assert options["apiKey"] == "{env:AZURE_FOUNDRY_API_KEY}"
    assert child["env"]["LUNA_OPENAI_BASE_URL"] == "https://example.invalid/openai/v1"
    assert child["env"]["AZURE_FOUNDRY_API_KEY"] == 'dummy key="quoted" with equals='
    assert child["env"]["LUNA_DEPLOYMENT"] == "workshop-deployment"
    assert model_options["reasoningEffort"] == "medium"
    assert all("dummy key" not in value for value in [raw_config, *child["args"]])
    assert not any(key.startswith("FILE_") for key in child["env"])
    assert not (repo / "opencode.json").exists()


def test_opencode_v2_starts_interactively_without_the_removed_model_flag(launch):
    run, repo = launch
    (repo.parent / "cli" / "opencode-help.txt").write_text("opencode [directory]\n--standalone\n")
    result = run("opencode-luna", """
LLM_BASE_URL=https://example.invalid/openai/v1
LLM_API_KEY=dummy-key
LUNA_DEPLOYMENT=luna-test
""")
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    assert child["args"] == ["--standalone"]
    assert json.loads(child["env"]["OPENCODE_CONFIG_CONTENT"])["model"] == "workshop-luna/luna"


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
        "CLAUDE_CODE_EFFORT_LEVEL": "high",
    }, args=("-p", "Reply with exactly: OK"))
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    assert child["args"][0] == "--settings"
    assert child["args"][2:] == ["--effort", "medium", "--permission-mode", "auto", "-p", "Reply with exactly: OK"]
    # Claude applies saved settings after the shell environment. CLI settings
    # must also pin the provider to override a saved Bedrock/Vertex selection.
    provider_settings = json.loads(child["args"][1])["env"]
    assert provider_settings["CLAUDE_CODE_USE_FOUNDRY"] == "1"
    assert provider_settings["CLAUDE_CODE_EFFORT_LEVEL"] == ""
    for key in (
        "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_MANTLE", "CLAUDE_CODE_USE_ANTHROPIC_AWS",
    ):
        assert provider_settings[key] == ""
    assert all("dummy-" not in arg for arg in child["args"])
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
        "CLAUDE_CODE_EFFORT_LEVEL",
    ):
        assert key not in environment


def test_haiku_auto_mode_falls_back_to_accept_edits(launch):
    run, repo = launch
    (repo.parent / "cli" / "claude-help.txt").write_text('--permission-mode <mode> (choices: "acceptEdits")\n')
    result = run("claude-haiku", """
LLM_API_KEY=dummy-key
LLM_BASE_URL=https://example.invalid/openai/v1
LUNA_DEPLOYMENT=luna-test
HAIKU_ANTHROPIC_BASE_URL=https://example.invalid/anthropic
HAIKU_DEPLOYMENT=haiku-test
""", args=("-p", "OK"))
    assert result.returncode == 0, result.stderr
    args = json.loads(result.stdout)["args"]
    start = args.index("--permission-mode")
    assert args[start:start + 2] == ["--permission-mode", "acceptEdits"]


def test_codex_sandbox_can_write_the_uv_cache(launch):
    run, repo = launch
    uv = repo.parent / "cli" / "uv"
    uv.write_text("#!/bin/sh\necho '/home/participant/.cache/uv'\n")
    uv.chmod(0o755)
    result = run("codex-luna", """
LLM_API_KEY=dummy-key
LLM_BASE_URL=https://example.invalid/openai/v1
LUNA_DEPLOYMENT=luna-test
""", args=("exec", "OK"))
    assert result.returncode == 0, result.stderr
    args = json.loads(result.stdout)["args"]
    roots = args[args.index("never") + 2]
    assert args[args.index("never") + 1] == "-c"
    assert tomllib.loads(roots)["sandbox_workspace_write"]["writable_roots"] == ["/home/participant/.cache/uv"]


@pytest.mark.parametrize("script", ["codex-luna", "claude-haiku"])
def test_auto_mode_can_be_turned_off(launch, script):
    run, _ = launch
    result = run(script, """
LLM_API_KEY=dummy-key
LLM_BASE_URL=https://example.invalid/openai/v1
LUNA_DEPLOYMENT=luna-test
HAIKU_ANTHROPIC_BASE_URL=https://example.invalid/anthropic
HAIKU_DEPLOYMENT=haiku-test
""", overrides={"ASSISTANT_AUTO": "0"}, args=("-p", "OK"))
    assert result.returncode == 0, result.stderr
    args = json.loads(result.stdout)["args"]
    assert not {"--sandbox", "--ask-for-approval", "--permission-mode"} & set(args)


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
    ("opencode-luna", "LUNA_OPENAI_BASE_URL"),
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


def test_haiku_skips_old_native_installation_for_newer_cli_on_path(launch):
    run, repo = launch
    native = repo.parent / "cli"
    (native / "version.txt").write_text("2.1.92 (Claude Code)\n")
    homebrew = repo.parent / "homebrew with spaces"
    homebrew.mkdir()
    shutil.copy2(native / "claude", homebrew / "claude")
    shutil.copy2(native / "claude-help.txt", homebrew / "claude-help.txt")
    (homebrew / "version.txt").write_text("2.1.308 (Claude Code)\n")
    result = run("claude-haiku", """
LLM_API_KEY=dummy-key
HAIKU_ANTHROPIC_BASE_URL=https://example.invalid/anthropic
HAIKU_DEPLOYMENT=claude-haiku-5-5
""", overrides={"PATH": f"{native}:{homebrew}:/usr/bin:/bin"}, args=("-p", "OK"))
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    assert child["executable"] == str(homebrew / "claude")
    assert child["args"][2:] == ["--effort", "medium", "--permission-mode", "auto", "-p", "OK"]
    assert "skipped older Claude" in result.stderr


@pytest.mark.parametrize("version", ["2.1.92", "2.1.292"])
def test_haiku_rejects_unsupported_cli_before_loading_configuration(launch, version):
    run, repo = launch
    cli = repo.parent / "cli"
    (cli / "version.txt").write_text(f"{version} (Claude Code)\n")
    result = run("claude-haiku")
    assert result.returncode != 0
    assert not result.stdout
    assert "2.1.293 or later" in result.stderr
    assert str(cli / "claude") in result.stderr


def test_haiku_version_works_without_credentials_at_minimum_supported_version(launch):
    run, repo = launch
    (repo.parent / "cli" / "version.txt").write_text("2.1.293 (Claude Code)\n")
    result = run("claude-haiku", args=("--version",))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2.1.293 (Claude Code)"


@pytest.mark.parametrize("script", ["codex-luna", "claude-haiku", "opencode-luna"])
def test_participant_setup_from_current_template(launch, script):
    run, _ = launch
    template = TEMPLATE.read_text()
    defaults = dotenv_values(TEMPLATE, interpolate=False)
    config = template.replace("LLM_API_KEY=", "LLM_API_KEY=dummy-template-key", 1)
    if script in ("codex-luna", "opencode-luna"):
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
    elif script == "opencode-luna":
        assert child["env"]["LUNA_OPENAI_BASE_URL"] == "https://example.invalid/openai/v1"
        assert child["env"]["AZURE_FOUNDRY_API_KEY"] == "dummy-template-key"
        assert child["env"]["LUNA_DEPLOYMENT"] == defaults["LUNA_DEPLOYMENT"]
    else:
        assert child["env"]["ANTHROPIC_FOUNDRY_API_KEY"] == "dummy-template-key"
        assert child["env"]["ANTHROPIC_MODEL"] == defaults["HAIKU_DEPLOYMENT"]


@pytest.mark.parametrize("script", ["codex-luna", "opencode-luna"])
def test_luna_launchers_use_explicit_assistant_endpoint_and_key(launch, script):
    run, _ = launch
    result = run(script, """
LLM_BASE_URL=https://app.invalid/openai/v1
LLM_API_KEY=dummy-app-key
AZURE_FOUNDRY_API_KEY=dummy-assistant-key
LUNA_OPENAI_BASE_URL=https://assistant.invalid/openai/v1
LUNA_DEPLOYMENT=assistant-deployment
""")
    assert result.returncode == 0, result.stderr
    child = json.loads(result.stdout)
    if script == "codex-luna":
        provider = tomllib.loads(child["args"][3])["model_providers"]["luna"]
        assert provider["base_url"] == "https://assistant.invalid/openai/v1"
        assert child["env"][provider["env_key"]] == "dummy-assistant-key"
        assert child["args"][-1] == "assistant-deployment"
    else:
        assert child["env"]["LUNA_OPENAI_BASE_URL"] == "https://assistant.invalid/openai/v1"
        assert child["env"]["AZURE_FOUNDRY_API_KEY"] == "dummy-assistant-key"
        assert child["env"]["LUNA_DEPLOYMENT"] == "assistant-deployment"


@pytest.mark.parametrize("script, cli", [
    ("codex-luna", "codex"), ("claude-haiku", "claude"), ("opencode-luna", "opencode"),
])
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
