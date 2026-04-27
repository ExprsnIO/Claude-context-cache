"""Handoff document generation, validation, and persistence."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from ccc.state import State, StateStore

WORD_LIMIT = 750

REQUIRED_SECTIONS = (
    "## Code Style",
    "## Original Prompt / Current Phase",
    "## Completed Results",
    "## To-Do",
    "## Sprints / Phases for Next Context Window",
)


def count_words(text: str) -> int:
    """Word count that ignores Markdown fences and code-block lines."""
    in_code = False
    words = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        words += len(re.findall(r"\b\w+\b", line))
    return words


def validate(text: str) -> list[str]:
    """Return a list of validation problems. Empty list = doc is good."""
    problems: list[str] = []
    wc = count_words(text)
    if wc > WORD_LIMIT:
        problems.append(f"word count {wc} exceeds limit of {WORD_LIMIT}")
    for section in REQUIRED_SECTIONS:
        if section not in text:
            problems.append(f"missing required section: {section!r}")
    return problems


def truncate_to_limit(text: str, limit: int = WORD_LIMIT) -> str:
    """Trim trailing lines until the document is under the word limit."""
    if count_words(text) <= limit:
        return text
    lines = text.splitlines()
    while lines and count_words("\n".join(lines)) > limit:
        lines.pop()
    return "\n".join(lines).rstrip() + "\n"


def write_handoff(store: StateStore, text: str, label: str = "") -> Path:
    """Persist a handoff document under `.ccc/handoffs/` and return the path."""
    store.handoffs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{label}" if label else ""
    path = store.handoffs_dir / f"handoff-{stamp}{suffix}.md"
    path.write_text(text, encoding="utf-8")
    return path


def parse_handoff(text: str) -> dict[str, str]:
    """Split a handoff document into a {section: body} map."""
    sections: dict[str, str] = {}
    current_key: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_key is not None:
                sections[current_key] = "\n".join(buffer).strip()
            current_key = line[3:].strip()
            buffer = []
        elif current_key is not None:
            buffer.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(buffer).strip()
    return sections


def hydrate_state_from_handoff(text: str, state: State) -> State:
    """Reload a State from a previously-written handoff document.

    Only fills empty fields; never overwrites live state.
    """
    sections = parse_handoff(text)

    if not state.code_style:
        state.code_style = sections.get("Code Style", "")

    op_section = sections.get("Original Prompt / Current Phase", "")
    if not state.original_prompt and op_section:
        first_para = op_section.split("\n\n", 1)[0].strip()
        state.original_prompt = first_para

    todo_section = sections.get("To-Do", "")
    if todo_section and not state.todos:
        for line in todo_section.splitlines():
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")):
                state.add_todo(stripped[2:].strip())

    return state
