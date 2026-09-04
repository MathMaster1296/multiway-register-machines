"""Reproducible figure generation, no plotting library required.

Figures are written as hand-assembled SVG from the deterministic layout, so
regenerating them always produces identical bytes. The registry maps figure
names to builders; ``mrm figure NAME --out DIR`` and scripts/make_figures.py
both go through it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from pathlib import Path

from . import builders
from .counting import PathCount, path_counts
from .ensemble import EnsembleRow, ensemble
from .evolve import Evolution, evolve
from .layout import layered_layout
from .machine import Config, Instruction, instructions_from_wfr, machine_from_wfr

SCALE = 72.0
NODE_RADIUS = 16.0
MARGIN = 48.0


def _svg_document(width: float, height: float, body: list[str], title: str | None = None) -> str:
    label = f' role="img" aria-label="{title}"' if title else ""
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="Helvetica, Arial, sans-serif"{label}>'
    )
    if title:
        head += f"\n<title>{title}</title>"
    defs = (
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#8f8e88"/></marker></defs>'
    )
    background = f'<rect width="{width:.0f}" height="{height:.0f}" fill="white"/>'
    return "\n".join([head, defs, background, *body, "</svg>"]) + "\n"


def evolution_svg(
    ev: Evolution,
    *,
    caption: str | None = None,
    node_text: Callable[[int], str] | None = None,
) -> str:
    """Render an evolution top-to-bottom with labeled state chips."""
    positions = layered_layout(ev, x_gap=1.35, y_gap=1.0)
    xs = [p[0] for p in positions.values()] or [0.0]
    ys = [p[1] for p in positions.values()] or [0.0]
    width = (max(xs) - min(xs)) * SCALE + 2 * MARGIN
    if caption:
        width = max(width, len(caption) * 7.5 + 2 * MARGIN)
    dx = width / 2 - ((max(xs) + min(xs)) / 2) * SCALE
    dy = MARGIN + (30 if caption else 0) - min(ys) * SCALE
    height = (max(ys) - min(ys)) * SCALE + 2 * MARGIN + (30 if caption else 0)

    def at(node: int) -> tuple[float, float]:
        x, y = positions[node]
        return x * SCALE + dx, y * SCALE + dy

    body = []
    if caption:
        body.append(
            f'<text x="{width / 2:.1f}" y="24" text-anchor="middle" '
            f'font-size="15" fill="#222">{caption}</text>'
        )
    for edge in ev.edges:
        (x1, y1), (x2, y2) = at(edge.src), at(edge.dst)
        body.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            'stroke="#8f8e88" stroke-width="1.2" marker-end="url(#arrow)"/>'
        )
    for node, config in ev.nodes.items():
        x, y = at(node)
        terminal = node in ev.terminals
        fill, stroke = ("#fcecc8", "#b97f00") if terminal else ("#cde2fb", "#2a78d6")
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{NODE_RADIUS:.0f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
        )
        text = node_text(node) if node_text else str(config.registers[0])
        body.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" '
            f'font-size="11" fill="#111">{text}</text>'
        )
    return _svg_document(width, height, body, title=caption)


def growth_svg(series: list[tuple[str, list[int]]], caption: str) -> str:
    """A small line chart of growth series (layer sizes per step)."""
    width, height, pad = 560.0, 320.0, 48.0
    top = max((max(s) for _, s in series if s), default=1)
    steps = max((len(s) for _, s in series), default=1)
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]

    def x_at(i: int) -> float:
        return pad + i * (width - 2 * pad) / max(steps - 1, 1)

    def y_at(v: int) -> float:
        return height - pad - v * (height - 2 * pad) / top

    body = [
        f'<text x="{width / 2:.1f}" y="24" text-anchor="middle" font-size="15" '
        f'fill="#222">{caption}</text>',
        f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" '
        f'y2="{height - pad}" stroke="#333"/>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#333"/>',
        f'<text x="{pad - 8:.1f}" y="{y_at(top) + 4:.1f}" text-anchor="end" '
        f'font-size="11" fill="#333">{top}</text>',
        f'<text x="{pad - 8:.1f}" y="{height - pad + 4:.1f}" text-anchor="end" '
        f'font-size="11" fill="#333">0</text>',
        f'<text x="{width - pad:.1f}" y="{height - pad + 20:.1f}" text-anchor="end" '
        f'font-size="11" fill="#333">step {steps - 1}</text>',
    ]
    for color, (label, values) in zip(colors, series, strict=False):
        points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(values))
        body.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
        if values:
            body.append(
                f'<text x="{x_at(len(values) - 1) + 6:.1f}" '
                f'y="{y_at(values[-1]) + 4:.1f}" font-size="12" '
                f'fill="{color}">{label}</text>'
            )
    return _svg_document(width, height, body)


def _figure_fibonacci_dag() -> dict[str, str]:
    machine = builders.fibonacci_machine()
    ev = evolve(machine, Config(1, (12,)))
    counts = path_counts(ev)

    def text(node: int) -> str:
        count = counts[node]
        suffix = "?" if isinstance(count, PathCount) else str(count)
        return f"{ev.nodes[node].registers[0]}:{suffix}"

    caption = "Fibonacci recursion, states graph: value k, paths from the root"
    return {"fibonacci-dag.svg": evolution_svg(ev, caption=caption, node_text=text)}


def _figure_grid_paths() -> dict[str, str]:
    ev = evolve(builders.grid_paths_machine(3, 3), Config(1, (0, 0)))
    caption = "Grid paths 3 x 3: 16 states, binomial(6, 3) = 20 paths"

    def text(node: int) -> str:
        i, j = ev.nodes[node].registers
        return f"{i},{j}"

    return {"grid-paths.svg": evolution_svg(ev, caption=caption, node_text=text)}


def _figure_collatz_multiway() -> dict[str, str]:
    machine = machine_from_wfr(builders.collatz_instructions(), 2)
    ev = evolve(machine, Config(8, (0, 5)), max_steps=12)
    caption = "Multiway Collatz from 5, both branches of every odometer state"

    def text(node: int) -> str:
        config = ev.nodes[node]
        return f"{config.registers[0]},{config.registers[1]}"

    return {"collatz-multiway.svg": evolution_svg(ev, caption=caption, node_text=text)}


def _figure_growth() -> dict[str, str]:
    machine = builders.fibonacci_machine()
    tree = evolve(machine, Config(1, (16,)), mode="tree", max_states=10**6)
    states = evolve(machine, Config(1, (16,)), mode="states")
    caption = "Fibonacci k = 16: tree frontier vs merged states per step"
    return {
        "growth.svg": growth_svg(
            [("tree", tree.growth_series()), ("states", states.growth_series())],
            caption,
        )
    }


FIGURES: dict[str, Callable[[], dict[str, str]]] = {
    "fibonacci-dag": _figure_fibonacci_dag,
    "grid-paths": _figure_grid_paths,
    "collatz-multiway": _figure_collatz_multiway,
    "growth": _figure_growth,
}


def make_figure(name: str, out_dir: Path) -> list[Path]:
    """Write one figure (or all with ``name == "all"``); returns the paths."""
    names = list(FIGURES) if name == "all" else [name]
    written = []
    for figure_name in names:
        if figure_name not in FIGURES:
            raise KeyError(f"unknown figure {figure_name!r}; known: {list(FIGURES)}")
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in FIGURES[figure_name]().items():
            path = out_dir / filename
            path.write_text(content)
            written.append(path)
    return written


SUCCESS_COLOR = "#2a78d6"
FAIL_COLOR = "#eb6834"


def _gray(reg: int, n_registers: int) -> str:
    """The WFR grayscale for register identity: r1 light, higher darker."""
    level = 0.8 if n_registers <= 1 else 0.8 + (reg - 1) * (0.5 - 0.8) / (n_registers - 1)
    value = round(level * 255)
    return f"rgb({value},{value},{value})"


def _instruction_triangle(cx: float, cy: float, size: float, op: str) -> str:
    """Direction marker: increments point right, decrements point left."""
    tip = cx + size if op == "inc" else cx - size
    back = cx - size * 0.6 if op == "inc" else cx + size * 0.6
    return (
        f'<polygon points="{tip:.1f},{cy:.1f} {back:.1f},{cy - size * 0.8:.1f} '
        f'{back:.1f},{cy + size * 0.8:.1f}" fill="#222"/>'
    )


def rule_plot_svg(instructions: Sequence[Instruction], n_registers: int) -> str:
    """The WFR ``RulePlot``, drawn to this project's palette.

    Instruction boxes sit in a row, shaded by the register they touch, with
    a direction marker for increment or decrement. Success branches arch
    above the row and fail branches below; arch height grows with jump
    distance, as in the original. Success is blue and failure orange here
    (the original used green and red).
    """
    scale = 56.0
    m = len(instructions)
    arcs: list[tuple[int, int, bool]] = []
    for i, ins in enumerate(instructions, start=1):
        arcs.extend((i, t, False) for t in ins.next_pcs)
        arcs.extend((i, t, True) for t in ins.fail_pcs)
    heights = [1.0]
    depths = [0.4]
    for i, t, is_fail in arcs:
        magnitude = max(1.0, abs(i - t) ** 0.5) + (0.0 if is_fail else 1.0)
        (depths if is_fail else heights).append(magnitude)
    top = max(heights) + 0.7
    bottom = max(depths) + 0.9
    width = (
        (max(t for i, t, _ in arcs for t in (i, t)) + 1.4) * scale if arcs else (m + 1.4) * scale
    )
    height = (top + bottom + 1.0) * scale

    def x_at(unit: float) -> float:
        return unit * scale

    def y_at(unit: float) -> float:  # world y up, box spans 0..1
        return (top + 1.0 - unit) * scale

    body = []
    for i, t, is_fail in arcs:
        x1, x2 = x_at(i + 0.5), x_at(t + 0.5)
        magnitude = max(1.0, abs(i - t) ** 0.5) + (0.0 if is_fail else 1.0)
        y0 = y_at(0.0 if is_fail else 1.0)
        peak = y_at(-magnitude - 0.35 if is_fail else 1.0 + magnitude)
        color = FAIL_COLOR if is_fail else SUCCESS_COLOR
        spread = 0.0 if i != t else 0.35 * scale
        body.append(
            f'<path d="M {x1 - spread:.1f} {y0:.1f} C {x1 - spread:.1f} {peak:.1f}, '
            f'{x2 + spread:.1f} {peak:.1f}, {x2 + spread:.1f} {y0:.1f}" fill="none" '
            f'stroke="{color}" stroke-width="1.6" marker-end="url(#arrow)"/>'
        )
    for i, ins in enumerate(instructions, start=1):
        left, size = x_at(i + 0.1), 0.8 * scale
        box_top = y_at(0.9)
        body.append(
            f'<rect x="{left:.1f}" y="{box_top:.1f}" width="{size:.1f}" '
            f'height="{size:.1f}" rx="4" fill="{_gray(ins.reg, n_registers)}" '
            'stroke="#333" stroke-width="1"/>'
        )
        body.append(_instruction_triangle(x_at(i + 0.5), y_at(0.5), 0.16 * scale, ins.op))
        body.append(
            f'<text x="{x_at(i + 0.5):.1f}" y="{y_at(-0.28):.1f}" text-anchor="middle" '
            f'font-size="12" fill="#555">{i}</text>'
        )
    return _svg_document(
        width,
        height,
        body,
        title=f"Rule diagram of {m} instructions: blue arcs are success branches, "
        "orange arcs are fail branches",
    )


def circle_plot_svg(instructions: Sequence[Instruction], n_registers: int) -> str:
    """The WFR ``CirclePlot``: instructions on a circle, arrows between them.

    Success arrows in blue, fail arrows in orange (green and red in the
    original); jump targets past the program end are drawn as smaller open
    halt nodes on the same circle.
    """
    scale = 54.0
    m = len(instructions)
    targets = {t for ins in instructions for t in (*ins.next_pcs, *ins.fail_pcs)}
    total = max(m, max(targets, default=m))
    radius = 3.0
    node_r = 0.30

    def position(pc: int) -> tuple[float, float]:
        angle = 2 * math.pi * (pc - 1) / total
        return radius * math.cos(angle), radius * math.sin(angle)

    def to_px(x: float, y: float) -> tuple[float, float]:
        margin = radius + 1.1
        return (x + margin) * scale, (margin - y) * scale

    side = (2 * (radius + 1.1)) * scale
    body = []
    for i, ins in enumerate(instructions, start=1):
        for is_fail, pcs in ((False, ins.next_pcs), (True, ins.fail_pcs)):
            color = FAIL_COLOR if is_fail else SUCCESS_COLOR
            for t in pcs:
                if t == i:
                    cx, cy = to_px(*position(i))
                    away = math.atan2(cy - side / 2, cx - side / 2)
                    lx = cx + math.cos(away) * node_r * scale * 2.1
                    ly = cy + math.sin(away) * node_r * scale * 2.1
                    body.append(
                        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="{node_r * scale * 0.75:.1f}" '
                        f'fill="none" stroke="{color}" stroke-width="1.6"/>'
                    )
                    continue
                x1, y1 = position(i)
                x2, y2 = position(t)
                length = math.hypot(x2 - x1, y2 - y1) or 1.0
                inset = node_r + 0.12
                ux, uy = (x2 - x1) / length, (y2 - y1) / length
                a = to_px(x1 + ux * inset, y1 + uy * inset)
                b = to_px(x2 - ux * inset, y2 - uy * inset)
                body.append(
                    f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                    f'stroke="{color}" stroke-width="1.6" marker-end="url(#arrow)"/>'
                )
    for pc in range(1, total + 1):
        cx, cy = to_px(*position(pc))
        if pc <= m:
            ins = instructions[pc - 1]
            body.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{node_r * scale:.1f}" '
                f'fill="{_gray(ins.reg, n_registers)}" stroke="#333" stroke-width="1.1"/>'
            )
            body.append(_instruction_triangle(cx, cy, 0.13 * scale, ins.op))
        else:
            body.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{node_r * scale * 0.62:.1f}" '
                'fill="white" stroke="#999" stroke-width="1.1" stroke-dasharray="3 2"/>'
            )
        body.append(
            f'<text x="{cx:.1f}" y="{cy + node_r * scale + 14:.1f}" text-anchor="middle" '
            f'font-size="12" fill="#555">{pc}</text>'
        )
    return _svg_document(
        side,
        side,
        body,
        title=f"Circle diagram of {m} instructions with success arrows in blue "
        "and fail arrows in orange",
    )


def scatter_svg(rows: Sequence[EnsembleRow], caption: str) -> str:
    """Complexity against realized branching, one point per machine.

    Machines whose evolution dies immediately sit on the floor as open gray
    circles; the dashed diagonal marks perfect prediction.
    """
    width, height, pad = 560.0, 420.0, 56.0
    xs = [row.complexity for row in rows] or [1.0]
    ys = [row.mean_branching for row in rows] or [1.0]
    low = min(*xs, *ys, 0.9)
    high = max(*xs, *ys, 1.1) + 0.1

    def px(value: float) -> float:
        return pad + (value - low) * (width - 2 * pad) / (high - low)

    def py(value: float) -> float:
        return height - pad - (value - low) * (height - 2 * pad) / (high - low)

    body = [
        f'<text x="{width / 2:.1f}" y="24" text-anchor="middle" font-size="15" '
        f'fill="#222">{caption}</text>',
        f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" '
        f'y2="{height - pad}" stroke="#333"/>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#333"/>',
        f'<line x1="{px(low):.1f}" y1="{py(low):.1f}" x2="{px(high):.1f}" y2="{py(high):.1f}" '
        'stroke="#999" stroke-width="1" stroke-dasharray="5 4"/>',
        f'<text x="{width / 2:.1f}" y="{height - 14:.1f}" text-anchor="middle" '
        'font-size="12" fill="#555">complexity (predicted branching)</text>',
        f'<text x="18" y="{height / 2:.1f}" text-anchor="middle" font-size="12" fill="#555" '
        f'transform="rotate(-90 18 {height / 2:.1f})">realized branching of the path tree</text>',
    ]
    for value in (1.0, 1.5, 2.0, 2.5, 3.0):
        if low <= value <= high:
            body.append(
                f'<text x="{px(value):.1f}" y="{height - pad + 16:.1f}" text-anchor="middle" '
                f'font-size="11" fill="#777">{value:g}</text>'
            )
            body.append(
                f'<text x="{pad - 8:.1f}" y="{py(value) + 4:.1f}" text-anchor="end" '
                f'font-size="11" fill="#777">{value:g}</text>'
            )
    for row in rows:
        if row.mean_branching == 0.0:
            body.append(
                f'<circle cx="{px(row.complexity):.1f}" cy="{py(low):.1f}" r="3.5" '
                'fill="none" stroke="#999" stroke-width="1.2">'
                f"<title>seed {row.seed}: died at step 0</title></circle>"
            )
        else:
            body.append(
                f'<circle cx="{px(row.complexity):.1f}" cy="{py(row.mean_branching):.1f}" '
                f'r="4" fill="{SUCCESS_COLOR}" stroke="white" stroke-width="1.5">'
                f"<title>seed {row.seed}: complexity {row.complexity:.3f}, "
                f"branching {row.mean_branching:.3f}, {row.states} states</title></circle>"
            )
    return _svg_document(width, height, body)


def animated_reveal_svg(ev: Evolution, caption: str, node_text: Callable[[int], str]) -> str:
    """The step-by-step reveal as a self-contained CSS-animated SVG.

    Each layer fades in at its own moment and the whole cycle loops, which is
    the animation a printed figure cannot do. Plays anywhere the SVG renders
    as an image, including a GitHub README.
    """
    static = evolution_svg(ev, caption=caption, node_text=node_text)
    layer_of: dict[int, int] = {}
    for index, members in enumerate(ev.layers):
        for node in members:
            layer_of[node] = index
    layer_count = len(ev.layers)
    duration = 0.9 * layer_count + 2.5

    rules = []
    for index in range(layer_count):
        start = 2.0 + index * 78.0 / max(layer_count - 1, 1)
        rules.append(
            f"@keyframes reveal{index} {{ 0%, {start:.1f}% {{ opacity: 0 }} "
            f"{start + 3.0:.1f}%, 93% {{ opacity: 1 }} 100% {{ opacity: 0 }} }}\n"
            f".layer{index} {{ opacity: 0; animation: reveal{index} {duration:.1f}s "
            "linear infinite; }"
        )
    style = "<style>" + "\n".join(rules) + "</style>"

    # Tag every node and edge with its layer class.
    lines = static.split("\n")
    node_ids = list(ev.nodes)
    node_cursor = 0
    edge_cursor = 0
    for i, line in enumerate(lines):
        if line.startswith("<circle"):
            node = node_ids[node_cursor]
            node_cursor += 1
            lines[i] = line.replace("<circle", f'<circle class="layer{layer_of[node]}"', 1)
        elif line.startswith("<line"):
            edge = ev.edges[edge_cursor]
            edge_cursor += 1
            edge_layer = max(layer_of[edge.src], layer_of[edge.dst])
            lines[i] = line.replace("<line", f'<line class="layer{edge_layer}"', 1)
    lines.insert(1, style)
    return "\n".join(lines)


def _figure_rule_diagrams() -> dict[str, str]:
    instructions = instructions_from_wfr(builders.collatz_instructions())
    return {
        "collatz-rule-plot.svg": rule_plot_svg(instructions, 2),
        "collatz-circle-plot.svg": circle_plot_svg(instructions, 2),
    }


def _figure_ensemble() -> dict[str, str]:
    rows = ensemble(150, seed=1)
    caption = "150 random machines: the complexity measure against realized branching"
    return {"ensemble.svg": scatter_svg(rows, caption)}


def _figure_fibonacci_reveal() -> dict[str, str]:
    machine = builders.fibonacci_machine()
    ev = evolve(machine, Config(1, (12,)))
    counts = path_counts(ev)

    def text(node: int) -> str:
        count = counts[node]
        suffix = "?" if isinstance(count, PathCount) else str(count)
        return f"{ev.nodes[node].registers[0]}:{suffix}"

    caption = "Fibonacci recursion, revealed step by step: value k, paths from the root"
    return {"fibonacci-reveal.svg": animated_reveal_svg(ev, caption, text)}


FIGURES["rule-diagrams"] = _figure_rule_diagrams
FIGURES["ensemble"] = _figure_ensemble
FIGURES["fibonacci-reveal"] = _figure_fibonacci_reveal
