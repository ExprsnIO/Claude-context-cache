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

A passing baseline before any change: 54 Python tests, 50 npm tests (40 in the npm package, 10 in the `context-store` workspace).

## Architecture in one minute

Request path for `ccc ask`:

1. `cli.py` / `cli.ts` parses args, loads `State` from `.ccc/state.json`.
2. `client.make_client()` calls `auth.detect_api_key(project_root=…)` and walks the cascade: `env vars → project .env → ~/.env → platform config file → OS keyring (Python only)`. The first valid hit wins; values are never written into `os.environ`.
3. `client.py` / `client.ts` calls `gather_context_sources_cached(state)` — `source_cache` reads each registered source through a SHA-256-keyed local cache.
4. `_build_system_blocks(base_prompt, topic_text)` returns `[system, topic]` blocks; if the combined length ≥ `MIN_CACHE_PREFIX_CHARS` (4 096), the **last** block carries `cache_control: ephemeral`. Below that floor the marker is dropped, since the 25 % cache-write premium would never amortize.
5. `client.messages.create(...)` runs; `usage` is recorded into `State` and the per-call telemetry line (`input` / `output` / `cache_read` / `cache_creation` / `hit%`) is written to **stderr**.
6. `compact.should_compact(state)` checks whether session tokens crossed the threshold and prints a reminder.

`ccc handoff` / `ccc compact` reuse steps 2 – 4 with `HANDOFF_SYSTEM_PROMPT`, then validate / truncate the response and write it under `.ccc/handoffs/`.

Other entry points: `ccc auth [-v]` invokes `auth.detect_api_key` + `auth.search_summary` directly (no Anthropic call); `ccc tui` launches the Textual app at `src/ccc/tui.py`, which reuses every primitive above on a worker thread so the UI stays responsive.

## Non-negotiable rules

These rules exist because violating them silently destroys cache hit rate, costs money, or breaks correctness. They are tested — do not work around the tests.

1. **Cache key is a content hash, never `mtime`.** `mtime` flips under `touch`, restored backups, sub-second filesystems, and editors that preserve it. If you add a new fingerprint input, hash bytes.
2. **`cache_control` sits on the last STABLE block, never on the user message.** Anthropic walks the prefix top-down; a marker below volatile content produces zero hits. The placement is locked in `tests/test_client_blocks.py` and `npm/tests/client-blocks.test.ts`.
3. **Prefixes shorter than `MIN_CACHE_PREFIX_CHARS` get NO `cache_control`.** The cache-write premium is 25%; below the API's minimum-cacheable-prefix floor, it never amortizes.
4. **Volatile content goes in `messages`, never in `system` or `tools`.** No timestamps, no request ids, no per-user data above the breakpoint.
5. **API key is sourced via `ccc.auth.detect_api_key`, never from a hard-coded path or a cached topic source.** The detector cascade is `env vars → project .env → ~/.env → platform config file → OS keyring`. New auth sources are added to that detector, never inlined elsewhere; the cached topic context is NEVER scanned for keys (a key in a `ccc cache`'d source would be uploaded to the model). Detected values are never written into `os.environ` — they leak into subprocesses if you do. `.env` is git-ignored; ship `.env.example` instead. If a key is committed, rotate it at console.anthropic.com — purging history is insufficient.
6. **Python and npm packages stay behaviorally identical.** A change to source-cache fingerprinting, system-block layout, or prompt text in one MUST land in the other in the same commit. Optional UX layers (e.g. the Textual TUI at `src/ccc/tui.py`) are exempt from this rule — they are Python-only by design and the npm package has no equivalent.

## Coding style

- Python ≥ 3.10, full type hints, `from __future__ import annotations` at the top of every module.
- TypeScript with `strict: true`. Explicit return types on every exported function.
- No comments that restate what the code does. Comments earn their place by explaining a non-obvious WHY (a constraint, an Anthropic-API quirk, a security invariant).
- Tests use the file naming `tests/test_<module>.py` (Python) and `npm/tests/<module>.test.ts` (Node, `node:test`).

## Editing checklist

When you change anything in the request path (cli, client, source-cache, prompts, compact, auth), verify:

- [ ] Both Python and npm packages updated (parity exception: optional UX layers like `src/ccc/tui.py` are Python-only).
- [ ] `python -m pytest tests/ -q` passes
- [ ] `npm test` passes
- [ ] `npm run build` is clean (no TypeScript errors)
- [ ] If you touched cache key derivation, system-block layout, or telemetry, the matching test (`test_client_blocks.py` / `client-blocks.test.ts` / `test_source_cache.py` / `source-cache.test.ts`) covers the new behavior.
- [ ] If you touched the auth cascade, `tests/test_auth.py` and `npm/tests/auth.test.ts` cover the new source. Never bypass the detector by reading env vars or files directly from `client.py` / `client.ts` — every new source goes through `auth.detect_api_key`.
- [ ] If you added a new dependency, place it in the right `[…]` optional group in `pyproject.toml` (see "Optional dependencies" below). The core install must stay at one runtime dep (`anthropic`) for Python and one for npm (`@anthropic-ai/sdk`).

## Optional dependencies

The core install is intentionally lean. Anything beyond the Anthropic SDK lives behind an opt-in extra:

| Group | Adds | Used by |
|---|---|---|
| `[tui]` | `textual>=0.79` | `ccc tui` (Python only) |
| `[keyring]` | `keyring>=24` | The OS-keyring step in the auth cascade (Python only) |
| `[redis]`, `[mysql]`, `[postgres]`, `[mongodb]`, `[all-stores]` | the matching driver | Tiered store backends in `src/ccc/store/` |
| `[dev]` | `pytest>=7.0` | Test suite |

If a feature genuinely needs a new runtime dependency, prefer adding a new `[…]` group over expanding the core. Lazy-import the dep inside the consuming module so the rest of the CLI keeps working when the extra isn't installed (see `tui.py`'s `_require_textual()` and `auth.py`'s `_keyring_get()` for the pattern).

## When to drive `ccc` yourself

If a session in this repo is going to span more than one context window — large refactor, multi-feature build, multi-day investigation — use the project subagent at `.claude/agents/context-cache.md`. It runs `ccc init`, `ccc cache`, `ccc todo`/`ccc done`, and emits a handoff before the window fills. Do not edit `.ccc/state.json` by hand; always go through the CLI.

## What lives where

```
src/ccc/                    # Python package
  cli.py                    # argparse entry; ccc <subcommand>
  auth.py                   # API key detection cascade (env/.env/config/keyring)
  client.py                 # Anthropic SDK wrapper; cache_control placement
  source_cache.py           # SHA-256-keyed local source cache
  prompts.py                # ASK / HANDOFF system prompts (frozen)
  state.py                  # State dataclass + StateStore (.ccc/state.json)
  compact.py                # threshold check + reset-after-handoff
  handoff.py                # validate/truncate/write handoff documents
  tui.py                    # OPTIONAL Textual TUI (pip install -e ".[tui]")
  store/                    # tiered KV adapter (sqlite/redis/postgres/...)

npm/src/                    # parallel TypeScript package — keep in sync
context-store/src/          # @claude-context-cache/context-store (workspace)

tests/                      # pytest suite
npm/tests/                  # node --test suite
context-store/tests/        # node --test suite
```
