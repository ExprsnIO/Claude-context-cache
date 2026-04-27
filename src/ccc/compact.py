"""Auto-compact: emit a handoff and reset the live conversation state when
token usage approaches a threshold."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ccc.client import generate_handoff
from ccc.handoff import truncate_to_limit, validate, write_handoff
from ccc.state import State, StateStore

DEFAULT_THRESHOLD_TOKENS = 150_000


def session_token_estimate(state: State) -> int:
    """Conservative estimate of tokens consumed in this session.

    Cache reads are billed at ~10% but still pressure the context window;
    count them at full weight for the compaction trigger.
    """
    return (
        state.session_input_tokens
        + state.session_output_tokens
        + state.cache_read_tokens
        + state.cache_creation_tokens
    )


def should_compact(state: State, threshold: int = DEFAULT_THRESHOLD_TOKENS) -> bool:
    return session_token_estimate(state) >= threshold


def compact(
    store: StateStore,
    state: State,
    *,
    threshold: int = DEFAULT_THRESHOLD_TOKENS,
    force: bool = False,
    project_root: Path | str | None = None,
) -> tuple[Path, State] | None:
    """Generate a handoff document and reset volatile session counters.

    Returns (handoff_path, new_state) if compaction ran; None if it was skipped.
    The persisted state keeps todos, completed items, sprints, phases, code
    style, and the original prompt — those are durable across context windows.
    Only the per-session token counters and the cache-read counter are reset.
    """
    if not force and not should_compact(state, threshold):
        return None

    text, usage = generate_handoff(state, project_root=project_root)
    state.record_usage(usage)
    text = truncate_to_limit(text)
    problems = validate(text)
    if problems:
        # Write anyway so the user can inspect, but flag in the filename.
        path = write_handoff(store, text, label="needs-review")
    else:
        path = write_handoff(store, text, label="auto")

    new_state = replace(
        state,
        session_input_tokens=0,
        session_output_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        last_handoff_path=str(path),
    )
    store.save(new_state)
    return path, new_state
