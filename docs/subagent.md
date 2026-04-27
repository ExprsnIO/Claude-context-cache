# Claude Code subagent

A project-level subagent ships at [`.claude/agents/context-cache.md`](../.claude/agents/context-cache.md). When Claude Code runs in a repository that contains this file, it spawns the **`context-cache`** agent for long-running tasks and drives `ccc` automatically — initializing the workspace, tracking todos/sprints/phases, calling `ccc ask` against the cached context, and generating handoffs when the context window fills.

## When the subagent engages

The subagent engages proactively when any of these conditions hold:

1. The user describes a task that will plausibly span more than one context window (large refactor, migration, multi-feature build, multi-day investigation).
2. The user references prior session work ("continue where we left off", "pick up the JWT thing").
3. The current session has accumulated >100K tokens of conversation and substantial work has been done — recommend a compact.
4. The user asks to "save progress", "hand off", "compact", "resume", or "checkpoint".
5. A `.ccc/` directory exists in the working tree — treat it as a signal that this project is already under context-cache management.

If none apply, the subagent stays quiet. It does not invoke `ccc` for one-shot questions.

## Install globally

The npm package's `postinstall` drops the agent file into your project automatically. To make it available to **every** Claude Code session, copy the file into your user agents directory:

```bash
mkdir -p ~/.claude/agents
cp .claude/agents/context-cache.md ~/.claude/agents/
```

Invoke explicitly with `/agents` in Claude Code, or just describe a multi-session task and Claude will route to it.

## Operating principles

The agent follows a small set of rules:

- **Run `ccc` via Bash.** All state lives in `.ccc/state.json`; never edit it by hand.
- **Cache early.** Once the relevant files / directories are known, run `ccc cache <path>` for each so subsequent `ccc ask` calls hit the prompt cache.
- **Capture the original prompt and code style up front.** `ccc init --prompt "<verbatim user request>" --phase "<phase>" --style "<observed conventions>"`.
- **Track work as it happens.** `ccc todo` for new work, `ccc done <id-prefix>` the moment something finishes. No batching.
- **Sprints group todos under a phase.** `ccc sprint start` at the start of a focused chunk; `ccc sprint complete --notes "<summary>"` when it's done.
- **`ccc status` whenever state is unclear.**
- **Compact at sensible breakpoints**, not mid-thought. End of a sprint, end of a phase, or when token use approaches the threshold.

## Standard workflows

### Starting fresh

```bash
ccc init --prompt "<the user's literal request>" --phase "<MVP / refactor / investigation / ...>"
ccc style "$(cat <<'EOF'
- <observed convention 1>
- <observed convention 2>
EOF
)"
ccc cache <relevant-dir-or-file>      # repeat for each
ccc sprint start "<scope of first sprint>" --phase "<phase>"
ccc todo "<first concrete task>"
ccc todo "<second concrete task>"
```

### Resuming from a previous session

```bash
ls -t .ccc/handoffs/*.md | head -5    # find the latest
ccc resume .ccc/handoffs/<file>.md    # hydrates todos + original prompt
ccc status                            # confirm what got loaded
```

After `ccc resume`, re-cache any sources whose paths may have changed (`ccc cache` is idempotent).

### Context pressure

```bash
ccc status                    # check session token estimate
ccc compact                   # auto-generates handoff if over threshold
ccc compact --force           # generate a handoff right now regardless
ccc handoff --print           # print to stdout in addition to writing the file
```

## Boundaries

- **Never** modifies `.ccc/state.json` directly. Always uses the CLI.
- **Never** invokes `ccc ask` for trivia or general questions — only for queries that benefit from cached topic context.
- **Never** auto-`ccc compact --force`s without telling the user; it costs an API call.
- **Does not** add `ccc` commands to project hooks or git pre-commit on the user's behalf without confirmation.
- **Does not** delete handoff files — they are the audit trail.

## Reporting back

When the agent completes a unit of work, it returns a short summary to the orchestrator: what it ran, what state changed (new todos, completed todos, current phase/sprint), and any handoff path written. Kept under ~100 words; the parent surfaces what the user needs to see.

## See also

- [Handoff documents](./handoff-documents.md) — the artifact the subagent produces.
- [CLI reference](./cli-reference.md) — every command the subagent uses.
- [Troubleshooting](./troubleshooting.md) — failure modes the subagent will flag.
