# Getting started

A 90-second tour: install, initialize a workspace, cache some context, ask Claude a question, and produce a handoff.

## Prerequisites

- An Anthropic API key exported as `ANTHROPIC_API_KEY`.
- Python ≥ 3.10 (for the primary `ccc` CLI), or Node ≥ 18 (for the npm port).

## Install

### Python (primary)

```bash
pip install -e .
export ANTHROPIC_API_KEY=...
```

This installs the `ccc` console script defined in `pyproject.toml`.

### Node / npm

```bash
npm install claude-context-cache
export ANTHROPIC_API_KEY=...
```

The npm package ships a TypeScript port of the same CLI plus a `postinstall` hook that:

1. Drops `.claude/agents/context-cache.md` into your project so Claude Code routes long-running tasks to the subagent automatically.
2. Initializes `.ccc/state.json` if missing.

Both actions are idempotent and skipped when `CCC_NO_AUTOENGAGE=1` or `CI` is set, or when installing globally.

## Quick start

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

ccc ask "Sketch the LoginView class. Use the cached source for naming conventions."

ccc done <id>            # mark a todo complete
ccc status               # see open todos, completed work, token use, current phase
```

When the context window fills up:

```bash
ccc compact              # writes a ≤750-word handoff doc + resets session counters
ccc handoff --print      # generate one on demand
```

In the next session:

```bash
ccc resume .ccc/handoffs/handoff-<stamp>.md
ccc status
```

## What gets created

After `ccc init`, the project root contains:

```
.ccc/
  state.json          # phase, sprint, todos, completed, token counters, cached sources
  handoffs/           # generated handoff documents
.claude/
  agents/
    context-cache.md  # Claude Code subagent (project-scoped)
```

`state.json` is the single source of truth. Don't edit it by hand — use the CLI.

## Next steps

- Read the [CLI reference](./cli-reference.md) for every command and flag.
- Skim [Handoff documents](./handoff-documents.md) before your first `ccc compact`.
- If you're using Claude Code, see the [subagent guide](./subagent.md).
