# Prompt caching

Why repeated `ccc ask` calls cost ~10% of the first one — and what invalidates the cache.

## The shape of every call

Each `ccc ask` (and `ccc handoff`, and `ccc compact`) sends a request shaped like this:

```
system: [
  <fixed CCC instructions>,
  <code style>,
  <original prompt>,
  <each cached source's contents>,                    ← cache_control: ephemeral
]
messages: [
  { role: "user", content: <your volatile prompt> }
]
```

The cached topic context is stitched into the system prompt with `cache_control: ephemeral`, marking the end of the cache prefix.

## Why this is fast

The system-prompt prefix — system instructions + code style + original prompt + every cached source — is **byte-stable** across `ccc ask` calls. The Anthropic API hashes the prefix; if the hash matches a recent request, the cached tokens are read at ~10% of the input price.

In practical terms:

- **First call:** writes the cache. Pays full input price for the prefix, plus full price for your user message.
- **Subsequent calls:** reads the cache. Pays ~10% for the prefix, full price only for the new user message.

The user message sits **after** the cache breakpoint and is the only volatile part.

## What invalidates the cache

The cache is keyed on the byte-exact prefix. Anything that changes the prefix invalidates it once; the next call warms a fresh entry.

Operations that invalidate:

- `ccc cache <new-path>` — new source appended to the prefix.
- `ccc prompt <text>` — original prompt replaced.
- `ccc style <text>` (without `--append`) — style block replaced.
- Editing a cached file on disk — file mtime/size changes are detected by the source-cache layer (see [Context store](./context-store.md)).

Operations that **do not** invalidate:

- `ccc todo`, `ccc done`, `ccc sprint *`, `ccc phase` — these update `state.json` but are not part of the call's system prefix during `ccc ask`. They affect `ccc handoff` payloads instead.
- `ccc status` — local-only, no API call.

## The source-read cache (Node only)

The npm package adds a second cache layer in front of the file system:

- Source files registered with `ccc cache` are read via a fingerprint of `mtime + size`.
- If neither has changed, the previous read is returned from the [context store](./context-store.md) (Redis → SQLite in-memory → SQLite on-disk).
- Any on-disk change invalidates that single entry.

This avoids re-walking and re-reading large directories on every call. The Anthropic prompt cache then picks up where the source-read cache leaves off.

## Tracking cache effectiveness

Every API call's usage is recorded into `state.json`:

- `session_input_tokens` — non-cached input
- `session_output_tokens` — Claude's output
- `cache_read_tokens` — input tokens served from cache
- `cache_creation_tokens` — input tokens written to a fresh cache entry

`ccc status` prints these. A healthy long session shows `cache_read_tokens` dominating after the first call or two.

## Trade-offs

- **Cache TTL is short** (minutes, not hours). Long pauses between `ccc ask` calls can let the entry expire, forcing a re-write on the next call.
- **Adding a cached source mid-session has a one-call cost.** Plan to register everything you'll need with `ccc cache` up front when possible.
- **Editing files is fine.** The source-read cache invalidates only the affected entry; the Anthropic prompt cache invalidates once on the next call.

## See also

- [Context store](./context-store.md) — backends behind the source-read cache.
- [Configuration](./configuration.md) — env vars that influence caching.
