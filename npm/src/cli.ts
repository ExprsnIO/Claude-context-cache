#!/usr/bin/env node
/** `ccc` command-line entry. */

import { existsSync, readFileSync, statSync, readdirSync } from "node:fs";
import { resolve, basename, join } from "node:path";

import { Command } from "commander";

import { ask, generateHandoff, DEFAULT_MODEL } from "./client.js";
import {
  compact,
  DEFAULT_THRESHOLD_TOKENS,
  sessionTokenEstimate,
  shouldCompact,
} from "./compact.js";
import {
  WORD_LIMIT,
  countWords,
  hydrateStateFromHandoff,
  truncateToLimit,
  validate,
  writeHandoff,
} from "./handoff.js";
import { State, StateStore, type AnthropicUsage } from "./state.js";

const PKG_VERSION = "0.1.0";

/** One-line per-call cache telemetry written to stderr.
 *
 * Surfaces `cache_creation_input_tokens` and `cache_read_input_tokens` for
 * the current call so cache effectiveness regressions are visible instead
 * of buried in aggregate counters.
 */
function formatUsageLine(usage: AnthropicUsage): string {
  const inp = usage.input_tokens ?? 0;
  const out = usage.output_tokens ?? 0;
  const cacheRead = usage.cache_read_input_tokens ?? 0;
  const cacheCreation = usage.cache_creation_input_tokens ?? 0;
  const cacheable = cacheRead + cacheCreation;
  const hitPct = cacheable > 0 ? (cacheRead / cacheable) * 100 : 0;
  return (
    `[ccc] tokens — input=${inp} output=${out} ` +
    `cache_read=${cacheRead} cache_creation=${cacheCreation} ` +
    `hit=${hitPct.toFixed(0)}%`
  );
}

function getStore(opts: { root?: string }): StateStore {
  return new StateStore(opts.root ?? ".");
}

function loadState(opts: { root?: string }): {
  store: StateStore;
  state: State;
} {
  const store = getStore(opts);
  const state = store.load();
  return { store, state };
}

function dirSize(path: string): number {
  let total = 0;
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    const child = join(path, entry.name);
    if (entry.isDirectory()) total += dirSize(child);
    else if (entry.isFile()) total += statSync(child).size;
  }
  return total;
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

const program = new Command();
program
  .name("ccc")
  .description(
    "Cache Claude topic contexts and emit <=750-word handoff documents.",
  )
  .version(PKG_VERSION)
  .option(
    "--root <dir>",
    "Project root (where .ccc/ lives). Defaults to cwd.",
    ".",
  );

program
  .command("init")
  .description("Initialize a .ccc/ workspace")
  .option("--prompt <text>", "Original task prompt to record")
  .option("--style <text>", "Initial code-style notes")
  .option("--phase <name>", "Starting phase label")
  .action((opts) => {
    const root = program.opts().root as string;
    const store = new StateStore(root);
    const state = store.init();
    if (opts.prompt) state.original_prompt = opts.prompt;
    if (opts.style) state.code_style = opts.style;
    if (opts.phase) state.setPhase(opts.phase);
    store.save(state);
    process.stdout.write(`Initialized state at ${store.path}\n`);
  });

program
  .command("cache")
  .description("Cache a topic source (file or directory)")
  .argument("<path>")
  .option("--label <text>", "Short label (defaults to filename)")
  .action((path: string, opts: { label?: string }) => {
    const { store, state } = loadState(program.opts());
    const abs = resolve(path);
    if (!existsSync(abs)) {
      process.stderr.write(`error: ${abs} does not exist\n`);
      process.exit(1);
    }
    const label = opts.label ?? basename(abs);
    const stat = statSync(abs);
    const size = stat.isDirectory() ? dirSize(abs) : stat.size;
    state.addContextSource(abs, label, size);
    store.save(state);
    process.stdout.write(`Cached source: ${label} (${abs}, ${size} bytes)\n`);
  });

program
  .command("prompt")
  .description("Set or replace the original prompt")
  .argument("<text>")
  .action((text: string) => {
    const { store, state } = loadState(program.opts());
    state.original_prompt = text;
    store.save(state);
    process.stdout.write("Original prompt updated.\n");
  });

program
  .command("style")
  .description("Set or append code-style notes")
  .argument("<text>")
  .option("--append", "Append to existing notes")
  .action((text: string, opts: { append?: boolean }) => {
    const { store, state } = loadState(program.opts());
    if (opts.append && state.code_style) {
      state.code_style = state.code_style.replace(/\s+$/, "") + "\n" + text;
    } else {
      state.code_style = text;
    }
    store.save(state);
    process.stdout.write("Code style updated.\n");
  });

program
  .command("todo")
  .description("Add a todo to the current sprint/phase")
  .argument("<text>")
  .action((text: string) => {
    const { store, state } = loadState(program.opts());
    const todo = state.addTodo(text);
    store.save(state);
    process.stdout.write(`Added todo ${todo.id}: ${todo.text}\n`);
  });

program
  .command("done")
  .description("Mark a todo complete (by id prefix)")
  .argument("<id>")
  .action((id: string) => {
    const { store, state } = loadState(program.opts());
    const todo = state.completeTodo(id);
    if (!todo) {
      process.stderr.write(`error: no todo matching '${id}'\n`);
      process.exit(1);
    }
    store.save(state);
    process.stdout.write(`Completed ${todo.id}: ${todo.text}\n`);
  });

const sprint = program.command("sprint").description("Manage sprints");
sprint
  .command("start")
  .argument("<name>")
  .option("--phase <name>")
  .action((name: string, opts: { phase?: string }) => {
    const { store, state } = loadState(program.opts());
    const s = state.startSprint(name, opts.phase ?? null);
    store.save(state);
    process.stdout.write(`Started sprint ${s.name} (phase=${s.phase ?? "-"})\n`);
  });
sprint
  .command("complete")
  .option("--notes <text>", "Closing notes", "")
  .action((opts: { notes?: string }) => {
    const { store, state } = loadState(program.opts());
    const s = state.completeSprint(opts.notes ?? "");
    if (!s) {
      process.stderr.write("error: no active sprint to complete\n");
      process.exit(1);
    }
    store.save(state);
    process.stdout.write(`Completed sprint ${s.name}\n`);
  });

program
  .command("phase")
  .description("Set the current phase label")
  .argument("<name>")
  .action((name: string) => {
    const { store, state } = loadState(program.opts());
    state.setPhase(name);
    store.save(state);
    process.stdout.write(`Current phase: ${state.current_phase}\n`);
  });

program
  .command("status")
  .description("Show the current session state")
  .action(() => {
    const { store, state } = loadState(program.opts());
    const lines: string[] = [];
    lines.push(`State: ${store.path}`);
    lines.push(`Phase: ${state.current_phase || "(unset)"}`);
    lines.push(`Sprint: ${state.current_sprint || "(none)"}`);
    lines.push(
      `Original prompt: ${state.original_prompt.slice(0, 80) || "(unset)"}`,
    );
    lines.push(`Cached sources: ${state.context_sources.length}`);
    for (const s of state.context_sources) {
      lines.push(`  - ${s.label} (${s.path}, ${s.bytes} bytes)`);
    }
    lines.push(`Todos open: ${state.todos.length}`);
    for (const t of state.todos) lines.push(`  [${t.id}] ${t.text}`);
    lines.push(`Completed: ${state.completed.length}`);
    lines.push(
      `Session tokens (input+output+cache): ${sessionTokenEstimate(state)}`,
    );
    if (state.last_handoff_path)
      lines.push(`Last handoff: ${state.last_handoff_path}`);
    process.stdout.write(lines.join("\n") + "\n");
  });

program
  .command("ask")
  .description(
    "Send a prompt to Claude with the cached topic context (uses prompt caching).",
  )
  .argument("[text]")
  .option("--model <id>", "Model id", DEFAULT_MODEL)
  .option("--max-tokens <n>", "Max tokens", (v) => Number.parseInt(v, 10), 16000)
  .option(
    "--threshold <n>",
    "Token budget that triggers an auto-compact reminder.",
    (v) => Number.parseInt(v, 10),
    DEFAULT_THRESHOLD_TOKENS,
  )
  .action(
    async (
      text: string | undefined,
      opts: { model: string; maxTokens: number; threshold: number },
    ) => {
      const { store, state } = loadState(program.opts());
      const prompt = text ?? (await readStdin());
      if (!prompt.trim()) {
        process.stderr.write("error: empty prompt\n");
        process.exit(1);
      }
      try {
        const { text: reply, usage } = await ask(state, prompt, {
          model: opts.model,
          maxTokens: opts.maxTokens,
        });
        state.recordUsage(usage);
        store.save(state);
        process.stdout.write(reply + "\n");
        process.stderr.write(formatUsageLine(usage) + "\n");
        if (shouldCompact(state, opts.threshold)) {
          process.stderr.write(
            `[ccc] session tokens hit ${sessionTokenEstimate(state)} ` +
              `(threshold ${opts.threshold}); run \`ccc compact\` to emit a handoff.\n`,
          );
        }
      } catch (err) {
        process.stderr.write(`error: ${(err as Error).message}\n`);
        process.exit(1);
      }
    },
  );

program
  .command("handoff")
  .description("Generate a <=750-word handoff document for the next context window.")
  .option("--model <id>", "Model id", DEFAULT_MODEL)
  .option("--print", "Print the document to stdout")
  .action(async (opts: { model: string; print?: boolean }) => {
    const { store, state } = loadState(program.opts());
    try {
      const { text: raw, usage } = await generateHandoff(state, {
        model: opts.model,
      });
      state.recordUsage(usage);
      const text = truncateToLimit(raw);
      const problems = validate(text);
      const label = problems.length > 0 ? "needs-review" : "manual";
      for (const p of problems) process.stderr.write(`warning: ${p}\n`);
      const path = writeHandoff(store, text, label);
      state.last_handoff_path = path;
      store.save(state);
      process.stdout.write(
        `Handoff written to ${path} (${countWords(text)} words, limit ${WORD_LIMIT})\n`,
      );
      if (opts.print) {
        process.stdout.write("\n" + text + "\n");
      }
      if (problems.length > 0) process.exit(2);
    } catch (err) {
      process.stderr.write(`error: ${(err as Error).message}\n`);
      process.exit(1);
    }
  });

program
  .command("compact")
  .description(
    "Auto-compact: emit handoff and reset session counters when over threshold.",
  )
  .option(
    "--threshold <n>",
    "Token budget threshold",
    (v) => Number.parseInt(v, 10),
    DEFAULT_THRESHOLD_TOKENS,
  )
  .option("--force", "Compact even if the threshold has not been reached.")
  .action(async (opts: { threshold: number; force?: boolean }) => {
    const { store, state } = loadState(program.opts());
    try {
      const result = await compact(store, state, {
        threshold: opts.threshold,
        force: opts.force,
      });
      if (!result) {
        const used = sessionTokenEstimate(state);
        process.stdout.write(
          `Skipped: session tokens ${used} below threshold ${opts.threshold}. ` +
            "Use --force to compact anyway.\n",
        );
        return;
      }
      process.stdout.write(`Compacted. Handoff: ${result.handoffPath}\n`);
      for (const p of result.problems) {
        process.stderr.write(`warning: ${p}\n`);
      }
    } catch (err) {
      process.stderr.write(`error: ${(err as Error).message}\n`);
      process.exit(1);
    }
  });

program
  .command("resume")
  .description(
    "Load a handoff document into a fresh state for the new context window.",
  )
  .argument("<handoff>")
  .option("--overwrite", "Replace any existing state with the handoff contents.")
  .action((handoff: string, opts: { overwrite?: boolean }) => {
    const store = getStore(program.opts());
    if (!existsSync(handoff)) {
      process.stderr.write(`error: ${handoff} does not exist\n`);
      process.exit(1);
    }
    const text = readFileSync(handoff, "utf8");
    let state: State;
    if (store.exists() && !opts.overwrite) {
      state = store.load();
    } else {
      state = new State();
    }
    hydrateStateFromHandoff(text, state);
    state.last_handoff_path = resolve(handoff);
    store.save(state);
    process.stdout.write(
      `Resumed from ${handoff}. Loaded ${state.todos.length} todos. ` +
        `Phase=${state.current_phase || "-"}.\n`,
    );
  });

program.parseAsync(process.argv).catch((err: Error) => {
  process.stderr.write(`error: ${err.message}\n`);
  process.exit(1);
});
