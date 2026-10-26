"""Foundry spike: one tool-calling turn on the test fixture. Run: uv run python scripts/spike_llm.py ["question"]"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run by path: make the repo root importable

import backend.app.tools  # noqa: F401
from backend.app.agent.loop import run_turn
from backend.app.data import load_bundle
from backend.app.tools.registry import TOOLS, ToolContext
from tests.conftest import FIXTURE_DIR

for spec in TOOLS.values():  # the spike tests the tool loop, so register everything (step-00 ships them unregistered)
    spec.registered = True

question = sys.argv[1] if len(sys.argv) > 1 else (
    "Which sites are in the flood footprint, and which companies have the highest exposed TIV there?")

start = time.perf_counter()
turn = run_turn(question, ToolContext(load_bundle(FIXTURE_DIR)), history=[], turn_id="t_spike")
for e in turn.trace:
    p = e["payload"]
    detail = {"tool_call": lambda: f"{p['tool']}({p['args']})",
              "tool_result": lambda: f"{p['status']}: {p['summary']}",
              "llm_response": lambda: f"{len(p['function_calls'])} call(s), usage={p['usage']}",
              "error": lambda: p["message"]}.get(e["type"], lambda: "")()
    print(f"{e['seq']:>2} {e['type']:<17} {e['duration_ms'] or '':>8} {detail}")
print(f"\nAnswer ({time.perf_counter() - start:.1f}s): {turn.reply}")
