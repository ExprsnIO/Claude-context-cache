/** Public library API. */

export {
  State,
  StateStore,
  type Todo,
  type Sprint,
  type ContextSource,
  type StateData,
  type AnthropicUsage,
} from "./state.js";

export {
  WORD_LIMIT,
  REQUIRED_SECTIONS,
  countWords,
  validate,
  truncateToLimit,
  writeHandoff,
  parseHandoff,
  hydrateStateFromHandoff,
} from "./handoff.js";

export {
  ASK_SYSTEM_PROMPT,
  HANDOFF_SYSTEM_PROMPT,
  renderTopicContext,
} from "./prompts.js";

export {
  ask,
  generateHandoff,
  gatherContextSources,
  DEFAULT_MODEL,
  DEFAULT_MAX_TOKENS,
  type AskOptions,
  type AskResult,
} from "./client.js";

export {
  compact,
  sessionTokenEstimate,
  shouldCompact,
  DEFAULT_THRESHOLD_TOKENS,
  type CompactResult,
} from "./compact.js";
