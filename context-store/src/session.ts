import { createStore, type ResolvedStore } from "./factory.js";
import type { ContextStore, SetOptions, StoreConfig } from "./types.js";

export interface SessionOptions extends StoreConfig {
  /**
   * Auto-close the session after this many ms of idleness. Set to 0 to disable.
   * Defaults to 5 minutes.
   */
  idleTimeoutMs?: number;
  /**
   * Register process-exit handlers (SIGINT/SIGTERM/exit) to close the
   * underlying connections cleanly. Defaults to true.
   */
  installSignalHandlers?: boolean;
}

const DEFAULT_IDLE_MS = 5 * 60 * 1000;

export class Session implements ContextStore {
  private opened: ResolvedStore | null = null;
  private opening: Promise<ResolvedStore> | null = null;
  private idleTimer: NodeJS.Timeout | null = null;
  private cleanupRegistered = false;
  private readonly idleMs: number;
  private readonly installSignals: boolean;

  constructor(private readonly options: SessionOptions = {}) {
    this.idleMs = options.idleTimeoutMs ?? DEFAULT_IDLE_MS;
    this.installSignals = options.installSignalHandlers ?? true;
  }

  get kind() {
    return this.opened?.store.kind ?? ("sqlite-memory" as const);
  }

  async info() {
    const r = await this.ensureOpen();
    return r.info;
  }

  async start(): Promise<void> {
    await this.ensureOpen();
  }

  async get(key: string): Promise<string | null> {
    const r = await this.ensureOpen();
    this.touch();
    return r.store.get(key);
  }

  async set(key: string, value: string, opts?: SetOptions): Promise<void> {
    const r = await this.ensureOpen();
    this.touch();
    return r.store.set(key, value, opts);
  }

  async delete(key: string): Promise<boolean> {
    const r = await this.ensureOpen();
    this.touch();
    return r.store.delete(key);
  }

  async list(prefix?: string): Promise<string[]> {
    const r = await this.ensureOpen();
    this.touch();
    return r.store.list(prefix);
  }

  async close(): Promise<void> {
    if (this.idleTimer) {
      clearTimeout(this.idleTimer);
      this.idleTimer = null;
    }
    const opened = this.opened;
    this.opened = null;
    this.opening = null;
    if (opened) await opened.store.close();
  }

  private async ensureOpen(): Promise<ResolvedStore> {
    if (this.opened) return this.opened;
    if (!this.opening) {
      this.opening = createStore(this.options).then((r) => {
        this.opened = r;
        if (this.installSignals) this.registerCleanup();
        return r;
      });
    }
    return this.opening;
  }

  private touch(): void {
    if (this.idleMs <= 0) return;
    if (this.idleTimer) clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => {
      void this.close();
    }, this.idleMs);
    this.idleTimer.unref?.();
  }

  private registerCleanup(): void {
    if (this.cleanupRegistered) return;
    this.cleanupRegistered = true;
    const handler = () => {
      void this.close();
    };
    process.once("SIGINT", handler);
    process.once("SIGTERM", handler);
    process.once("beforeExit", handler);
  }
}

export async function withSession<T>(
  fn: (s: Session) => Promise<T>,
  options: SessionOptions = {},
): Promise<T> {
  const session = new Session({ ...options, installSignalHandlers: false });
  try {
    return await fn(session);
  } finally {
    await session.close();
  }
}
