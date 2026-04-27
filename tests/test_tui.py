"""Smoke tests for the optional Textual TUI.

The whole module is skipped if `textual` is not installed — the TUI is
opt-in (`pip install -e ".[tui]"`). The tests exercise mount, tab
switching, and the on-disk state mutations driven by the UI handlers.
"""

from __future__ import annotations

import pytest

textual = pytest.importorskip("textual")

from ccc.state import StateStore  # noqa: E402
from ccc.tui import build_app  # noqa: E402


@pytest.mark.asyncio
async def test_app_mounts_with_empty_state(tmp_path) -> None:
    """The app must mount the five tabs and the header bar even before `ccc init`."""
    app = build_app(str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        # Header bar exists.
        assert app.query_one("#hdr") is not None
        # Five tab panes are present.
        from textual.widgets import TabbedContent
        tabs = app.query_one(TabbedContent)
        pane_ids = {pane.id for pane in tabs.query("TabPane")}
        assert pane_ids == {"status", "todos", "sources", "ask", "handoffs"}


@pytest.mark.asyncio
async def test_add_todo_via_ui(tmp_path) -> None:
    StateStore(str(tmp_path)).init()
    app = build_app(str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2")  # tab: todos
        await pilot.pause()
        # Find the todo input by id and stuff text into it.
        inp = app.query_one("#todo-input")
        inp.value = "first todo from the TUI"
        await pilot.click("#todo-add")
        await pilot.pause()
    # Persisted on disk.
    state = StateStore(str(tmp_path)).load()
    assert any(t.text == "first todo from the TUI" for t in state.todos)


@pytest.mark.asyncio
async def test_tab_switching(tmp_path) -> None:
    StateStore(str(tmp_path)).init()
    app = build_app(str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        for key, expected in (
            ("1", "status"),
            ("2", "todos"),
            ("3", "sources"),
            ("4", "ask"),
            ("5", "handoffs"),
        ):
            await pilot.press(key)
            await pilot.pause()
            from textual.widgets import TabbedContent
            assert app.query_one(TabbedContent).active == expected
