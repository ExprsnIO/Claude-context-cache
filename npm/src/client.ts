/** Anthropic SDK wrapper with prompt caching for topic context. */

import { readFileSync, statSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

import Anthropic from "@anthropic-ai/sdk";

import {
  ASK_SYSTEM_PROMPT,
  HANDOFF_SYSTEM_PROMPT,
  renderTopicContext,
} from "./prompts.js";
import type { State, AnthropicUsage } from "./state.js";

export const DEFAULT_MODEL = "claude-opus-4-7";
export const DEFAULT_MAX_TOKENS = 16000;

function readSourceText(path: string): string {
  const stat = statSync(path);
  if (!stat.isDirectory()) {
    return readFileSync(path, "utf8");
  }
  const chunks: string[] = [];
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      const child = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(child);
      } else if (entry.isFile()) {
        try {
          const text = readFileSync(child, "utf8");
          const rel = relative(path, child);
          chunks.push(`--- ${rel} ---\n${text}`);
        } catch {
          /* skip non-utf8 / unreadable */
        }
      }
    }
  };
  walk(path);
  return chunks.join("\n\n");
}

export function gatherContextSources(state: State): Array<[string, string]> {
  const sources: Array<[string, string]> = [];
  for (const src of state.context_sources) {
    try {
      sources.push([src.label, readSourceText(src.path)]);
    } catch {
      /* skip vanished / unreadable */
    }
  }
  return sources;
}

function makeClient(): Anthropic {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error(
      "ANTHROPIC_API_KEY is not set. Export it before running `ccc ask` or `ccc handoff`.",
    );
  }
  return new Anthropic({ apiKey });
}

interface SystemBlock {
  type: "text";
  text: string;
  cache_control?: { type: "ephemeral" };
}

function buildSystemBlocks(basePrompt: string, topicText: string): SystemBlock[] {
  const blocks: SystemBlock[] = [{ type: "text", text: basePrompt }];
  if (topicText) {
    blocks.push({
      type: "text",
      text: topicText,
      cache_control: { type: "ephemeral" },
    });
  } else {
    blocks[0]!.cache_control = { type: "ephemeral" };
  }
  return blocks;
}

export interface AskOptions {
  model?: string;
  maxTokens?: number;
}

export interface AskResult {
  text: string;
  usage: AnthropicUsage;
}

export async function ask(
  state: State,
  userMessage: string,
  options: AskOptions = {},
): Promise<AskResult> {
  const client = makeClient();
  const topicText = renderTopicContext(gatherContextSources(state));
  const system = buildSystemBlocks(ASK_SYSTEM_PROMPT, topicText);

  const messages: Anthropic.MessageParam[] = [];
  if (state.original_prompt) {
    messages.push({
      role: "user",
      content: `Original task: ${state.original_prompt}`,
    });
    messages.push({
      role: "assistant",
      content: "Acknowledged. Working from cached context.",
    });
  }
  messages.push({ role: "user", content: userMessage });

  const response = await client.messages.create({
    model: options.model ?? DEFAULT_MODEL,
    max_tokens: options.maxTokens ?? DEFAULT_MAX_TOKENS,
    system: system as unknown as Anthropic.TextBlockParam[],
    messages,
  });

  const text = response.content
    .filter((b): b is Anthropic.TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("");

  return { text, usage: response.usage as AnthropicUsage };
}

export async function generateHandoff(
  state: State,
  options: { model?: string; maxTokens?: number } = {},
): Promise<AskResult> {
  const client = makeClient();
  const topicText = renderTopicContext(gatherContextSources(state));
  const system = buildSystemBlocks(HANDOFF_SYSTEM_PROMPT, topicText);

  const completedList =
    state.completed.length > 0
      ? state.completed.map((t) => `- ${t.text}`).join("\n")
      : "- (none)";
  const todoList =
    state.todos.length > 0
      ? state.todos.map((t) => `- ${t.text}`).join("\n")
      : "- (none)";
  const sprintList =
    state.sprints.length > 0
      ? state.sprints
          .map((s) => `- ${s.name} (${s.status}, phase=${s.phase ?? "-"})`)
          .join("\n")
      : "- (none)";

  const userPayload = [
    "Generate the handoff document now. Hard limit: 750 words.",
    "",
    `Original prompt: ${state.original_prompt || "(not set)"}`,
    `Current phase: ${state.current_phase || "(not set)"}`,
    `Active sprint: ${state.current_sprint || "(none)"}`,
    "",
    "Code style notes (verbatim from harness):",
    state.code_style || "(none recorded)",
    "",
    "Completed items:",
    completedList,
    "",
    "Outstanding to-do items:",
    todoList,
    "",
    "Sprint history (most recent last):",
    sprintList,
  ].join("\n");

  const response = await client.messages.create({
    model: options.model ?? DEFAULT_MODEL,
    max_tokens: options.maxTokens ?? 4000,
    system: system as unknown as Anthropic.TextBlockParam[],
    messages: [{ role: "user", content: userPayload }],
  });

  const text = response.content
    .filter((b): b is Anthropic.TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("")
    .trim();

  return { text, usage: response.usage as AnthropicUsage };
}
