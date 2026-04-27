# Example: building a SQLite WASM module with `ccc`

A worked walk-through of `ccc` driving a real multi-session task: take the [SQLite amalgamation](https://www.sqlite.org/amalgamation.html) source, compile it to WebAssembly with [Emscripten](https://emscripten.org/), and ship a small JavaScript wrapper that exposes a `Database` class from the browser. The task spans more than one Claude context window, so it's a natural fit for `ccc`.

The transcript is illustrative — Claude's actual output will vary and is omitted where it would add no information. Lines starting with `$` are commands you run; lines starting with `[ccc]` are emitted by `ccc` on stderr; everything else is summary or reply excerpt.

For best practices, see [Best Practices.md](./Best%20Practices.md). For the command reference, see [Usage.md](./Usage.md).

## Why this example

The task hits every reason `ccc` exists:

- **Large stable input**: SQLite's amalgamation is ~9 MB / ~250 K LOC of C. It changes once per release, never within a session. Caching it once and re-reading at ~10 % the input price is the difference between a usable workflow and an unaffordable one.
- **Multi-phase work**: download → patch for WASM → compile → write JS bindings → write tests → ship. Each phase is a sprint; the whole arc takes more than one context window.
- **Volatile per-call queries**: each `ccc ask` is a different question against the same source ("How does the VFS layer dispatch reads?", "Which symbols need `EMSCRIPTEN_KEEPALIVE`?"). Exactly the shape Anthropic's prompt cache rewards.

## Phase 1 — initialize and cache the source

```bash
$ mkdir -p sqlite-wasm && cd sqlite-wasm
$ curl -O https://www.sqlite.org/2025/sqlite-amalgamation-3500000.zip
$ unzip sqlite-amalgamation-3500000.zip
$ mv sqlite-amalgamation-3500000 src
$ ls src
sqlite3.c  sqlite3.h  shell.c  sqlite3ext.h

$ ccc init \
    --prompt "Compile SQLite (amalgamation) to a single WASM module with a JS wrapper exposing a Database class. Target: Emscripten, modern browsers, no Node-only deps." \
    --phase "MVP"

$ ccc style "$(cat <<'EOF'
- C: SQLite house style — 2-space indent, K&R braces, sqlite3_ prefix
- JS: TypeScript, strict, ES2022, no class inheritance, prefer composition
- Build: emcc directly, no CMake; one Makefile target per artifact
- No external runtime deps in the JS wrapper
EOF
)"

$ ccc cache ./src --label "sqlite amalgamation"
Cached source: sqlite amalgamation (.../sqlite-wasm/src, 9123456 bytes)
```

`ccc cache ./src` registers the directory; the harness will read it through the SHA-256-keyed source cache the first time `ccc ask` runs and reuse the result on every subsequent call until any byte under `./src` changes.

## Phase 2 — sprint 1: figure out what to compile

```bash
$ ccc sprint start "compile-baseline" --phase "MVP"
Started sprint compile-baseline (phase=MVP)

$ ccc todo "Identify minimum SQLITE_OMIT_* set for browser builds"
$ ccc todo "Pick threading model (single-threaded for first cut)"
$ ccc todo "Draft emcc command line"
$ ccc todo "Confirm sqlite3_os_init / sqlite3_os_end stubs for VFS"

$ ccc ask "Read the cached amalgamation. List the SQLITE_OMIT_* and SQLITE_DEFAULT_* compile-time options most relevant when targeting WASM in a browser sandbox: no fork, no mmap, no shared memory, no real filesystem. Quote the source lines that gate each option."
```

Claude responds with a list of recommended `-D` flags grounded in `sqlite3.c` (`SQLITE_OMIT_LOAD_EXTENSION`, `SQLITE_THREADSAFE=0`, `SQLITE_DEFAULT_MEMSTATUS=0`, etc.). The first call writes the prompt cache:

```
[ccc] tokens — input=312 output=1421 cache_read=0 cache_creation=2356008 hit=0%
```

`cache_creation=2356008` is the cached portion of the prefix (the amalgamation source plus the system prompt) being written to Anthropic's prompt cache. The first call is the expensive one.

Second call in the same sprint:

```bash
$ ccc ask "Now identify which symbols (sqlite3_open_v2, sqlite3_prepare_v2, sqlite3_step, sqlite3_column_*, sqlite3_finalize, sqlite3_close) need EMSCRIPTEN_KEEPALIVE annotations or to be listed in EXPORTED_FUNCTIONS. Cite the function declarations from the cached header."
```

```
[ccc] tokens — input=287 output=1903 cache_read=2356008 cache_creation=0 hit=100%
```

`cache_read=2356008, hit=100%`. The amalgamation didn't have to be re-uploaded; we paid ~10 % of the input price for the prefix.

```bash
$ ccc done <id>     # mark each todo complete as it lands
$ ccc done <id>
$ ccc done <id>
$ ccc done <id>
$ ccc sprint complete --notes "Picked SQLITE_THREADSAFE=0 + memvfs; drafted 12-symbol export list."
```

## Phase 3 — sprint 2: write the build, watch the cache

```bash
$ ccc sprint start "emcc-build" --phase "MVP"
$ ccc todo "Write Makefile with debug + release targets"
$ ccc todo "Stub a memvfs so :memory: works in the browser"
$ ccc todo "Resolve any unresolved symbols at link time"

$ ccc ask "Draft a Makefile with two targets — debug (-O0 -gsource-map) and release (-O3 -flto). Inputs: src/sqlite3.c plus the JS glue we'll write next. Use -sEXPORTED_FUNCTIONS, -sEXPORTED_RUNTIME_METHODS=ccall,cwrap,UTF8ToString,stringToUTF8, -sMODULARIZE=1, -sEXPORT_ES6=1."
```

```
[ccc] tokens — input=243 output=1102 cache_read=2356008 cache_creation=0 hit=100%
```

We add a JS wrapper file, register it with `ccc cache`, and watch the prefix change:

```bash
$ mkdir -p js && touch js/database.ts
$ ccc cache ./js --label "js wrapper"
Cached source: js wrapper (.../sqlite-wasm/js, 0 bytes)

$ ccc ask "Sketch the Database class in js/database.ts. It wraps the WASM module emitted by emcc, exposes `prepare(sql)` returning a Statement, and `exec(sql)` for one-shot queries. Use ccall/cwrap from the runtime methods we exported."
```

```
[ccc] tokens — input=298 output=1855 cache_read=2356008 cache_creation=192 hit=99%
```

`cache_creation=192` is small — the new `./js` directory was added to the cached prefix; only the new bytes had to be written. Read tokens still dominate. **This is the pattern to look for**: a tiny `cache_creation` after `ccc cache` of a small new source, dwarfed by `cache_read`.

## Phase 4 — context window fills, compact

After 25-odd `ccc ask` calls across two sprints, `ccc status` reports session tokens above the threshold:

```bash
$ ccc status
State: .../sqlite-wasm/.ccc/state.json
Phase: MVP
Sprint: emcc-build
Original prompt: Compile SQLite (amalgamation) to a single WASM module with a JS wrap...
Cached sources: 2
  - sqlite amalgamation (.../sqlite-wasm/src, 9123456 bytes)
  - js wrapper (.../sqlite-wasm/js, 4811 bytes)
Todos open: 4
  [a3f2c1d4] Wire memvfs through sqlite3_vfs_register at module init
  [b1d99e02] Resolve __syscall_unlinkat link error
  [c84b71f5] Add Statement.bind for parameterized queries
  [d22a09cb] Write a smoke test that opens :memory: and runs CREATE TABLE
Completed: 12
Session tokens (input+output+cache): 168240
Last handoff: (none)

$ ccc compact
Compacted. Handoff: .ccc/handoffs/handoff-2026-04-27T22-30-12-auto.md
```

The handoff is a ≤750-word Markdown document with the five required sections (Code Style, Original Prompt / Current Phase, Completed Results, To-Do, Sprints / Phases for Next Context Window). Open it to confirm:

```bash
$ cat .ccc/handoffs/handoff-2026-04-27T22-30-12-auto.md | head -40
## Code Style
- C: SQLite house style — 2-space indent, K&R braces, sqlite3_ prefix
- JS: TypeScript strict, ES2022, no class inheritance, prefer composition
- Build: emcc directly, single Makefile, no CMake
- No runtime JS deps in the wrapper

## Original Prompt / Current Phase
"Compile SQLite (amalgamation) to a single WASM module with a JS wrapper exposing a Database class. Target: Emscripten, modern browsers, no Node-only deps."
Phase: MVP. Active sprint: emcc-build.

## Completed Results
- Identified minimum SQLITE_OMIT_* set for browser builds (sqlite3.c:1241–1380)
- Drafted Makefile with debug/release targets (Makefile:1–48)
- Wrote stub memvfs registration (js/database.ts:14–37)
- Picked 12-symbol export list (Makefile:18)
[...]
```

End of context window — close the laptop.

## Phase 5 — next session, resume

The next morning, in a fresh Claude Code window:

```bash
$ cd sqlite-wasm
$ ls -t .ccc/handoffs/*.md | head -1
.ccc/handoffs/handoff-2026-04-27T22-30-12-auto.md

$ ccc resume .ccc/handoffs/handoff-2026-04-27T22-30-12-auto.md
Resumed from .ccc/handoffs/handoff-2026-04-27T22-30-12-auto.md. Loaded 4 todos. Phase=MVP.

$ ccc status
[...same shape, fresh session-token counters at 0...]

$ ccc ask "Where did we leave off on the __syscall_unlinkat link error? Suggest a stub implementation that returns -ENOSYS."
```

```
[ccc] tokens — input=412 output=782 cache_read=0 cache_creation=2356200 hit=0%
```

The cache is cold for the new context window (Anthropic's prompt cache is tied to the prompt prefix, not your local `.ccc/`), so the first call rewarms it. From the second call onward you're back at `hit ≈ 100 %`.

**Don't paste the handoff into the chat as well as `ccc resume`.** The state hydration already loaded everything; pasting it would duplicate the content into the user message and burn tokens for nothing.

## Phase 6 — ship

```bash
$ ccc sprint start "wrapper-tests" --phase "MVP"
$ ccc todo "Write smoke test: open :memory:, CREATE TABLE, INSERT, SELECT"
$ ccc todo "Write Statement.bind tests for ?N and :name parameters"
$ ccc todo "Wire vitest to load the .wasm via ?url import"

$ ccc ask "Write a vitest spec at tests/database.test.ts that covers the smoke path. Use the cached js/database.ts as the import. Mock nothing — load the real WASM."

# ... sprint completes ...

$ ccc sprint complete --notes "Smoke + bind tests green; CI runs in 14s."
$ ccc phase "release"
$ ccc sprint start "publish" --phase "release"
$ ccc todo "Tag v0.1.0"
$ ccc todo "Publish to npm with provenance"
```

When the project ships, `ccc compact --force` writes a final handoff for posterity. The `.ccc/handoffs/` directory is the audit trail of how the build came together.

## What you just got out of `ccc`

- **Token cost**: the 9 MB amalgamation was uploaded to Anthropic **once per cache TTL** (5 minutes by default, 1 hour optionally), not on every `ccc ask`. With ~30 calls per session the cost difference is roughly an order of magnitude.
- **Continuity**: the next session reads a 750-word handoff instead of re-reading the entire prior conversation. Resume time goes from "ten minutes of getting Claude back up to speed" to one CLI command.
- **Auditability**: every sprint, every completed todo, and every cache invalidation is recorded in `.ccc/state.json` and the handoff archive. Six months from now, `ls .ccc/handoffs/` is the project's high-level changelog.

## Other use cases

The same pattern applies any time you have a **stable large input** + **many volatile queries** + **a session that won't fit in one context window**.

| Use case | What you cache | Why it's a good fit |
|---|---|---|
| Porting a C codebase to Rust | The original C source tree | Same source, hundreds of "translate `<function>` to idiomatic Rust" calls |
| Auditing a smart contract | The Solidity source + relevant OpenZeppelin libs | Same code, dozens of "is this re-entrancy safe?" / "what happens if X" calls |
| Reverse-engineering a binary | Disassembly + decompiled C output | Static input, iterative "what does function 0x1a40 do?" probes |
| Reviewing a 200-page RFC or spec | The spec PDF rendered to text | Static input, repeated "does the protocol allow X?" lookups |
| Migrating a database schema | Current schema + sample query workload | Same schema, many "rewrite this query for the new shape" calls |
| Translating documentation | Source-language docs | One source, many `"translate section X to <language>"` calls |
| Triaging a flaky test suite | The whole test directory + recent CI logs | Stable corpus, repeated "why might `test_foo` flake?" probes |
| Long-running competitive-programming session | Editorial PDFs + your own past solutions | Stable archive, many "approach for problem Y given style Z" calls |
| Drafting a long-form piece (book, paper, RFC) | Outline + reference material + style guide | Stable references, hundreds of "write section 3.2 in this voice" calls across days |
| Onboarding to a new codebase | The whole repo, scoped to the modules you'll touch | Stable code, dozens of "where is X defined and who calls it?" probes |

The decision rule is simple: **if the same large input is going to feed more than two queries, cache it. If the work is going to span more than one context window, run it under `ccc`.**
