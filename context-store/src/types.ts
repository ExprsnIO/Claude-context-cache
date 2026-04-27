export type BackendKind =
  | "redis"
  | "sqlite-memory"
  | "sqlite-disk"
  | "mysql"
  | "postgres"
  | "mongodb";

export interface ContextEntry {
  key: string;
  value: string;
  expiresAt: number | null;
  updatedAt: number;
}

export interface SetOptions {
  /** Time-to-live in milliseconds. */
  ttlMs?: number;
}

export interface ContextStore {
  readonly kind: BackendKind;
  get(key: string): Promise<string | null>;
  set(key: string, value: string, opts?: SetOptions): Promise<void>;
  delete(key: string): Promise<boolean>;
  list(prefix?: string): Promise<string[]>;
  close(): Promise<void>;
}

export interface CacheTierConfig {
  /** Redis connection URL, e.g. redis://localhost:6379. */
  redisUrl?: string;
  /** Path for the on-disk SQLite fallback. */
  sqlitePath?: string;
  /** Skip Redis probing even if a URL is set. */
  disableRedis?: boolean;
  /** Skip SQLite in-memory tier. */
  disableSqliteMemory?: boolean;
}

export interface PersistentBackingConfig {
  /** mysql://user:pass@host:port/db */
  mysqlUrl?: string;
  /** postgres://user:pass@host:port/db */
  postgresUrl?: string;
  /** mongodb://user:pass@host:port/db */
  mongoUrl?: string;
  /** Table / collection name. Defaults to "ccc_context". */
  tableName?: string;
}

export interface StoreConfig extends CacheTierConfig, PersistentBackingConfig {
  /**
   * Namespace prefix prepended to every key. Lets multiple projects share a
   * Redis or SQL instance without colliding.
   */
  namespace?: string;
  /** Probe timeout for backend connection attempts (ms). Defaults to 1500. */
  probeTimeoutMs?: number;
}
