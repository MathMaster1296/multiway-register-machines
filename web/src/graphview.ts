/** The graph canvas: layered top-to-bottom rendering of an evolution.
 *
 * SVG below CANVAS_THRESHOLD nodes (interactive: pan, zoom, selection,
 * ancestor/descendant highlighting, edge labels above a zoom threshold);
 * a 2d canvas above it (pan and zoom only). The switch is automatic.
 */

import type { EvolutionJson } from "./types.js";

export const CANVAS_THRESHOLD = 2000;
const SCALE = 90;
const CHIP_HEIGHT = 26;
const LABEL_ZOOM = 0.7;

const SVG_NS = "http://www.w3.org/2000/svg";

interface ViewData {
  evolution: EvolutionJson;
  positions: Map<number, [number, number]>;
  layerOf: Map<number, number>;
  labels: Map<number, string>;
}

export class GraphView {
  private data: ViewData | null = null;
  private transform = { x: 40, y: 40, k: 1 };
  private visibleStep = Infinity;
  private selected: number | null = null;
  private ancestors = new Set<number>();
  private descendants = new Set<number>();
  private branchialEdges: [number, number][] = [];
  private pathEdges = new Set<number>();
  private svg: SVGSVGElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private fitUsedFallback = false;
  private userMoved = false;

  constructor(
    private root: HTMLElement,
    private onSelect: (node: number | null) => void,
  ) {
    this.attachPanZoom();
    new ResizeObserver(() => {
      const refittable = this.fitUsedFallback || !this.userMoved;
      if (refittable && this.data && this.root.clientWidth > 0) {
        this.fit();
        this.refresh();
      }
    }).observe(this.root);
  }

  get usingCanvas(): boolean {
    return this.canvas !== null;
  }

  setEvolution(evolution: EvolutionJson, layout: Record<string, [number, number]>): void {
    const positions = new Map<number, [number, number]>();
    for (const [id, [x, y]] of Object.entries(layout)) {
      positions.set(Number(id), [x * SCALE, y * SCALE]);
    }
    const layerOf = new Map<number, number>();
    evolution.layers.forEach((layer, index) => {
      for (const node of layer) layerOf.set(node, index);
    });
    const labels = new Map<number, string>();
    for (const [id, pc, registers] of evolution.nodes) {
      labels.set(id, `${pc} | ${registers.join(",")}`);
    }
    this.data = { evolution, positions, layerOf, labels };
    this.selected = null;
    this.ancestors.clear();
    this.descendants.clear();
    this.branchialEdges = [];
    this.pathEdges = new Set();
    this.visibleStep = evolution.layers.length - 1;
    this.userMoved = false;
    this.fit();
    this.rebuild();
  }

  setStep(step: number): void {
    this.visibleStep = step;
    this.refresh();
  }

  /** Zoom around the center of the view; the buttons and keyboard use this. */
  zoomBy(factor: number): void {
    this.userMoved = true;
    const cx = this.root.clientWidth / 2;
    const cy = this.root.clientHeight / 2;
    const { x, y, k } = this.transform;
    const next = Math.min(6, Math.max(0.05, k * factor));
    this.transform = { k: next, x: cx - ((cx - x) / k) * next, y: cy - ((cy - y) / k) * next };
    this.refresh();
  }

  fitView(): void {
    this.userMoved = false;
    this.fit();
    this.refresh();
  }

  setBranchial(edges: [number, number][]): void {
    this.branchialEdges = edges;
    this.rebuild();
  }

  select(node: number | null): void {
    this.selected = node;
    this.ancestors = node === null ? new Set() : this.reach(node, "in");
    this.descendants = node === null ? new Set() : this.reach(node, "out");
    this.pathEdges = node === null ? new Set() : this.shortestPathEdges(node);
    this.refresh();
    this.onSelect(node);
  }

  /** Edge indices of one shortest path from the roots to the node. */
  private shortestPathEdges(target: number): Set<number> {
    if (!this.data) return new Set();
    const roots = new Set(this.data.evolution.layers[0] ?? []);
    if (roots.has(target)) return new Set();
    const outgoing = new Map<number, [number, number][]>();
    this.data.evolution.edges.forEach(([src, dst], index) => {
      const list = outgoing.get(src);
      if (list) list.push([dst, index]);
      else outgoing.set(src, [[dst, index]]);
    });
    const via = new Map<number, number>();
    let frontier = [...roots];
    while (frontier.length && !via.has(target)) {
      const next: number[] = [];
      for (const node of frontier) {
        for (const [dst, index] of outgoing.get(node) ?? []) {
          if (!via.has(dst) && !roots.has(dst)) {
            via.set(dst, index);
            next.push(dst);
          }
        }
      }
      frontier = next;
    }
    const picked = new Set<number>();
    let node = target;
    while (!roots.has(node)) {
      const index = via.get(node);
      if (index === undefined) return new Set();
      picked.add(index);
      node = this.data.evolution.edges[index]?.[0] ?? node;
    }
    return picked;
  }

  exportSvg(): string | null {
    if (!this.svg) return null;
    const clone = this.svg.cloneNode(true) as SVGSVGElement;
    clone.setAttribute("xmlns", SVG_NS);
    return new XMLSerializer().serializeToString(clone);
  }

  async exportPng(): Promise<Blob | null> {
    if (this.canvas) {
      return new Promise((resolve) => this.canvas?.toBlob(resolve, "image/png"));
    }
    const text = this.exportSvg();
    if (!text) return null;
    const image = new Image();
    const url = URL.createObjectURL(new Blob([text], { type: "image/svg+xml" }));
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = reject;
      image.src = url;
    });
    const target = document.createElement("canvas");
    target.width = this.root.clientWidth * 2;
    target.height = this.root.clientHeight * 2;
    const context = target.getContext("2d");
    if (!context) return null;
    context.scale(2, 2);
    context.drawImage(image, 0, 0);
    URL.revokeObjectURL(url);
    return new Promise((resolve) => target.toBlob(resolve, "image/png"));
  }

  private reach(start: number, direction: "in" | "out"): Set<number> {
    if (!this.data) return new Set();
    const adjacency = new Map<number, number[]>();
    for (const [src, dst] of this.data.evolution.edges) {
      const [from, to] = direction === "out" ? [src, dst] : [dst, src];
      const list = adjacency.get(from);
      if (list) list.push(to);
      else adjacency.set(from, [to]);
    }
    const seen = new Set<number>();
    let frontier = [start];
    while (frontier.length) {
      const next: number[] = [];
      for (const node of frontier) {
        for (const neighbor of adjacency.get(node) ?? []) {
          if (!seen.has(neighbor)) {
            seen.add(neighbor);
            next.push(neighbor);
          }
        }
      }
      frontier = next;
    }
    return seen;
  }

  private fit(): void {
    if (!this.data || this.data.positions.size === 0) return;
    // The host can measure 0x0 mid-layout; fall back to nominal dimensions
    // and let the ResizeObserver refit once real sizes arrive.
    this.fitUsedFallback = this.root.clientWidth === 0 || this.root.clientHeight === 0;
    const hostWidth = this.root.clientWidth || 800;
    const hostHeight = this.root.clientHeight || 500;
    const xs = [...this.data.positions.values()].map((p) => p[0]);
    const ys = [...this.data.positions.values()].map((p) => p[1]);
    const width = Math.max(...xs) - Math.min(...xs) + 2 * SCALE;
    const height = Math.max(...ys) - Math.min(...ys) + 2 * SCALE;
    const k = Math.max(
      0.02,
      Math.min(1.2, hostWidth / Math.max(width, 1), hostHeight / Math.max(height, 1)),
    );
    this.transform = {
      k,
      x: hostWidth / 2 - ((Math.max(...xs) + Math.min(...xs)) / 2) * k,
      y: 30 - Math.min(...ys) * k,
    };
  }

  private nodeVisible(node: number): boolean {
    return (this.data?.layerOf.get(node) ?? 0) <= this.visibleStep;
  }

  /** Full rebuild: chooses SVG or canvas by node count. */
  rebuild(): void {
    this.root.querySelector(".graph-surface")?.remove();
    this.svg = null;
    this.canvas = null;
    if (!this.data) return;
    if (this.data.evolution.nodes.length > CANVAS_THRESHOLD) {
      this.buildCanvas();
    } else {
      this.buildSvg();
    }
    this.refresh();
  }

  private buildSvg(): void {
    if (!this.data) return;
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.classList.add("graph-surface");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Multiway evolution graph");
    const defs = document.createElementNS(SVG_NS, "defs");
    defs.innerHTML =
      '<marker id="ge-arrow" viewBox="0 0 10 10" refX="9" refY="5"' +
      ' markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">' +
      '<path d="M 0 0 L 10 5 L 0 10 z" class="arrowhead"/></marker>';
    svg.append(defs);
    const viewport = document.createElementNS(SVG_NS, "g");
    viewport.classList.add("viewport");

    this.data.evolution.edges.forEach(([src, dst, rule], edgeIndex) => {
      const from = this.data?.positions.get(src);
      const to = this.data?.positions.get(dst);
      if (!from || !to) return;
      const group = document.createElementNS(SVG_NS, "g");
      group.classList.add("edge");
      group.dataset["src"] = String(src);
      group.dataset["dst"] = String(dst);
      group.dataset["idx"] = String(edgeIndex);
      const line = document.createElementNS(SVG_NS, "line");
      if (src === dst) {
        const loop = document.createElementNS(SVG_NS, "path");
        const [x, y] = from;
        loop.setAttribute(
          "d",
          `M ${x + 14} ${y - 6} C ${x + 46} ${y - 26}, ${x + 46} ${y + 26}, ${x + 14} ${y + 6}`,
        );
        loop.classList.add("edge-line");
        loop.setAttribute("marker-end", "url(#ge-arrow)");
        group.append(loop);
      } else {
        line.setAttribute("x1", String(from[0]));
        line.setAttribute("y1", String(from[1] + CHIP_HEIGHT / 2));
        line.setAttribute("x2", String(to[0]));
        line.setAttribute("y2", String(to[1] - CHIP_HEIGHT / 2));
        line.classList.add("edge-line");
        line.setAttribute("marker-end", "url(#ge-arrow)");
        group.append(line);
      }
      const label = document.createElementNS(SVG_NS, "text");
      label.textContent = rule;
      label.classList.add("edge-label");
      label.setAttribute("x", String((from[0] + to[0]) / 2 + 4));
      label.setAttribute("y", String((from[1] + to[1]) / 2));
      group.append(label);
      viewport.append(group);
    });

    for (const [a, b] of this.branchialEdges) {
      const from = this.data.positions.get(a);
      const to = this.data.positions.get(b);
      if (!from || !to) continue;
      const line = document.createElementNS(SVG_NS, "line");
      line.classList.add("branchial-line");
      line.setAttribute("x1", String(from[0]));
      line.setAttribute("y1", String(from[1]));
      line.setAttribute("x2", String(to[0]));
      line.setAttribute("y2", String(to[1]));
      viewport.append(line);
    }

    for (const [id] of this.data.positions) {
      const position = this.data.positions.get(id);
      if (!position) continue;
      const label = this.data.labels.get(id) ?? String(id);
      const group = document.createElementNS(SVG_NS, "g");
      group.classList.add("node");
      group.dataset["id"] = String(id);
      group.setAttribute("tabindex", "0");
      group.setAttribute("role", "button");
      group.setAttribute("aria-label", `State ${label}`);
      const terminalKind = this.data.evolution.terminals[String(id)];
      if (terminalKind) group.classList.add(`terminal-${terminalKind}`);
      const width = Math.max(34, label.length * 7 + 14);
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("x", String(position[0] - width / 2));
      rect.setAttribute("y", String(position[1] - CHIP_HEIGHT / 2));
      rect.setAttribute("width", String(width));
      rect.setAttribute("height", String(CHIP_HEIGHT));
      rect.setAttribute("rx", "6");
      const text = document.createElementNS(SVG_NS, "text");
      text.textContent = label;
      text.setAttribute("x", String(position[0]));
      text.setAttribute("y", String(position[1] + 4));
      text.setAttribute("text-anchor", "middle");
      group.append(rect, text);
      const activate = () => this.select(this.selected === id ? null : id);
      group.addEventListener("click", (event) => {
        event.stopPropagation();
        activate();
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
      viewport.append(group);
    }

    svg.append(viewport);
    svg.addEventListener("click", () => this.select(null));
    this.root.append(svg);
    this.svg = svg;
  }

  private buildCanvas(): void {
    const canvas = document.createElement("canvas");
    canvas.classList.add("graph-surface");
    canvas.width = this.root.clientWidth * devicePixelRatio;
    canvas.height = this.root.clientHeight * devicePixelRatio;
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.title =
      "Large graph: rendered on a canvas without labels. Below " +
      `${CANVAS_THRESHOLD} nodes the view switches to interactive SVG.`;
    this.root.append(canvas);
    this.canvas = canvas;
  }

  /** Cheap refresh: visibility, highlighting, zoom transform. */
  refresh(): void {
    if (this.canvas) {
      this.paintCanvas();
      return;
    }
    if (!this.svg || !this.data) return;
    const viewport = this.svg.querySelector(".viewport");
    if (!(viewport instanceof SVGGElement)) return;
    const { x, y, k } = this.transform;
    viewport.setAttribute("transform", `translate(${x}, ${y}) scale(${k})`);
    this.svg.classList.toggle("labels-hidden", k < LABEL_ZOOM);
    const dimming = this.selected !== null;
    for (const element of viewport.querySelectorAll<SVGGElement>("g.node")) {
      const id = Number(element.dataset["id"]);
      element.classList.toggle("hidden", !this.nodeVisible(id));
      element.classList.toggle("selected", id === this.selected);
      element.classList.toggle("ancestor", this.ancestors.has(id));
      element.classList.toggle("descendant", this.descendants.has(id) && id !== this.selected);
      element.classList.toggle(
        "dimmed",
        dimming && id !== this.selected && !this.ancestors.has(id) && !this.descendants.has(id),
      );
    }
    for (const element of viewport.querySelectorAll<SVGGElement>("g.edge")) {
      const src = Number(element.dataset["src"]);
      const dst = Number(element.dataset["dst"]);
      const index = Number(element.dataset["idx"]);
      element.classList.toggle("hidden", !this.nodeVisible(src) || !this.nodeVisible(dst));
      const related =
        !dimming ||
        ((this.ancestors.has(src) || src === this.selected) &&
          (this.ancestors.has(dst) || dst === this.selected)) ||
        ((this.descendants.has(dst) || dst === this.selected) &&
          (this.descendants.has(src) || src === this.selected));
      element.classList.toggle("dimmed", dimming && !related);
      element.classList.toggle("pathline", this.pathEdges.has(index));
    }
  }

  private paintCanvas(): void {
    if (!this.canvas || !this.data) return;
    const context = this.canvas.getContext("2d");
    if (!context) return;
    const styles = getComputedStyle(this.root);
    const edgeColor = styles.getPropertyValue("--edge").trim() || "#888";
    const nodeColor = styles.getPropertyValue("--accent").trim() || "#4a90d9";
    context.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    const { x, y, k } = this.transform;
    context.translate(x, y);
    context.scale(k, k);
    context.strokeStyle = edgeColor;
    context.globalAlpha = 0.55;
    context.lineWidth = 1;
    context.beginPath();
    for (const [src, dst] of this.data.evolution.edges) {
      if (!this.nodeVisible(src) || !this.nodeVisible(dst)) continue;
      const from = this.data.positions.get(src);
      const to = this.data.positions.get(dst);
      if (!from || !to) continue;
      context.moveTo(from[0], from[1]);
      context.lineTo(to[0], to[1]);
    }
    context.stroke();
    context.globalAlpha = 1;
    context.fillStyle = nodeColor;
    for (const [id, position] of this.data.positions) {
      if (!this.nodeVisible(id)) continue;
      context.beginPath();
      context.arc(position[0], position[1], 3.2, 0, Math.PI * 2);
      context.fill();
    }
  }

  private attachPanZoom(): void {
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    this.root.addEventListener("pointerdown", (event) => {
      this.userMoved = true;
      dragging = true;
      lastX = event.clientX;
      lastY = event.clientY;
      this.root.setPointerCapture(event.pointerId);
    });
    this.root.addEventListener("pointermove", (event) => {
      if (!dragging) return;
      this.transform.x += event.clientX - lastX;
      this.transform.y += event.clientY - lastY;
      lastX = event.clientX;
      lastY = event.clientY;
      this.refresh();
    });
    this.root.addEventListener("pointerup", () => {
      dragging = false;
    });
    this.root.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        this.userMoved = true;
        const factor = Math.exp(-event.deltaY * 0.0015);
        const rect = this.root.getBoundingClientRect();
        const px = event.clientX - rect.left;
        const py = event.clientY - rect.top;
        const { x, y, k } = this.transform;
        const next = Math.min(6, Math.max(0.05, k * factor));
        this.transform = {
          k: next,
          x: px - ((px - x) / k) * next,
          y: py - ((py - y) / k) * next,
        };
        this.refresh();
      },
      { passive: false },
    );
  }
}
