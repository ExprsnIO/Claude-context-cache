import { test } from "node:test";
import assert from "node:assert/strict";

import {
  REQUIRED_SECTIONS,
  WORD_LIMIT,
  countWords,
  hydrateStateFromHandoff,
  parseHandoff,
  truncateToLimit,
  validate,
} from "../src/handoff.js";
import { State } from "../src/state.js";

const GOOD_DOC = `## Code Style
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
Sprint 2 - Polish (Phase: beta)
  - Add docs
  - Tag release
`;

test("countWords ignores fenced code blocks", () => {
  const text =
    "hello world\n```ts\nlots and lots and lots of code words here\n```\nend";
  assert.equal(countWords(text), 3);
});

test("validate accepts a well-formed doc", () => {
  assert.deepEqual(validate(GOOD_DOC), []);
});

test("validate flags missing required section", () => {
  const text = GOOD_DOC.replace(
    /## To-Do\n- Add tests\n- Wire up Anthropic client\n\n/,
    "",
  );
  const problems = validate(text);
  assert.ok(problems.some((p) => p.includes("To-Do")));
});

test("validate flags over-limit word count", () => {
  const longBlock = Array.from({ length: WORD_LIMIT + 50 })
    .map(() => "word")
    .join(" ");
  const problems = validate(GOOD_DOC + "\n" + longBlock);
  assert.ok(problems.some((p) => p.includes("word count")));
});

test("truncateToLimit drops trailing lines until under limit", () => {
  const longBlock = Array.from({ length: 2000 })
    .map((_, i) => `filler line ${i}`)
    .join("\n");
  const truncated = truncateToLimit(GOOD_DOC + "\n" + longBlock);
  assert.ok(countWords(truncated) <= WORD_LIMIT);
});

test("parseHandoff extracts every required section", () => {
  const sections = parseHandoff(GOOD_DOC);
  for (const required of REQUIRED_SECTIONS) {
    const key = required.slice(3);
    assert.ok(key in sections, `missing ${key}`);
  }
});

test("hydrateStateFromHandoff fills empty state from a doc", () => {
  const state = new State();
  hydrateStateFromHandoff(GOOD_DOC, state);
  assert.match(state.code_style, /4-space indent/);
  assert.match(state.original_prompt, /Build a CLI tool/);
  assert.ok(state.todos.some((t) => t.text === "Add tests"));
  assert.ok(state.todos.some((t) => t.text === "Wire up Anthropic client"));
});
