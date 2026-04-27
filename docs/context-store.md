# Context store

`@claude-context-cache/context-store` is the tiered cache that sits behind the Node implementation's source-read cache. One small Node.js package, one `ContextStore` interface, six pluggable backends.

## Cache tier (auto-fallback)

The cache backend is chosen at session start by probing in order:

1. **Redis** — if `CCC_REDIS_URL` (or `REDIS_URL`) is set and reachable.
2. **SQLite (in-memory)** — fast ephemeral fallback, no native I/O.
3. **SQLite (on-disk)** — last-resort durable fallback at `./.ccc-cache/store.sqlite`.

Each step has a probe timeout (default 1500 ms). The first one that opens cleanly wins; failed probes are recorded on `info.attempts` so you can see which backend served a session.

## Optional persistent backing

Set any of these and the cache becomes a write-through in front of the persistent store:

| Env var | Driver (peer dep) |
|---|---|
| `CCC_MYSQL_URL` | `mysql2` |
| `CCC_POSTGRES_URL` | `pg` |
| `CCC_MONGO_URL` | `mongodb` |

Drivers are loaded lazily — install only the one you need.

## Install

```bash
npm install @claude-context-cache/context-store

# Optional, only when you need them:
npm install redis            # Redis cache tier
npm install mysql2           # MySQL backing
npm install pg               # Postgres backing
npm install mongodb          # MongoDB backing
```

`better-sqlite3` is a regular dependency, so the SQLite tiers always work out of the box.

## Quick start

```ts
import { Session } from "@claude-context-cache/context-store";

const ctx = new Session();        // auto-selects backend on first call
await ctx.set("topic:src", "...long cached source...");
const value = await ctx.get("topic:src");
await ctx.list("topic:");         // → ["topic:src"]
await ctx.close();                // explicit teardown
```

One-shot:

```ts
import { withSession } from "@claude-context-cache/context-store";

await withSession(async (ctx) => {
  await ctx.set("k", "v", { ttlMs: 60_000 });
  return ctx.get("k");
});
```

## Sessions: spin up and tear down

`Session` is a lazy, lifecycle-aware wrapper around the underlying store:

- **Lazy open.** The backend is not opened until the first `get/set/delete/list` call. `await session.start()` forces an open if you want to surface connection errors early.
- **Idle teardown.** After `idleTimeoutMs` of inactivity (default 5 min) the underlying connections are closed; the next call transparently re-opens. Set `idleTimeoutMs: 0` to disable.
- **Process-exit teardown.** `SIGINT`, `SIGTERM`, and `beforeExit` are wired to a graceful close so connections don't leak. Disable with `installSignalHandlers: false`.
- **`withSession(fn)`** opens, runs, closes — useful in scripts, jobs, and tests.

## Configuration

All env vars have a programmatic equivalent (`new Session({ redisUrl: ... })`).

| Env var | Effect |
|---|---|
| `CCC_REDIS_URL` / `REDIS_URL` | Redis URL for the cache tier |
| `CCC_SQLITE_PATH` | Override the on-disk SQLite path |
| `CCC_DISABLE_REDIS=1` | Skip the Redis probe |
| `CCC_DISABLE_SQLITE_MEMORY=1` | Skip the in-memory tier (go straight to disk) |
| `CCC_MYSQL_URL` | Enable MySQL write-through backing |
| `CCC_POSTGRES_URL` | Enable Postgres write-through backing |
| `CCC_MONGO_URL` | Enable MongoDB write-through backing |
| `CCC_TABLE_NAME` | Override table / collection name (default `ccc_context`) |
| `CCC_NAMESPACE` | Key namespace prefix (default `""`) |
| `CCC_PROBE_TIMEOUT_MS` | Backend probe timeout (default `1500`) |

## API

```ts
interface ContextStore {
  readonly kind: BackendKind;
  get(key: string): Promise<string | null>;
  set(key: string, value: string, opts?: { ttlMs?: number }): Promise<void>;
  delete(key: string): Promise<boolean>;
  list(prefix?: string): Promise<string[]>;
  close(): Promise<void>;
}

createStore(config?): Promise<{ store: ContextStore; info: StoreInfo }>;
new Session(options?);
withSession(fn, options?): Promise<T>;
```

`info.cache` is the active cache backend; `info.backing` is the persistent backing (or `null`); `info.attempts[]` records every probe.

## Inspecting the chosen backend

```ts
const session = new Session();
await session.start();
console.log(await session.info());
// { cache: "sqlite-memory", backing: null, attempts: [
//   { kind: "redis", ok: false, error: "redis connect timed out after 1500ms" },
//   { kind: "sqlite-memory", ok: true },
// ]}
```

## Notes

- **Namespaces** keep multiple projects from colliding when they share a Redis or SQL backend. Set `CCC_NAMESPACE=myproject` and every key is stored as `myproject:<key>`.
- **TTL** is uniform across backends: `set(k, v, { ttlMs: 60_000 })` works the same on Redis (`PX`), SQLite (sweep on read/list), and the SQL/Mongo backings.
- The `tableName` is validated for Postgres because it's interpolated into DDL; MySQL is escaped with backticks; Mongo uses it as the collection name.

## See also

- [Prompt caching](./prompt-caching.md) — the second cache layer that this store feeds.
- [Architecture](./architecture.md) — where context-store fits in the monorepo.
