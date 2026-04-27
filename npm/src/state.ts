/**
 * Session state: code style, original prompt, phases, sprints, todos.
 */

import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { resolve, join } from "node:path";
import { randomUUID } from "node:crypto";

const isoNow = (): string => new Date().toISOString().replace(/\.\d+Z$/, "Z");
const newId = (): string => randomUUID().replace(/-/g, "").slice(0, 8);

export interface Todo {
  id: string;
  text: string;
  phase: string | null;
  sprint: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Sprint {
  name: string;
  phase: string | null;
  status: "active" | "complete";
  started_at: string;
  ended_at: string | null;
  notes: string;
}

export interface ContextSource {
  path: string;
  label: string;
  bytes: number;
  cached_at: string;
}

export interface AnthropicUsage {
  input_tokens?: number;
  output_tokens?: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
}

export interface StateData {
  code_style: string;
  original_prompt: string;
  current_phase: string;
  current_sprint: string;
  todos: Todo[];
  completed: Todo[];
  sprints: Sprint[];
  phases: string[];
  context_sources: ContextSource[];
  session_input_tokens: number;
  session_output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  last_handoff_path: string | null;
  created_at: string;
  updated_at: string;
}

export class State implements StateData {
  code_style = "";
  original_prompt = "";
  current_phase = "";
  current_sprint = "";
  todos: Todo[] = [];
  completed: Todo[] = [];
  sprints: Sprint[] = [];
  phases: string[] = [];
  context_sources: ContextSource[] = [];
  session_input_tokens = 0;
  session_output_tokens = 0;
  cache_read_tokens = 0;
  cache_creation_tokens = 0;
  last_handoff_path: string | null = null;
  created_at = isoNow();
  updated_at = isoNow();

  addTodo(text: string): Todo {
    const todo: Todo = {
      id: newId(),
      text,
      phase: this.current_phase || null,
      sprint: this.current_sprint || null,
      created_at: isoNow(),
      completed_at: null,
    };
    this.todos.push(todo);
    return todo;
  }

  completeTodo(idOrPrefix: string): Todo | null {
    const idx = this.todos.findIndex(
      (t) => t.id === idOrPrefix || t.id.startsWith(idOrPrefix),
    );
    if (idx < 0) return null;
    const todo = this.todos[idx]!;
    todo.completed_at = isoNow();
    this.completed.push(todo);
    this.todos.splice(idx, 1);
    return todo;
  }

  startSprint(name: string, phase: string | null = null): Sprint {
    for (const s of this.sprints) {
      if (s.status === "active") {
        s.status = "complete";
        s.ended_at = isoNow();
      }
    }
    const sprint: Sprint = {
      name,
      phase: phase || this.current_phase || null,
      status: "active",
      started_at: isoNow(),
      ended_at: null,
      notes: "",
    };
    this.sprints.push(sprint);
    this.current_sprint = name;
    if (phase) this.setPhase(phase);
    return sprint;
  }

  completeSprint(notes = ""): Sprint | null {
    for (let i = this.sprints.length - 1; i >= 0; i--) {
      const s = this.sprints[i]!;
      if (s.status === "active") {
        s.status = "complete";
        s.ended_at = isoNow();
        if (notes) s.notes = notes;
        this.current_sprint = "";
        return s;
      }
    }
    return null;
  }

  setPhase(phase: string): void {
    if (phase && !this.phases.includes(phase)) this.phases.push(phase);
    this.current_phase = phase;
  }

  addContextSource(path: string, label: string, bytes: number): ContextSource {
    for (const src of this.context_sources) {
      if (src.path === path) {
        src.bytes = bytes;
        src.cached_at = isoNow();
        return src;
      }
    }
    const src: ContextSource = { path, label, bytes, cached_at: isoNow() };
    this.context_sources.push(src);
    return src;
  }

  recordUsage(usage: AnthropicUsage | null | undefined): void {
    if (!usage) return;
    this.session_input_tokens += usage.input_tokens ?? 0;
    this.session_output_tokens += usage.output_tokens ?? 0;
    this.cache_read_tokens += usage.cache_read_input_tokens ?? 0;
    this.cache_creation_tokens += usage.cache_creation_input_tokens ?? 0;
  }

  toJSON(): StateData {
    return {
      code_style: this.code_style,
      original_prompt: this.original_prompt,
      current_phase: this.current_phase,
      current_sprint: this.current_sprint,
      todos: this.todos,
      completed: this.completed,
      sprints: this.sprints,
      phases: this.phases,
      context_sources: this.context_sources,
      session_input_tokens: this.session_input_tokens,
      session_output_tokens: this.session_output_tokens,
      cache_read_tokens: this.cache_read_tokens,
      cache_creation_tokens: this.cache_creation_tokens,
      last_handoff_path: this.last_handoff_path,
      created_at: this.created_at,
      updated_at: this.updated_at,
    };
  }

  static fromJSON(data: Partial<StateData>): State {
    const s = new State();
    Object.assign(s, data);
    return s;
  }
}

export class StateStore {
  readonly root: string;
  readonly dir: string;
  readonly path: string;
  readonly handoffsDir: string;

  constructor(root: string = ".") {
    this.root = resolve(root);
    this.dir = join(this.root, ".ccc");
    this.path = join(this.dir, "state.json");
    this.handoffsDir = join(this.dir, "handoffs");
  }

  exists(): boolean {
    return existsSync(this.path);
  }

  init(): State {
    mkdirSync(this.dir, { recursive: true });
    mkdirSync(this.handoffsDir, { recursive: true });
    if (this.exists()) return this.load();
    const state = new State();
    this.save(state);
    return state;
  }

  load(): State {
    if (!this.exists()) {
      throw new Error(`No state at ${this.path}. Run \`ccc init\` first.`);
    }
    const raw = readFileSync(this.path, "utf8");
    return State.fromJSON(JSON.parse(raw) as Partial<StateData>);
  }

  save(state: State): void {
    mkdirSync(this.dir, { recursive: true });
    state.updated_at = isoNow();
    writeFileSync(this.path, JSON.stringify(state.toJSON(), null, 2), "utf8");
  }
}
