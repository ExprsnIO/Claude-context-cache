# Troubleshooting

Common errors and how to recover.

## `ANTHROPIC_API_KEY` not set

**Symptom:** `ccc ask`, `ccc handoff`, and `ccc compact` exit with an error.

**Fix:** Export the key in your shell.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The other commands (`init`, `cache`, `todo`, `done`, `sprint`, `phase`, `status`, `resume`) run offline and don't need the key.

## `No state at .ccc/state.json. Run `ccc init` first.`

**Symptom:** Any command other than `init` errors out on a fresh checkout.

**Fix:** Run `ccc init` with whatever context you have, then retry.

```bash
ccc init --prompt "<your task>" --phase "<phase>"
```

## A cached source path no longer exists on disk

**Symptom:** A file or directory you registered with `ccc cache` was moved or deleted.

**Behavior:** The client silently skips it on the next `ccc ask`. The entry stays in `state.json`.

**Fix:** Inspect the registry, then refresh.

```bash
ccc status                        # see registered sources
ccc cache <new-or-replacement-path>
```

## Handoff file written with `needs-review` suffix

**Symptom:** `ccc handoff` exits with code `2` and the file in `.ccc/handoffs/` ends in `-needs-review.md`. Stderr lists the failed checks.

**Cause:** Claude exceeded 750 words or omitted one of the required sections.

**Fix:** Open the file and edit by hand. Common edits:

- Trim verbose paragraphs until the word count fits.
- Add the missing section header (e.g. `## Code Style`) and a short body.
- Re-order sections to: Code Style → Original Prompt / Current Phase → Completed Results → To-Do → Sprints / Phases for Next Context Window.

You can resume from a `needs-review` file as-is — the suffix is informational, not blocking — but the parser may miss content from malformed sections.

## `ccc compact` is a no-op

**Symptom:** `ccc compact` prints a "below threshold" message and writes nothing.

**Cause:** Session token usage hasn't hit the threshold (default `150000`).

**Fix:** Either wait until more `ccc ask` traffic accumulates, or force it.

```bash
ccc compact --force
```

## npm `postinstall` did nothing

**Symptom:** Installing `claude-context-cache` did not drop `.claude/agents/context-cache.md` and did not initialize `.ccc/`.

**Causes (any of):**

- Installed globally (`npm install -g`) — auto-skips by design.
- Running in CI (`CI` env var set) — auto-skips.
- `CCC_NO_AUTOENGAGE=1` is set in the environment.

**Fix:**

```bash
# Option 1: rerun without the env vars
unset CCC_NO_AUTOENGAGE
npm install claude-context-cache

# Option 2: drop the file by hand
mkdir -p .claude/agents
cp node_modules/claude-context-cache/assets/context-cache.md .claude/agents/
ccc init
```

## Prompt cache hit rate looks low

**Symptom:** `ccc status` shows `cache_read_tokens` is small relative to `session_input_tokens` after several `ccc ask` calls.

**Possible causes:**

- **Long pause between calls.** The Anthropic prompt cache TTL is short (minutes). If you wait too long, the entry expires and the next call rewrites it.
- **You changed the cached prefix.** Adding a `ccc cache` source, replacing the original prompt, or replacing (not appending) the style block invalidates the cache once.
- **A cached file changed on disk.** The source-read cache (Node) detects mtime/size changes and invalidates that entry, which in turn changes the byte-stable prefix.

**Fix:** Batch related `ccc ask` calls close together. Register all the sources you'll need with `ccc cache` up front. See [Prompt caching](./prompt-caching.md) for the full model.

## Context store falls back to SQLite when Redis is configured

**Symptom:** `info.cache` reports `sqlite-memory` or `sqlite-disk` even though `CCC_REDIS_URL` is set.

**Causes:**

- Redis was unreachable within the probe timeout.
- The Redis URL is wrong or auth failed.

**Fix:** Inspect `info.attempts` to see the exact failure.

```ts
const session = new Session();
await session.start();
console.log(await session.info());
```

Increase the timeout if the network is slow:

```bash
export CCC_PROBE_TIMEOUT_MS=5000
```

## State file got corrupted

**Symptom:** `ccc` commands fail with a JSON parse error on `.ccc/state.json`.

**Fix:** If you have a recent handoff, recover by resuming.

```bash
mv .ccc/state.json .ccc/state.json.bak
ccc init
ccc resume .ccc/handoffs/<latest>.md
```

If no handoff is available, hand-edit `.ccc/state.json.bak` to extract what you can, then `ccc init` and re-add todos manually.

## See also

- [CLI reference](./cli-reference.md) for exit codes.
- [Configuration](./configuration.md) for env vars that influence behavior.
- [Handoff documents](./handoff-documents.md) for the validation contract.
