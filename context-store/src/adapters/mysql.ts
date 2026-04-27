import type { ContextStore, SetOptions } from "../types.js";
import { withNamespace, stripNamespace, withTimeout } from "../config.js";

interface Options {
  url: string;
  namespace: string;
  table: string;
  probeTimeoutMs: number;
}

interface MysqlPool {
  query(sql: string, params?: unknown[]): Promise<[unknown[], unknown]>;
  end(): Promise<void>;
}

interface MysqlModule {
  createPool(opts: { uri: string }): MysqlPool;
}

async function loadMysql(): Promise<MysqlModule> {
  try {
    const mod = (await import("mysql2/promise")) as unknown as MysqlModule;
    return mod;
  } catch {
    throw new Error(
      "mysql backend requested but the 'mysql2' package is not installed. " +
        "Run `npm install mysql2` or unset CCC_MYSQL_URL.",
    );
  }
}

export async function openMysql({
  url,
  namespace,
  table,
  probeTimeoutMs,
}: Options): Promise<ContextStore> {
  const mod = await loadMysql();
  const pool = mod.createPool({ uri: url });
  await withTimeout(
    pool.query(
      `CREATE TABLE IF NOT EXISTS \`${table}\` (
         \`key\` VARCHAR(512) PRIMARY KEY,
         \`value\` LONGTEXT NOT NULL,
         \`expires_at\` BIGINT NULL,
         \`updated_at\` BIGINT NOT NULL,
         INDEX (\`expires_at\`)
       )`,
    ),
    probeTimeoutMs,
    "mysql init",
  );

  const sweep = async () => {
    await pool.query(
      `DELETE FROM \`${table}\` WHERE expires_at IS NOT NULL AND expires_at < ?`,
      [Date.now()],
    );
  };

  return {
    kind: "mysql",
    async get(key) {
      await sweep();
      const [rows] = await pool.query(
        `SELECT \`value\` FROM \`${table}\` WHERE \`key\` = ?`,
        [withNamespace(namespace, key)],
      );
      const list = rows as Array<{ value: string }>;
      return list.length ? list[0].value : null;
    },
    async set(key, value, opts: SetOptions = {}) {
      const now = Date.now();
      const expiresAt = opts.ttlMs ? now + opts.ttlMs : null;
      await pool.query(
        `INSERT INTO \`${table}\` (\`key\`, \`value\`, \`expires_at\`, \`updated_at\`)
         VALUES (?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE
           \`value\` = VALUES(\`value\`),
           \`expires_at\` = VALUES(\`expires_at\`),
           \`updated_at\` = VALUES(\`updated_at\`)`,
        [withNamespace(namespace, key), value, expiresAt, now],
      );
    },
    async delete(key) {
      const [result] = await pool.query(
        `DELETE FROM \`${table}\` WHERE \`key\` = ?`,
        [withNamespace(namespace, key)],
      );
      const affected = (result as unknown as { affectedRows?: number })
        .affectedRows;
      return (affected ?? 0) > 0;
    },
    async list(prefix) {
      await sweep();
      const match = withNamespace(namespace, `${prefix ?? ""}%`);
      const [rows] = await pool.query(
        `SELECT \`key\` FROM \`${table}\` WHERE \`key\` LIKE ?`,
        [match],
      );
      return (rows as Array<{ key: string }>).map((r) =>
        stripNamespace(namespace, r.key),
      );
    },
    async close() {
      await pool.end();
    },
  };
}
