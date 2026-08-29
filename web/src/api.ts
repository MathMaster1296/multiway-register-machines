/** Client wrapper around the engine worker: promise-based requests, a status
 * callback, and cancellation by respawning the worker. */

import type { RunParams, RunResult, WorkerResponse } from "./types.js";

export type EngineStage =
  | "loading-pyodide"
  | "loading-engine"
  | "ready"
  | "working"
  | "failed";

interface Pending {
  resolve(payload: string): void;
  reject(error: Error): void;
}

export class EngineClient {
  private worker: Worker | null = null;
  private pending = new Map<number, Pending>();
  private nextId = 1;
  private ready = false;
  private readyWaiters: (() => void)[] = [];

  constructor(
    private wheelUrl: string,
    private onStage: (stage: EngineStage, detail?: string) => void,
  ) {}

  start(): void {
    this.ready = false;
    const worker = new Worker("js/worker.js", { type: "module" });
    this.worker = worker;
    worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      const message = event.data;
      if (message.type === "status") {
        this.onStage(message.stage);
        if (message.stage === "ready") {
          this.ready = true;
          for (const wake of this.readyWaiters.splice(0)) wake();
        }
      } else if (message.type === "result") {
        this.pending.get(message.id)?.resolve(message.payload);
        this.pending.delete(message.id);
      } else if (message.type === "error") {
        if (message.id !== null && this.pending.has(message.id)) {
          this.pending.get(message.id)?.reject(new Error(message.message));
          this.pending.delete(message.id);
        } else {
          this.onStage("failed", message.message);
        }
      }
    };
    worker.onerror = (event) => {
      this.onStage("failed", event.message);
    };
    worker.postMessage({ type: "init", wheelUrl: this.wheelUrl });
  }

  /** Terminate a running computation and bring up a fresh engine. */
  cancel(): void {
    this.worker?.terminate();
    for (const pending of this.pending.values()) {
      pending.reject(new Error("cancelled"));
    }
    this.pending.clear();
    this.start();
  }

  private whenReady(): Promise<void> {
    if (this.ready) return Promise.resolve();
    return new Promise((resolve) => this.readyWaiters.push(resolve));
  }

  private request(message: object): Promise<string> {
    const id = this.nextId++;
    return new Promise<string>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker?.postMessage({ ...message, id });
    });
  }

  async run(docJson: string, params: RunParams): Promise<RunResult> {
    await this.whenReady();
    this.onStage("working");
    try {
      const payload = await this.request({
        type: "run",
        doc: docJson,
        params: JSON.stringify(params),
      });
      return JSON.parse(payload) as RunResult;
    } finally {
      if (this.ready) this.onStage("ready");
    }
  }

  async branchial(step: number): Promise<[number, number][]> {
    await this.whenReady();
    const payload = await this.request({ type: "branchial", step });
    const data = JSON.parse(payload) as { ok: boolean; edges: [number, number][] };
    return data.ok ? data.edges : [];
  }
}
