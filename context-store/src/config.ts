import type { StoreConfig } from "./types.js";

const DEFAULT_SQLITE_PATH = ".ccc-cache/store.sqlite";
const DEFAULT_TABLE_NAME = "ccc_context";
const DEFAULT_PROBE_TIMEOUT_MS = 1500;

export function loadConfig(overrides: StoreConfig = {}): Required<
  Omit<StoreConfig, "redisUrl" | "mysqlUrl" | "postgresUrl" | "mongoUrl">
> &
  Pick<StoreConfig, "redisUrl" | "mysqlUrl" | "postgresUrl" | "mongoUrl"> {
  const env = process.env;
  return {
    redisUrl: overrides.redisUrl ?? env.CCC_REDIS_URL ?? env.REDIS_URL,
    sqlitePath:
      overrides.sqlitePath ?? env.CCC_SQLITE_PATH ?? DEFAULT_SQLITE_PATH,
    disableRedis:
      overrides.disableRedis ?? env.CCC_DISABLE_REDIS === "1",
    disableSqliteMemory:
      overrides.disableSqliteMemory ?? env.CCC_DISABLE_SQLITE_MEMORY === "1",
    mysqlUrl: overrides.mysqlUrl ?? env.CCC_MYSQL_URL,
    postgresUrl: overrides.postgresUrl ?? env.CCC_POSTGRES_URL,
    mongoUrl: overrides.mongoUrl ?? env.CCC_MONGO_URL,
    tableName:
      overrides.tableName ?? env.CCC_TABLE_NAME ?? DEFAULT_TABLE_NAME,
    namespace: overrides.namespace ?? env.CCC_NAMESPACE ?? "",
    probeTimeoutMs:
      overrides.probeTimeoutMs ??
      (Number(env.CCC_PROBE_TIMEOUT_MS) || DEFAULT_PROBE_TIMEOUT_MS),
  };
}

export function withNamespace(ns: string, key: string): string {
  return ns ? `${ns}:${key}` : key;
}

export function stripNamespace(ns: string, key: string): string {
  if (!ns) return key;
  const prefix = `${ns}:`;
  return key.startsWith(prefix) ? key.slice(prefix.length) : key;
}

export function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      },
    );
  });
}
