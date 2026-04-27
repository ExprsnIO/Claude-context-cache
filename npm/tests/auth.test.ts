/**
 * Tests for the npm port of the API-key detection cascade.
 *
 * The cascade is `env > .env > platform config` (the npm port has no
 * keyring step). Earlier hits shadow later ones. We never put a real
 * key in tests; the placeholder `sk-ant-` shape is enough to satisfy
 * the shape check.
 */

import { test, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { detectApiKey, parseDotenv, redact, searchSummary } from "../src/auth.js";

const VALID = "sk-ant-" + "a".repeat(32);
const ALT = "sk-ant-" + "b".repeat(32);

let savedEnv: Record<string, string | undefined> = {};
let tmpRoot: string;
let fakeHome: string;
let fakeXdg: string;

before(() => {
  // Snapshot env vars we'll mutate per-test so we restore at the end.
  savedEnv = {
    ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,
    CLAUDE_API_KEY: process.env.CLAUDE_API_KEY,
    HOME: process.env.HOME,
    XDG_CONFIG_HOME: process.env.XDG_CONFIG_HOME,
    APPDATA: process.env.APPDATA,
  };
});

after(() => {
  for (const [k, v] of Object.entries(savedEnv)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
  if (tmpRoot) rmSync(tmpRoot, { recursive: true, force: true });
});

beforeEach(() => {
  // Fresh tmp + clean env each test.
  if (tmpRoot) rmSync(tmpRoot, { recursive: true, force: true });
  tmpRoot = mkdtempSync(join(tmpdir(), "ccc-auth-"));
  fakeHome = join(tmpRoot, "home");
  fakeXdg = join(tmpRoot, "xdg");
  mkdirSync(fakeHome, { recursive: true });
  delete process.env.ANTHROPIC_API_KEY;
  delete process.env.CLAUDE_API_KEY;
  process.env.HOME = fakeHome;
  process.env.XDG_CONFIG_HOME = fakeXdg;
  process.env.APPDATA = join(tmpRoot, "appdata");
});

test("env var wins when set", () => {
  process.env.ANTHROPIC_API_KEY = VALID;
  const hit = detectApiKey();
  assert.ok(hit);
  assert.equal(hit.key, VALID);
  assert.equal(hit.source, "$ANTHROPIC_API_KEY");
});

test("CLAUDE_API_KEY alias works when ANTHROPIC_API_KEY is unset", () => {
  process.env.CLAUDE_API_KEY = VALID;
  const hit = detectApiKey();
  assert.ok(hit);
  assert.equal(hit.source, "$CLAUDE_API_KEY");
});

test("ANTHROPIC_API_KEY shadows CLAUDE_API_KEY", () => {
  process.env.ANTHROPIC_API_KEY = VALID;
  process.env.CLAUDE_API_KEY = ALT;
  const hit = detectApiKey();
  assert.ok(hit);
  assert.equal(hit.key, VALID);
});

test("project .env is used when no env var is present", () => {
  const projectRoot = join(tmpRoot, "proj");
  mkdirSync(projectRoot, { recursive: true });
  writeFileSync(join(projectRoot, ".env"), `ANTHROPIC_API_KEY="${VALID}"\n`);
  const hit = detectApiKey({ projectRoot });
  assert.ok(hit);
  assert.equal(hit.key, VALID);
  assert.ok(hit.source.endsWith(".env"));
});

test("env var shadows .env file", () => {
  process.env.ANTHROPIC_API_KEY = VALID;
  const projectRoot = join(tmpRoot, "proj");
  mkdirSync(projectRoot, { recursive: true });
  writeFileSync(join(projectRoot, ".env"), `ANTHROPIC_API_KEY=${ALT}\n`);
  const hit = detectApiKey({ projectRoot });
  assert.ok(hit);
  assert.equal(hit.key, VALID);
});

test("XDG config file picked up on Linux/Unix", () => {
  if (process.platform === "win32") {
    return; // Windows uses APPDATA; covered separately
  }
  const cfg = join(fakeXdg, "anthropic", "api_key");
  mkdirSync(join(fakeXdg, "anthropic"), { recursive: true });
  writeFileSync(cfg, VALID + "\n");
  const hit = detectApiKey();
  assert.ok(hit);
  assert.equal(hit.key, VALID);
});

test("legacy ~/.anthropic/api_key is detected", () => {
  const cfg = join(fakeHome, ".anthropic", "api_key");
  mkdirSync(join(fakeHome, ".anthropic"), { recursive: true });
  writeFileSync(cfg, VALID);
  const hit = detectApiKey();
  assert.ok(hit);
  assert.equal(hit.key, VALID);
});

test("invalid placeholder in .env is ignored", () => {
  const projectRoot = join(tmpRoot, "proj");
  mkdirSync(projectRoot, { recursive: true });
  writeFileSync(
    join(projectRoot, ".env"),
    "ANTHROPIC_API_KEY=put-your-real-key-here\n",
  );
  assert.equal(detectApiKey({ projectRoot }), null);
});

test("redact hides most of the key", () => {
  const r = redact(VALID);
  assert.ok(!r.includes(VALID));
  assert.ok(r.startsWith(VALID.slice(0, 8)));
  assert.ok(r.endsWith(VALID.slice(-4)));
});

test("searchSummary lists candidates including OS keyring note", () => {
  process.env.ANTHROPIC_API_KEY = VALID;
  const rows = searchSummary();
  const map = new Map(rows);
  assert.equal(map.get("$ANTHROPIC_API_KEY"), true);
  assert.equal(map.get("$CLAUDE_API_KEY"), false);
  // The npm port surfaces the keyring gap explicitly.
  const keyringRow = rows.find(([label]) => label.includes("OS keyring"));
  assert.ok(keyringRow, "OS keyring note should be present in search summary");
  assert.equal(keyringRow![1], false);
});

test("parseDotenv handles quotes, comments, export, and bad lines", () => {
  const p = join(tmpRoot, "test.env");
  writeFileSync(
    p,
    [
      "# comment",
      "",
      "export ANTHROPIC_API_KEY='single-quoted'",
      'CLAUDE_API_KEY="double-quoted"',
      "BARE=value-no-quotes",
      "EMPTY=",
      "BAD_LINE_NO_EQUALS",
    ].join("\n"),
  );
  const map = new Map(parseDotenv(p));
  assert.equal(map.get("ANTHROPIC_API_KEY"), "single-quoted");
  assert.equal(map.get("CLAUDE_API_KEY"), "double-quoted");
  assert.equal(map.get("BARE"), "value-no-quotes");
  assert.equal(map.get("EMPTY"), "");
  assert.equal(map.has("BAD_LINE_NO_EQUALS"), false);
});

test("no key anywhere returns null", () => {
  assert.equal(detectApiKey(), null);
});
