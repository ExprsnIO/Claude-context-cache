/**
 * API key detection across well-known locations.
 *
 * Mirrors the Python `ccc.auth.detect_api_key` cascade. Order:
 *
 *   1. Environment variables: ANTHROPIC_API_KEY, then CLAUDE_API_KEY.
 *   2. `.env` file in the project root (if `detectApiKey({ projectRoot })`).
 *   3. `.env` file in the user's home directory.
 *   4. Platform-specific user-config file:
 *        - Windows: %APPDATA%\anthropic\api_key
 *        - macOS:   ~/Library/Application Support/anthropic/api_key
 *        - Linux/Unix: $XDG_CONFIG_HOME/anthropic/api_key
 *                     (default ~/.config/anthropic/api_key)
 *   5. ~/.anthropic/api_key (legacy convention).
 *
 * The npm port deliberately stops here. Reading the OS keyring from Node
 * requires a native binding (`keytar` is deprecated; `@napi-rs/keyring`
 * works but adds a non-trivial install step). Users who keep their key
 * in the OS keyring should export it into `ANTHROPIC_API_KEY` for the
 * shell that runs `ccc`, or use the Python package which has first-class
 * keyring support via the optional `keyring` extra.
 */

import { existsSync, readFileSync, statSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join, resolve } from "node:path";

export const ENV_VARS = ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"] as const;

export interface ApiKeyHit {
  key: string;
  source: string;
}

/** Safe-to-print form: 8 leading chars + ellipsis + 4 trailing. */
export function redact(key: string): string {
  if (key.length <= 12) return "***";
  return `${key.slice(0, 8)}…${key.slice(-4)}`;
}

export interface DetectOptions {
  projectRoot?: string;
}

export function detectApiKey(opts: DetectOptions = {}): ApiKeyHit | null {
  const root = opts.projectRoot ? resolve(opts.projectRoot) : null;

  for (const env of ENV_VARS) {
    const val = process.env[env];
    if (val && looksLikeKey(val)) {
      return { key: val.trim(), source: `$${env}` };
    }
  }

  for (const envPath of dotenvCandidates(root)) {
    for (const [k, v] of parseDotenv(envPath)) {
      if ((ENV_VARS as readonly string[]).includes(k) && looksLikeKey(v)) {
        return { key: v.trim(), source: envPath };
      }
    }
  }

  for (const cfg of configCandidates()) {
    const val = readFirstLine(cfg);
    if (val && looksLikeKey(val)) {
      return { key: val.trim(), source: cfg };
    }
  }

  return null;
}

/** Per-candidate report for `ccc auth -v`. `present` = the candidate yielded
 * a syntactically valid key, regardless of who wins the cascade. */
export function searchSummary(
  opts: DetectOptions = {},
): Array<[string, boolean]> {
  const root = opts.projectRoot ? resolve(opts.projectRoot) : null;
  const rows: Array<[string, boolean]> = [];

  for (const env of ENV_VARS) {
    const val = process.env[env];
    rows.push([`$${env}`, !!(val && looksLikeKey(val))]);
  }

  for (const envPath of dotenvCandidates(root)) {
    let hit = false;
    for (const [k, v] of parseDotenv(envPath)) {
      if ((ENV_VARS as readonly string[]).includes(k) && looksLikeKey(v)) {
        hit = true;
        break;
      }
    }
    rows.push([envPath, hit]);
  }

  for (const cfg of configCandidates()) {
    const val = readFirstLine(cfg);
    rows.push([cfg, !!(val && looksLikeKey(val))]);
  }

  rows.push([
    "OS keyring (npm port: not supported; export to env var instead)",
    false,
  ]);
  return rows;
}

function looksLikeKey(val: string): boolean {
  const s = val.trim();
  return s.startsWith("sk-ant-") && s.length >= 32;
}

function dotenvCandidates(projectRoot: string | null): string[] {
  const out: string[] = [];
  if (projectRoot) out.push(join(projectRoot, ".env"));
  out.push(join(homedir(), ".env"));
  return out;
}

function configCandidates(): string[] {
  const home = homedir();
  const out: string[] = [];
  if (platform() === "win32") {
    const appdata = process.env.APPDATA;
    if (appdata) out.push(join(appdata, "anthropic", "api_key"));
  } else if (platform() === "darwin") {
    out.push(
      join(home, "Library", "Application Support", "anthropic", "api_key"),
    );
  }
  const xdg = process.env.XDG_CONFIG_HOME ?? join(home, ".config");
  out.push(join(xdg, "anthropic", "api_key"));
  out.push(join(home, ".anthropic", "api_key"));
  // Dedupe in order.
  return Array.from(new Set(out));
}

/** Tiny `.env` parser: blank lines and `#` comments ignored, optional
 * `export ` prefix stripped, single- and double-quoted values unwrapped.
 * No interpolation, no multi-line values, no escapes. */
export function parseDotenv(path: string): Array<[string, string]> {
  if (!existsSync(path)) return [];
  let text: string;
  try {
    if (!statSync(path).isFile()) return [];
    text = readFileSync(path, "utf8");
  } catch {
    return [];
  }
  const out: Array<[string, string]> = [];
  for (const raw of text.split(/\r?\n/)) {
    let line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("export ")) line = line.slice("export ".length);
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const k = line.slice(0, eq).trim();
    let v = line.slice(eq + 1).trim();
    if (
      v.length >= 2 &&
      ((v[0] === '"' && v[v.length - 1] === '"') ||
        (v[0] === "'" && v[v.length - 1] === "'"))
    ) {
      v = v.slice(1, -1);
    }
    if (k) out.push([k, v]);
  }
  return out;
}

function readFirstLine(path: string): string | null {
  if (!existsSync(path)) return null;
  try {
    const stat = statSync(path);
    if (!stat.isFile() || stat.size === 0) return null;
    const text = readFileSync(path, "utf8");
    const first = text.split(/\r?\n/, 1)[0];
    return first ? first.trim() : null;
  } catch {
    return null;
  }
}
