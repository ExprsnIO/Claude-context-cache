"""Tests for `_build_system_blocks` cache-control placement.

The placement and admission rules drive whether `ccc ask` actually
benefits from prompt caching. These tests lock the rules in:

1. The `cache_control` marker sits on the LAST block, never on the
   user message — Anthropic walks the prefix top-to-bottom, so a
   marker below volatile content produces zero cache hits.
2. Prefixes shorter than the API's minimum-cacheable-tokens floor
   skip the marker entirely, since the 25% cache-write premium
   would never amortize.
"""

from __future__ import annotations

from ccc.client import MIN_CACHE_PREFIX_CHARS, _build_system_blocks


def _has_cache_control(block: dict) -> bool:
    return block.get("cache_control") == {"type": "ephemeral"}


def test_marker_on_last_block_when_topic_present() -> None:
    base = "x" * (MIN_CACHE_PREFIX_CHARS // 2)
    topic = "y" * (MIN_CACHE_PREFIX_CHARS // 2 + 1)
    blocks = _build_system_blocks(base, topic)
    assert len(blocks) == 2
    assert not _has_cache_control(blocks[0])
    assert _has_cache_control(blocks[-1])


def test_marker_on_only_block_when_no_topic_but_prefix_long_enough() -> None:
    base = "x" * (MIN_CACHE_PREFIX_CHARS + 1)
    blocks = _build_system_blocks(base, "")
    assert len(blocks) == 1
    assert _has_cache_control(blocks[0])


def test_no_marker_when_prefix_below_floor_with_topic() -> None:
    base = "x" * 100
    topic = "y" * 100
    blocks = _build_system_blocks(base, topic)
    assert len(blocks) == 2
    assert not any(_has_cache_control(b) for b in blocks)


def test_no_marker_when_prefix_below_floor_without_topic() -> None:
    """Tiny system prompt + no topic must not pay the 25% write premium."""
    blocks = _build_system_blocks("tiny prompt", "")
    assert len(blocks) == 1
    assert not _has_cache_control(blocks[0])
