import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openSqlite } from "../src/adapters/sqlite.js";

test("sqlite-memory: set/get/delete round-trip", async () => {
  const store = openSqlite({ path: ":memory:", namespace: "", kind: "sqlite-memory" });
  await store.set("foo", "bar");
  assert.equal(await store.get("foo"), "bar");
  assert.equal(await store.delete("foo"), true);
  assert.equal(await store.get("foo"), null);
  await store.close();
});

test("sqlite-memory: list with prefix and namespace", async () => {
  const store = openSqlite({ path: ":memory:", namespace: "ns", kind: "sqlite-memory" });
  await store.set("a/1", "x");
  await store.set("a/2", "y");
  await store.set("b/1", "z");
  const aKeys = await store.list("a/");
  assert.deepEqual(aKeys.sort(), ["a/1", "a/2"]);
  const all = await store.list();
  assert.deepEqual(all.sort(), ["a/1", "a/2", "b/1"]);
  await store.close();
});

test("sqlite-memory: TTL expires entries", async () => {
  const store = openSqlite({ path: ":memory:", namespace: "", kind: "sqlite-memory" });
  await store.set("temp", "soon", { ttlMs: 30 });
  assert.equal(await store.get("temp"), "soon");
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(await store.get("temp"), null);
  await store.close();
});

test("sqlite-disk: persists across reopens", async () => {
  const dir = mkdtempSync(join(tmpdir(), "ccc-store-"));
  const path = join(dir, "store.sqlite");
  try {
    const a = openSqlite({ path, namespace: "", kind: "sqlite-disk" });
    await a.set("durable", "yes");
    await a.close();
    const b = openSqlite({ path, namespace: "", kind: "sqlite-disk" });
    assert.equal(await b.get("durable"), "yes");
    await b.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
