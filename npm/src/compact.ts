/** Auto-compact: emit handoff and reset session counters at threshold. */

import { generateHandoff } from "./client.js";
import { truncateToLimit, validate, writeHandoff } from "./handoff.js";
import type { State, StateStore } from "./state.js";

export const DEFAULT_THRESHOLD_TOKENS = 150_000;

export function sessionTokenEstimate(state: State): number {
  return (
    state.session_input_tokens +
    state.session_output_tokens +
    state.cache_read_tokens +
    state.cache_creation_tokens
  );
}

export function shouldCompact(
  state: State,
  threshold = DEFAULT_THRESHOLD_TOKENS,
): boolean {
  return sessionTokenEstimate(state) >= threshold;
}

export interface CompactResult {
  handoffPath: string;
  problems: string[];
}

export async function compact(
  store: StateStore,
  state: State,
  opts: { threshold?: number; force?: boolean } = {},
): Promise<CompactResult | null> {
  const threshold = opts.threshold ?? DEFAULT_THRESHOLD_TOKENS;
  if (!opts.force && !shouldCompact(state, threshold)) return null;

  const result = await generateHandoff(state);
  state.recordUsage(result.usage);

  const text = truncateToLimit(result.text);
  const problems = validate(text);
  const label = problems.length > 0 ? "needs-review" : "auto";
  const handoffPath = writeHandoff(store, text, label);

  state.session_input_tokens = 0;
  state.session_output_tokens = 0;
  state.cache_read_tokens = 0;
  state.cache_creation_tokens = 0;
  state.last_handoff_path = handoffPath;
  store.save(state);

  return { handoffPath, problems };
}
