import type { ContextStore, SetOptions } from "../types.js";
import { withNamespace, stripNamespace, withTimeout } from "../config.js";

interface Options {
  url: string;
  namespace: string;
  collection: string;
  probeTimeoutMs: number;
}

interface MongoCollection {
  findOne(filter: Record<string, unknown>): Promise<{ value: string; expiresAt: number | null } | null>;
  updateOne(
    filter: Record<string, unknown>,
    update: Record<string, unknown>,
    opts: { upsert: boolean },
  ): Promise<unknown>;
  deleteOne(filter: Record<string, unknown>): Promise<{ deletedCount?: number }>;
  deleteMany(filter: Record<string, unknown>): Promise<unknown>;
  find(filter: Record<string, unknown>): { project(p: Record<string, 0 | 1>): { toArray(): Promise<Array<{ _id: string }>> } };
  createIndex(
    spec: Record<string, 1 | -1>,
    opts?: { partialFilterExpression?: Record<string, unknown> },
  ): Promise<unknown>;
}

interface MongoDb {
  collection(name: string): MongoCollection;
}

interface MongoClientLike {
  connect(): Promise<unknown>;
  close(): Promise<unknown>;
  db(): MongoDb;
}

interface MongoModule {
  MongoClient: new (url: string) => MongoClientLike;
}

async function loadMongo(): Promise<MongoModule> {
  try {
    return (await import("mongodb")) as unknown as MongoModule;
  } catch {
    throw new Error(
      "mongodb backend requested but the 'mongodb' package is not installed. " +
        "Run `npm install mongodb` or unset CCC_MONGO_URL.",
    );
  }
}

export async function openMongo({
  url,
  namespace,
  collection,
  probeTimeoutMs,
}: Options): Promise<ContextStore> {
  const mod = await loadMongo();
  const client = new mod.MongoClient(url);
  await withTimeout(client.connect(), probeTimeoutMs, "mongo connect");
  const col = client.db().collection(collection);
  await col.createIndex(
    { expiresAt: 1 },
    { partialFilterExpression: { expiresAt: { $type: "number" } } },
  );

  const sweep = async () => {
    await col.deleteMany({ expiresAt: { $lt: Date.now() } });
  };

  return {
    kind: "mongodb",
    async get(key) {
      await sweep();
      const doc = await col.findOne({ _id: withNamespace(namespace, key) });
      return doc ? doc.value : null;
    },
    async set(key, value, opts: SetOptions = {}) {
      const now = Date.now();
      const expiresAt = opts.ttlMs ? now + opts.ttlMs : null;
      await col.updateOne(
        { _id: withNamespace(namespace, key) },
        { $set: { value, expiresAt, updatedAt: now } },
        { upsert: true },
      );
    },
    async delete(key) {
      const result = await col.deleteOne({
        _id: withNamespace(namespace, key),
      });
      return (result.deletedCount ?? 0) > 0;
    },
    async list(prefix) {
      await sweep();
      const match = withNamespace(namespace, prefix ?? "");
      const filter = match ? { _id: { $regex: `^${escapeRegex(match)}` } } : {};
      const docs = await col.find(filter).project({ _id: 1 }).toArray();
      return docs.map((d) => stripNamespace(namespace, d._id));
    },
    async close() {
      await client.close();
    },
  };
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
