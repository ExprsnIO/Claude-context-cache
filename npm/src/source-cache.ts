/**
 * Caches the *read* content of `state.context_sources` between `ccc ask`
 * calls so we don't re-read the same files from disk every time. Cache key
 * is a fingerprint of the source's mtimes + sizes, so any on-disk change
 * invalidates automatically.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, relative } from "node:path";

import { Session, type SessionOptions } from "@claude-context-cache/context-store";

import type { State } from "./state.js";

const SOURCE_NAMESPACE = "ccc-npm-sources";

let sharedSession: Session | null = null;

export function getSourceSession(options: SessionOptions = {}): Session {
  if (!sharedSession) {
    sharedSession = new Session({
      namespace: SOURCE_NAMESPACE,
      ...options,
    });
  }
  return sharedSession;
}

export async function closeSourceSession(): Promise<void> {
  if (sharedSession) {
    const s = sharedSession;
    sharedSession = null;
    await s.close();
  }
}

function fingerprint(path: string): string {
  const stat = statSync(path);
  if (!stat.isDirectory()) {
    return `f:${stat.mtimeMs}:${stat.size}`;
  }
  const parts: string[] = [];
  const walk = (dir: string): void => {
    const entries = readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
      a.name.localeCompare(b.name),
    );
    for (const entry of entries) {
      if (entry.name.startsWith(".")) continue;
      const child = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(child);
      } else if (entry.isFile()) {
        try {
          const s = statSync(child);
          parts.push(`${relative(path, child)}:${s.mtimeMs}:${s.size}`);
        } catch {
          /* skip */
        }
      }
    }
  };
  walk(path);
  return `d:${createHash("sha1").update(parts.join("|")).digest("hex")}`;
}

function readSourceText(path: string): string {
  const stat = statSync(path);
  if (!stat.isDirectory()) {
    return readFileSync(path, "utf8");
  }
  const chunks: string[] = [];
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      const child = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(child);
      } else if (entry.isFile()) {
        try {
          const text = readFileSync(child, "utf8");
          const rel = relative(path, child);
          chunks.push(`--- ${rel} ---\n${text}`);
        } catch {
          /* skip non-utf8 / unreadable */
        }
      }
    }
  };
  walk(path);
  return chunks.join("\n\n");
}

export async function readSourceCached(
  path: string,
): Promise<{ text: string; cacheHit: boolean }> {
  let key: string;
  try {
    key = `${path}:${fingerprint(path)}`;
  } catch {
    // path vanished — let the caller deal with the read error.
    return { text: readSourceText(path), cacheHit: false };
  }
  const session = getSourceSession();
  try {
    const cached = await session.get(key);
    if (cached !== null) return { text: cached, cacheHit: true };
    const text = readSourceText(path);
    await session.set(key, text);
    return { text, cacheHit: false };
  } catch {
    // Store failure is non-fatal — fall back to a direct read.
    return { text: readSourceText(path), cacheHit: false };
  }
}

export async function gatherContextSourcesCached(
  state: State,
): Promise<Array<[string, string]>> {
  const sources: Array<[string, string]> = [];
  for (const src of state.context_sources) {
    try {
      const { text } = await readSourceCached(src.path);
      sources.push([src.label, text]);
    } catch {
      /* skip vanished / unreadable */
    }
  }
  return sources;
}
