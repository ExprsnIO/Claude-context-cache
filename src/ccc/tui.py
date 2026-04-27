"""Optional Textual-based TUI for the `ccc` workspace.

This module is imported lazily by `ccc tui` so that the core CLI stays
zero-dependency aside from `anthropic`. The user opts in with:

    pip install -e ".[tui]"   # adds textual

Layout: a header showing phase/sprint/source counts, a TabbedContent with
five panes (Status, Todos, Sources, Ask, Handoffs), and a footer with
keybindings. Anthropic calls run on a worker thread so the UI stays
responsive; the per-call telemetry line is rendered inline in the Ask pane.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ccc.compact import (
    DEFAULT_THRESHOLD_TOKENS,
    compact,
    session_token_estimate,
)
from ccc.handoff import (
    WORD_LIMIT,
    count_words,
    truncate_to_limit,
    validate,
    write_handoff,
)
from ccc.state import State, StateStore

if TYPE_CHECKING:  # pragma: no cover
    from textual.app import ComposeResult


def _require_textual() -> Any:
    try:
        import textual  # noqa: F401
    except ImportError as exc:  # pragma: no cover - install path
        raise SystemExit(
            "The `ccc tui` command requires textual. Install with:\n"
            "    pip install -e \".[tui]\"\n"
            "or:\n"
            "    pip install textual"
        ) from exc
    return textual


def build_app(root: str | Path = ".") -> Any:
    """Construct the Textual app. Importable without textual for tests."""
    _require_textual()

    from textual import on
    from textual.app import App
    from textual.binding import Binding
    from textual.containers import Horizontal, VerticalScroll
    from textual.reactive import reactive
    from textual.widgets import (
        Button,
        DataTable,
        Footer,
        Header,
        Input,
        Label,
        Static,
        TabbedContent,
        TabPane,
        TextArea,
    )

    class HeaderBar(Static):
        """Top-of-screen status strip; re-rendered on every state change."""

        DEFAULT_CSS = """
        HeaderBar { height: 1; background: $boost; color: $text; padding: 0 1; }
        """

        def render_state(self, state: State, threshold: int) -> str:
            phase = state.current_phase or "—"
            sprint = state.current_sprint or "—"
            sources = len(state.context_sources)
            tokens = session_token_estimate(state)
            return (
                f"phase: [b]{phase}[/]  "
                f"sprint: [b]{sprint}[/]  "
                f"sources: [b]{sources}[/]  "
                f"tokens: [b]{tokens}[/]/{threshold}"
            )

    class CCCApp(App):  # type: ignore[misc]
        CSS = """
        Screen { layout: vertical; }
        #body { height: 1fr; }
        #ask-prompt { height: 7; border: tall $accent; }
        #ask-output { height: 1fr; border: tall $primary-darken-2; padding: 0 1; }
        #ask-usage { height: 1; color: $text-muted; }
        DataTable { height: 1fr; }
        .row { height: 3; }
        Input { width: 1fr; }
        Button { margin-left: 1; }
        """

        BINDINGS = [
            Binding("q", "quit", "quit"),
            Binding("r", "refresh", "refresh"),
            Binding("c", "compact", "compact"),
            Binding("h", "handoff", "handoff"),
            Binding("1", "show_tab('status')", "status"),
            Binding("2", "show_tab('todos')", "todos"),
            Binding("3", "show_tab('sources')", "sources"),
            Binding("4", "show_tab('ask')", "ask"),
            Binding("5", "show_tab('handoffs')", "handoffs"),
        ]

        store_root: reactive[str] = reactive(str(root))
        threshold: reactive[int] = reactive(DEFAULT_THRESHOLD_TOKENS)

        def __init__(self, root_path: str | Path = ".") -> None:
            super().__init__()
            self._store = StateStore(root_path)
            self._state: State = self._safe_load_state()

        def _safe_load_state(self) -> State:
            if self._store.exists():
                return self._store.load()
            # Don't auto-init from the TUI — the user may not want a
            # workspace here. Surface an empty state and let them act.
            return State()

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield HeaderBar(id="hdr")
            with TabbedContent(id="body", initial="status"):
                with TabPane("Status", id="status"):
                    yield VerticalScroll(Static(id="status-body"))
                with TabPane("Todos", id="todos"):
                    yield Horizontal(
                        Input(placeholder="new todo text", id="todo-input"),
                        Button("Add", id="todo-add", variant="primary"),
                        Button("Complete selected", id="todo-done"),
                        classes="row",
                    )
                    yield DataTable(id="todo-table", cursor_type="row")
                with TabPane("Sources", id="sources"):
                    yield Horizontal(
                        Input(placeholder="path to file or directory", id="src-input"),
                        Input(placeholder="label (optional)", id="src-label"),
                        Button("Cache", id="src-add", variant="primary"),
                        classes="row",
                    )
                    yield DataTable(id="src-table")
                with TabPane("Ask", id="ask"):
                    yield TextArea(
                        "",
                        id="ask-prompt",
                        language=None,
                        show_line_numbers=False,
                    )
                    yield Horizontal(
                        Button("Submit", id="ask-submit", variant="primary"),
                        Button("Clear", id="ask-clear"),
                        classes="row",
                    )
                    yield VerticalScroll(Static(id="ask-output"))
                    yield Label("", id="ask-usage")
                with TabPane("Handoffs", id="handoffs"):
                    yield Horizontal(
                        Button("Generate handoff", id="hd-generate", variant="primary"),
                        Button("Compact (auto)", id="hd-compact"),
                        Button("Compact --force", id="hd-compact-force"),
                        classes="row",
                    )
                    yield DataTable(id="hd-table")
            yield Footer()

        # ---- lifecycle -----------------------------------------------------

        def on_mount(self) -> None:
            for tid, cols in (
                ("todo-table", ("id", "text", "phase", "sprint")),
                ("src-table", ("label", "path", "bytes")),
                ("hd-table", ("file", "words", "label")),
            ):
                t = self.query_one(f"#{tid}", DataTable)
                t.add_columns(*cols)
            self._refresh_all()

        # ---- actions -------------------------------------------------------

        def action_refresh(self) -> None:
            self._state = self._safe_load_state()
            self._refresh_all()

        def action_show_tab(self, tab_id: str) -> None:
            self.query_one(TabbedContent).active = tab_id

        def action_compact(self) -> None:
            self._do_compact(force=False)

        def action_handoff(self) -> None:
            self._do_handoff()

        # ---- button handlers ----------------------------------------------

        @on(Button.Pressed, "#todo-add")
        def _add_todo(self) -> None:
            inp = self.query_one("#todo-input", Input)
            text = inp.value.strip()
            if not text or not self._store.exists():
                if not self._store.exists():
                    self.notify("Run `ccc init` first.", severity="warning")
                return
            self._state.add_todo(text)
            self._store.save(self._state)
            inp.value = ""
            self._refresh_all()

        @on(Button.Pressed, "#todo-done")
        def _complete_todo(self) -> None:
            table = self.query_one("#todo-table", DataTable)
            if not table.row_count:
                return
            row = table.cursor_row
            if row is None or row >= table.row_count:
                return
            todo_id = str(table.get_row_at(row)[0])
            todo = self._state.complete_todo(todo_id)
            if todo is None:
                self.notify(f"No todo {todo_id!r}", severity="warning")
                return
            self._store.save(self._state)
            self._refresh_all()

        @on(Button.Pressed, "#src-add")
        def _add_source(self) -> None:
            path_str = self.query_one("#src-input", Input).value.strip()
            label = self.query_one("#src-label", Input).value.strip()
            if not path_str:
                return
            if not self._store.exists():
                self.notify("Run `ccc init` first.", severity="warning")
                return
            path = Path(path_str).expanduser().resolve()
            if not path.exists():
                self.notify(f"{path} does not exist", severity="error")
                return
            size = (
                sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
                if path.is_dir()
                else path.stat().st_size
            )
            self._state.add_context_source(str(path), label or path.name, size)
            self._store.save(self._state)
            self.query_one("#src-input", Input).value = ""
            self.query_one("#src-label", Input).value = ""
            self._refresh_all()

        @on(Button.Pressed, "#ask-submit")
        def _ask_submit(self) -> None:
            prompt = self.query_one("#ask-prompt", TextArea).text.strip()
            if not prompt:
                return
            if not self._store.exists():
                self.notify("Run `ccc init` first.", severity="warning")
                return
            self.query_one("#ask-output", Static).update("[i]Calling Claude…[/]")
            self.query_one("#ask-usage", Label).update("")
            self.run_worker(self._ask_async(prompt), exclusive=True)

        @on(Button.Pressed, "#ask-clear")
        def _ask_clear(self) -> None:
            self.query_one("#ask-prompt", TextArea).text = ""
            self.query_one("#ask-output", Static).update("")
            self.query_one("#ask-usage", Label).update("")

        @on(Button.Pressed, "#hd-generate")
        def _gen_handoff(self) -> None:
            self._do_handoff()

        @on(Button.Pressed, "#hd-compact")
        def _do_compact_btn(self) -> None:
            self._do_compact(force=False)

        @on(Button.Pressed, "#hd-compact-force")
        def _do_compact_force_btn(self) -> None:
            self._do_compact(force=True)

        # ---- workers -------------------------------------------------------

        async def _ask_async(self, prompt: str) -> None:
            from ccc.cli import _format_usage_line  # reuse the CLI formatter
            from ccc.client import ask

            try:
                text, usage = await asyncio.to_thread(ask, self._state, prompt)
            except Exception as exc:  # noqa: BLE001 - surface any backend error
                self.query_one("#ask-output", Static).update(
                    f"[red]error:[/] {exc}"
                )
                return
            self._state.record_usage(usage)
            self._store.save(self._state)
            self.query_one("#ask-output", Static).update(text)
            self.query_one("#ask-usage", Label).update(_format_usage_line(usage))
            self._refresh_header()

        def _do_handoff(self) -> None:
            if not self._store.exists():
                self.notify("Run `ccc init` first.", severity="warning")
                return
            self.notify("Generating handoff…")
            self.run_worker(self._handoff_async(), exclusive=True)

        async def _handoff_async(self) -> None:
            from ccc.client import generate_handoff

            try:
                raw, usage = await asyncio.to_thread(
                    generate_handoff, self._state
                )
            except Exception as exc:  # noqa: BLE001
                self.notify(f"handoff failed: {exc}", severity="error")
                return
            self._state.record_usage(usage)
            text = truncate_to_limit(raw)
            problems = validate(text)
            label = "needs-review" if problems else "manual"
            path = write_handoff(self._store, text, label=label)
            self._state.last_handoff_path = str(path)
            self._store.save(self._state)
            words = count_words(text)
            self.notify(
                f"Handoff: {path.name} ({words}/{WORD_LIMIT} words"
                + (f", {len(problems)} problems" if problems else "")
                + ")",
                severity="warning" if problems else "information",
            )
            self._refresh_all()

        def _do_compact(self, *, force: bool) -> None:
            if not self._store.exists():
                self.notify("Run `ccc init` first.", severity="warning")
                return
            self.notify("Compacting…")
            self.run_worker(self._compact_async(force=force), exclusive=True)

        async def _compact_async(self, *, force: bool) -> None:
            try:
                result = await asyncio.to_thread(
                    compact,
                    self._store,
                    self._state,
                    threshold=int(self.threshold),
                    force=force,
                )
            except Exception as exc:  # noqa: BLE001
                self.notify(f"compact failed: {exc}", severity="error")
                return
            if result is None:
                self.notify(
                    f"Below threshold ({session_token_estimate(self._state)} "
                    f"< {self.threshold}). Use --force to compact anyway."
                )
                return
            path, new_state = result
            self._state = new_state
            self.notify(f"Compacted: {path.name}")
            self._refresh_all()

        # ---- rendering -----------------------------------------------------

        def _refresh_all(self) -> None:
            self._refresh_header()
            self._refresh_status()
            self._refresh_todos()
            self._refresh_sources()
            self._refresh_handoffs()

        def _refresh_header(self) -> None:
            hdr = self.query_one("#hdr", HeaderBar)
            hdr.update(hdr.render_state(self._state, int(self.threshold)))

        def _refresh_status(self) -> None:
            s = self._state
            tokens = session_token_estimate(s)
            lines = [
                f"[b]workspace[/]    {self._store.path}",
                f"[b]exists[/]       {self._store.exists()}",
                f"[b]phase[/]        {s.current_phase or '—'}",
                f"[b]sprint[/]       {s.current_sprint or '—'}",
                "",
                f"[b]original prompt[/]",
                f"  {s.original_prompt or '(unset)'}",
                "",
                f"[b]code style[/]",
                "  " + ("(none)" if not s.code_style else s.code_style.replace("\n", "\n  ")),
                "",
                f"[b]session tokens[/] {tokens}/{int(self.threshold)} "
                f"(input={s.session_input_tokens} output={s.session_output_tokens} "
                f"cache_read={s.cache_read_tokens} cache_creation={s.cache_creation_tokens})",
                f"[b]last handoff[/]  {s.last_handoff_path or '(none)'}",
            ]
            self.query_one("#status-body", Static).update("\n".join(lines))

        def _refresh_todos(self) -> None:
            t = self.query_one("#todo-table", DataTable)
            t.clear()
            for todo in self._state.todos:
                t.add_row(
                    todo.id,
                    todo.text,
                    todo.phase or "—",
                    todo.sprint or "—",
                )

        def _refresh_sources(self) -> None:
            t = self.query_one("#src-table", DataTable)
            t.clear()
            for src in self._state.context_sources:
                t.add_row(src.label, src.path, str(src.bytes_))

        def _refresh_handoffs(self) -> None:
            t = self.query_one("#hd-table", DataTable)
            t.clear()
            handoffs_dir = self._store.handoffs_dir
            if not handoffs_dir.exists():
                return
            for path in sorted(handoffs_dir.glob("handoff-*.md"), reverse=True):
                try:
                    body = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                label = "needs-review" if "needs-review" in path.name else "ok"
                t.add_row(path.name, str(count_words(body)), label)

    return CCCApp(root)


def run(root: str | Path = ".") -> int:
    """Entry point for `ccc tui`. Returns the app's exit code."""
    app = build_app(root)
    app.run()
    return 0
