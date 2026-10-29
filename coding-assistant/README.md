# Coding assistant

Use Codex CLI (Luna) or Claude Code (Haiku) with the workshop endpoints.
No personal subscription is required.

## Setup

Install [Codex CLI](https://developers.openai.com/codex/cli/) or
[Claude Code](https://code.claude.com/docs/en/setup). Choose one.
Use Bash on macOS/Linux, or WSL on Windows.

From the repository root, create `.env` if you haven't already done so for the app:

```bash
cp .example.env .env
```

Fill in `LLM_API_KEY` and your chosen assistant's settings using the values
provided by the organisers. The app and both assistants share this key.

| Assistant | Settings in `.env` |
|-----------|-------------------|
| Codex / Luna | `LUNA_DEPLOYMENT` and `LUNA_OPENAI_BASE_URL` |
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
```

Ask it to reply with `OK` to check the connection, then use it for the exercises.
Use these launchers each time you want to connect through the workshop endpoints.
