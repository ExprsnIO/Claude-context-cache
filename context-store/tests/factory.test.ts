import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createStore } from "../src/factory.js";

test("factory falls back to sqlite-memory when no Redis configured", async () => {
  const { store, info } = await createStore({
    redisUrl: undefined,
    sqlitePath: ":memory:",
  });
  assert.equal(store.kind, "sqlite-memory");
  assert.equal(info.cache, "sqlite-memory");
  assert.equal(info.backing, null);
  await store.close();
});

test("factory falls back to sqlite-disk when memory is disabled", async () => {
  const dir = mkdtempSync(join(tmpdir(), "ccc-factory-"));
  try {
    const { store, info } = await createStore({
      sqlitePath: join(dir, "store.sqlite"),
      disableSqliteMemory: true,
    });
    assert.equal(store.kind, "sqlite-disk");
    assert.equal(info.cache, "sqlite-disk");
    await store.set("k", "v");
    assert.equal(await store.get("k"), "v");
    await store.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("factory records failed Redis probe and falls back", async () => {
  const { store, info } = await createStore({
    redisUrl: "redis://127.0.0.1:1",
    probeTimeoutMs: 200,
  });
  assert.equal(store.kind, "sqlite-memory");
  const redisAttempt = info.attempts.find((a) => a.kind === "redis");
  assert.ok(redisAttempt, "redis attempt recorded");
  assert.equal(redisAttempt!.ok, false);
  await store.close();
});
