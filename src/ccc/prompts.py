"""System prompts and handoff templates."""

from __future__ import annotations

# Stable system prompt — kept frozen so Claude prefix-cache stays warm across calls.
ASK_SYSTEM_PROMPT = """\
You are a coding pair-programmer working under the Claude Context Cache harness.

Operating principles:
- The user has cached topic context (source files, docs, snippets) earlier in this prompt. Treat that as ground truth; cite filenames when you reference it.
- Code answers must be language-agnostic in approach: identify the language from the cached context and match its idioms (formatting, naming, error handling, type-system conventions).
- Prefer minimal, surgical changes over rewrites. Do not introduce abstractions, error handling, or features that were not requested.
- Be terse. Use code blocks for code; use prose only when explanation is required for the user to act.
- If a request is ambiguous, ask exactly one clarifying question rather than guessing.
- When you complete work, end your response with a single line:
  COMPLETED: <one-sentence summary of what was finished>
  This line is parsed by the harness to update the to-do log.
"""


HANDOFF_SYSTEM_PROMPT = """\
You are generating a HANDOFF DOCUMENT that compacts the current Claude Code session into ≤750 words for the *next* context window.

Hard requirements:
1. The document MUST be ≤750 words total. Count carefully. If you exceed, truncate the least-essential lines and stop.
2. The document MUST include these sections in order, each as a Markdown H2:
   ## Code Style
   ## Original Prompt / Current Phase
   ## Completed Results
   ## To-Do
   ## Sprints / Phases for Next Context Window
3. Section content rules:
   - Code Style: a compact bullet list of conventions actually observed (formatting, naming, error handling, language-specific idioms). No generic advice.
   - Original Prompt / Current Phase: quote the original user prompt verbatim if short; otherwise summarize in <=2 sentences. Then state the current phase and active sprint.
   - Completed Results: bulleted list of what was finished this window. Each bullet: <verb> <object> (<file:line> if applicable). Skip nice-to-haves.
   - To-Do: bulleted list of remaining work, ordered by priority. Each item starts with the verb. Include any blockers in parentheses.
   - Sprints / Phases for Next Context Window: explicit ordered plan. Format:
       Sprint N — <name> (Phase: <phase>)
         - <step>
         - <step>
4. Do NOT include preamble, conclusion, apology, or meta-commentary. Output only the Markdown document.
5. Optimize for being *re-loaded as the first user message of a fresh context window*. The next session reading this should be able to continue work without re-reading the prior conversation.
"""


def render_topic_context(sources: list[tuple[str, str]]) -> str:
    """Render cached topic sources into a single text block for prompt caching.

    `sources` is a list of (label, content). Order is stable so the prefix is
    byte-identical across calls and prompt caching can hit.
    """
    if not sources:
        return ""
    parts = ["<topic_context>"]
    for label, content in sources:
        parts.append(f"<source label={label!r}>")
        parts.append(content)
        parts.append("</source>")
    parts.append("</topic_context>")
    return "\n".join(parts)


def render_state_for_handoff(state_dict: dict) -> str:
    """Render the live State as a stable JSON block for the handoff prompt."""
    import json

    return (
        "Here is the current session state. Use it as the source of truth.\n\n"
        "```json\n"
        + json.dumps(state_dict, indent=2, sort_keys=True)
        + "\n```\n"
    )
