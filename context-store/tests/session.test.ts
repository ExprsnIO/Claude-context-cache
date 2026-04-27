import { test } from "node:test";
import assert from "node:assert/strict";
import { Session, withSession } from "../src/session.js";

test("Session lazily opens on first call", async () => {
  const session = new Session({
    sqlitePath: ":memory:",
    installSignalHandlers: false,
    idleTimeoutMs: 0,
  });
  await session.set("hello", "world");
  assert.equal(await session.get("hello"), "world");
  assert.equal(session.kind, "sqlite-memory");
  await session.close();
});

test("Session idle timeout closes the underlying store", async () => {
  const session = new Session({
    sqlitePath: ":memory:",
    installSignalHandlers: false,
    idleTimeoutMs: 30,
  });
  await session.set("k", "v");
  await new Promise((r) => setTimeout(r, 80));
  // After idle close, a fresh access should re-open and return null because
  // the previous store was in-memory.
  assert.equal(await session.get("k"), null);
  await session.close();
});

test("withSession scopes the session lifecycle", async () => {
  let observedKind = "";
  const result = await withSession(
    async (s) => {
      await s.set("ping", "pong");
      observedKind = s.kind;
      return s.get("ping");
    },
    { sqlitePath: ":memory:" },
  );
  assert.equal(result, "pong");
  assert.equal(observedKind, "sqlite-memory");
});
