# Handoff documents

Handoffs are the artifact that lets a brand-new context window pick up exactly where the previous one left off. They are intentionally small and intentionally structured.

## The contract

Every handoff is enforced to:

- ≤ **750 words**
- Contain these five sections, **in order**:

1. **Code Style** — observed conventions (formatting, naming, error handling, language idioms).
2. **Original Prompt / Current Phase** — the verbatim original task plus the active phase + sprint.
3. **Completed Results** — what was finished this window.
4. **To-Do** — outstanding work, ordered by priority.
5. **Sprints / Phases for Next Context Window** — explicit ordered plan for the next session.

If the harness detects an overshoot or a missing section, the file is written with a `needs-review` suffix and the failing checks are printed to stderr (exit code `2`).

## Why these five sections

Every section answers one question the next context window will ask within its first few turns:

| Section | Question it answers |
|---|---|
| Code Style | "How should I write code in this repo?" |
| Original Prompt / Current Phase | "What were we even doing, and what stage are we in?" |
| Completed Results | "What's already done so I don't redo it?" |
| To-Do | "What's left, in what order?" |
| Sprints / Phases for Next Context Window | "What's the explicit plan for *this* session?" |

A handoff that satisfies all five is enough to bootstrap. One that's missing any of them is flagged so a human can patch it before resuming.

## File naming and location

Handoffs are written to `.ccc/handoffs/handoff-<timestamp>.md`. Filenames carry one of these suffixes:

| Suffix | Meaning |
|---|---|
| (none) / `manual` | Generated cleanly. Safe to resume from. |
| `needs-review` | Validation flagged a missing section or word overrun. Open and edit before resuming. |

Handoffs are part of the audit trail — don't delete them.

## How they're produced

`ccc handoff` and `ccc compact` both call the same code path:

1. Build a system prompt from your code style, original prompt, current phase/sprint, todos, completed work, and cached sources.
2. Call Claude with prompt caching so the prefix is reused across invocations.
3. Truncate the response to 750 words if Claude overshoots.
4. Validate the five required sections.
5. Write the file and update `state.last_handoff_path`.

Token usage from the call is recorded in `state.json` like any other `ccc ask`.

## Resuming

```bash
ccc resume .ccc/handoffs/handoff-<stamp>.md
```

`resume` parses the five sections out of the file and hydrates a `State`:

- Original prompt and phase are extracted from section 2.
- Code style is loaded from section 1.
- Each line item under To-Do becomes a `Todo`.
- Completed Results are stored as completed todos.
- Sprints / Phases for Next Context Window seed the next sprint plan.

Pass `--overwrite` to replace an existing `.ccc/state.json` instead of merging.

## When a handoff has a `needs-review` suffix

Open it. Common fixes:

- Trim verbose paragraphs until the word count fits.
- Add the missing section header (e.g. `## Code Style`) and a short paragraph or bullet list.
- Re-order sections to the canonical order.

You can resume from a `needs-review` file as-is — the suffix is informational, not blocking — but the parser may miss content from malformed sections.

## See also

- [`ccc handoff` and `ccc compact`](./cli-reference.md#ccc-handoff) in the CLI reference.
- [Prompt caching](./prompt-caching.md) for why these calls are cheap to repeat.
