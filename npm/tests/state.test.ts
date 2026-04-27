import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { State, StateStore } from "../src/state.js";

function tmpRoot(): string {
  return mkdtempSync(join(tmpdir(), "ccc-test-"));
}

test("state round-trips through StateStore", () => {
  const root = tmpRoot();
  try {
    const store = new StateStore(root);
    const state = store.init();
    state.original_prompt = "Build a thing";
    state.code_style = "- 4 spaces\n- type hints";
    state.setPhase("MVP");
    state.startSprint("scaffolding", "MVP");
    const todo = state.addTodo("write tests");
    state.addTodo("ship CLI");
    state.completeTodo(todo.id);
    store.save(state);

    const reloaded = store.load();
    assert.equal(reloaded.original_prompt, "Build a thing");
    assert.equal(reloaded.current_phase, "MVP");
    assert.equal(reloaded.current_sprint, "scaffolding");
    assert.equal(reloaded.todos.length, 1);
    assert.equal(reloaded.completed.length, 1);
    assert.equal(reloaded.completed[0]!.text, "write tests");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("complete todo by id prefix", () => {
  const state = new State();
  const todo = state.addTodo("first");
  state.addTodo("second");
  const completed = state.completeTodo(todo.id.slice(0, 3));
  assert.ok(completed);
  assert.equal(completed!.text, "first");
  assert.equal(state.todos.length, 1);
});

test("starting a new sprint closes the active one", () => {
  const state = new State();
  const a = state.startSprint("alpha", "MVP");
  state.startSprint("beta", "MVP");
  assert.equal(a.status, "complete");
  assert.equal(state.current_sprint, "beta");
});

test("recordUsage accumulates across calls", () => {
  const state = new State();
  const usage = {
    input_tokens: 100,
    output_tokens: 50,
    cache_read_input_tokens: 200,
    cache_creation_input_tokens: 0,
  };
  state.recordUsage(usage);
  state.recordUsage(usage);
  assert.equal(state.session_input_tokens, 200);
  assert.equal(state.session_output_tokens, 100);
  assert.equal(state.cache_read_tokens, 400);
});
