from dataclasses import dataclass, field

from backend.app.data import Bundle
from backend.app.tools.registry import ToolContext


@dataclass
class Session:
    id: str
    ctx: ToolContext
    history: list = field(default_factory=list)
    turns: list[dict] = field(default_factory=list)

    def next_turn_id(self) -> str:
        return f"t_{len(self.turns) + 1:04d}"


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str, bundle: Bundle) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id, ToolContext(bundle))
        return self._sessions[session_id]

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
