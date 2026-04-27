from __future__ import annotations

from ccc.state import State, StateStore


def test_state_round_trip(tmp_path):
    store = StateStore(tmp_path)
    state = store.init()
    state.original_prompt = "Build a thing"
    state.code_style = "- 4 spaces\n- type hints"
    state.set_phase("MVP")
    state.start_sprint("scaffolding", phase="MVP")
    todo = state.add_todo("write tests")
    state.add_todo("ship CLI")
    state.complete_todo(todo.id)
    store.save(state)

    reloaded = store.load()
    assert reloaded.original_prompt == "Build a thing"
    assert reloaded.current_phase == "MVP"
    assert reloaded.current_sprint == "scaffolding"
    assert len(reloaded.todos) == 1
    assert len(reloaded.completed) == 1
    assert reloaded.completed[0].text == "write tests"


def test_complete_todo_by_prefix():
    state = State()
    todo = state.add_todo("first")
    state.add_todo("second")
    completed = state.complete_todo(todo.id[:3])
    assert completed is not None
    assert completed.text == "first"
    assert len(state.todos) == 1


def test_start_sprint_closes_active():
    state = State()
    a = state.start_sprint("alpha", phase="MVP")
    state.start_sprint("beta", phase="MVP")
    assert a.status == "complete"
    assert state.current_sprint == "beta"


def test_record_usage_accumulates():
    state = State()

    class Usage:
        input_tokens = 100
        output_tokens = 50
        cache_read_input_tokens = 200
        cache_creation_input_tokens = 0

    state.record_usage(Usage())
    state.record_usage(Usage())
    assert state.session_input_tokens == 200
    assert state.session_output_tokens == 100
    assert state.cache_read_tokens == 400
