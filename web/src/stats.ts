/** The statistics pane: counts, growth chart, path counts, absorption, and a
 * plain-language interpretation line for presets. */

import type { EvolutionJson, RunOk } from "./types.js";

const SVG_NS = "http://www.w3.org/2000/svg";

function fibonacci(k: number): number {
  let a = 1;
  let b = 1;
  for (let i = 1; i < k; i += 1) [a, b] = [b, a + b];
  return a;
}

function binomial(n: number, k: number): number {
  let result = 1;
  for (let i = 1; i <= k; i += 1) result = (result * (n - k + i)) / i;
  return Math.round(result);
}

function totalFinitePaths(evolution: EvolutionJson): number | null {
  let total = 0;
  for (const count of Object.values(evolution.path_counts)) {
    if (count === "infinite") return null;
    total += count;
  }
  return total;
}

/** Preset-specific one-liner tying the numbers to the closed form. */
export function interpretation(preset: string | null, evolution: EvolutionJson): string | null {
  const total = totalFinitePaths(evolution);
  if (preset === "fibonacci") {
    const k = evolution.parameters.initial[0]?.[1][0];
    if (k !== undefined && total !== null && total === fibonacci(k)) {
      return `paths to base cases: ${total} = F(${k})`;
    }
  }
  if (preset === "grid_paths" || preset === "custom") {
    let m = 0;
    let n = 0;
    for (const rule of evolution.machine.rules) {
      for (const condition of rule.guard) {
        if (condition.op === "<" && condition.reg === 1) m = condition.value;
        if (condition.op === "<" && condition.reg === 2) n = condition.value;
      }
    }
    if (m && n && total !== null && total === binomial(m + n, m)) {
      return `paths from (0,0) to (${m},${n}): ${total} = C(${m + n},${m})`;
    }
  }
  if (preset === "collatz_reverse") {
    const values = evolution.nodes.filter(
      ([, pc, registers]) => pc === 1 && registers[1] === 0,
    ).length;
    return `distinct Collatz-tree values reached: ${values}`;
  }
  return null;
}

export class StatsPane {
  constructor(private root: HTMLElement) {}

  clear(message: string): void {
    this.root.replaceChildren();
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = message;
    this.root.append(p);
  }

  show(result: RunOk, preset: string | null, selected: number | null): void {
    const evolution = result.evolution;
    this.root.replaceChildren();

    const summary = document.createElement("dl");
    summary.className = "stat-grid";
    const kinds = { halt: 0, stuck: 0, cutoff: 0 };
    for (const kind of Object.values(evolution.terminals)) kinds[kind] += 1;
    const entries: [string, string][] = [
      ["nodes", String(evolution.nodes.length)],
      ["edges", String(evolution.edges.length)],
      ["steps", String(evolution.layers.length - 1)],
      ["halt / stuck / cut", `${kinds.halt} / ${kinds.stuck} / ${kinds.cutoff}`],
    ];
    if (result.complexity !== undefined) {
      entries.push(["complexity", result.complexity.toFixed(4)]);
    }
    for (const [term, value] of entries) {
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      dd.textContent = value;
      summary.append(dt, dd);
    }
    this.root.append(summary);

    const line = interpretation(preset, evolution);
    if (line) {
      const p = document.createElement("p");
      p.className = "interpretation";
      p.textContent = line;
      this.root.append(p);
    }

    this.root.append(sectionTitle("Growth"), this.growthChart(evolution.growth_series));

    const counts = Object.entries(evolution.path_counts);
    if (counts.length) {
      this.root.append(sectionTitle("Paths to terminals"));
      const list = document.createElement("ul");
      list.className = "plain-list";
      const labelOf = new Map(
        evolution.nodes.map(([id, pc, registers]) => [id, `${pc} | ${registers.join(",")}`]),
      );
      for (const [id, count] of counts.slice(0, 12)) {
        const item = document.createElement("li");
        item.textContent = `${labelOf.get(Number(id)) ?? id}: ${count}`;
        list.append(item);
      }
      if (counts.length > 12) {
        const item = document.createElement("li");
        item.textContent = `and ${counts.length - 12} more`;
        list.append(item);
      }
      this.root.append(list);
    }

    if (result.absorption) {
      const a = result.absorption;
      this.root.append(sectionTitle("Uniform-branching chain (exact)"));
      const list = document.createElement("ul");
      list.className = "plain-list";
      const rows = [
        `halting probability: ${a.halting}`,
        `never halting: ${a.never_halting}`,
        a.unresolved !== "0" ? `unresolved (capped): ${a.unresolved}` : null,
        a.expected_steps !== null ? `expected steps: ${a.expected_steps}` : null,
      ];
      for (const row of rows) {
        if (!row) continue;
        const item = document.createElement("li");
        item.textContent = row;
        list.append(item);
      }
      this.root.append(list);
    }

    if (selected !== null) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = `selected state ${selected}: ancestors amber, descendants blue`;
      this.root.append(p);
    }
  }

  private growthChart(series: number[]): SVGSVGElement {
    const width = 260;
    const height = 80;
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("class", "growth-chart");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `Layer sizes per step: ${series.join(", ")}`);
    const top = Math.max(...series, 1);
    const barWidth = width / series.length;
    series.forEach((value, index) => {
      const bar = document.createElementNS(SVG_NS, "rect");
      const barHeight = Math.max(1, (value / top) * (height - 14));
      bar.setAttribute("x", String(index * barWidth + 1));
      bar.setAttribute("y", String(height - barHeight));
      bar.setAttribute("width", String(Math.max(1, barWidth - 2)));
      bar.setAttribute("height", String(barHeight));
      const title = document.createElementNS(SVG_NS, "title");
      title.textContent = `step ${index}: ${value}`;
      bar.append(title);
      svg.append(bar);
    });
    return svg;
  }
}

function sectionTitle(text: string): HTMLHeadingElement {
  const heading = document.createElement("h3");
  heading.textContent = text;
  return heading;
}
