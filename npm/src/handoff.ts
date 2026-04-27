/** Handoff document generation, validation, and persistence. */

import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import type { State } from "./state.js";
import type { StateStore } from "./state.js";

export const WORD_LIMIT = 750;

export const REQUIRED_SECTIONS = [
  "## Code Style",
  "## Original Prompt / Current Phase",
  "## Completed Results",
  "## To-Do",
  "## Sprints / Phases for Next Context Window",
] as const;

export function countWords(text: string): number {
  let inCode = false;
  let words = 0;
  for (const line of text.split("\n")) {
    const stripped = line.trim();
    if (stripped.startsWith("```")) {
      inCode = !inCode;
      continue;
    }
    if (inCode) continue;
    const matches = line.match(/\b\w+\b/g);
    if (matches) words += matches.length;
  }
  return words;
}

export function validate(text: string): string[] {
  const problems: string[] = [];
  const wc = countWords(text);
  if (wc > WORD_LIMIT) {
    problems.push(`word count ${wc} exceeds limit of ${WORD_LIMIT}`);
  }
  for (const section of REQUIRED_SECTIONS) {
    if (!text.includes(section)) {
      problems.push(`missing required section: '${section}'`);
    }
  }
  return problems;
}

export function truncateToLimit(text: string, limit = WORD_LIMIT): string {
  if (countWords(text) <= limit) return text;
  const lines = text.split("\n");
  while (lines.length > 0 && countWords(lines.join("\n")) > limit) {
    lines.pop();
  }
  return lines.join("\n").replace(/\s+$/, "") + "\n";
}

export function writeHandoff(
  store: StateStore,
  text: string,
  label = "",
): string {
  mkdirSync(store.handoffsDir, { recursive: true });
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+/, "Z");
  const suffix = label ? `-${label}` : "";
  const path = join(store.handoffsDir, `handoff-${stamp}${suffix}.md`);
  writeFileSync(path, text, "utf8");
  return path;
}

export function parseHandoff(text: string): Record<string, string> {
  const sections: Record<string, string> = {};
  let currentKey: string | null = null;
  let buffer: string[] = [];
  for (const line of text.split("\n")) {
    if (line.startsWith("## ")) {
      if (currentKey !== null) {
        sections[currentKey] = buffer.join("\n").trim();
      }
      currentKey = line.slice(3).trim();
      buffer = [];
    } else if (currentKey !== null) {
      buffer.push(line);
    }
  }
  if (currentKey !== null) {
    sections[currentKey] = buffer.join("\n").trim();
  }
  return sections;
}

export function hydrateStateFromHandoff(text: string, state: State): State {
  const sections = parseHandoff(text);

  if (!state.code_style && sections["Code Style"]) {
    state.code_style = sections["Code Style"]!;
  }

  const op = sections["Original Prompt / Current Phase"];
  if (!state.original_prompt && op) {
    state.original_prompt = op.split("\n\n", 1)[0]!.trim();
  }

  const todoSection = sections["To-Do"];
  if (todoSection && state.todos.length === 0) {
    for (const line of todoSection.split("\n")) {
      const stripped = line.trim();
      if (stripped.startsWith("- ") || stripped.startsWith("* ")) {
        state.addTodo(stripped.slice(2).trim());
      }
    }
  }

  return state;
}
