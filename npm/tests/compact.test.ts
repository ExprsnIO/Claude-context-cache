import { test } from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_THRESHOLD_TOKENS,
  sessionTokenEstimate,
  shouldCompact,
} from "../src/compact.js";
import { State } from "../src/state.js";

test("shouldCompact is false below threshold", () => {
  const state = new State();
  state.session_input_tokens = 1000;
  assert.equal(shouldCompact(state), false);
});

test("shouldCompact is true at threshold", () => {
  const state = new State();
  state.session_input_tokens = DEFAULT_THRESHOLD_TOKENS;
  assert.equal(shouldCompact(state), true);
});

test("sessionTokenEstimate sums every counter", () => {
  const state = new State();
  state.session_input_tokens = 100;
  state.session_output_tokens = 200;
  state.cache_read_tokens = 300;
  state.cache_creation_tokens = 400;
  assert.equal(sessionTokenEstimate(state), 1000);
});
