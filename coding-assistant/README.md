# Coding assistants for the workshop

Use the workshop's Azure AI Foundry endpoints with Codex CLI (Luna) or Claude
Code (Haiku) if you don't have a coding assistant subscription. Choose one;
you don't need to install both. The organisers provide the endpoints, deployment
names and API key privately.

## Setup

1. Install your preferred CLI using the official instructions:
   [Codex CLI](https://developers.openai.com/codex/cli/) or
   [Claude Code](https://code.claude.com/docs/en/setup).
   Check that `codex --version` or `claude --version` works in your terminal.
   The launchers below require Bash (macOS/Linux, or WSL on Windows).
2. From the repository root, copy the template **once**, unless you already have
   a `.env` for the workshop app:

   ```bash
   cp .example.env .env
   ```

3. Fill in the app's `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`, then complete
   the coding assistant section for your chosen CLI:

   | Assistant | Settings in the root `.env` |
   |-----------|----------------------------|
   | Codex / Luna | `LUNA_DEPLOYMENT`; `LUNA_OPENAI_BASE_URL` only if different from `LLM_BASE_URL` |
   | Claude Code / Haiku | `HAIKU_ANTHROPIC_BASE_URL` and `HAIKU_DEPLOYMENT` |

   Both launchers reuse `LLM_API_KEY`. Set `AZURE_FOUNDRY_API_KEY` only if the
   coding assistants need a different key from the app. Confirm deployment names
   with the organisers; they are Azure deployment names, not CLI model aliases.

   For Codex, use the full resource-level OpenAI base URL ending in `/openai/v1`,
   rather than a Foundry project URL or a URL ending in `/responses`.
   For Claude Code, use the Foundry base URL ending in `/anthropic`.
   Claude Code appends `/v1/messages` when sending a Messages request. If the
   organisers give you the complete endpoint ending in `/anthropic/v1/messages`,
   remove `/v1/messages` before filling `HAIKU_ANTHROPIC_BASE_URL`.
   No API-version setting is needed by these launchers.

4. Run one quick connection check from the repository root:

   ```bash
   coding-assistant/bin/codex-luna exec "Reply with exactly: OK"
   # Or, for Claude Code:
   coding-assistant/bin/claude-haiku -p "Reply with exactly: OK"
   ```

   This sends a model request and uses the workshop's API allowance.

## Use during the exercises

Start an interactive session with your chosen assistant:

```bash
coding-assistant/bin/codex-luna
# Or:
coding-assistant/bin/claude-haiku
```

Use the launcher each time you want to use the workshop endpoint. Arguments are
passed through to the CLI. Both launchers work from any directory and start the
assistant in this repository. They configure only the child process, so no edits
to your global Codex or Claude Code settings are needed.

In Claude Code, `/status` should show Microsoft Foundry and your Haiku deployment.
All Claude model aliases and subagents use that deployment. Codex uses a custom
`luna` provider with the Responses API and the configured deployment name.
See the official [Codex provider configuration](https://developers.openai.com/codex/config-advanced/#custom-model-providers)
and [Claude Code on Microsoft Foundry](https://code.claude.com/docs/en/microsoft-foundry)
for details.

## One configuration file

The app and launchers use the root `.env`, copied from the root `.example.env`.
There are no separate assistant config or secrets files. The launchers read
literal `KEY=VALUE` lines, with optional surrounding quotes and whitespace;
they never execute the file or expand `$VARIABLE` references. Put comments on
their own lines. Nonempty exported settings take precedence over `.env` values.
Only the chosen assistant's settings are required.

Endpoint URLs and keys are deliberately blank in the public template. Keep the
filled `.env` local; it is ignored by Git. The launchers don't display keys or
put them in command-line arguments.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Missing setting | Fill the named field in the root `.env`; don't overwrite an existing `.env` when copying the template. |
| CLI not found | Install the chosen CLI and make sure its version command works in the same terminal. |
| 401 / 403 | Check the key and that it belongs to the resource hosting the deployment. |
| 404 / deployment not found | Check the full API base URL and deployment name with the organisers. |
| Connection timeout | Confirm your network/proxy allows access to the endpoint supplied by the organisers. |
| Claude uses another provider | Check `/status`; an `env` block in local or managed Claude settings can override the launcher. |
| Claude model not allowed | Ask your administrator whether managed `availableModels` permits the deployment. |
| 429 / rate limit | Wait and retry; the shared deployment has a workshop usage allowance. |
