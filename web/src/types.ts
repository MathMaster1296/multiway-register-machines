/** Shared document and protocol types. Mirrors docs/machine.schema.json and
 * docs/evolution.schema.json; the Python engine is the source of truth. */

export interface ConditionJson {
  reg: number;
  op: ">" | ">=" | "==" | "<" | "%==";
  value: number;
  modulus?: number;
}

export interface UpdateJson {
  reg: number;
  delta: number;
}

export interface RuleJson {
  id: string;
  pc_from: number;
  guard: ConditionJson[];
  updates: UpdateJson[];
  pc_to: number;
}

export interface MachineDoc {
  schema: "mrm/machine/1";
  name?: string;
  description?: string;
  n_registers: number;
  rules: RuleJson[];
  halt_pcs: number[];
  instructions?: unknown;
  initial?: [number, number[]];
}

export interface RunParams {
  mode: "states" | "tree";
  max_steps: number;
  max_states: number;
  max_frontier: number;
  analyze: boolean;
}

export interface EvolutionJson {
  schema: string;
  machine: MachineDoc;
  parameters: {
    mode: "states" | "tree";
    max_steps: number;
    max_states: number;
    max_frontier: number;
    initial: [number, number[]][];
  };
  nodes: [number, number, number[]][];
  edges: [number, number, string][];
  layers: number[][];
  terminals: Record<string, "halt" | "stuck" | "cutoff">;
  path_counts: Record<string, number | "infinite">;
  growth_series: number[];
  truncated: boolean;
  truncation_reason: string | null;
}

export interface AbsorptionJson {
  terminals: Record<string, string>;
  halting: string;
  never_halting: string;
  unresolved: string;
  expected_steps: string | null;
}

export interface RunOk {
  ok: true;
  evolution: EvolutionJson;
  layout: Record<string, [number, number]>;
  absorption?: AbsorptionJson;
  absorption_times?: { probabilities: number[]; tail: number };
  absorption_error?: string;
  complexity?: number;
  rule_plot?: string;
  circle_plot?: string;
}

export interface RunProblems {
  ok: false;
  problems: string[];
}

export type RunResult = RunOk | RunProblems;

/** Messages into the worker. */
export type WorkerRequest =
  | { type: "init"; wheelUrl: string }
  | { type: "run"; id: number; doc: string; params: string }
  | { type: "branchial"; id: number; step: number };

/** Messages out of the worker. */
export type WorkerResponse =
  | { type: "status"; stage: "loading-pyodide" | "loading-engine" | "ready" }
  | { type: "result"; id: number; payload: string }
  | { type: "error"; id: number | null; message: string };

export interface PresetInfo {
  id: string;
  name: string;
  description: string;
}

export interface AppState {
  doc: MachineDoc;
  params: RunParams;
  preset: string | null;
}
