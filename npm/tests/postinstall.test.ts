import { test } from "node:test";
import assert from "node:assert/strict";
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
  mkdirSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname_ = dirname(fileURLToPath(import.meta.url));
// In compiled output the test lives at dist-test/tests/, so the package root
// is two levels up (.., ..). The postinstall script lives next to package.json.
const POSTINSTALL = resolve(__dirname_, "..", "..", "scripts", "postinstall.cjs");

function runPostinstall(env: Record<string, string>): {
  status: number | null;
  stdout: string;
  stderr: string;
} {
  const result = spawnSync(process.execPath, [POSTINSTALL], {
    env: { ...process.env, ...env },
    encoding: "utf8",
  });
  return {
    status: result.status,
    stdout: result.stdout,
    stderr: result.stderr,
  };
}

test("postinstall auto-engages in a fresh consumer directory", () => {
  const consumer = mkdtempSync(join(tmpdir(), "ccc-postinstall-"));
  try {
    const result = runPostinstall({
      INIT_CWD: consumer,
      CI: "",
      CCC_NO_AUTOENGAGE: "",
      npm_config_global: "",
    });
    assert.equal(result.status, 0, `stderr: ${result.stderr}`);
    assert.ok(existsSync(join(consumer, ".claude", "agents", "context-cache.md")));
    assert.ok(existsSync(join(consumer, ".ccc", "state.json")));
    const state = JSON.parse(
      readFileSync(join(consumer, ".ccc", "state.json"), "utf8"),
    );
    assert.equal(state.original_prompt, "");
    assert.deepEqual(state.todos, []);
  } finally {
    rmSync(consumer, { recursive: true, force: true });
  }
});

test("postinstall is idempotent — does not overwrite existing user content", () => {
  const consumer = mkdtempSync(join(tmpdir(), "ccc-postinstall-"));
  try {
    mkdirSync(join(consumer, ".claude", "agents"), { recursive: true });
    writeFileSync(
      join(consumer, ".claude", "agents", "context-cache.md"),
      "USER WROTE THIS",
      "utf8",
    );
    runPostinstall({
      INIT_CWD: consumer,
      CI: "",
      CCC_NO_AUTOENGAGE: "",
      npm_config_global: "",
    });
    const after = readFileSync(
      join(consumer, ".claude", "agents", "context-cache.md"),
      "utf8",
    );
    assert.equal(after, "USER WROTE THIS");
  } finally {
    rmSync(consumer, { recursive: true, force: true });
  }
});

test("postinstall skips when CCC_NO_AUTOENGAGE=1", () => {
  const consumer = mkdtempSync(join(tmpdir(), "ccc-postinstall-"));
  try {
    const result = runPostinstall({
      INIT_CWD: consumer,
      CCC_NO_AUTOENGAGE: "1",
      CI: "",
      npm_config_global: "",
    });
    assert.equal(result.status, 0);
    assert.match(result.stdout, /skipped/);
    assert.equal(existsSync(join(consumer, ".ccc")), false);
  } finally {
    rmSync(consumer, { recursive: true, force: true });
  }
});

test("postinstall skips when CI=true", () => {
  const consumer = mkdtempSync(join(tmpdir(), "ccc-postinstall-"));
  try {
    const result = runPostinstall({
      INIT_CWD: consumer,
      CI: "true",
      CCC_NO_AUTOENGAGE: "",
      npm_config_global: "",
    });
    assert.equal(result.status, 0);
    assert.match(result.stdout, /skipped/);
    assert.equal(existsSync(join(consumer, ".ccc")), false);
  } finally {
    rmSync(consumer, { recursive: true, force: true });
  }
});
