/** The machine editor: an editable rule table plus machine-level inputs.
 * Guards and updates use a compact text syntax that round-trips with the
 * JSON document:
 *   guard    "r1>0 & r2%2==1"     (comparisons: > >= == < and r%k==c)
 *   updates  "r1-=1, r2+=2"
 */

import type { ConditionJson, MachineDoc, RuleJson, UpdateJson } from "./types.js";

const GUARD_ATOM = /^r(\d+)\s*(?:%\s*(\d+)\s*==\s*(\d+)|(>=|==|<|>)\s*(\d+))$/;
const UPDATE_ATOM = /^r(\d+)\s*([+-]=)\s*(\d+)$/;

export function formatGuard(guard: ConditionJson[]): string {
  return guard
    .map((c) =>
      c.op === "%==" ? `r${c.reg}%${c.modulus}==${c.value}` : `r${c.reg}${c.op}${c.value}`,
    )
    .join(" & ");
}

export function formatUpdates(updates: UpdateJson[]): string {
  return updates
    .map((u) => `r${u.reg}${u.delta < 0 ? "-=" : "+="}${Math.abs(u.delta)}`)
    .join(", ");
}

export function parseGuard(text: string): ConditionJson[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  return trimmed.split(/[&,;]/).map((part) => {
    const match = GUARD_ATOM.exec(part.trim());
    if (!match) throw new Error(`cannot read condition "${part.trim()}"`);
    if (match[2] !== undefined) {
      return {
        reg: Number(match[1]),
        op: "%==" as const,
        value: Number(match[3]),
        modulus: Number(match[2]),
      };
    }
    return {
      reg: Number(match[1]),
      op: match[4] as ">" | ">=" | "==" | "<",
      value: Number(match[5]),
    };
  });
}

export function parseUpdates(text: string): UpdateJson[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  return trimmed.split(/[,;]/).map((part) => {
    const match = UPDATE_ATOM.exec(part.trim());
    if (!match) throw new Error(`cannot read update "${part.trim()}"`);
    const magnitude = Number(match[3]);
    return { reg: Number(match[1]), delta: match[2] === "-=" ? -magnitude : magnitude };
  });
}

export interface EditorCallbacks {
  onChange(): void;
}

/** Renders and maintains the rule table plus the machine-level inputs.
 * The document object is mutated in place; `onChange` fires after every
 * successful edit so the app can re-run and refresh the URL. */
export class MachineEditor {
  private doc: MachineDoc;
  private rowErrors = new Map<number, string>();
  private serverProblems: string[] = [];

  constructor(
    private root: HTMLElement,
    doc: MachineDoc,
    private callbacks: EditorCallbacks,
  ) {
    this.doc = doc;
  }

  get document(): MachineDoc {
    return this.doc;
  }

  setDocument(doc: MachineDoc): void {
    this.doc = doc;
    this.rowErrors.clear();
    this.serverProblems = [];
    this.render();
  }

  setProblems(problems: string[]): void {
    this.serverProblems = problems;
    this.render();
  }

  private input(
    value: string,
    label: string,
    apply: (text: string) => void,
    options: { size?: number } = {},
  ): HTMLInputElement {
    const element = window.document.createElement("input");
    element.type = "text";
    element.value = value;
    element.setAttribute("aria-label", label);
    if (options.size) element.size = options.size;
    element.addEventListener("change", () => apply(element.value));
    return element;
  }

  private applyRowEdit(index: number, edit: (rule: RuleJson) => void): void {
    const rule = this.doc.rules[index];
    if (!rule) return;
    try {
      edit(rule);
      this.rowErrors.delete(index);
      this.callbacks.onChange();
    } catch (error) {
      this.rowErrors.set(index, error instanceof Error ? error.message : String(error));
    }
    this.render();
  }

  render(): void {
    const doc = this.doc;
    this.root.replaceChildren();

    const machineRow = window.document.createElement("div");
    machineRow.className = "editor-machine-row";
    machineRow.append(
      labeled(
        "Registers",
        this.input(String(doc.n_registers), "Register count", (text) => {
          const count = Number(text);
          if (!Number.isInteger(count) || count < 1) return;
          doc.n_registers = count;
          const [pc, regs] = doc.initial ?? [1, []];
          doc.initial = [pc, resize(regs, count)];
          this.callbacks.onChange();
          this.render();
        }, { size: 3 }),
      ),
      labeled(
        "Initial pc",
        this.input(String(doc.initial?.[0] ?? 1), "Initial program counter", (text) => {
          const pc = Number(text);
          if (!Number.isInteger(pc) || pc < 1) return;
          doc.initial = [pc, doc.initial?.[1] ?? new Array(doc.n_registers).fill(0)];
          this.callbacks.onChange();
        }, { size: 3 }),
      ),
      labeled(
        "Initial registers",
        this.input(
          (doc.initial?.[1] ?? []).join(", "),
          "Initial register values, comma separated",
          (text) => {
            const values = text.split(",").map((v) => Number(v.trim()));
            if (values.some((v) => !Number.isInteger(v) || v < 0)) return;
            doc.initial = [doc.initial?.[0] ?? 1, resize(values, doc.n_registers)];
            this.callbacks.onChange();
          },
          { size: 10 },
        ),
      ),
      labeled(
        "Halt pcs",
        this.input(doc.halt_pcs.join(", "), "Halting program counters", (text) => {
          const values = text
            .split(",")
            .map((v) => v.trim())
            .filter(Boolean)
            .map(Number);
          if (values.some((v) => !Number.isInteger(v) || v < 1)) return;
          doc.halt_pcs = values;
          this.callbacks.onChange();
        }, { size: 8 }),
      ),
    );
    this.root.append(machineRow);

    const table = window.document.createElement("table");
    table.className = "rule-table";
    table.createCaption().textContent = "Rules";
    const head = table.createTHead().insertRow();
    for (const title of ["id", "from", "guard", "updates", "to", ""]) {
      const cell = window.document.createElement("th");
      cell.textContent = title;
      head.append(cell);
    }
    const body = table.createTBody();
    doc.rules.forEach((rule, index) => {
      const row = body.insertRow();
      row.insertCell().append(
        this.input(rule.id, `Rule ${index + 1} id`, (text) =>
          this.applyRowEdit(index, (r) => {
            if (!text.trim()) throw new Error("id cannot be empty");
            r.id = text.trim();
          }), { size: 6 }),
      );
      row.insertCell().append(
        this.input(String(rule.pc_from), `Rule ${rule.id} source pc`, (text) =>
          this.applyRowEdit(index, (r) => {
            r.pc_from = parsePc(text);
          }), { size: 3 }),
      );
      row.insertCell().append(
        this.input(formatGuard(rule.guard), `Rule ${rule.id} guard`, (text) =>
          this.applyRowEdit(index, (r) => {
            r.guard = parseGuard(text);
          }), { size: 16 }),
      );
      row.insertCell().append(
        this.input(formatUpdates(rule.updates), `Rule ${rule.id} updates`, (text) =>
          this.applyRowEdit(index, (r) => {
            r.updates = parseUpdates(text);
          }), { size: 14 }),
      );
      row.insertCell().append(
        this.input(String(rule.pc_to), `Rule ${rule.id} target pc`, (text) =>
          this.applyRowEdit(index, (r) => {
            r.pc_to = parsePc(text);
          }), { size: 3 }),
      );
      const remove = window.document.createElement("button");
      remove.textContent = "delete";
      remove.setAttribute("aria-label", `Delete rule ${rule.id}`);
      remove.addEventListener("click", () => {
        doc.rules.splice(index, 1);
        this.callbacks.onChange();
        this.render();
      });
      row.insertCell().append(remove);

      const rowError = this.rowErrors.get(index);
      const serverError = this.serverProblems.find((p) => p.includes(`'${rule.id}'`));
      const problem = rowError ?? serverError;
      if (problem) {
        const errorRow = body.insertRow();
        errorRow.className = "rule-error";
        const cell = errorRow.insertCell();
        cell.colSpan = 6;
        cell.textContent = problem;
      }
    });
    this.root.append(table);

    const addButton = window.document.createElement("button");
    addButton.textContent = "add rule";
    addButton.addEventListener("click", () => {
      const used = new Set(doc.rules.map((r) => r.id));
      let n = doc.rules.length + 1;
      while (used.has(`r${n}`)) n += 1;
      doc.rules.push({ id: `r${n}`, pc_from: 1, guard: [], updates: [], pc_to: 1 });
      this.callbacks.onChange();
      this.render();
    });
    this.root.append(addButton);

    const general = this.serverProblems.filter(
      (p) => !doc.rules.some((r) => p.includes(`'${r.id}'`)),
    );
    if (general.length) {
      const box = window.document.createElement("div");
      box.className = "problem-box";
      box.setAttribute("role", "alert");
      box.textContent = general.join("; ");
      this.root.append(box);
    }
  }
}

function labeled(text: string, control: HTMLElement): HTMLLabelElement {
  const label = window.document.createElement("label");
  const span = window.document.createElement("span");
  span.textContent = text;
  label.append(span, control);
  return label;
}

function parsePc(text: string): number {
  const pc = Number(text);
  if (!Number.isInteger(pc) || pc < 1) throw new Error(`pc must be a positive integer`);
  return pc;
}

function resize(values: number[], length: number): number[] {
  return Array.from({ length }, (_, i) => values[i] ?? 0);
}
