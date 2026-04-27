# Claude Context Cache — Documentation

A small CLI tool (`ccc`) that caches Claude topic contexts via the Anthropic prompt-caching API, tracks to-dos / sprints / phases for the active session, and emits **≤750-word handoff documents** so the next context window can pick up where the last one stopped.

This documentation set is organized for two audiences:

- **Users** running `ccc` from the command line or letting the Claude Code subagent drive it.
- **Library consumers** integrating the Node primitives into their own scripts or services.

## Start here

| Page | When to read |
|---|---|
| [Getting started](./getting-started.md) | First-time install and a 90-second tour. |
| [CLI reference](./cli-reference.md) | Every command, every flag, exit codes. |
| [Handoff documents](./handoff-documents.md) | The ≤750-word contract and what each section means. |
| [Prompt caching](./prompt-caching.md) | Why repeat `ccc ask` calls cost ~10% of the first one. |

## Going deeper

| Page | Scope |
|---|---|
| [Architecture](./architecture.md) | Monorepo layout, language split, build order. |
| [Context store](./context-store.md) | Tiered cache backends (Redis → SQLite). |
| [Node library API](./node-library.md) | TypeScript primitives exported from the npm package. |
| [Claude Code subagent](./subagent.md) | The project-scoped agent that drives `ccc` for you. |
| [Configuration](./configuration.md) | Environment variables, defaults, override knobs. |
| [Troubleshooting](./troubleshooting.md) | Common errors and how to recover. |

## Project files

- [README.md](../README.md) — top-level overview.
- [Usage.md](../Usage.md) — long-form reference (this docs set is the structured split).
- [License.md](../License.md) — MIT.
