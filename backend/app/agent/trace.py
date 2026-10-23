import json
import logging
import time
from datetime import datetime, timezone

log = logging.getLogger("trace")


class Trace:
    """Ordered, backend-recorded execution events for one chat turn."""

    def __init__(self, turn_id: str):
        self.turn_id = turn_id
        self.events: list[dict] = []

    def emit(self, type_: str, payload: dict, duration_ms: float | None = None) -> dict:
        event = {
            "turn_id": self.turn_id,
            "seq": len(self.events) + 1,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "type": type_,
            "duration_ms": None if duration_ms is None else round(duration_ms, 1),
            "payload": payload,
        }
        self.events.append(event)
        log.info(json.dumps(event, default=str))
        return event


class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = (time.perf_counter() - self.start) * 1000
