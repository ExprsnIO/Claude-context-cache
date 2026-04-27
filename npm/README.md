# claude-context-cache (npm)

Cache Claude topic contexts, track session work (todos / sprints / phases), and emit **≤750-word handoff documents** so the next context window can pick up where the last one stopped — all from Node.js.

When you `npm install` this package as a dependency, it **auto-engages** the [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) subagent into your project so Claude will drive `ccc` for you.

## Install

```bash
npm install claude-context-cache
export ANTHROPIC_API_KEY=...
```

On install, the package will:

1. Drop `.claude/agents/context-cache.md` into your project (so Claude Code routes long-running tasks to the `context-cache` subagent automatically).
2. Initialize `.ccc/state.json` if it doesn't exist.

These actions are idempotent — re-running `npm install` won't overwrite anything you've edited.

### Skip auto-engage

```bash
CCC_NO_AUTOENGAGE=1 npm install claude-context-cache
```

The hook also skips automatically when `CI` is set or when installing globally.

## CLI

```bash
npx ccc init --prompt "Build a JWT login flow" --phase "MVP"
npx ccc style "- 4-space indent\n- ESM imports with .js extension"
npx ccc cache ./src --label "app source"
npx ccc cache ./tests --label "test suite"

npx ccc sprint start "scaffolding" --phase "MVP"
npx ccc todo "Write LoginView class"
npx ccc todo "Add JWT helpers"

npx ccc ask "Sketch the LoginView class. Use the cached source for naming."
npx ccc done <id>
npx ccc status

# When the context window is filling up:
npx ccc compact            # writes a ≤750-word handoff doc + resets session counters
npx ccc handoff --print    # generate one on demand

# In the next session:
npx ccc resume .ccc/handoffs/<file>.md
```

## What the handoff document contains

Every handoff is enforced to ≤750 words and to include these five sections:

1. **Code Style** — observed conventions
2. **Original Prompt / Current Phase** — the original task plus active phase + sprint
3. **Completed Results** — what was finished this window
4. **To-Do** — outstanding work, ordered by priority
5. **Sprints / Phases for Next Context Window** — explicit ordered plan

If Claude overshoots the word count or skips a section, the file is written with a `needs-review` suffix.

## Library API

The package also exports its primitives:

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

## Why prompt caching

Cached topic context (everything you `ccc cache`'d) is stitched into the system prompt with `cache_control: ephemeral`. The system-prompt prefix is byte-stable across `ccc ask` calls, so the second and later calls read from cache at ~10% the input price.

## Defaults

- Model: `claude-opus-4-7`
- Compaction threshold: 150,000 session tokens
- Handoff word limit: 750
- Node ≥ 18

## Layout

```
.ccc/
  state.json
  handoffs/
.claude/
  agents/
    context-cache.md   # Claude Code subagent (installed automatically)
```

## License

MIT
