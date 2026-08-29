/** The engine worker: loads Pyodide, installs the mrm wheel, and answers
 * run/branchial requests. All mathematics happens in Python; this file only
 * moves JSON strings around. */

import type { WorkerRequest, WorkerResponse } from "./types.js";

const PYODIDE_INDEX = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

const ctx = self as unknown as {
  postMessage(message: WorkerResponse): void;
  onmessage: ((event: MessageEvent<WorkerRequest>) => void) | null;
};

const GLUE = `
import json

from mrm import Config, evolve
from mrm.analysis import absorption
from mrm.counting import strongly_connected_components, successor_lists
from mrm.graph import branchial_graph
from mrm.layout import layered_layout
from mrm.machine import complexity
from mrm.serialize import evolution_to_json, machine_from_json

LAST = None

def _analysis_tractable(ev):
    # Exact rational solves blow up on large cyclic components; skip the
    # analysis rather than stall the page.
    if len(ev.nodes) > 5000:
        return False
    succ = successor_lists(ev)
    return all(
        len(comp) <= 250
        for comp in strongly_connected_components(list(ev.nodes), succ)
    )

def mrm_run(doc_text, params_text):
    global LAST
    params = json.loads(params_text)
    try:
        doc = machine_from_json(json.loads(doc_text))
    except (ValueError, KeyError, TypeError) as exc:
        return json.dumps({"ok": False, "problems": [f"machine document: {exc}"]})
    problems = doc.machine.validate()
    if problems:
        return json.dumps({"ok": False, "problems": problems})
    if doc.initial is None:
        return json.dumps({"ok": False, "problems": ["no initial configuration set"]})
    try:
        ev = evolve(
            doc.machine,
            doc.initial,
            mode=params["mode"],
            max_steps=int(params["max_steps"]),
            max_states=int(params["max_states"]),
            max_frontier=int(params["max_frontier"]),
        )
    except ValueError as exc:
        return json.dumps({"ok": False, "problems": [str(exc)]})
    LAST = ev
    payload = {
        "ok": True,
        "evolution": evolution_to_json(ev),
        "layout": {str(n): [x, y] for n, (x, y) in layered_layout(ev).items()},
    }
    if params.get("analyze") and _analysis_tractable(ev):
        try:
            result = absorption(ev)
            payload["absorption"] = {
                "terminals": {
                    str(n): str(p) for n, p in result.terminal_probabilities.items()
                },
                "halting": str(result.halting_probability),
                "never_halting": str(result.never_halting),
                "unresolved": str(result.unresolved),
                "expected_steps": None
                if result.expected_steps is None
                else str(result.expected_steps),
            }
        except Exception as exc:  # analysis is optional; never sink the run
            payload["absorption_error"] = str(exc)
    if doc.machine.instructions is not None:
        payload["complexity"] = complexity(doc.machine.instructions)
    return json.dumps(payload)

def mrm_branchial(step):
    if LAST is None:
        return json.dumps({"ok": False, "edges": []})
    try:
        graph = branchial_graph(LAST, int(step))
    except ValueError:
        return json.dumps({"ok": True, "edges": []})
    return json.dumps({"ok": True, "edges": [[a, b] for a, b, _ in graph.edges]})
`;

interface PyProxy {
  (...args: unknown[]): unknown;
}

interface Pyodide {
  loadPackage(url: string): Promise<void>;
  runPython(code: string): unknown;
  globals: { get(name: string): PyProxy };
}

let runFn: PyProxy | null = null;
let branchialFn: PyProxy | null = null;

async function init(wheelUrl: string): Promise<void> {
  ctx.postMessage({ type: "status", stage: "loading-pyodide" });
  const module = (await import(PYODIDE_INDEX + "pyodide.mjs")) as {
    loadPyodide(options: { indexURL: string }): Promise<Pyodide>;
  };
  const pyodide = await module.loadPyodide({ indexURL: PYODIDE_INDEX });
  ctx.postMessage({ type: "status", stage: "loading-engine" });
  await pyodide.loadPackage(wheelUrl);
  pyodide.runPython(GLUE);
  runFn = pyodide.globals.get("mrm_run");
  branchialFn = pyodide.globals.get("mrm_branchial");
  ctx.postMessage({ type: "status", stage: "ready" });
}

ctx.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const message = event.data;
  void (async () => {
    try {
      if (message.type === "init") {
        await init(message.wheelUrl);
      } else if (message.type === "run") {
        if (!runFn) throw new Error("engine is not ready yet");
        const payload = runFn(message.doc, message.params) as string;
        ctx.postMessage({ type: "result", id: message.id, payload });
      } else if (message.type === "branchial") {
        if (!branchialFn) throw new Error("engine is not ready yet");
        const payload = branchialFn(message.step) as string;
        ctx.postMessage({ type: "result", id: message.id, payload });
      }
    } catch (error) {
      ctx.postMessage({
        type: "error",
        id: "id" in message ? message.id : null,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  })();
};
