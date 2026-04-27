#!/usr/bin/env node
/**
 * Auto-engage CCC when this package is installed as a dependency.
 *
 * Behaviour:
 *  - Drops `assets/context-cache.md` into the consuming project's
 *    `.claude/agents/context-cache.md` so Claude Code picks it up.
 *  - Runs `ccc init` to create `.ccc/state.json` if missing.
 *  - Idempotent: re-running on a subsequent `npm install` is a no-op.
 *
 * Skip rules:
 *  - CCC_NO_AUTOENGAGE=1            -> skip everything
 *  - CI=true (any non-empty value)  -> skip (unsurprising in pipelines)
 *  - npm_config_global=true         -> skip (global installs)
 *  - INIT_CWD missing or equal to package dir -> skip (we're being installed
 *    as the package itself, not as a dependency).
 */

const fs = require("node:fs");
const path = require("node:path");

function log(message) {
  process.stdout.write(`[ccc] ${message}\n`);
}

function shouldSkip() {
  if (process.env.CCC_NO_AUTOENGAGE === "1") {
    return "CCC_NO_AUTOENGAGE=1 set";
  }
  if (process.env.CI && process.env.CI !== "false" && process.env.CI !== "0") {
    return "CI environment detected";
  }
  if (process.env.npm_config_global === "true") {
    return "global install";
  }
  return null;
}

function consumerRoot() {
  // npm sets INIT_CWD to the directory where the user ran `npm install`.
  // When the package is installed in its own dev tree, INIT_CWD === packageDir.
  const initCwd = process.env.INIT_CWD;
  const packageDir = path.resolve(__dirname, "..");
  if (!initCwd) return null;
  if (path.resolve(initCwd) === packageDir) return null;
  return initCwd;
}

function copyAgent(consumerDir) {
  const agentSrc = path.resolve(__dirname, "..", "assets", "context-cache.md");
  if (!fs.existsSync(agentSrc)) return false;
  const targetDir = path.join(consumerDir, ".claude", "agents");
  const targetFile = path.join(targetDir, "context-cache.md");
  if (fs.existsSync(targetFile)) return false; // never overwrite user content
  fs.mkdirSync(targetDir, { recursive: true });
  fs.copyFileSync(agentSrc, targetFile);
  return true;
}

function ensureCccDir(consumerDir) {
  const stateFile = path.join(consumerDir, ".ccc", "state.json");
  if (fs.existsSync(stateFile)) return false;
  fs.mkdirSync(path.dirname(stateFile), { recursive: true });
  fs.mkdirSync(path.join(consumerDir, ".ccc", "handoffs"), { recursive: true });
  const now = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const initial = {
    code_style: "",
    original_prompt: "",
    current_phase: "",
    current_sprint: "",
    todos: [],
    completed: [],
    sprints: [],
    phases: [],
    context_sources: [],
    session_input_tokens: 0,
    session_output_tokens: 0,
    cache_read_tokens: 0,
    cache_creation_tokens: 0,
    last_handoff_path: null,
    created_at: now,
    updated_at: now,
  };
  fs.writeFileSync(stateFile, JSON.stringify(initial, null, 2), "utf8");
  return true;
}

function main() {
  const skip = shouldSkip();
  if (skip) {
    log(`auto-engage skipped (${skip})`);
    return;
  }
  const consumer = consumerRoot();
  if (!consumer) {
    // Either INIT_CWD missing or this is the package's own dev install.
    return;
  }
  const actions = [];
  try {
    if (copyAgent(consumer)) {
      actions.push(".claude/agents/context-cache.md");
    }
  } catch (err) {
    log(`warning: could not install agent file: ${err.message}`);
  }
  try {
    if (ensureCccDir(consumer)) {
      actions.push(".ccc/state.json");
    }
  } catch (err) {
    log(`warning: could not initialize .ccc/: ${err.message}`);
  }

  if (actions.length === 0) {
    log("auto-engage: nothing to do (already initialized)");
    return;
  }
  log(`auto-engaged in ${consumer}`);
  for (const a of actions) log(`  + ${a}`);
  log("Run `npx ccc init --prompt \"<your task>\"` to set the original prompt.");
  log(
    "Set CCC_NO_AUTOENGAGE=1 in your environment if you'd rather opt out of this on future installs.",
  );
}

try {
  main();
} catch (err) {
  // Postinstall must never break `npm install`. Log and exit 0.
  log(`auto-engage failed: ${err && err.message ? err.message : err}`);
  process.exit(0);
}
