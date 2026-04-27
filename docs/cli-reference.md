# CLI reference

Every `ccc` subcommand, with flags and exit codes.

All commands accept `--root <path>` (defaults to cwd) to point at a non-current project root. `--version` prints the package version.

## `ccc init`

Initialize a `.ccc/` workspace.

```bash
ccc init [--prompt <text>] [--style <text>] [--phase <name>]
```

| Flag | Effect |
|---|---|
| `--prompt` | Record the original task prompt verbatim |
| `--style` | Initial code-style notes |
| `--phase` | Starting phase label (e.g. `MVP`, `refactor`) |

Re-running `ccc init` on an existing workspace is a no-op for state but ensures the directory layout exists.

## `ccc cache <path>`

Register a file or directory as cached topic context. The path is recorded with its byte size; file content is read at `ccc ask` time and stitched into the system prompt.

```bash
ccc cache ./src   --label "app source"
ccc cache ./tests --label "test suite"
```

| Flag | Effect |
|---|---|
| `--label` | Short label (defaults to the basename) |

Re-caching the same path refreshes the entry's byte count and `cached_at` timestamp.

## `ccc prompt <text>` / `ccc style <text>`

Replace the recorded original prompt or code-style notes. `ccc style --append` adds to existing notes instead of replacing them.

## `ccc phase <name>`

Set the current phase label. Phases group sprints. New phase names are appended to the phase history.

## `ccc sprint`

| Subcommand | Purpose |
|---|---|
| `ccc sprint start <name> [--phase <name>]` | Start a focused chunk of work under a phase. Auto-completes any active sprint. |
| `ccc sprint complete [--notes <text>]` | Close the active sprint, recording an optional one-line summary. |

## `ccc todo <text>` / `ccc done <id-prefix>`

Track work items in real time. `done` accepts any unique id prefix (4 chars is usually enough).

```bash
ccc todo "Write LoginView class"
# Added todo a3f2c1: Write LoginView class
ccc done a3f2
# Completed a3f2c1: Write LoginView class
```

## `ccc status`

Print phase, sprint, original prompt (truncated to 80 chars), cached sources, open todos, completed work, accumulated session token usage, and the path to the last handoff.

## `ccc ask <text>`

Send a prompt to Claude with the cached topic context. The system-prompt prefix is byte-stable across calls, so the second and later calls hit the prompt cache at ~10% of the input price.

```bash
ccc ask "Sketch the LoginView class. Use the cached source for naming conventions."
```

| Flag | Default | Effect |
|---|---|---|
| `--model` | `claude-opus-4-7` | Override the model |
| `--max-tokens` | `16000` | Output token cap |
| `--threshold` | `150000` | Session-token budget that triggers an auto-compact reminder on stderr |

If stdin is piped and `<text>` is omitted, the prompt is read from stdin.

## `ccc handoff`

Generate a ≤750-word handoff document on demand. The CLI validates the output (word count + required sections); if either check fails, the file is written with a `needs-review` suffix and warnings are printed to stderr.

| Flag | Effect |
|---|---|
| `--model` | Override the model |
| `--print` | Echo the document to stdout in addition to writing it |

**Exit codes:** `0` on success, `2` when validation flagged the document (file is still written, with `needs-review` in its name).

See [Handoff documents](./handoff-documents.md) for the full contract.

## `ccc compact`

Auto-compact: emit a handoff and reset session counters once accumulated session tokens exceed the threshold.

| Flag | Default | Effect |
|---|---|---|
| `--threshold` | `150000` | Token budget that triggers compaction |
| `--force` | `false` | Compact even if under the threshold |

If under threshold and `--force` is not given, the command prints what would have happened and exits `0` (no-op).

## `ccc resume <handoff>`

Load a handoff document into a fresh state for the new context window. Hydrates todos, the original prompt, code style, and the current phase from the document's required sections.

| Flag | Effect |
|---|---|
| `--overwrite` | Replace any existing `.ccc/state.json` with the handoff contents |

By default `ccc resume` merges into an existing state if one is present.

## Common exit codes

| Code | Meaning |
|---|---|
| `0` | Success (or no-op) |
| `1` | User error: missing argument, missing path, no matching todo, no active sprint |
| `2` | Handoff written but failed validation; review the file |

## See also

- [Configuration](./configuration.md) for env vars and defaults.
- [Troubleshooting](./troubleshooting.md) for typical error conditions.
