# Claude Context Cache

A small CLI tool that caches Claude topic contexts (via the Anthropic prompt-caching API), tracks to-dos / sprints / phases for the active session, and emits **≤750-word handoff documents** so the next context window can pick up where the last one stopped.

Docs: [Usage.md](./Usage.md) · [Best Practices.md](./Best%20Practices.md) · [Example.md](./Example.md) · [CLAUDE.md](./CLAUDE.md) · [License.md](./License.md)

The goal is to minimize tokens spent re-establishing context: cache the topic once, accumulate progress notes locally, and compact into a tiny handoff at the end.

## Install

```bash
pip install -e .
export ANTHROPIC_API_KEY=...   # or copy .env.example to .env
```

> Never commit your API key. `.env` is git-ignored; a `.env.example` template ships at the repo root.

## Quick start

```bash
ccc init --prompt "Add a JWT login flow to the Flask app" --phase "MVP"
ccc style "- 4-space indent\n- type hints required\n- match existing test style"
ccc cache ./src --label "app source"
ccc cache ./tests --label "test suite"

ccc sprint start "scaffolding" --phase "MVP"
ccc todo "Write LoginView class"
ccc todo "Add JWT helpers"

ccc ask "Sketch the LoginView class. Use the cached source for naming conventions."

ccc done <id>            # mark a todo complete
ccc status               # see open todos, completed work, token use, current phase

# When the context window gets crowded:
ccc compact              # writes a ≤750-word handoff doc + resets session counters
ccc handoff --print      # generate one on demand

# Starting a new context window? Hand the doc to the next session:
ccc resume .ccc/handoffs/handoff-<stamp>.md
```

## What the handoff document contains

Every handoff is enforced to ≤750 words and to include these five sections:

1. **Code Style** — observed conventions (formatting, naming, error handling, language idioms)
2. **Original Prompt / Current Phase** — the original task plus active phase + sprint
3. **Completed Results** — what was finished this window
4. **To-Do** — outstanding work, ordered by priority
5. **Sprints / Phases for Next Context Window** — explicit ordered plan for the next session

The harness validates the document, truncates if Claude overshoots, and flags any missing sections by writing the file with a `needs-review` suffix.

## Why prompt caching

The cached topic context (everything you `ccc cache`'d) is stitched into the system prompt with `cache_control: ephemeral`. The prompt prefix — system prompt + topic context — is byte-stable across `ccc ask` calls, so the second and later calls read from cache at ~10% the input price.

The only volatile part is the user message, which sits after the cache breakpoint. Adding more cached sources or changing the original prompt will invalidate the cache once; subsequent calls warm it again.

### Caching policy

- **Cache-key inputs.** The on-disk source cache is keyed by a SHA-256 hash of file bytes (or, for a directory, a hash over the sorted relative-path + per-file content hashes). Touching `mtime` without changing bytes does **not** invalidate; rewriting with identical bytes does **not** invalidate; any byte-level change does.
- **Minimum cacheable prefix.** `cache_control` is only emitted when the system prompt + topic context together exceed ~4 096 characters (a conservative proxy for Anthropic's 1 024-token floor). Below that, the 25 % cache-write premium would never amortize, so the marker is dropped.
- **Marker placement.** The marker sits on the **last** stable system block — after `tools` and `system`, before any `messages`. Volatile content (the user's new message, the per-call `Original task: …` framing) lives in `messages` so the cached prefix stays byte-stable.
- **Per-call telemetry.** After every `ccc ask`, a one-line summary on stderr reports `input`, `output`, `cache_read`, `cache_creation`, and the resulting hit-rate so cache regressions are visible immediately. Aggregate counters live in `ccc status`.

## Layout

```
.ccc/
  state.json          # phase, sprint, todos, completed, token counters, cached source list
  handoffs/           # generated handoff documents
```

## Monorepo

This repository is an **npm workspaces monorepo** alongside the Python package at the root:

```
.
├── pyproject.toml          # Python ccc package (root)
├── src/ccc/                # Python source
├── tests/                  # Python tests
├── package.json            # workspaces root
├── npm/                    # claude-context-cache (Node CLI + library)
└── context-store/          # @claude-context-cache/context-store (tiered store)
```

A single `npm install` at the root wires both Node packages together via npm workspaces. `context-store` is symlinked into `npm/`'s `node_modules/`, so changes propagate without republishing.

```bash
npm install                 # installs all workspaces, builds in topo order
npm test                    # runs every workspace's tests
npm run build               # rebuilds context-store, then npm
npm run build:context-store # build a single workspace
npm run test:npm            # test a single workspace
```

The build order is enforced by listing `context-store` first in the root `workspaces` array; `npm run build --workspaces --if-present` then iterates in that order.

## Commands

| Command | Purpose |
|---|---|
| `ccc init` | create `.ccc/` and seed prompt/style/phase |
| `ccc cache <path>` | register a file or directory as cached topic context |
| `ccc prompt <text>` | replace the original prompt |
| `ccc style <text>` | replace (or `--append`) code-style notes |
| `ccc phase <name>` | set the current phase label |
| `ccc sprint start <name>` / `ccc sprint complete` | manage sprints |
| `ccc todo <text>` / `ccc done <id>` | track work items |
| `ccc status` | print current state |
| `ccc ask <text>` | call Claude with the cached context (uses prompt caching) |
| `ccc handoff` | generate a ≤750-word handoff document on demand |
| `ccc compact` | auto-compact when token usage hits the threshold |
| `ccc resume <handoff>` | load a handoff doc as the seed of a new state |

## Defaults

- Model: `claude-opus-4-7` (override per call with `--model`)
- Compaction threshold: 150,000 session tokens (override with `--threshold`)
- Handoff word limit: 750

## Claude Code subagent

A project-level subagent ships at [`.claude/agents/context-cache.md`](.claude/agents/context-cache.md). When you run Claude Code in this repo (or copy that file into another repo's `.claude/agents/`, or your global `~/.claude/agents/`), Claude will spawn the **`context-cache`** agent for long-running tasks and drive `ccc` on your behalf — initializing the workspace, tracking todos/sprints/phases, calling `ccc ask` against the cached context, and generating handoffs when the context window fills.

To install globally:

```bash
mkdir -p ~/.claude/agents
cp .claude/agents/context-cache.md ~/.claude/agents/
```

Invoke explicitly with `/agents` in Claude Code, or just describe a multi-session task and Claude will route to it automatically.
