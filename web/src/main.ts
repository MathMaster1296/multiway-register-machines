/** Application wiring: presets, editor, engine worker, graph view, stats,
 * URL state, playback, and exports. */

import { EngineClient, type EngineStage } from "./api.js";
import { MachineEditor } from "./editor.js";
import { GraphView } from "./graphview.js";
import { StatsPane } from "./stats.js";
import type { AppState, MachineDoc, PresetInfo, RunOk, RunParams } from "./types.js";
import { decodeState, writeStateToUrl } from "./urlstate.js";

function element<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (!found) throw new Error(`missing #${id}`);
  return found as T;
}

const DEFAULT_PARAMS: RunParams = {
  mode: "states",
  max_steps: 60,
  max_states: 20000,
  max_frontier: 10000,
  analyze: true,
};

class App {
  private engine: EngineClient;
  private editor: MachineEditor;
  private view: GraphView;
  private stats: StatsPane;
  private presets: PresetInfo[] = [];
  private state: AppState = {
    doc: emptyDoc(),
    params: { ...DEFAULT_PARAMS },
    preset: null,
  };
  private lastRun: RunOk | null = null;
  private playTimer: number | null = null;
  private branchialOn = false;

  constructor() {
    this.engine = new EngineClient(
      new URL("public/wheels/mrm.whl", document.baseURI).toString(),
      (stage, detail) => this.showStage(stage, detail),
    );
    this.stats = new StatsPane(element("stats-body"));
    this.view = new GraphView(element("graph-host"), (node) => {
      if (this.lastRun) this.stats.show(this.lastRun, this.state.preset, node);
    });
    this.editor = new MachineEditor(element("editor-host"), this.state.doc, {
      onChange: () => {
        this.state.preset = this.state.preset === "custom" ? "custom" : null;
        void this.runAndRender();
      },
    });
  }

  async boot(): Promise<void> {
    const meta = (await fetchJson("public/site-meta.json")) as { wheel: string };
    this.engine = new EngineClient(
      new URL(`public/wheels/${meta.wheel}`, document.baseURI).toString(),
      (stage, detail) => this.showStage(stage, detail),
    );
    this.engine.start();
    this.presets = (await fetchJson("public/presets/manifest.json")) as PresetInfo[];
    this.fillPresetDropdown();

    window.addEventListener("hashchange", () => void this.applyHash());
    const fromUrl = await decodeState(location.hash);
    if (fromUrl) {
      this.applyState(fromUrl);
      await this.runAndRender();
    } else {
      await this.loadPreset("fibonacci");
    }
  }

  private applyState(state: AppState): void {
    this.state = state;
    this.state.params.analyze = true;
    element<HTMLSelectElement>("preset-select").value = this.state.preset ?? "";
    element("preset-description").textContent = this.state.doc.description ?? "";
    this.editor.setDocument(this.state.doc);
    this.syncParamInputs();
  }

  /** A pasted or back/forward link changes the hash without a reload. */
  private async applyHash(): Promise<void> {
    const state = await decodeState(location.hash);
    if (!state) return;
    this.applyState(state);
    await this.runAndRender();
  }

  private fillPresetDropdown(): void {
    const select = element<HTMLSelectElement>("preset-select");
    select.replaceChildren();
    for (const preset of this.presets) {
      const option = document.createElement("option");
      option.value = preset.id;
      option.textContent = preset.name;
      option.title = preset.description;
      select.append(option);
    }
    select.addEventListener("change", () => void this.loadPreset(select.value));
  }

  private async loadPreset(id: string): Promise<void> {
    const doc = (await fetchJson(`public/presets/${id}.json`)) as MachineDoc;
    this.state = { doc, params: { ...DEFAULT_PARAMS }, preset: id };
    element<HTMLSelectElement>("preset-select").value = id;
    element("preset-description").textContent = doc.description ?? "";
    this.editor.setDocument(doc);
    this.syncParamInputs();
    await this.runAndRender();
  }

  private syncParamInputs(): void {
    element<HTMLSelectElement>("mode-select").value = this.state.params.mode;
    element<HTMLInputElement>("max-steps").value = String(this.state.params.max_steps);
    element<HTMLInputElement>("max-states").value = String(this.state.params.max_states);
    element<HTMLInputElement>("max-frontier").value = String(this.state.params.max_frontier);
  }

  private readParamInputs(): void {
    this.state.params.mode =
      element<HTMLSelectElement>("mode-select").value === "tree" ? "tree" : "states";
    this.state.params.max_steps = readInt("max-steps", this.state.params.max_steps);
    this.state.params.max_states = readInt("max-states", this.state.params.max_states);
    this.state.params.max_frontier = readInt("max-frontier", this.state.params.max_frontier);
  }

  async runAndRender(): Promise<void> {
    this.readParamInputs();
    this.stopPlayback();
    void writeStateToUrl(this.state);
    const result = await this.engine
      .run(JSON.stringify(this.state.doc), this.state.params)
      .catch((error: Error) => {
        if (error.message === "cancelled") {
          this.showBanner("Cancelled; the engine restarted and is ready.", "warning");
        } else {
          this.showBanner(`engine error: ${error.message}`, "error");
        }
        return null;
      });
    if (!result) return;
    if (!result.ok) {
      this.editor.setProblems(result.problems);
      this.stats.clear("Fix the highlighted problems and rerun.");
      return;
    }
    this.editor.setProblems([]);
    this.lastRun = result;
    this.renderDiagrams(result);
    this.view.setEvolution(result.evolution, result.layout);
    this.stats.show(result, this.state.preset, null);
    this.renderTable(result);
    this.setupSlider(result);
    if (this.branchialOn) await this.refreshBranchial();

    const evolution = result.evolution;
    if (evolution.truncated) {
      const knob = {
        max_steps: "max steps",
        max_states: "max states",
        max_frontier: "max frontier",
      }[evolution.truncation_reason ?? ""];
      this.showBanner(
        `Truncated by ${evolution.truncation_reason}: this is a prefix of the` +
          ` evolution, not all of it. Raise ${knob ?? "the caps"} to see more.`,
        "warning",
      );
    } else {
      this.hideBanner();
    }
    element("canvas-note").hidden = !this.view.usingCanvas;
  }

  private setupSlider(result: RunOk): void {
    const slider = element<HTMLInputElement>("step-slider");
    const last = result.evolution.layers.length - 1;
    slider.max = String(last);
    slider.value = String(last);
    element("step-readout").textContent = `step ${last} / ${last}`;
    slider.oninput = () => {
      const step = Number(slider.value);
      element("step-readout").textContent = `step ${step} / ${last}`;
      this.view.setStep(step);
      if (this.branchialOn) void this.refreshBranchial();
    };
  }

  private async refreshBranchial(): Promise<void> {
    const step = Number(element<HTMLInputElement>("step-slider").value);
    const edges = await this.engine.branchial(step);
    this.view.setBranchial(edges);
    this.view.setStep(step);
  }

  togglePlayback(): void {
    if (this.playTimer !== null) {
      this.stopPlayback();
      return;
    }
    const slider = element<HTMLInputElement>("step-slider");
    if (slider.value === slider.max) slider.value = "0";
    element("play-button").textContent = "pause";
    this.playTimer = window.setInterval(() => {
      const next = Number(slider.value) + 1;
      if (next > Number(slider.max)) {
        this.stopPlayback();
        return;
      }
      slider.value = String(next);
      slider.dispatchEvent(new Event("input"));
    }, 650);
  }

  private stopPlayback(): void {
    if (this.playTimer !== null) {
      clearInterval(this.playTimer);
      this.playTimer = null;
    }
    element("play-button").textContent = "play";
  }

  async toggleBranchial(on: boolean): Promise<void> {
    this.branchialOn = on;
    if (on) await this.refreshBranchial();
    else {
      this.view.setBranchial([]);
    }
  }

  private renderDiagrams(result: RunOk): void {
    const details = element<HTMLDetailsElement>("diagrams");
    const host = element("diagram-host");
    if (result.rule_plot || result.circle_plot) {
      details.hidden = false;
      host.innerHTML = (result.rule_plot ?? "") + (result.circle_plot ?? "");
    } else {
      details.hidden = true;
      host.replaceChildren();
    }
  }

  async copyLink(): Promise<void> {
    const button = element("copy-link");
    try {
      await navigator.clipboard.writeText(location.href);
      button.textContent = "copied";
    } catch {
      button.textContent = "copy failed";
    }
    window.setTimeout(() => {
      button.textContent = "copy link";
    }, 1300);
  }

  async importDocument(file: File): Promise<void> {
    let parsed: unknown;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      this.showBanner(`${file.name} is not valid JSON`, "error");
      return;
    }
    const doc = parsed as MachineDoc;
    if (doc?.schema !== "mrm/machine/1") {
      this.showBanner(
        `${file.name} is not a machine document (expected schema mrm/machine/1)`,
        "error",
      );
      return;
    }
    this.state = { doc, params: { ...DEFAULT_PARAMS }, preset: null };
    element<HTMLSelectElement>("preset-select").value = "";
    element("preset-description").textContent = doc.description ?? file.name;
    this.editor.setDocument(doc);
    this.syncParamInputs();
    await this.runAndRender();
  }

  zoom(factor: number): void {
    this.view.zoomBy(factor);
  }

  fit(): void {
    this.view.fitView();
  }

  nudgeStep(delta: number): void {
    const slider = element<HTMLInputElement>("step-slider");
    const next = Number(slider.value) + delta;
    if (next < 0 || next > Number(slider.max)) return;
    slider.value = String(next);
    slider.dispatchEvent(new Event("input"));
  }

  private renderTable(result: RunOk): void {
    const host = element("table-host");
    host.replaceChildren();
    const table = document.createElement("table");
    table.createCaption().textContent = "States (text view)";
    const head = table.createTHead().insertRow();
    for (const title of ["id", "layer", "pc", "registers", "terminal"]) {
      const cell = document.createElement("th");
      cell.textContent = title;
      head.append(cell);
    }
    const layerOf = new Map<number, number>();
    result.evolution.layers.forEach((layer, index) => {
      for (const node of layer) layerOf.set(node, index);
    });
    const body = table.createTBody();
    for (const [id, pc, registers] of result.evolution.nodes.slice(0, 500)) {
      const row = body.insertRow();
      for (const value of [
        id,
        layerOf.get(id) ?? "",
        pc,
        registers.join(", "),
        result.evolution.terminals[String(id)] ?? "",
      ]) {
        row.insertCell().textContent = String(value);
      }
    }
    host.append(table);
    if (result.evolution.nodes.length > 500) {
      const note = document.createElement("p");
      note.className = "muted";
      note.textContent = `showing the first 500 of ${result.evolution.nodes.length} states`;
      host.append(note);
    }
  }

  private showStage(stage: EngineStage, detail?: string): void {
    const overlay = element("engine-status");
    const messages: Record<EngineStage, string> = {
      "loading-pyodide": "Loading Python runtime (about 6 MB, cached after the first visit)",
      "loading-engine": "Installing the mrm engine wheel",
      ready: "",
      working: "Evolving",
      failed: `Engine failed: ${detail ?? "unknown error"}`,
    };
    const text = messages[stage];
    overlay.hidden = text === "";
    overlay.textContent = text;
    overlay.classList.toggle("error", stage === "failed");
  }

  private showBanner(text: string, kind: "warning" | "error"): void {
    const banner = element("banner");
    banner.hidden = false;
    banner.textContent = text;
    banner.className = `banner ${kind}`;
  }

  private hideBanner(): void {
    element("banner").hidden = true;
  }

  cancel(): void {
    this.engine.cancel();
    this.showBanner("Cancelled; the engine is restarting.", "warning");
  }

  downloadJson(): void {
    if (!this.lastRun) return;
    download(
      JSON.stringify(this.lastRun.evolution, null, 1),
      "evolution.json",
      "application/json",
    );
  }

  downloadSvg(): void {
    const text = this.view.exportSvg();
    if (text) download(text, "evolution.svg", "image/svg+xml");
  }

  async downloadPng(): Promise<void> {
    const blob = await this.view.exportPng();
    if (blob) downloadBlob(blob, "evolution.png");
  }
}

function emptyDoc(): MachineDoc {
  return {
    schema: "mrm/machine/1",
    n_registers: 1,
    rules: [],
    halt_pcs: [],
    initial: [1, [0]],
  };
}

async function fetchJson(path: string): Promise<unknown> {
  // no-cache still allows 304 revalidation; it only forbids silent staleness.
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function readInt(id: string, fallback: number): number {
  const value = Number(element<HTMLInputElement>(id).value);
  return Number.isInteger(value) && value > 0 ? value : fallback;
}

function download(text: string, filename: string, type: string): void {
  downloadBlob(new Blob([text], { type }), filename);
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

const app = new App();
element("run-button").addEventListener("click", () => void app.runAndRender());
element("cancel-button").addEventListener("click", () => app.cancel());
element("play-button").addEventListener("click", () => app.togglePlayback());
element<HTMLInputElement>("branchial-toggle").addEventListener("change", (event) => {
  void app.toggleBranchial((event.target as HTMLInputElement).checked);
});
element<HTMLInputElement>("table-toggle").addEventListener("change", (event) => {
  element("table-host").hidden = !(event.target as HTMLInputElement).checked;
});
element("copy-link").addEventListener("click", () => void app.copyLink());
element("import-button").addEventListener("click", () => element("import-file").click());
element<HTMLInputElement>("import-file").addEventListener("change", (event) => {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (file) void app.importDocument(file);
  (event.target as HTMLInputElement).value = "";
});
document.addEventListener("keydown", (event) => {
  const target = event.target as HTMLElement;
  if (target.closest("input, select, textarea, [contenteditable]")) return;
  if (event.key === " ") {
    event.preventDefault();
    app.togglePlayback();
  } else if (event.key === "ArrowRight") {
    app.nudgeStep(1);
  } else if (event.key === "ArrowLeft") {
    app.nudgeStep(-1);
  }
});
element("zoom-in").addEventListener("click", () => app.zoom(1.25));
element("zoom-out").addEventListener("click", () => app.zoom(0.8));
element("zoom-fit").addEventListener("click", () => app.fit());
element("graph-host").addEventListener("keydown", (event) => {
  if (event.key === "+" || event.key === "=") app.zoom(1.25);
  else if (event.key === "-") app.zoom(0.8);
  else if (event.key === "0") app.fit();
  else return;
  event.preventDefault();
});
try {
  const help = element<HTMLDetailsElement>("help");
  help.open = localStorage.getItem("mrm-help-seen") !== "yes";
  help.addEventListener("toggle", () => {
    if (!help.open) localStorage.setItem("mrm-help-seen", "yes");
  });
} catch {
  // Storage can be unavailable; the help panel simply stays at its default.
}
element("export-svg").addEventListener("click", () => app.downloadSvg());
element("export-png").addEventListener("click", () => void app.downloadPng());
element("export-json").addEventListener("click", () => app.downloadJson());
void app.boot();
