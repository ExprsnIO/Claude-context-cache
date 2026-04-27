# CLAUDE.md

Project memory for Claude Code working in this repository. For human-facing docs see [README.md](./README.md), [Usage.md](./Usage.md), [Best Practices.md](./Best%20Practices.md), and [Example.md](./Example.md).

## What this project is

`claude-context-cache` (`ccc`) is a CLI + library that caches Claude topic contexts via Anthropic's prompt-caching API, tracks todos/sprints/phases for the active session, and emits ≤750-word handoff documents so the next context window can resume without re-establishing context.

It ships in two parallel packages that must stay behaviorally identical:

- **Python** — `src/ccc/`, console script `ccc`, declared in `pyproject.toml`
- **npm** — `npm/src/`, plus the shared `context-store/` workspace (tiered KV adapter)

Tests live in `tests/` (pytest) and `npm/tests/` + `context-store/tests/` (`node --test`).

## Commands

```bash
# Python
pip install -e .
python -m pytest tests/ -q

# npm workspaces
npm install
npm test
npm run build
```

A passing baseline before any change: 37 Python tests, 28 npm tests (including 10 in the `context-store` workspace).

## Architecture in one minute

Request path for `ccc ask`:

1. `cli.py` / `cli.ts` parses args, loads `State` from `.ccc/state.json`.
2. `client.py` / `client.ts` calls `gather_context_sources_cached(state)` — `source_cache` reads each registered source through a SHA-256-keyed local cache.
3. `_build_system_blocks(base_prompt, topic_text)` returns `[system, topic]` blocks; if the combined length ≥ `MIN_CACHE_PREFIX_CHARS` (4 096), the **last** block carries `cache_control: ephemeral`.
4. `client.messages.create(...)` runs; `usage` is recorded into `State` and the per-call telemetry line is written to **stderr**.
5. `compact.should_compact(state)` checks whether session tokens crossed the threshold and prints a reminder.

`ccc handoff` / `ccc compact` reuse steps 2 and 3 with `HANDOFF_SYSTEM_PROMPT`, then validate / truncate the response and write it under `.ccc/handoffs/`.

## Non-negotiable rules

These rules exist because violating them silently destroys cache hit rate, costs money, or breaks correctness. They are tested — do not work around the tests.

1. **Cache key is a content hash, never `mtime`.** `mtime` flips under `touch`, restored backups, sub-second filesystems, and editors that preserve it. If you add a new fingerprint input, hash bytes.
2. **`cache_control` sits on the last STABLE block, never on the user message.** Anthropic walks the prefix top-down; a marker below volatile content produces zero hits. The placement is locked in `tests/test_client_blocks.py` and `npm/tests/client-blocks.test.ts`.
3. **Prefixes shorter than `MIN_CACHE_PREFIX_CHARS` get NO `cache_control`.** The cache-write premium is 25%; below the API's minimum-cacheable-prefix floor, it never amortizes.
4. **Volatile content goes in `messages`, never in `system` or `tools`.** No timestamps, no request ids, no per-user data above the breakpoint.
5. **`ANTHROPIC_API_KEY` only from environment.** Never read from a config file, never log, never embed. `.env` is git-ignored; ship `.env.example` instead. If a key is committed, rotate it at console.anthropic.com — purging history is insufficient.
6. **Python and npm packages stay behaviorally identical.** A change to source-cache fingerprinting, system-block layout, or prompt text in one MUST land in the other in the same commit.

## Coding style

- Python ≥ 3.10, full type hints, `from __future__ import annotations` at the top of every module.
- TypeScript with `strict: true`. Explicit return types on every exported function.
- No comments that restate what the code does. Comments earn their place by explaining a non-obvious WHY (a constraint, an Anthropic-API quirk, a security invariant).
- Tests use the file naming `tests/test_<module>.py` (Python) and `npm/tests/<module>.test.ts` (Node, `node:test`).

## Editing checklist

When you change anything in the request path (cli, client, source-cache, prompts, compact), verify:

- [ ] Both Python and npm packages updated
- [ ] `python -m pytest tests/ -q` passes
- [ ] `npm test` passes
- [ ] `npm run build` is clean (no TypeScript errors)
- [ ] If you touched cache key derivation, system-block layout, or telemetry, the corresponding test in `test_client_blocks.py` / `client-blocks.test.ts` / `test_source_cache.py` / `source-cache.test.ts` covers the new behavior

## When to drive `ccc` yourself

If a session in this repo is going to span more than one context window — large refactor, multi-feature build, multi-day investigation — use the project subagent at `.claude/agents/context-cache.md`. It runs `ccc init`, `ccc cache`, `ccc todo`/`ccc done`, and emits a handoff before the window fills. Do not edit `.ccc/state.json` by hand; always go through the CLI.

## What lives where

```
src/ccc/                    # Python package
  cli.py                    # argparse entry; ccc <subcommand>
  client.py                 # Anthropic SDK wrapper; cache_control placement
  source_cache.py           # SHA-256-keyed local source cache
  prompts.py                # ASK / HANDOFF system prompts (frozen)
  state.py                  # State dataclass + StateStore (.ccc/state.json)
  compact.py                # threshold check + reset-after-handoff
  handoff.py                # validate/truncate/write handoff documents
  store/                    # tiered KV adapter (sqlite/redis/postgres/...)

npm/src/                    # parallel TypeScript package — keep in sync
context-store/src/          # @claude-context-cache/context-store (workspace)

tests/                      # pytest suite
npm/tests/                  # node --test suite
context-store/tests/        # node --test suite
```
