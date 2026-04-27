"""Session state: code style, original prompt, phases, sprints, todos."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Todo:
    id: str
    text: str
    phase: str | None = None
    sprint: str | None = None
    created_at: str = field(default_factory=_now)
    completed_at: str | None = None


@dataclass
class Sprint:
    name: str
    phase: str | None = None
    status: str = "active"  # active | complete
    started_at: str = field(default_factory=_now)
    ended_at: str | None = None
    notes: str = ""


@dataclass
class ContextSource:
    path: str
    label: str
    bytes_: int
    cached_at: str = field(default_factory=_now)


@dataclass
class State:
    code_style: str = ""
    original_prompt: str = ""
    current_phase: str = ""
    current_sprint: str = ""
    todos: list[Todo] = field(default_factory=list)
    completed: list[Todo] = field(default_factory=list)
    sprints: list[Sprint] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    context_sources: list[ContextSource] = field(default_factory=list)
    session_input_tokens: int = 0
    session_output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    last_handoff_path: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def add_todo(self, text: str) -> Todo:
        todo = Todo(
            id=_new_id(),
            text=text,
            phase=self.current_phase or None,
            sprint=self.current_sprint or None,
        )
        self.todos.append(todo)
        return todo

    def complete_todo(self, todo_id: str) -> Todo | None:
        for i, todo in enumerate(self.todos):
            if todo.id == todo_id or todo.id.startswith(todo_id):
                todo.completed_at = _now()
                self.completed.append(todo)
                self.todos.pop(i)
                return todo
        return None

    def start_sprint(self, name: str, phase: str | None = None) -> Sprint:
        for sprint in self.sprints:
            if sprint.status == "active":
                sprint.status = "complete"
                sprint.ended_at = _now()
        sprint = Sprint(name=name, phase=phase or self.current_phase or None)
        self.sprints.append(sprint)
        self.current_sprint = name
        if phase:
            self.set_phase(phase)
        return sprint

    def complete_sprint(self, notes: str = "") -> Sprint | None:
        for sprint in reversed(self.sprints):
            if sprint.status == "active":
                sprint.status = "complete"
                sprint.ended_at = _now()
                if notes:
                    sprint.notes = notes
                self.current_sprint = ""
                return sprint
        return None

    def set_phase(self, phase: str) -> None:
        if phase and phase not in self.phases:
            self.phases.append(phase)
        self.current_phase = phase

    def add_context_source(self, path: str, label: str, bytes_: int) -> ContextSource:
        for source in self.context_sources:
            if source.path == path:
                source.bytes_ = bytes_
                source.cached_at = _now()
                return source
        source = ContextSource(path=path, label=label, bytes_=bytes_)
        self.context_sources.append(source)
        return source

    def record_usage(self, usage: Any) -> None:
        self.session_input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.session_output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_creation_tokens += (
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["todos"] = [asdict(t) for t in self.todos]
        d["completed"] = [asdict(t) for t in self.completed]
        d["sprints"] = [asdict(s) for s in self.sprints]
        d["context_sources"] = [asdict(c) for c in self.context_sources]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> State:
        todos = [Todo(**t) for t in data.get("todos", [])]
        completed = [Todo(**t) for t in data.get("completed", [])]
        sprints = [Sprint(**s) for s in data.get("sprints", [])]
        context_sources = [
            ContextSource(**c) for c in data.get("context_sources", [])
        ]
        keep = {
            k: v
            for k, v in data.items()
            if k
            not in {"todos", "completed", "sprints", "context_sources"}
        }
        return cls(
            todos=todos,
            completed=completed,
            sprints=sprints,
            context_sources=context_sources,
            **keep,
        )


class StateStore:
    """Persist State as JSON in `.ccc/state.json`."""

    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root).resolve()
        self.dir = self.root / ".ccc"
        self.path = self.dir / "state.json"
        self.handoffs_dir = self.dir / "handoffs"

    def exists(self) -> bool:
        return self.path.exists()

    def init(self) -> State:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.handoffs_dir.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            return self.load()
        state = State()
        self.save(state)
        return state

    def load(self) -> State:
        if not self.path.exists():
            raise FileNotFoundError(
                f"No state at {self.path}. Run `ccc init` first."
            )
        with self.path.open("r", encoding="utf-8") as f:
            return State.from_dict(json.load(f))

    def save(self, state: State) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        state.updated_at = _now()
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)
