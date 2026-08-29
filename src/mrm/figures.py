"""Reproducible figure generation, no plotting library required.

Figures are written as hand-assembled SVG from the deterministic layout, so
regenerating them always produces identical bytes. The registry maps figure
names to builders; ``mrm figure NAME --out DIR`` and scripts/make_figures.py
both go through it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import builders
from .counting import PathCount, path_counts
from .evolve import Evolution, evolve
from .layout import layered_layout
from .machine import Config, machine_from_wfr

SCALE = 72.0
NODE_RADIUS = 16.0
MARGIN = 48.0


def _svg_document(width: float, height: float, body: list[str]) -> str:
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        'font-family="Helvetica, Arial, sans-serif">'
    )
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
    return _svg_document(width, height, body)


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
