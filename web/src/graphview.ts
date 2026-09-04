/** The graph canvas: layered top-to-bottom rendering of an evolution.
 *
 * SVG below CANVAS_THRESHOLD nodes (interactive: pan, zoom, selection,
 * ancestor/descendant highlighting, shortest-path emphasis, edge labels
 * above a zoom threshold); a 2d canvas above it (pan and zoom only). The
 * switch is automatic. Edges are colored by rule family, chips carry the
 * program counter as a badge, and faint bands mark the steps.
 */

import type { EvolutionJson } from "./types.js";

export const CANVAS_THRESHOLD = 2000;
const X_SCALE = 118;
const Y_SCALE = 104;
const CHIP_HEIGHT = 30;
const LABEL_ZOOM = 0.62;
const RULE_COLOR_SLOTS = 8;

const SVG_NS = "http://www.w3.org/2000/svg";

interface ViewData {
  evolution: EvolutionJson;
  positions: Map<number, [number, number]>;
  layerOf: Map<number, number>;
  ruleSlot: Map<string, number>;
  bounds: { minX: number; maxX: number; minY: number; maxY: number };
}

function chipWidth(pc: number, registers: number[]): { badge: number; total: number } {
  const badge = 14 + 7.2 * String(pc).length;
  const label = registers.join(", ");
  const total = badge + 16 + 7.2 * label.length;
  return { badge, total: Math.max(total, 52) };
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

  /** Rule id -> color slot in order of first appearance; -1 past the palette. */
  ruleColors(): Map<string, number> {
    return new Map(this.data?.ruleSlot ?? []);
  }

  setEvolution(evolution: EvolutionJson, layout: Record<string, [number, number]>): void {
    const positions = new Map<number, [number, number]>();
    for (const [id, [x, y]] of Object.entries(layout)) {
      positions.set(Number(id), [x * X_SCALE, y * Y_SCALE]);
    }
    const layerOf = new Map<number, number>();
    evolution.layers.forEach((layer, index) => {
      for (const node of layer) layerOf.set(node, index);
    });
    const ruleSlot = new Map<string, number>();
    for (const [, , rule] of evolution.edges) {
      if (!ruleSlot.has(rule)) {
        const next = ruleSlot.size;
        ruleSlot.set(rule, next < RULE_COLOR_SLOTS ? next : -1);
      }
    }
    const xs = [...positions.values()].map((p) => p[0]);
    const ys = [...positions.values()].map((p) => p[1]);
    const bounds = {
      minX: Math.min(...xs, 0),
      maxX: Math.max(...xs, 0),
      minY: Math.min(...ys, 0),
      maxY: Math.max(...ys, 0),
    };
    this.data = { evolution, positions, layerOf, ruleSlot, bounds };
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

  setStep(step: number, follow = false): void {
    this.visibleStep = step;
    if (follow) this.keepStepVisible(step);
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

  exportSvg(): string | null {
    if (!this.svg) return null;
    const clone = this.svg.cloneNode(true) as SVGSVGElement;
    clone.setAttribute("xmlns", SVG_NS);
    clone.setAttribute("width", String(this.root.clientWidth));
    clone.setAttribute("height", String(this.root.clientHeight));
    const style = document.createElementNS(SVG_NS, "style");
    style.textContent = exportStyles();
    clone.insertBefore(style, clone.firstChild);
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
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, this.root.clientWidth, this.root.clientHeight);
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

  /** Fit to width, keep chips readable, and start at the top for tall graphs. */
  private fit(): void {
    if (!this.data || this.data.positions.size === 0) return;
    this.fitUsedFallback = this.root.clientWidth === 0 || this.root.clientHeight === 0;
    const hostWidth = this.root.clientWidth || 800;
    const hostHeight = this.root.clientHeight || 500;
    const { minX, maxX, minY, maxY } = this.data.bounds;
    const width = maxX - minX + X_SCALE * 1.7;
    const height = maxY - minY + Y_SCALE * 1.2;
    const widthFit = (hostWidth - 24) / width;
    const allFit = Math.min(widthFit, (hostHeight - 24) / height);
    const k = Math.min(1.15, Math.max(allFit, Math.min(0.62, widthFit)));
    const contentHeight = height * k;
    this.transform = {
      k,
      x: hostWidth / 2 - ((maxX + minX) / 2) * k,
      y:
        contentHeight < hostHeight
          ? (hostHeight - contentHeight) / 2 - (minY - Y_SCALE * 0.6) * k
          : 36 - minY * k,
    };
  }

  /** Pan just enough that the given step's row is on screen. */
  private keepStepVisible(step: number): void {
    if (!this.data) return;
    const first = this.data.evolution.layers[step]?.[0];
    if (first === undefined) return;
    const position = this.data.positions.get(first);
    if (!position) return;
    const { y, k } = this.transform;
    const screenY = position[1] * k + y;
    const hostHeight = this.root.clientHeight;
    const margin = CHIP_HEIGHT * k + 28;
    if (screenY > hostHeight - margin) {
      this.transform = { ...this.transform, y: y - (screenY - (hostHeight - margin)) };
    } else if (screenY < margin) {
      this.transform = { ...this.transform, y: y + (margin - screenY) };
    }
  }

  private nodeVisible(node: number): boolean {
    return (this.data?.layerOf.get(node) ?? 0) <= this.visibleStep;
  }

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

  private edgePath(from: [number, number], to: [number, number], src: number, dst: number): string {
    const x1 = from[0];
    const y1 = from[1] + CHIP_HEIGHT / 2;
    const x2 = to[0];
    const y2 = to[1] - CHIP_HEIGHT / 2;
    if (src === dst) {
      const [x, y] = from;
      return `M ${x + 20} ${y - 8} C ${x + 62} ${y - 34}, ${x + 62} ${y + 34}, ${x + 20} ${y + 8}`;
    }
    if (y2 <= y1) {
      const bulge = 70 + Math.abs(y1 - y2) * 0.15;
      const ax = Math.max(x1, x2) + bulge;
      return `M ${x1} ${y1} C ${ax} ${y1 + 40}, ${ax} ${y2 - 40}, ${x2} ${y2}`;
    }
    const bend = (y2 - y1) * 0.55;
    return `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
  }

  private buildSvg(): void {
    if (!this.data) return;
    const { evolution, positions, ruleSlot, bounds } = this.data;
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.classList.add("graph-surface");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Multiway evolution graph");
    const defs = document.createElementNS(SVG_NS, "defs");
    defs.innerHTML =
      '<marker id="ge-arrow" viewBox="0 0 10 10" refX="8.5" refY="5"' +
      ' markerWidth="6" markerHeight="6" orient="auto-start-reverse">' +
      '<path d="M 0 0 L 10 5 L 0 10 z" class="arrowhead"/></marker>' +
      '<filter id="ge-glow" x="-40%" y="-60%" width="180%" height="220%">' +
      '<feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#2a78d6" flood-opacity="0.75"/>' +
      "</filter>";
    svg.append(defs);
    const viewport = document.createElementNS(SVG_NS, "g");
    viewport.classList.add("viewport");

    const bands = document.createElementNS(SVG_NS, "g");
    bands.classList.add("bands");
    const bandLeft = bounds.minX - X_SCALE * 0.85;
    const bandWidth = bounds.maxX - bounds.minX + X_SCALE * 1.7;
    evolution.layers.forEach((layer, index) => {
      const first = layer[0];
      const position = first === undefined ? undefined : positions.get(first);
      if (!position) return;
      const band = document.createElementNS(SVG_NS, "rect");
      band.classList.add("band");
      if (index % 2 === 1) band.classList.add("band-alt");
      band.setAttribute("x", String(bandLeft));
      band.setAttribute("y", String(position[1] - Y_SCALE / 2));
      band.setAttribute("width", String(bandWidth));
      band.setAttribute("height", String(Y_SCALE));
      band.setAttribute("rx", "10");
      bands.append(band);
      const label = document.createElementNS(SVG_NS, "text");
      label.classList.add("band-label");
      label.textContent = `step ${index}`;
      label.setAttribute("x", String(bandLeft + 12));
      label.setAttribute("y", String(position[1] - Y_SCALE / 2 + 15));
      bands.append(label);
    });
    viewport.append(bands);

    const edgeLayer = document.createElementNS(SVG_NS, "g");
    evolution.edges.forEach(([src, dst, rule], edgeIndex) => {
      const from = positions.get(src);
      const to = positions.get(dst);
      if (!from || !to) return;
      const group = document.createElementNS(SVG_NS, "g");
      group.classList.add("edge");
      const slot = ruleSlot.get(rule) ?? -1;
      if (slot >= 0) group.classList.add(`rule-${slot}`);
      group.dataset["src"] = String(src);
      group.dataset["dst"] = String(dst);
      group.dataset["idx"] = String(edgeIndex);
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", this.edgePath(from, to, src, dst));
      path.classList.add("edge-line");
      path.setAttribute("marker-end", "url(#ge-arrow)");
      group.append(path);
      const label = document.createElementNS(SVG_NS, "text");
      label.textContent = rule;
      label.classList.add("edge-label");
      const midX = src === dst ? from[0] + 66 : (from[0] + to[0]) / 2;
      const midY = src === dst ? from[1] + 3 : (from[1] + to[1]) / 2 + 3;
      label.setAttribute("x", String(midX));
      label.setAttribute("y", String(midY));
      label.setAttribute("text-anchor", "middle");
      group.append(label);
      edgeLayer.append(group);
    });
    viewport.append(edgeLayer);

    for (const [a, b] of this.branchialEdges) {
      const from = positions.get(a);
      const to = positions.get(b);
      if (!from || !to) continue;
      const line = document.createElementNS(SVG_NS, "path");
      line.classList.add("branchial-line");
      const top = CHIP_HEIGHT / 2;
      const lift = 26;
      line.setAttribute(
        "d",
        `M ${from[0]} ${from[1] - top} C ${from[0]} ${from[1] - top - lift}, ` +
          `${to[0]} ${to[1] - top - lift}, ${to[0]} ${to[1] - top}`,
      );
      viewport.append(line);
    }

    const nodeLayer = document.createElementNS(SVG_NS, "g");
    for (const [id, pc, registers] of evolution.nodes) {
      const position = positions.get(id);
      if (!position) continue;
      const { badge, total } = chipWidth(pc, registers);
      const [x, y] = position;
      const left = x - total / 2;
      const top = y - CHIP_HEIGHT / 2;
      const group = document.createElementNS(SVG_NS, "g");
      group.classList.add("node");
      group.dataset["id"] = String(id);
      group.setAttribute("tabindex", "0");
      group.setAttribute("role", "button");
      group.setAttribute("aria-label", `State at pc ${pc} with registers ${registers.join(", ")}`);
      const terminalKind = evolution.terminals[String(id)];
      if (terminalKind) group.classList.add(`terminal-${terminalKind}`);

      const chip = document.createElementNS(SVG_NS, "rect");
      chip.classList.add("chip");
      chip.setAttribute("x", String(left));
      chip.setAttribute("y", String(top));
      chip.setAttribute("width", String(total));
      chip.setAttribute("height", String(CHIP_HEIGHT));
      chip.setAttribute("rx", "9");

      const badgeRect = document.createElementNS(SVG_NS, "rect");
      badgeRect.classList.add("badge");
      badgeRect.setAttribute("x", String(left + 3));
      badgeRect.setAttribute("y", String(top + 3));
      badgeRect.setAttribute("width", String(badge - 4));
      badgeRect.setAttribute("height", String(CHIP_HEIGHT - 6));
      badgeRect.setAttribute("rx", "7");

      const badgeText = document.createElementNS(SVG_NS, "text");
      badgeText.classList.add("badge-text");
      badgeText.textContent = String(pc);
      badgeText.setAttribute("x", String(left + 1 + badge / 2));
      badgeText.setAttribute("y", String(y + 4));
      badgeText.setAttribute("text-anchor", "middle");

      const regText = document.createElementNS(SVG_NS, "text");
      regText.classList.add("reg-text");
      regText.textContent = registers.join(", ");
      regText.setAttribute("x", String(left + badge + (total - badge) / 2));
      regText.setAttribute("y", String(y + 4));
      regText.setAttribute("text-anchor", "middle");

      group.append(chip, badgeRect, badgeText, regText);
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
      nodeLayer.append(group);
    }
    viewport.append(nodeLayer);

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
    context.globalAlpha = 0.5;
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
      context.arc(position[0], position[1], 3.4, 0, Math.PI * 2);
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

/** Styles inlined into exported SVGs so they look right outside the page. */
function exportStyles(): string {
  return [
    ".band { fill: #f1f1ee; } .band-alt { fill: #e9e9e5; }",
    ".band-label { font: 10px sans-serif; fill: #8a8984; }",
    ".chip { fill: #e8f1fc; stroke: #2a78d6; stroke-width: 1.2; }",
    ".badge { fill: #2a78d6; } .badge-text { font: 600 11px monospace; fill: #fff; }",
    ".reg-text { font: 11px monospace; fill: #111; }",
    ".terminal-halt .chip, .terminal-stuck .chip { fill: #fcecc8; stroke: #b97f00; }",
    ".terminal-halt .badge, .terminal-stuck .badge { fill: #b97f00; }",
    ".edge-line { fill: none; stroke: #9a9994; stroke-width: 1.3; }",
    ".arrowhead { fill: #9a9994; }",
    ".rule-0 .edge-line { stroke: #2a78d6; } .rule-1 .edge-line { stroke: #eb6834; }",
    ".rule-2 .edge-line { stroke: #1baf7a; } .rule-3 .edge-line { stroke: #c98500; }",
    ".rule-4 .edge-line { stroke: #d55181; } .rule-5 .edge-line { stroke: #008300; }",
    ".rule-6 .edge-line { stroke: #4a3aa7; } .rule-7 .edge-line { stroke: #e34948; }",
    ".edge-label { font: 9.5px monospace; fill: #555; paint-order: stroke; stroke: #fff; stroke-width: 3px; }",
    ".branchial-line { fill: none; stroke: #4a3aa7; stroke-width: 1.6; stroke-dasharray: 5 4; }",
    ".hidden { display: none; } .dimmed { opacity: 0.15; }",
  ].join("\n");
}
