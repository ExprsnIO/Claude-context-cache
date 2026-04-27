# Usage

Detailed reference for the `ccc` CLI, the Claude Code subagent, and the Node library.

For an overview, see [README.md](./README.md). For the license, see [License.md](./License.md).

## Contents

- [Installation](#installation)
- [Environment](#environment)
- [Workspace layout](#workspace-layout)
- [Command reference](#command-reference)
- [Workflow patterns](#workflow-patterns)
- [Prompt caching internals](#prompt-caching-internals)
- [The Claude Code subagent](#the-claude-code-subagent)
- [Node library API](#node-library-api)
- [Configuration & defaults](#configuration--defaults)
- [Troubleshooting](#troubleshooting)

## Installation

### Python (primary)

```bash
pip install -e .
```

This installs the `ccc` console script defined in `pyproject.toml` (`ccc = "ccc.cli:main"`). Requires Python ≥ 3.10 and the `anthropic` SDK ≥ 0.39.0.

### Node / npm

```bash
npm install claude-context-cache
```

The npm package ships a TypeScript port of the same CLI plus a `postinstall` hook that:

1. Drops `.claude/agents/context-cache.md` into the consumer project so Claude Code routes long-running tasks to the subagent automatically.
2. Initializes `.ccc/state.json` if missing.

Both actions are idempotent and skipped when `CCC_NO_AUTOENGAGE=1` or `CI` is set, or when installing globally.

## Environment

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes (for `ask`/`handoff`/`compact`) | Auth for the Anthropic API |
| `CCC_NO_AUTOENGAGE` | no | Skip the npm `postinstall` auto-engage step |

## Workspace layout

After `ccc init`, the project root contains:

```
.ccc/
  state.json          # phase, sprint, todos, completed, token counters, cached source list
  handoffs/           # generated handoff documents
.claude/
  agents/
    context-cache.md  # Claude Code subagent (project-scoped)
```

`state.json` is the single source of truth. Never edit it by hand — use the CLI.

## Command reference

All commands accept `--root <path>` (defaults to cwd) to point at a non-current project root.

### `ccc init`

Initialize a `.ccc/` workspace.

```bash
ccc init [--prompt <text>] [--style <text>] [--phase <name>]
```

| Flag | Effect |
|---|---|
| `--prompt` | Record the original task prompt verbatim |
| `--style` | Initial code-style notes |
| `--phase` | Starting phase label (e.g. `MVP`, `refactor`) |

### `ccc cache <path>`

Register a file or directory as cached topic context. The path is recorded with its byte size; the file content is read at `ccc ask` time and stitched into the system prompt.

```bash
ccc cache ./src --label "app source"
ccc cache ./tests --label "test suite"
```

| Flag | Effect |
|---|---|
| `--label` | Short label (defaults to the basename) |

### `ccc prompt <text>` / `ccc style <text>`

Replace the recorded original prompt or code-style notes. `ccc style --append` adds to the existing notes instead of replacing them.

### `ccc phase <name>`

Set the current phase label. Phases group sprints.

### `ccc sprint start <name> [--phase <name>]`

Start a focused chunk of work under a phase.

### `ccc sprint complete [--notes <text>]`

Close the active sprint, recording an optional one-line summary.

### `ccc todo <text>` / `ccc done <id-prefix>`

Track work items in real time. `done` accepts any unique id prefix (4 chars is usually enough).

```bash
ccc todo "Write LoginView class"
# Added todo a3f2c1: Write LoginView class
ccc done a3f2
# Completed a3f2c1: Write LoginView class
```

### `ccc status`

Print phase, sprint, original prompt, cached sources, open todos, completed work, accumulated session token usage, and the path to the last handoff.

### `ccc ask <text>`

Send a prompt to Claude with the cached topic context. The system-prompt prefix is byte-stable across calls, so the second and later calls hit the prompt cache at ~10% of the input price.

```bash
ccc ask "Sketch the LoginView class. Use the cached source for naming conventions."
```

| Flag | Default | Effect |
|---|---|---|
| `--model` | `claude-opus-4-7` | Override the model |
| `--max-tokens` | `16000` | Output token cap |
| `--threshold` | `150000` | Session-token budget that triggers an auto-compact reminder on stderr |

If stdin is piped and `<text>` is omitted, the prompt is read from stdin.

### `ccc handoff`

Generate a ≤750-word handoff document on demand. The CLI validates the output (word count + required sections); if either check fails, the file is written with a `needs-review` suffix and warnings are printed to stderr (exit code `2`).

| Flag | Effect |
|---|---|
| `--model` | Override the model |
| `--print` | Echo the document to stdout in addition to writing it |

### `ccc compact`

Auto-compact: emit a handoff and reset session counters once accumulated session tokens exceed the threshold.

| Flag | Default | Effect |
|---|---|---|
| `--threshold` | `150000` | Token budget that triggers compaction |
| `--force` | `false` | Compact even if under the threshold |

If under threshold and `--force` is not given, the command is a no-op and prints what would have happened.

### `ccc resume <handoff>`

Load a handoff document into a fresh state for the new context window. Hydrates todos, the original prompt, code style, and the current phase from the document's required sections.

| Flag | Effect |
|---|---|
| `--overwrite` | Replace any existing `.ccc/state.json` with the handoff contents |

## Workflow patterns

### Starting fresh on a multi-session task

```bash
ccc init --prompt "Add a JWT login flow to the Flask app" --phase "MVP"
ccc style "- 4-space indent
- type hints required
- match existing test style"
ccc cache ./src   --label "app source"
ccc cache ./tests --label "test suite"

ccc sprint start "scaffolding" --phase "MVP"
ccc todo "Write LoginView class"
ccc todo "Add JWT helpers"
```

### During work

- `ccc done <id>` as soon as a todo is finished — don't batch.
- `ccc todo "<text>"` whenever new work surfaces.
- `ccc ask` for any Claude call that benefits from the cached context.
- `ccc status` whenever state is unclear.

### When the context window is filling up

```bash
ccc status                  # check session token estimate
ccc compact                 # auto-emits a handoff if over threshold
ccc compact --force         # generate a handoff right now regardless
ccc handoff --print         # generate one + echo to stdout
```

### Handing off to the next context window

```bash
ccc handoff --print
```

In the next session:

```bash
ccc resume .ccc/handoffs/handoff-<stamp>.md
ccc status
```

## Prompt caching internals

The cached topic context is stitched into the system prompt with `cache_control: ephemeral`. The system prompt + topic context prefix is byte-stable across `ccc ask` calls, so:

- The first call writes the cache and pays full input price for the prefix.
- Subsequent calls read from the cache at ~10% of the input price.
- The user message sits **after** the cache breakpoint and is the only volatile part.

Adding a `ccc cache` source or changing the original prompt invalidates the cache once; the next call warms it again.

## Handoff document contract

Every handoff is enforced to:

- ≤ **750 words**
- Contain these five sections, in order:

1. **Code Style** — observed conventions
2. **Original Prompt / Current Phase** — the original task plus active phase + sprint
3. **Completed Results** — what was finished this window
4. **To-Do** — outstanding work, ordered by priority
5. **Sprints / Phases for Next Context Window** — explicit ordered plan

If the harness detects an overshoot or a missing section, the file is written with a `needs-review` suffix and the failing checks are printed to stderr.

## The Claude Code subagent

A project-level subagent ships at [`.claude/agents/context-cache.md`](.claude/agents/context-cache.md). When Claude Code runs in a repository that contains this file, it spawns the **`context-cache`** agent for long-running tasks and drives `ccc` automatically.

To install globally:

```bash
mkdir -p ~/.claude/agents
cp .claude/agents/context-cache.md ~/.claude/agents/
```

Invoke explicitly with `/agents` in Claude Code, or just describe a multi-session task and Claude will route to it.

The subagent engages proactively when:

1. The user describes a task spanning more than one context window.
2. The user references prior session work ("continue where we left off").
3. The session has accumulated >100K tokens of conversation with substantial work done.
4. The user asks to "save progress", "hand off", "compact", "resume", or "checkpoint".
5. A `.ccc/` directory already exists in the working tree.

## Node library API

The npm package also exports its primitives:

```ts
import {
  StateStore,
  ask,
  generateHandoff,
  compact,
} from "claude-context-cache";

const store = new StateStore("./");
const state = store.load();
const { text, usage } = await ask(state, "What does FooClass do?");
state.recordUsage(usage);
store.save(state);
```

## Configuration & defaults

| Setting | Default | Override |
|---|---|---|
| Model | `claude-opus-4-7` | `--model` per call |
| Compaction threshold | `150_000` session tokens | `--threshold` |
| Handoff word limit | `750` | (compile-time constant) |
| Workspace root | cwd | `--root <path>` |
| Python | ≥ 3.10 | — |
| Node | ≥ 18 | — |

## Troubleshooting

**`ANTHROPIC_API_KEY` not set.** `ccc ask`, `ccc handoff`, and `ccc compact` exit with an error. Export the key in your shell.

**`No state at .ccc/state.json. Run \`ccc init\` first.`** Run `ccc init` with whatever context you have, then retry.

**A cached source path no longer exists on disk.** The client silently skips it. Run `ccc status` to inspect the registry, then `ccc cache <new-path>` to refresh.

**Handoff file written with a `needs-review` suffix.** Claude exceeded 750 words or skipped a required section. Open the file, edit it by hand, then save. Resuming from a `needs-review` handoff still works.

**`ccc compact` is a no-op.** Session token usage is below the threshold. Pass `--force` to compact anyway, or wait until more `ccc ask` traffic accumulates.

**npm `postinstall` did nothing.** It auto-skips on global installs, in CI, or when `CCC_NO_AUTOENGAGE=1` is set. Drop `.claude/agents/context-cache.md` in by hand, or rerun `npm install` in a non-CI shell without the env var.
