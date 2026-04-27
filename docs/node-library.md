# Node library API

The npm package `claude-context-cache` exports its primitives so you can drive `ccc` from your own scripts, services, or tests without shelling out.

## Install

```bash
npm install claude-context-cache
export ANTHROPIC_API_KEY=...
```

## Top-level imports

```ts
import {
  StateStore,
  ask,
  generateHandoff,
  compact,
} from "claude-context-cache";
```

| Export | Role |
|---|---|
| `StateStore` | Read/write `.ccc/state.json`. Mirrors the Python `StateStore`. |
| `ask(state, text, opts?)` | Run an Anthropic call with the cached topic context. Returns `{ text, usage }`. |
| `generateHandoff(state, opts?)` | Produce a ≤750-word handoff document. Returns `{ text, usage }`. |
| `compact(store, state, opts?)` | Threshold-aware: produce a handoff and reset session counters. |

## Minimal example

```ts
import { StateStore, ask } from "claude-context-cache";

const store = new StateStore("./");
const state = store.load();
const { text, usage } = await ask(state, "What does FooClass do?");
state.recordUsage(usage);
store.save(state);

console.log(text);
```

## Source-read cache

`ask()` and `generateHandoff()` cache the *read* contents of every source you registered with `ccc cache`, so repeat calls don't re-walk and re-read the same files from disk. The cache key is a fingerprint of each source's `mtime + size` — any on-disk change invalidates the entry automatically.

The cache is backed by [`@claude-context-cache/context-store`](./context-store.md) and auto-selects a backend at session start (Redis → SQLite in-memory → SQLite on-disk). Configure with the same env vars (`CCC_REDIS_URL`, `CCC_SQLITE_PATH`, `CCC_NAMESPACE`, …).

```ts
import {
  Session,
  gatherContextSourcesCached,
  readSourceCached,
} from "claude-context-cache";

// Use the shared session that ask()/generateHandoff() already use:
const { text, cacheHit } = await readSourceCached("./src");

// Or run an isolated session (e.g. against Redis):
const session = new Session({ redisUrl: "redis://localhost:6379" });
await session.set("topic:notes", "...");
```

## State manipulation

```ts
import { StateStore } from "claude-context-cache";

const store = new StateStore("./");
const state = store.load();

state.addContextSource("./src", "app source", 12345);
const todo = state.addTodo("Wire up JWT helpers");
state.completeTodo(todo.id);
state.startSprint("scaffolding", "MVP");

store.save(state);
```

The same fields and methods exist as on the Python side. State is JSON-portable between the two implementations.

## Compact

```ts
import { StateStore, compact } from "claude-context-cache";

const store = new StateStore("./");
const state = store.load();

const result = await compact(store, state, { threshold: 150_000, force: false });
if (result) {
  console.log(`Compacted. Handoff at ${result.path}`);
}
```

`compact` returns `null` when below threshold and `force` is not set — matching the CLI's no-op behavior.

## Errors

- `ANTHROPIC_API_KEY` not set → `ask`, `generateHandoff`, and `compact` throw on the first API call.
- `StateStore.load()` on an uninitialized workspace throws — call `StateStore.init()` first or check `store.exists()`.
- Cached source paths that no longer exist on disk are silently skipped; check `state.contextSources` against the file system if you need to clean up.

## See also

- [CLI reference](./cli-reference.md) for the equivalent commands.
- [Context store](./context-store.md) for the cache layer behind source reads.
- [Prompt caching](./prompt-caching.md) for why repeat `ask()` calls are cheap.
