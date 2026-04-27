from __future__ import annotations

from ccc.compact import (
    DEFAULT_THRESHOLD_TOKENS,
    session_token_estimate,
    should_compact,
)
from ccc.state import State


def test_should_compact_below_threshold():
    state = State()
    state.session_input_tokens = 1000
    assert not should_compact(state)


def test_should_compact_at_threshold():
    state = State()
    state.session_input_tokens = DEFAULT_THRESHOLD_TOKENS
    assert should_compact(state)


def test_session_token_estimate_sums_all_counters():
    state = State(
        session_input_tokens=100,
        session_output_tokens=200,
        cache_read_tokens=300,
        cache_creation_tokens=400,
    )
    assert session_token_estimate(state) == 1000
