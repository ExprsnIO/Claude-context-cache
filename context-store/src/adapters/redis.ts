import type { ContextStore, SetOptions } from "../types.js";
import { withNamespace, stripNamespace, withTimeout } from "../config.js";

interface Options {
  url: string;
  namespace: string;
  probeTimeoutMs: number;
}

interface RedisLike {
  connect(): Promise<unknown>;
  quit(): Promise<unknown>;
  get(key: string): Promise<string | null>;
  set(key: string, value: string, opts?: { PX?: number }): Promise<unknown>;
  del(key: string): Promise<number>;
  scanIterator(opts: { MATCH: string }): AsyncIterable<string>;
  ping(): Promise<string>;
  on(event: string, listener: (err: unknown) => void): unknown;
}

interface RedisModule {
  createClient(opts: { url: string }): RedisLike;
}

async function loadRedis(): Promise<RedisModule> {
  try {
    return (await import("redis")) as unknown as RedisModule;
  } catch {
    throw new Error(
      "redis backend requested but the 'redis' package is not installed. " +
        "Run `npm install redis` or unset CCC_REDIS_URL.",
    );
  }
}

export async function openRedis({
  url,
  namespace,
  probeTimeoutMs,
}: Options): Promise<ContextStore> {
  const mod = await loadRedis();
  const client = mod.createClient({ url });
  client.on("error", () => {
    /* surfaced via probe / ops */
  });
  await withTimeout(client.connect(), probeTimeoutMs, "redis connect");
  await withTimeout(client.ping(), probeTimeoutMs, "redis ping");

  return {
    kind: "redis",
    async get(key) {
      return client.get(withNamespace(namespace, key));
    },
    async set(key, value, opts: SetOptions = {}) {
      const args = opts.ttlMs ? { PX: opts.ttlMs } : undefined;
      await client.set(withNamespace(namespace, key), value, args);
    },
    async delete(key) {
      const n = await client.del(withNamespace(namespace, key));
      return n > 0;
    },
    async list(prefix) {
      const match = withNamespace(namespace, `${prefix ?? ""}*`);
      const keys: string[] = [];
      for await (const k of client.scanIterator({ MATCH: match })) {
        keys.push(stripNamespace(namespace, k));
      }
      return keys;
    },
    async close() {
      await client.quit();
    },
  };
}
