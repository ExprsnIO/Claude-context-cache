import { test } from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  rmSync,
  writeFileSync,
  readFileSync,
  utimesSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  closeSourceSession,
  gatherContextSourcesCached,
  getSourceSession,
  readSourceCached,
} from "../src/source-cache.js";
import { State } from "../src/state.js";

function makeFile(dir: string, name: string, content: string): string {
  const path = join(dir, name);
  writeFileSync(path, content, "utf8");
  return path;
}

async function withTmpSession<T>(
  fn: (dir: string) => Promise<T>,
): Promise<T> {
  const dir = mkdtempSync(join(tmpdir(), "ccc-source-cache-"));
  // Force a fresh in-memory session for the test, isolated from any other run.
  await closeSourceSession();
  getSourceSession({ sqlitePath: ":memory:", installSignalHandlers: false });
  try {
    return await fn(dir);
  } finally {
    await closeSourceSession();
    rmSync(dir, { recursive: true, force: true });
  }
}

test("readSourceCached returns cacheHit=false on first call, true on second", async () => {
  await withTmpSession(async (dir) => {
    const path = makeFile(dir, "a.txt", "alpha");
    const first = await readSourceCached(path);
    assert.equal(first.cacheHit, false);
    assert.equal(first.text, "alpha");
    const second = await readSourceCached(path);
    assert.equal(second.cacheHit, true);
    assert.equal(second.text, "alpha");
  });
});

test("readSourceCached invalidates when file mtime/size changes", async () => {
  await withTmpSession(async (dir) => {
    const path = makeFile(dir, "a.txt", "alpha");
    const first = await readSourceCached(path);
    assert.equal(first.cacheHit, false);

    writeFileSync(path, "alpha-and-beta", "utf8");
    // Bump mtime explicitly in case the test runs faster than mtime resolution.
    const future = new Date(Date.now() + 5000);
    utimesSync(path, future, future);

    const second = await readSourceCached(path);
    assert.equal(second.cacheHit, false);
    assert.equal(second.text, "alpha-and-beta");
    const third = await readSourceCached(path);
    assert.equal(third.cacheHit, true);
    assert.equal(third.text, "alpha-and-beta");
  });
});

test("gatherContextSourcesCached produces label/text pairs in order", async () => {
  await withTmpSession(async (dir) => {
    const a = makeFile(dir, "a.txt", "alpha");
    const b = makeFile(dir, "b.txt", "beta");
    const state = new State();
    state.addContextSource(a, "labelA", readFileSync(a).length);
    state.addContextSource(b, "labelB", readFileSync(b).length);
    const result = await gatherContextSourcesCached(state);
    assert.deepEqual(result, [
      ["labelA", "alpha"],
      ["labelB", "beta"],
    ]);
  });
});

test("gatherContextSourcesCached skips vanished sources", async () => {
  await withTmpSession(async (dir) => {
    const a = makeFile(dir, "a.txt", "alpha");
    const state = new State();
    state.addContextSource(a, "labelA", 5);
    state.addContextSource(join(dir, "missing.txt"), "labelMissing", 0);
    const result = await gatherContextSourcesCached(state);
    assert.deepEqual(result, [["labelA", "alpha"]]);
  });
});
