# Architecture

How the repository is laid out, what each package does, and how the build is ordered.

## Repository layout

```
.
├── pyproject.toml            # Python `ccc` package (root)
├── src/ccc/                  # Python source
│   ├── cli.py                # argparse entry point (ccc = ccc.cli:main)
│   ├── client.py             # Anthropic API client + prompt assembly
│   ├── compact.py            # threshold check + handoff-and-reset
│   ├── handoff.py            # word count, validation, hydrate-from-handoff
│   ├── prompts.py            # system-prompt construction
│   ├── source_cache.py       # source-read cache
│   ├── state.py              # State + StateStore (json on disk)
│   └── store/                # Tiered store adapters (Python port)
├── tests/                    # Python tests (pytest)
├── package.json              # npm workspaces root
├── npm/                      # `claude-context-cache` (Node CLI + library)
│   ├── src/                  # TypeScript port of the Python CLI
│   ├── scripts/              # postinstall (auto-engage)
│   └── tests/
├── context-store/            # `@claude-context-cache/context-store`
│   ├── src/                  # Tiered store core + adapters
│   └── tests/
├── .claude/agents/           # `context-cache` Claude Code subagent (project-scoped)
├── README.md                 # top-level overview
├── Usage.md                  # long-form reference
└── docs/                     # this documentation set
```

## Two implementations, one contract

The Python and Node implementations of `ccc` share the same:

- CLI surface (`ccc init`, `ccc cache`, `ccc ask`, `ccc handoff`, `ccc compact`, `ccc resume`, …)
- State schema (`.ccc/state.json` is portable between them)
- Handoff document contract (5 sections, ≤750 words)
- Prompt-caching strategy (system prefix is byte-stable; user message is volatile)

Pick the one your project already uses. The npm package additionally exports a TypeScript library API (see [Node library](./node-library.md)).

## npm workspaces

The repository is an **npm workspaces monorepo** alongside the Python package:

| Package | Folder | Role |
|---|---|---|
| `claude-context-cache` | `npm/` | Node CLI + library port |
| `@claude-context-cache/context-store` | `context-store/` | Tiered context store: Redis → SQLite, optional MySQL/Postgres/Mongo backing |

A single `npm install` at the root wires both Node packages together; `context-store` is symlinked into `npm/`'s `node_modules/`, so changes propagate without republishing.

```bash
npm install                 # installs all workspaces, builds in topo order
npm test                    # runs every workspace's tests
npm run build               # rebuilds context-store, then npm
npm run build:context-store # build a single workspace
npm run test:npm            # test a single workspace
```

## Build order

The build order is enforced by listing `context-store` first in the root `workspaces` array. `npm run build --workspaces --if-present` then iterates in that order:

1. `context-store` builds first because `npm/` imports from it.
2. `npm` builds second.

If you add another workspace, position it relative to the dependency graph in `package.json`'s `workspaces` array.

## Data flow on `ccc ask`

```
ccc ask "<text>"
   │
   ▼
StateStore.load() ◄────── .ccc/state.json
   │
   ▼
prompts.build_system(state)
   │      ├─ static instructions
   │      ├─ code style + original prompt
   │      └─ each cached source (read via source-read cache)
   │           └── cache_control: ephemeral  ← Anthropic cache breakpoint
   ▼
client.ask(state, user_text)
   │      └─ Anthropic API call (prompt-cached prefix)
   ▼
state.record_usage(usage)
   │
   ▼
StateStore.save(state) ──► .ccc/state.json
```

`ccc handoff` and `ccc compact` follow the same shape, but the user message is a fixed handoff-generation instruction and the response is post-processed (truncate + validate) before being written to `.ccc/handoffs/`.

## Where state lives

- **`.ccc/state.json`** — single source of truth. Phase, current sprint, todos (open and completed), sprint history, registered context sources, accumulated session token counters, last handoff path. Don't edit by hand.
- **`.ccc/handoffs/*.md`** — generated handoff documents. Audit trail; don't delete.
- **Context store** (Node only) — source-read cache. Ephemeral; safe to wipe.

## See also

- [Context store](./context-store.md) for backend details.
- [Node library](./node-library.md) for the public TypeScript surface.
