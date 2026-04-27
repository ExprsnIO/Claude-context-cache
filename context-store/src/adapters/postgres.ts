import type { ContextStore, SetOptions } from "../types.js";
import { withNamespace, stripNamespace, withTimeout } from "../config.js";

interface Options {
  url: string;
  namespace: string;
  table: string;
  probeTimeoutMs: number;
}

interface PgPool {
  query(text: string, values?: unknown[]): Promise<{ rows: unknown[]; rowCount: number | null }>;
  end(): Promise<void>;
}

interface PgModule {
  Pool: new (opts: { connectionString: string }) => PgPool;
}

async function loadPg(): Promise<PgModule> {
  try {
    return (await import("pg")) as unknown as PgModule;
  } catch {
    throw new Error(
      "postgres backend requested but the 'pg' package is not installed. " +
        "Run `npm install pg` or unset CCC_POSTGRES_URL.",
    );
  }
}

function quoteIdent(name: string): string {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
    throw new Error(`invalid table name: ${name}`);
  }
  return `"${name}"`;
}

export async function openPostgres({
  url,
  namespace,
  table,
  probeTimeoutMs,
}: Options): Promise<ContextStore> {
  const mod = await loadPg();
  const pool = new mod.Pool({ connectionString: url });
  const t = quoteIdent(table);
  await withTimeout(
    pool.query(
      `CREATE TABLE IF NOT EXISTS ${t} (
         key TEXT PRIMARY KEY,
         value TEXT NOT NULL,
         expires_at BIGINT NULL,
         updated_at BIGINT NOT NULL
       )`,
    ),
    probeTimeoutMs,
    "postgres init",
  );
  await pool.query(
    `CREATE INDEX IF NOT EXISTS ${quoteIdent(`${table}_expires_idx`)}
       ON ${t}(expires_at) WHERE expires_at IS NOT NULL`,
  );

  const sweep = async () => {
    await pool.query(
      `DELETE FROM ${t} WHERE expires_at IS NOT NULL AND expires_at < $1`,
      [Date.now()],
    );
  };

  return {
    kind: "postgres",
    async get(key) {
      await sweep();
      const result = await pool.query(
        `SELECT value FROM ${t} WHERE key = $1`,
        [withNamespace(namespace, key)],
      );
      const rows = result.rows as Array<{ value: string }>;
      return rows.length ? rows[0].value : null;
    },
    async set(key, value, opts: SetOptions = {}) {
      const now = Date.now();
      const expiresAt = opts.ttlMs ? now + opts.ttlMs : null;
      await pool.query(
        `INSERT INTO ${t} (key, value, expires_at, updated_at)
         VALUES ($1, $2, $3, $4)
         ON CONFLICT (key) DO UPDATE SET
           value = EXCLUDED.value,
           expires_at = EXCLUDED.expires_at,
           updated_at = EXCLUDED.updated_at`,
        [withNamespace(namespace, key), value, expiresAt, now],
      );
    },
    async delete(key) {
      const result = await pool.query(`DELETE FROM ${t} WHERE key = $1`, [
        withNamespace(namespace, key),
      ]);
      return (result.rowCount ?? 0) > 0;
    },
    async list(prefix) {
      await sweep();
      const match = withNamespace(namespace, `${prefix ?? ""}%`);
      const result = await pool.query(
        `SELECT key FROM ${t} WHERE key LIKE $1`,
        [match],
      );
      return (result.rows as Array<{ key: string }>).map((r) =>
        stripNamespace(namespace, r.key),
      );
    },
    async close() {
      await pool.end();
    },
  };
}
