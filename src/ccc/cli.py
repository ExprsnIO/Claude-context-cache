"""`ccc` command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ccc import __version__
from ccc.compact import (
    DEFAULT_THRESHOLD_TOKENS,
    compact,
    session_token_estimate,
    should_compact,
)
from ccc.handoff import (
    WORD_LIMIT,
    count_words,
    hydrate_state_from_handoff,
    truncate_to_limit,
    validate,
    write_handoff,
)
from ccc.state import State, StateStore


def _store(args: argparse.Namespace) -> StateStore:
    return StateStore(args.root)


def _load(args: argparse.Namespace) -> tuple[StateStore, State]:
    store = _store(args)
    state = store.load()
    return store, state


# ---- command handlers ------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    store = _store(args)
    state = store.init()
    if args.prompt:
        state.original_prompt = args.prompt
    if args.style:
        state.code_style = args.style
    if args.phase:
        state.set_phase(args.phase)
    store.save(state)
    print(f"Initialized state at {store.path}")
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    store, state = _load(args)
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 1
    label = args.label or path.name
    size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else path.stat().st_size
    state.add_context_source(str(path), label, size)
    store.save(state)
    print(f"Cached source: {label} ({path}, {size} bytes)")
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    store, state = _load(args)
    state.original_prompt = args.text
    store.save(state)
    print("Original prompt updated.")
    return 0


def cmd_style(args: argparse.Namespace) -> int:
    store, state = _load(args)
    if args.append and state.code_style:
        state.code_style = state.code_style.rstrip() + "\n" + args.text
    else:
        state.code_style = args.text
    store.save(state)
    print("Code style updated.")
    return 0


def cmd_todo(args: argparse.Namespace) -> int:
    store, state = _load(args)
    todo = state.add_todo(args.text)
    store.save(state)
    print(f"Added todo {todo.id}: {todo.text}")
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    store, state = _load(args)
    todo = state.complete_todo(args.id)
    if todo is None:
        print(f"error: no todo matching {args.id!r}", file=sys.stderr)
        return 1
    store.save(state)
    print(f"Completed {todo.id}: {todo.text}")
    return 0


def cmd_sprint(args: argparse.Namespace) -> int:
    store, state = _load(args)
    if args.action == "start":
        sprint = state.start_sprint(args.name, phase=args.phase)
        store.save(state)
        print(f"Started sprint {sprint.name} (phase={sprint.phase or '-'})")
    elif args.action == "complete":
        sprint = state.complete_sprint(notes=args.notes or "")
        if sprint is None:
            print("error: no active sprint to complete", file=sys.stderr)
            return 1
        store.save(state)
        print(f"Completed sprint {sprint.name}")
    return 0


def cmd_phase(args: argparse.Namespace) -> int:
    store, state = _load(args)
    state.set_phase(args.name)
    store.save(state)
    print(f"Current phase: {state.current_phase}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store, state = _load(args)
    print(f"State: {store.path}")
    print(f"Phase: {state.current_phase or '(unset)'}")
    print(f"Sprint: {state.current_sprint or '(none)'}")
    print(f"Original prompt: {state.original_prompt[:80] or '(unset)'}")
    print(f"Cached sources: {len(state.context_sources)}")
    for s in state.context_sources:
        print(f"  - {s.label} ({s.path}, {s.bytes_} bytes)")
    print(f"Todos open: {len(state.todos)}")
    for t in state.todos:
        print(f"  [{t.id}] {t.text}")
    print(f"Completed: {len(state.completed)}")
    used = session_token_estimate(state)
    print(f"Session tokens (input+output+cache): {used}")
    if state.last_handoff_path:
        print(f"Last handoff: {state.last_handoff_path}")
    return 0


def _format_usage_line(usage: object) -> str:
    """One-line per-call cache telemetry written to stderr.

    Surfaces `cache_creation_input_tokens` and `cache_read_input_tokens`
    for the current call so cache effectiveness regressions are visible
    instead of buried in aggregate counters.
    """
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cacheable = cache_read + cache_creation
    hit_pct = (cache_read / cacheable * 100) if cacheable > 0 else 0.0
    return (
        f"[ccc] tokens — input={inp} output={out} "
        f"cache_read={cache_read} cache_creation={cache_creation} "
        f"hit={hit_pct:.0f}%"
    )


def cmd_ask(args: argparse.Namespace) -> int:
    from ccc.client import ask  # lazy: avoid forcing anthropic import

    store, state = _load(args)
    prompt = args.text or sys.stdin.read()
    if not prompt.strip():
        print("error: empty prompt", file=sys.stderr)
        return 1
    text, usage = ask(state, prompt, model=args.model, max_tokens=args.max_tokens)
    state.record_usage(usage)
    store.save(state)
    print(text)
    print(_format_usage_line(usage), file=sys.stderr)
    if should_compact(state, args.threshold):
        print(
            f"[ccc] session tokens hit {session_token_estimate(state)} "
            f"(threshold {args.threshold}); run `ccc compact` to emit a handoff.",
            file=sys.stderr,
        )
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    from ccc.client import generate_handoff

    store, state = _load(args)
    text, usage = generate_handoff(state, model=args.model)
    state.record_usage(usage)
    text = truncate_to_limit(text)
    problems = validate(text)
    label = "manual"
    if problems:
        label = "needs-review"
        for p in problems:
            print(f"warning: {p}", file=sys.stderr)
    path = write_handoff(store, text, label=label)
    state.last_handoff_path = str(path)
    store.save(state)
    print(f"Handoff written to {path} ({count_words(text)} words, limit {WORD_LIMIT})")
    if args.print:
        print()
        print(text)
    return 0 if not problems else 2


def cmd_compact(args: argparse.Namespace) -> int:
    store, state = _load(args)
    result = compact(store, state, threshold=args.threshold, force=args.force)
    if result is None:
        used = session_token_estimate(state)
        print(
            f"Skipped: session tokens {used} below threshold {args.threshold}. "
            f"Use --force to compact anyway."
        )
        return 0
    path, _ = result
    print(f"Compacted. Handoff: {path}")
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    from ccc import tui  # lazy: textual is an optional dependency

    return tui.run(root=args.root)


def cmd_resume(args: argparse.Namespace) -> int:
    store = _store(args)
    handoff_path = Path(args.handoff)
    if not handoff_path.exists():
        print(f"error: {handoff_path} does not exist", file=sys.stderr)
        return 1
    text = handoff_path.read_text(encoding="utf-8")
    if store.exists() and not args.overwrite:
        state = store.load()
    else:
        state = State()
    hydrate_state_from_handoff(text, state)
    state.last_handoff_path = str(handoff_path.resolve())
    store.save(state)
    print(
        f"Resumed from {handoff_path}. "
        f"Loaded {len(state.todos)} todos. Phase={state.current_phase or '-'}."
    )
    return 0


# ---- parser ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccc",
        description="Cache Claude topic contexts and emit ≤750-word handoff documents.",
    )
    parser.add_argument("--version", action="version", version=f"ccc {__version__}")
    parser.add_argument(
        "--root",
        default=".",
        help="Project root (where .ccc/ lives). Defaults to cwd.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Initialize a .ccc/ workspace")
    p.add_argument("--prompt", help="Original task prompt to record")
    p.add_argument("--style", help="Initial code-style notes")
    p.add_argument("--phase", help="Starting phase label")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("cache", help="Cache a topic source (file or directory)")
    p.add_argument("path")
    p.add_argument("--label", help="Short label (defaults to filename)")
    p.set_defaults(func=cmd_cache)

    p = sub.add_parser("prompt", help="Set or replace the original prompt")
    p.add_argument("text")
    p.set_defaults(func=cmd_prompt)

    p = sub.add_parser("style", help="Set or append code-style notes")
    p.add_argument("text")
    p.add_argument("--append", action="store_true")
    p.set_defaults(func=cmd_style)

    p = sub.add_parser("todo", help="Add a todo to the current sprint/phase")
    p.add_argument("text")
    p.set_defaults(func=cmd_todo)

    p = sub.add_parser("done", help="Mark a todo complete (by id prefix)")
    p.add_argument("id")
    p.set_defaults(func=cmd_done)

    p = sub.add_parser("sprint", help="Start or complete a sprint")
    sp = p.add_subparsers(dest="action", required=True)
    psp = sp.add_parser("start")
    psp.add_argument("name")
    psp.add_argument("--phase")
    psp.set_defaults(func=cmd_sprint)
    psp = sp.add_parser("complete")
    psp.add_argument("--notes", default="")
    psp.set_defaults(func=cmd_sprint)

    p = sub.add_parser("phase", help="Set the current phase label")
    p.add_argument("name")
    p.set_defaults(func=cmd_phase)

    p = sub.add_parser("status", help="Show the current session state")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser(
        "ask",
        help="Send a prompt to Claude with the cached topic context (uses prompt caching).",
    )
    p.add_argument("text", nargs="?")
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument("--max-tokens", type=int, default=16000)
    p.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD_TOKENS,
        help="Token budget that triggers an auto-compact reminder.",
    )
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser(
        "handoff",
        help="Generate a ≤750-word handoff document for the next context window.",
    )
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument("--print", action="store_true", help="Print the document to stdout")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser(
        "compact",
        help="Auto-compact: emit handoff and reset session counters when over threshold.",
    )
    p.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD_TOKENS)
    p.add_argument(
        "--force",
        action="store_true",
        help="Compact even if the threshold has not been reached.",
    )
    p.set_defaults(func=cmd_compact)

    p = sub.add_parser(
        "resume",
        help="Load a handoff document into a fresh state for the new context window.",
    )
    p.add_argument("handoff")
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace any existing state with the handoff contents.",
    )
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser(
        "tui",
        help="Launch the interactive Textual UI (requires `pip install -e \".[tui]\"`).",
    )
    p.set_defaults(func=cmd_tui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
