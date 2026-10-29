# Coding assistant

Use Codex CLI (Luna), Claude Code (Haiku), or OpenCode (Luna) with the workshop endpoints.
No personal subscription is required.

## Setup

Install [Codex CLI](https://developers.openai.com/codex/cli/),
[Claude Code](https://code.claude.com/docs/en/setup), or
[OpenCode](https://opencode.ai/docs/). Choose one.
Use Bash on macOS/Linux, or WSL on Windows.

The launcher supports OpenCode 1 and 2 and was tested with **1.19.5** and
**2.2.1** (`opencode --version`). It detects the installed command interface.

Haiku 5.5 requires Claude Code **2.1.293 or later**. Check with `claude --version`.
For a Homebrew installation, update with `brew upgrade --cask claude-code`;
for a native installation, use `claude update`, then restart the launcher.
Older versions can send `thinking.type.enabled`, which Haiku 5.5 rejects because
it uses adaptive thinking.

If several Claude installations are on PATH, the launcher uses the first one
that supports Haiku 5.5 and reports when it skips an older one. Check the selected
version with `coding-assistant/bin/claude-haiku --version`. For example, an old
`~/.local/bin/claude` can shadow an updated Homebrew installation. Use
`type -a claude` to list your installations; to prefer Homebrew for one launch:

```bash
PATH="/opt/homebrew/bin:$PATH" coding-assistant/bin/claude-haiku
```

From the repository root, create `.env` if you haven't already done so for the app:

```bash
cp .example.env .env
```

Fill in `LLM_API_KEY` and your chosen assistant's settings using the values
provided by the organisers. The app and coding assistants share this key.

| Assistant | Settings in `.env` |
|-----------|-------------------|
| Codex / Luna | `LUNA_DEPLOYMENT` and `LUNA_OPENAI_BASE_URL` |
| OpenCode / Luna | `LUNA_DEPLOYMENT` and `LUNA_OPENAI_BASE_URL` |
| Claude Code / Haiku | `HAIKU_DEPLOYMENT` and `HAIKU_ANTHROPIC_BASE_URL` |

For Luna, use a base URL ending in `/openai/v1`, or leave it blank to reuse
`LLM_BASE_URL`. For Haiku, use a base URL ending in `/anthropic`;
Claude Code adds `/v1/messages` itself.

Keep your filled `.env` local; don't commit it.

## Start

From the repository root, run your chosen assistant:

```bash
coding-assistant/bin/codex-luna
# Or:
coding-assistant/bin/claude-haiku
# Or:
coding-assistant/bin/opencode-luna
```

Ask it to reply with `OK` to check the connection, then use it for the exercises.
Use these launchers each time you want to connect through the workshop endpoints.

All launchers start with **medium reasoning effort**. To use a different level
for one session, pass an explicit override:

```bash
coding-assistant/bin/claude-haiku --effort high
coding-assistant/bin/codex-luna -c 'model_reasoning_effort="high"'
# OpenCode 1:
coding-assistant/bin/opencode-luna run --variant high "Explain this codebase"
# OpenCode 2:
coding-assistant/bin/opencode-luna run --model 'workshop-luna/luna#high' "Explain this codebase"
```

OpenCode reuses the Codex/Luna endpoint and deployment settings and connects via
the Responses API. The launcher supplies its provider configuration for the
session; you do not need `/connect` or an `opencode.json` file. To check the
connection without opening the interactive interface, run:

```bash
coding-assistant/bin/opencode-luna run "Reply with exactly: OK"
```

OpenCode 2 sessions start with a private server so they receive the launcher's
endpoint and key, even if a background OpenCode server is already running. The
launcher selects the model through configuration because OpenCode 2 no longer
accepts `--model` on its interactive root command.

The Haiku launcher selects Microsoft Foundry for its session, including when your
saved Claude settings select another provider. To check the connection settings,
run `/status` in Claude Code: the API provider should be **Microsoft Foundry** and
the base URL should match the workshop resource. A saved Bedrock provider can
otherwise cause `400 The provided model identifier is invalid` when given an
Azure deployment name.
