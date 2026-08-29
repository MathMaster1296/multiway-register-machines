"""Deterministic layered layout for evolution graphs.

Sugiyama-style: nodes are ranked by their BFS layer, ordered within each rank
by a fixed number of median-heuristic sweeps, and placed on a grid with each
rank centered. There is no randomness and no force simulation; the same
evolution always yields byte-identical coordinates, which is what lets the
paper's figures and the web explorer agree pixel for pixel.
"""

from __future__ import annotations

from statistics import median

from .evolve import Evolution, NodeId

PASSES = 4


def layered_layout(
    ev: Evolution, *, x_gap: float = 1.0, y_gap: float = 1.0
) -> dict[NodeId, tuple[float, float]]:
    """Coordinates for every node: layer-ranked, median-ordered, centered."""
    rank: dict[NodeId, int] = {}
    for r, layer in enumerate(ev.layers):
        for node in layer:
            rank[node] = r
    orders: list[list[NodeId]] = [list(layer) for layer in ev.layers]

    parents: dict[NodeId, list[NodeId]] = {n: [] for n in ev.nodes}
    children: dict[NodeId, list[NodeId]] = {n: [] for n in ev.nodes}
    for edge in ev.edges:
        if rank[edge.dst] == rank[edge.src] + 1:
            parents[edge.dst].append(edge.src)
            children[edge.src].append(edge.dst)

    def sweep(target: list[NodeId], reference: list[NodeId], up: bool) -> list[NodeId]:
        position = {n: i for i, n in enumerate(reference)}
        current = {n: i for i, n in enumerate(target)}

        def key(node: NodeId) -> float:
            neighbors = parents[node] if up else children[node]
            spots = [position[p] for p in neighbors if p in position]
            return median(spots) if spots else float(current[node])

        return sorted(target, key=key)  # stable: ties keep current order

    for _ in range(PASSES):
        for r in range(1, len(orders)):
            orders[r] = sweep(orders[r], orders[r - 1], up=True)
        for r in range(len(orders) - 2, -1, -1):
            orders[r] = sweep(orders[r], orders[r + 1], up=False)

    positions: dict[NodeId, tuple[float, float]] = {}
    for r, row in enumerate(orders):
        offset = (len(row) - 1) / 2
        for i, node in enumerate(row):
            positions[node] = ((i - offset) * x_gap, r * y_gap)
    return positions
