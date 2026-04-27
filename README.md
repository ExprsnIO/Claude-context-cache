# Claude Context Cache

A small CLI tool that caches Claude topic contexts (via the Anthropic prompt-caching API), tracks to-dos / sprints / phases for the active session, and emits **≤750-word handoff documents** so the next context window can pick up where the last one stopped.

The goal is to minimize tokens spent re-establishing context: cache the topic once, accumulate progress notes locally, and compact into a tiny handoff at the end.

## Install

```bash
pip install -e .
export ANTHROPIC_API_KEY=...
```

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

## Layout

```
.ccc/
  state.json          # phase, sprint, todos, completed, token counters, cached source list
  handoffs/           # generated handoff documents
```

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
