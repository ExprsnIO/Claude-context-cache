import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import Database from "better-sqlite3";
import type { BackendKind, ContextStore, SetOptions } from "../types.js";
import { withNamespace, stripNamespace } from "../config.js";

interface Options {
  path: string;
  namespace: string;
  kind: Extract<BackendKind, "sqlite-memory" | "sqlite-disk">;
}

export function openSqlite({ path, namespace, kind }: Options): ContextStore {
  if (kind === "sqlite-disk") {
    mkdirSync(dirname(resolve(path)), { recursive: true });
  }
  const db = new Database(kind === "sqlite-memory" ? ":memory:" : path);
  db.pragma("journal_mode = WAL");
  db.exec(`
    CREATE TABLE IF NOT EXISTS ccc_context (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      expires_at INTEGER,
      updated_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ccc_context_expires_idx
      ON ccc_context(expires_at) WHERE expires_at IS NOT NULL;
  `);

  const stmts = {
    get: db.prepare<[string], { value: string; expires_at: number | null }>(
      "SELECT value, expires_at FROM ccc_context WHERE key = ?",
    ),
    upsert: db.prepare(
      `INSERT INTO ccc_context (key, value, expires_at, updated_at)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(key) DO UPDATE SET
         value = excluded.value,
         expires_at = excluded.expires_at,
         updated_at = excluded.updated_at`,
    ),
    delete: db.prepare("DELETE FROM ccc_context WHERE key = ?"),
    listAll: db.prepare<[], { key: string }>("SELECT key FROM ccc_context"),
    listPrefix: db.prepare<[string], { key: string }>(
      "SELECT key FROM ccc_context WHERE key LIKE ?",
    ),
    deleteExpired: db.prepare(
      "DELETE FROM ccc_context WHERE expires_at IS NOT NULL AND expires_at < ?",
    ),
  };

  const sweep = () => stmts.deleteExpired.run(Date.now());

  return {
    kind,
    async get(key) {
      sweep();
      const row = stmts.get.get(withNamespace(namespace, key));
      if (!row) return null;
      if (row.expires_at !== null && row.expires_at < Date.now()) {
        stmts.delete.run(withNamespace(namespace, key));
        return null;
      }
      return row.value;
    },
    async set(key, value, opts: SetOptions = {}) {
      const now = Date.now();
      const expiresAt = opts.ttlMs ? now + opts.ttlMs : null;
      stmts.upsert.run(withNamespace(namespace, key), value, expiresAt, now);
    },
    async delete(key) {
      const result = stmts.delete.run(withNamespace(namespace, key));
      return result.changes > 0;
    },
    async list(prefix) {
      sweep();
      const fullPrefix = withNamespace(namespace, prefix ?? "");
      const rows = prefix
        ? stmts.listPrefix.all(`${fullPrefix}%`)
        : namespace
          ? stmts.listPrefix.all(`${namespace}:%`)
          : stmts.listAll.all();
      return rows.map((r) => stripNamespace(namespace, r.key));
    },
    async close() {
      db.close();
    },
  };
}
