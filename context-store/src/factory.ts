import type { BackendKind, ContextStore, SetOptions, StoreConfig } from "./types.js";
import { loadConfig } from "./config.js";
import { openSqlite } from "./adapters/sqlite.js";
import { openRedis } from "./adapters/redis.js";
import { openMysql } from "./adapters/mysql.js";
import { openPostgres } from "./adapters/postgres.js";
import { openMongo } from "./adapters/mongodb.js";

export interface StoreInfo {
  cache: BackendKind;
  backing: BackendKind | null;
  attempts: Array<{ kind: BackendKind; ok: boolean; error?: string }>;
}

export interface ResolvedStore {
  store: ContextStore;
  info: StoreInfo;
}

async function tryOpenCache(
  cfg: ReturnType<typeof loadConfig>,
  attempts: StoreInfo["attempts"],
): Promise<ContextStore> {
  if (cfg.redisUrl && !cfg.disableRedis) {
    try {
      const s = await openRedis({
        url: cfg.redisUrl,
        namespace: cfg.namespace,
        probeTimeoutMs: cfg.probeTimeoutMs,
      });
      attempts.push({ kind: "redis", ok: true });
      return s;
    } catch (e) {
      attempts.push({
        kind: "redis",
        ok: false,
        error: (e as Error).message,
      });
    }
  }
  if (!cfg.disableSqliteMemory) {
    try {
      const s = openSqlite({
        path: ":memory:",
        namespace: cfg.namespace,
        kind: "sqlite-memory",
      });
      attempts.push({ kind: "sqlite-memory", ok: true });
      return s;
    } catch (e) {
      attempts.push({
        kind: "sqlite-memory",
        ok: false,
        error: (e as Error).message,
      });
    }
  }
  const s = openSqlite({
    path: cfg.sqlitePath,
    namespace: cfg.namespace,
    kind: "sqlite-disk",
  });
  attempts.push({ kind: "sqlite-disk", ok: true });
  return s;
}

async function tryOpenBacking(
  cfg: ReturnType<typeof loadConfig>,
  attempts: StoreInfo["attempts"],
): Promise<ContextStore | null> {
  if (cfg.mysqlUrl) {
    const s = await openMysql({
      url: cfg.mysqlUrl,
      namespace: cfg.namespace,
      table: cfg.tableName,
      probeTimeoutMs: cfg.probeTimeoutMs,
    });
    attempts.push({ kind: "mysql", ok: true });
    return s;
  }
  if (cfg.postgresUrl) {
    const s = await openPostgres({
      url: cfg.postgresUrl,
      namespace: cfg.namespace,
      table: cfg.tableName,
      probeTimeoutMs: cfg.probeTimeoutMs,
    });
    attempts.push({ kind: "postgres", ok: true });
    return s;
  }
  if (cfg.mongoUrl) {
    const s = await openMongo({
      url: cfg.mongoUrl,
      namespace: cfg.namespace,
      collection: cfg.tableName,
      probeTimeoutMs: cfg.probeTimeoutMs,
    });
    attempts.push({ kind: "mongodb", ok: true });
    return s;
  }
  return null;
}

class TieredStore implements ContextStore {
  readonly kind: BackendKind;
  constructor(
    private cache: ContextStore,
    private backing: ContextStore | null,
  ) {
    this.kind = cache.kind;
  }
  async get(key: string): Promise<string | null> {
    const cached = await this.cache.get(key);
    if (cached !== null) return cached;
    if (!this.backing) return null;
    const persisted = await this.backing.get(key);
    if (persisted !== null) {
      await this.cache.set(key, persisted);
    }
    return persisted;
  }
  async set(key: string, value: string, opts?: SetOptions): Promise<void> {
    await this.cache.set(key, value, opts);
    if (this.backing) await this.backing.set(key, value, opts);
  }
  async delete(key: string): Promise<boolean> {
    const a = await this.cache.delete(key);
    const b = this.backing ? await this.backing.delete(key) : false;
    return a || b;
  }
  async list(prefix?: string): Promise<string[]> {
    const cacheKeys = await this.cache.list(prefix);
    if (!this.backing) return cacheKeys;
    const backingKeys = await this.backing.list(prefix);
    return Array.from(new Set([...cacheKeys, ...backingKeys])).sort();
  }
  async close(): Promise<void> {
    await this.cache.close();
    if (this.backing) await this.backing.close();
  }
}

export async function createStore(
  config: StoreConfig = {},
): Promise<ResolvedStore> {
  const cfg = loadConfig(config);
  const attempts: StoreInfo["attempts"] = [];
  const cache = await tryOpenCache(cfg, attempts);
  const backing = await tryOpenBacking(cfg, attempts);
  const store = backing ? new TieredStore(cache, backing) : cache;
  return {
    store,
    info: {
      cache: cache.kind,
      backing: backing?.kind ?? null,
      attempts,
    },
  };
}
