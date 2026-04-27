# Best Practices

How to get the most out of `ccc` and the underlying Anthropic prompt-caching API. The first sections describe what the harness already enforces; later sections cover patterns the user controls. Background and rationale at the bottom.

For a worked end-to-end example, see [Example.md](./Example.md). For the command reference, see [Usage.md](./Usage.md).

## What the harness enforces (you don't have to think about these)

These rules are baked in and covered by tests. Don't fight them.

| Rule | Where it lives |
|---|---|
| Source-cache key is a SHA-256 hash of file bytes, never `mtime` | `src/ccc/source_cache.py`, `npm/src/source-cache.ts` |
| `cache_control` sits on the last STABLE system block, never on the user message | `src/ccc/client.py:_build_system_blocks`, `npm/src/client.ts:buildSystemBlocks` |
| Prefixes shorter than ~4 096 chars (≈1 024 tokens) get NO `cache_control` | same files; constant `MIN_CACHE_PREFIX_CHARS` |
| Per-call cache telemetry on stderr after every `ccc ask` | `src/ccc/cli.py`, `npm/src/cli.ts` |
| API key resolved via the auth cascade (env / .env / config / keyring) | `src/ccc/auth.py`, `npm/src/auth.ts` |
| `system_input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` recorded per call | `State.record_usage` / `State.recordUsage` |

If you're modifying the harness itself, see [CLAUDE.md](./CLAUDE.md) for the editing checklist.

## What you control

### 1. Cache stable content first, volatile content last

Anthropic walks the request top-down (`tools → system → messages`) and matches the longest byte-identical prefix written within the last 20 blocks. The harness puts `cache_control` on the last system block — anything you put **above** it must be byte-stable across calls, or the cache will miss.

Do:

```bash
ccc init --prompt "Add OAuth2 to the Flask app"
ccc cache ./src --label "app source"
ccc cache ./tests --label "test suite"
ccc cache ./docs/auth-spec.md --label "spec"
```

Don't paste the current date, a request id, or anything else that changes per call into `ccc init --prompt` or `ccc style`. The original prompt is rendered into the **user** message (volatile), but the harness's framing (`Original task: ...`) is also part of the messages — anything in `--prompt` is fine. The trap is `ccc style`: it goes into the SYSTEM-prompt-adjacent state path; keep it static.

### 2. Cache at the right granularity

| Source size | Recommendation |
|---|---|
| < 1 KB single file | Don't bother caching — too small to clear the prefix floor on its own |
| 1 KB – 1 MB single file | `ccc cache <path>` directly |
| Whole module / package | `ccc cache <dir>` — the source cache hashes recursively, dotfiles excluded |
| Whole repo | Cache the relevant subtrees, not the root. Tests, vendored deps, and node_modules dilute the signal and inflate every prefix-hash recompute |
| > 100 MB | Don't cache. Build a focused excerpt or use retrieval |

### 3. Watch the telemetry line, not aggregate counters

After every `ccc ask`:

```
[ccc] tokens — input=152 output=803 cache_read=12048 cache_creation=0 hit=100%
```

The healthy patterns:

- **First call after `ccc cache`**: `cache_creation > 0`, `cache_read = 0`, `hit = 0%`. Expected — this writes the cache.
- **Second and later calls**: `cache_read > 0`, `cache_creation = 0`, `hit ≈ 100%`. The prefix is warm.
- **After `ccc cache <new-source>`**: one `cache_creation` round, then warm. Adding content invalidates once, then re-establishes.

The warning patterns:

- `hit = 0%` repeatedly with `cache_creation > 0` every call — the prefix is drifting. Something volatile slipped above the breakpoint, or a `ccc cache`'d file is being rewritten between calls.
- `hit = 0%` with `cache_creation = 0` — the prefix is too small (under ~4 096 chars), so `cache_control` was deliberately not emitted. Cache more sources or accept the small-context penalty.
- `cache_read > 0` but `hit < 100%` — partial hit. The prefix matched up to a point and then diverged. Find the divergence (usually a re-ordered `ccc cache` source).

### 4. Pick the right TTL for your session shape

Anthropic offers two ephemeral TTL tiers:

- **5 minutes** (1.25× write rate) — pays off after ~2 reads. Default for `ccc`. Right for one-shot pipelines and short interactive bursts.
- **1 hour** (2× write rate) — pays off after ~4 reads. Resets on every cache hit. Right for long-running coding sessions where the same context is hit dozens of times.

`ccc` currently uses the 5-minute default. If your workflow is "warm the cache once at the start of a 90-minute session and read from it dozens of times", patch `ASK_SYSTEM_PROMPT` / `_build_system_blocks` to set `{"type": "ephemeral", "ttl": "1h"}` on the marker. Mirror in both Python and npm packages.

### 5. Compact at clean breakpoints, not in the middle of a thought

`ccc compact` writes a ≤750-word handoff and resets session counters. Good moments:

- End of a sprint (`ccc sprint complete` then `ccc compact`).
- End of a phase.
- When `ccc status` reports session tokens approaching the threshold (default 150 K).
- Before a hard pause — meeting, end of day, OS update.

Bad moments: in the middle of debugging a single failing test, halfway through generating a multi-file refactor. The handoff is only as good as the state at the time it was generated; mid-thought state is hard to resume from.

### 6. One `ccc resume` per new context window

When the next session starts:

```bash
ls -t .ccc/handoffs/*.md | head -3   # find the latest
ccc resume .ccc/handoffs/handoff-<stamp>.md
ccc status                            # confirm what loaded
```

Do **not** also paste the handoff into the chat. `ccc resume` already hydrates `State`; pasting it duplicates the content into the user message and burns tokens for no benefit.

If the handoff was written with a `needs-review` suffix, open it first, fix the section that tripped validation (usually `## Sprints / Phases for Next Context Window` got truncated), then resume.

## Security

- **API key**: read via the auth detector (`src/ccc/auth.py`), which walks `env vars → project .env → ~/.env → platform config file → OS keyring`. First valid hit wins. The detector never mutates `os.environ`, so the key does not leak to subprocesses. Run `ccc auth -v` to see which candidate was picked. `.env` is git-ignored; copy `.env.example` to `.env` and fill it in. The OS keyring is the most secure of the supported sources — Keychain on macOS, Credential Manager on Windows, Secret Service / libsecret on Linux. Install with `pip install -e ".[keyring]"` then `keyring set anthropic api_key`.
- **Never put a key into a `ccc cache`'d source.** The detector deliberately does not scan cached topic content — anything you `ccc cache` is uploaded to the model. If you keep a key in a config file that ends up under a cached directory, the file goes to the model on the next `ccc ask`.
- **If a key is ever committed, rotate it at console.anthropic.com** — purging history alone is insufficient because GitHub may have already cached the blob.
- **Cached content sensitivity**: `.ccc/sources.sqlite` and `.ccc/handoffs/*.md` may contain proprietary code, internal docs, or PII surfaced from your `ccc cache` sources. Treat the `.ccc/` directory as you treat your `.env` — don't sync it to a public bucket, don't commit it, and consider full-disk encryption.
- **Logs**: nothing in `ccc` logs full prompts or completions at default verbosity. If you wrap `ccc` in your own tooling, preserve that property — never log the response body or the assembled system prompt outside an explicit `--debug` flag gated behind a non-default env var.

## Testing patterns when extending `ccc`

If you change source-cache fingerprinting, system-block layout, or telemetry, the existing test files lock in the contract:

- `tests/test_client_blocks.py` / `npm/tests/client-blocks.test.ts` — `cache_control` placement and the min-prefix guard.
- `tests/test_source_cache.py` / `npm/tests/source-cache.test.ts` — invalidate-on-content, mtime-only no-op, identical-bytes-rewrite no-op.
- `tests/test_state.py` / `npm/tests/state.test.ts` — usage accumulation across calls.

Add new tests, don't loosen old ones. The whole point of these tests is that "regressions in cache effectiveness" become "test failures in CI", not "20 % higher Anthropic bill next month".

## Background

The harness's defaults are the result of three observations from the field:

1. **Cache effectiveness regressions are silent** — without per-call telemetry you can't tell that your hit rate dropped from 95 % to 0 % until the bill arrives. That's why telemetry is on stderr by default and not behind a flag.
2. **`mtime`-based cache keys break under common workflows** — `git checkout`, restored backups, editors that preserve `mtime`, sub-second filesystem resolution. Content hashes cost more CPU but are the only correct option.
3. **The 1 024-token minimum is a real cliff, not a soft limit** — caching a 500-token prefix means paying the 25 % premium on every call and never reading it back. The min-prefix guard refuses to emit `cache_control` below the threshold.

If a future Anthropic API change moves these floors, `MIN_CACHE_PREFIX_CHARS` is the single constant to retune (in both `src/ccc/client.py` and `npm/src/client.ts`).
