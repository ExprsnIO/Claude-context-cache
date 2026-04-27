# Configuration

Environment variables, defaults, and per-call overrides.

## Environment variables

### Auth

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes (for `ask`/`handoff`/`compact`) | Auth for the Anthropic API |

`ccc init`, `ccc cache`, `ccc todo`, `ccc done`, `ccc status`, `ccc sprint`, `ccc phase`, and `ccc resume` all run offline and do not require the key.

### npm install

| Variable | Effect |
|---|---|
| `CCC_NO_AUTOENGAGE=1` | Skip the npm `postinstall` hook (no agent drop, no `.ccc/` init) |
| `CI` | Treated like `CCC_NO_AUTOENGAGE=1` |

The hook also auto-skips on global installs.

### Context store (Node only)

See [Context store](./context-store.md) for full details.

| Variable | Effect |
|---|---|
| `CCC_REDIS_URL` / `REDIS_URL` | Redis URL for the cache tier |
| `CCC_SQLITE_PATH` | Override the on-disk SQLite path |
| `CCC_DISABLE_REDIS=1` | Skip the Redis probe |
| `CCC_DISABLE_SQLITE_MEMORY=1` | Skip the in-memory tier (go straight to disk) |
| `CCC_MYSQL_URL` | Enable MySQL write-through backing |
| `CCC_POSTGRES_URL` | Enable Postgres write-through backing |
| `CCC_MONGO_URL` | Enable MongoDB write-through backing |
| `CCC_TABLE_NAME` | Override table / collection name (default `ccc_context`) |
| `CCC_NAMESPACE` | Key namespace prefix (default `""`) |
| `CCC_PROBE_TIMEOUT_MS` | Backend probe timeout (default `1500`) |

## Defaults

| Setting | Default | Override |
|---|---|---|
| Model | `claude-opus-4-7` | `--model` per call |
| Compaction threshold | `150_000` session tokens | `--threshold` |
| Handoff word limit | `750` | (compile-time constant) |
| Workspace root | cwd | `--root <path>` |
| `ccc ask --max-tokens` | `16000` | `--max-tokens` |
| Python | ≥ 3.10 | — |
| Node | ≥ 18 | — |

## Per-call overrides

Most defaults can be overridden on the command line.

```bash
ccc ask --model claude-sonnet-4-6 --max-tokens 4096 "..."
ccc handoff --model claude-haiku-4-5-20251001
ccc compact --threshold 80000
ccc compact --force
ccc resume .ccc/handoffs/foo.md --overwrite
ccc --root /path/to/project status
```

## Choosing a model

The default `claude-opus-4-7` is a sensible starting point for most work. For routine `ccc ask` calls where the cached prefix is doing the heavy lifting, swapping to `claude-sonnet-4-6` or `claude-haiku-4-5-20251001` cuts cost further. For handoff generation, prefer the strongest model you can afford — the document is the bridge between context windows and is worth getting right.

## Configuring the threshold

`150_000` session tokens is a rough budget that leaves headroom for in-flight work before the context window genuinely fills. Lower it if your model has a smaller window, your sessions tend to be conversation-heavy, or you want more frequent checkpoints.

```bash
ccc ask --threshold 80000 "..."
ccc compact --threshold 80000
```

The threshold is checked against the running sum of `session_input_tokens + session_output_tokens + cache_read_tokens + cache_creation_tokens` recorded in `state.json`.

## See also

- [CLI reference](./cli-reference.md) for the full flag list.
- [Context store](./context-store.md) for cache backend selection.
