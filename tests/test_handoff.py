from __future__ import annotations

from ccc.handoff import (
    REQUIRED_SECTIONS,
    WORD_LIMIT,
    count_words,
    hydrate_state_from_handoff,
    parse_handoff,
    truncate_to_limit,
    validate,
)
from ccc.state import State


GOOD_DOC = """\
## Code Style
- 4-space indent
- type hints required

## Original Prompt / Current Phase
Build a CLI tool. Phase: MVP. Sprint: scaffolding.

## Completed Results
- Wrote state module
- Added CLI parser

## To-Do
- Add tests
- Wire up Anthropic client

## Sprints / Phases for Next Context Window
Sprint 2 — Polish (Phase: beta)
  - Add docs
  - Tag release
"""


def test_count_words_ignores_code_fences():
    text = "hello world\n```python\nlots and lots and lots of code words here\n```\nend"
    assert count_words(text) == 3  # hello world end


def test_validate_good_doc():
    assert validate(GOOD_DOC) == []


def test_validate_missing_section():
    text = GOOD_DOC.replace("## To-Do\n- Add tests\n- Wire up Anthropic client\n\n", "")
    problems = validate(text)
    assert any("To-Do" in p for p in problems)


def test_validate_word_count_over_limit():
    long_block = " ".join(["word"] * (WORD_LIMIT + 50))
    text = GOOD_DOC + "\n" + long_block
    problems = validate(text)
    assert any("word count" in p for p in problems)


def test_truncate_to_limit():
    long_block = "\n".join(["filler line " + str(i) for i in range(2000)])
    text = GOOD_DOC + "\n" + long_block
    truncated = truncate_to_limit(text, WORD_LIMIT)
    assert count_words(truncated) <= WORD_LIMIT


def test_parse_handoff_sections():
    sections = parse_handoff(GOOD_DOC)
    for required in REQUIRED_SECTIONS:
        key = required[3:]
        assert key in sections


def test_hydrate_state_from_handoff_into_empty_state():
    state = State()
    hydrate_state_from_handoff(GOOD_DOC, state)
    assert "4-space indent" in state.code_style
    assert "Build a CLI tool" in state.original_prompt
    assert any(t.text == "Add tests" for t in state.todos)
    assert any(t.text == "Wire up Anthropic client" for t in state.todos)
