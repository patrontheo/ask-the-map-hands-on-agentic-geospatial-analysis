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

## Exercise scope and waiting

Keep the app running in its own terminal and use a second terminal for the coding
assistant. Give it the business goal, ask for a short plan, review the screening
rules, then implement the minimum path. Use the current checkout; checkpoint
recovery is facilitator-assisted after saving your work.

For Step 2, ask for the completed-response viewer first. Keep live updates,
pricing research and broad redesign outside the core task. Once event order,
older-response ownership, keyboard access and empty/error cases work, stop coding
and inspect the results. You can continue in the same coding conversation.

Organisers should prepare one compatible browser workflow before the event so
coding time is not spent installing or switching browser tools. Keep command and
snapshot output focused. Use the waiting time to review the plan, inspect a
boundary case or identify the fields connecting a call and result.

The app's `LLM_REASONING_EFFORT` does not configure the coding assistant. Organisers
can benchmark low coding reasoning against the current default using:

```bash
coding-assistant/bin/codex-luna -c 'model_reasoning_effort="low"'
```

This is a benchmark candidate, not an established speed improvement. Retain the
setting that completes the exercise correctly with fewer interventions. A 429
needs deployment-specific evidence and capacity checks; extra keys and repeated
retries do not establish more available capacity. Ask a facilitator if blocked.
