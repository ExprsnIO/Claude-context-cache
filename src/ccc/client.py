"""Anthropic client wrapper with prompt caching for topic context."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ccc.prompts import (
    ASK_SYSTEM_PROMPT,
    HANDOFF_SYSTEM_PROMPT,
    render_topic_context,
)
from ccc.source_cache import gather_context_sources_cached
from ccc.state import State

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 16000

# Anthropic only caches prefixes of ≥1024 tokens for most Claude models, and
# a cache write costs 25% more than a base input token, so caching a small
# prefix loses money. ~4 chars/token is the standard back-of-envelope, so
# 4096 chars is a conservative floor that keeps us above the API minimum
# without an extra tokenizer round-trip.
MIN_CACHE_PREFIX_CHARS = 4096


def _read_source(path: Path) -> str:
    if path.is_dir():
        chunks: list[str] = []
        for child in sorted(path.rglob("*")):
            if not child.is_file():
                continue
            if any(part.startswith(".") for part in child.relative_to(path).parts):
                continue
            try:
                text = child.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = child.relative_to(path)
            chunks.append(f"--- {rel} ---\n{text}")
        return "\n\n".join(chunks)
    return path.read_text(encoding="utf-8")


def gather_context_sources(state: State) -> list[tuple[str, str]]:
    """Read every cached source from disk; skip ones that vanished."""
    sources: list[tuple[str, str]] = []
    for src in state.context_sources:
        path = Path(src.path)
        if not path.exists():
            continue
        try:
            content = _read_source(path)
        except OSError:
            continue
        sources.append((src.label, content))
    return sources


def _import_anthropic():
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "anthropic package not installed. Run: pip install anthropic"
        ) from exc
    return anthropic


def _build_system_blocks(
    base_prompt: str, topic_text: str
) -> list[dict[str, Any]]:
    """System blocks with cache_control on the last block when worth it.

    Render order is `tools` → `system` → `messages`, so a marker on the last
    system block caches the entire prefix (tools + system) up to that point.
    The marker is only emitted when the combined prefix is large enough to
    clear the API's minimum-cacheable-tokens floor; otherwise the 25% cache
    write premium would never amortize.
    """
    blocks: list[dict[str, Any]] = [{"type": "text", "text": base_prompt}]
    if topic_text:
        blocks.append({"type": "text", "text": topic_text})
    if len(base_prompt) + len(topic_text) < MIN_CACHE_PREFIX_CHARS:
        return blocks
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def make_client():
    anthropic = _import_anthropic()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Export it before running `ccc ask` or `ccc handoff`."
        )
    return anthropic.Anthropic(api_key=api_key)


def ask(
    state: State,
    user_message: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[str, Any]:
    """Run a cached call against the topic context. Returns (text, usage)."""
    client = make_client()
    topic_text = render_topic_context(gather_context_sources_cached(state))
    system_blocks = _build_system_blocks(ASK_SYSTEM_PROMPT, topic_text)

    messages: list[dict[str, Any]] = []
    if state.original_prompt:
        messages.append(
            {
                "role": "user",
                "content": f"Original task: {state.original_prompt}",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Acknowledged. Working from cached context.",
            }
        )
    messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=messages,
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return text, response.usage


def generate_handoff(
    state: State,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4000,
) -> tuple[str, Any]:
    """Ask Claude to compact the session into a ≤750-word handoff document."""
    client = make_client()
    topic_text = render_topic_context(gather_context_sources_cached(state))
    system_blocks = _build_system_blocks(HANDOFF_SYSTEM_PROMPT, topic_text)

    user_payload = (
        "Generate the handoff document now. Hard limit: 750 words.\n\n"
        f"Original prompt: {state.original_prompt or '(not set)'}\n"
        f"Current phase: {state.current_phase or '(not set)'}\n"
        f"Active sprint: {state.current_sprint or '(none)'}\n\n"
        "Code style notes (verbatim from harness):\n"
        f"{state.code_style or '(none recorded)'}\n\n"
        "Completed items:\n"
        + (
            "\n".join(f"- {t.text}" for t in state.completed) or "- (none)"
        )
        + "\n\nOutstanding to-do items:\n"
        + (
            "\n".join(f"- {t.text}" for t in state.todos) or "- (none)"
        )
        + "\n\nSprint history (most recent last):\n"
        + (
            "\n".join(
                f"- {s.name} ({s.status}, phase={s.phase or '-'})"
                for s in state.sprints
            )
            or "- (none)"
        )
    )

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=[{"role": "user", "content": user_payload}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return text.strip(), response.usage
