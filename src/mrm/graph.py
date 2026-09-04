"""Derived graph structures over an evolution result.

All functions are pure and deterministic: node order follows discovery order,
edge order follows the evolution's edge list.
"""

from __future__ import annotations

from dataclasses import dataclass

from .evolve import Edge, Evolution, NodeId
from .machine import Config


@dataclass(frozen=True)
class Graph:
    """A small immutable graph: labeled edges, optional direction."""

    directed: bool
    nodes: tuple[NodeId, ...]
    edges: tuple[tuple[NodeId, NodeId, str | None], ...]

    def successors(self) -> dict[NodeId, list[NodeId]]:
        out: dict[NodeId, list[NodeId]] = {n: [] for n in self.nodes}
        for src, dst, _ in self.edges:
            out[src].append(dst)
            if not self.directed:
                out[dst].append(src)
        return out


def canonical_ids(ev: Evolution) -> tuple[dict[NodeId, NodeId], dict[NodeId, Config]]:
    """Map evolution node ids to canonical (merged) ids.

    For a states-mode evolution this is the identity. For a tree-mode
    evolution, nodes with equal configurations merge; canonical ids are
    assigned in first-appearance order, so they match what a states-mode run
    would have produced for the explored region.
    """
    mapping: dict[NodeId, NodeId] = {}
    configs: dict[NodeId, Config] = {}
    by_config: dict[Config, NodeId] = {}
    for node_id, config in ev.nodes.items():
        canonical = by_config.get(config)
        if canonical is None:
            canonical = len(by_config) + 1
            by_config[config] = canonical
            configs[canonical] = config
        mapping[node_id] = canonical
    return mapping, configs


def states_graph(ev: Evolution) -> Graph:
    """The multiway states graph: canonical configurations, labeled edges.

    Edge multiplicity is preserved: two rules producing the same successor
    give two edges with different labels. Use `Evolution.simple_edges` (or
    deduplicate the pairs) for the WFR-style collapsed view.
    """
    mapping, configs = canonical_ids(ev)
    seen: set[tuple[NodeId, NodeId, str]] = set()
    edges: list[tuple[NodeId, NodeId, str | None]] = []
    for edge in ev.edges:
        item = (mapping[edge.src], mapping[edge.dst], edge.rule_id)
        if item not in seen:
            seen.add(item)
            edges.append(item)
    return Graph(directed=True, nodes=tuple(configs), edges=tuple(edges))


def branchial_graph(ev: Evolution, step: int) -> Graph:
    """The branchial graph at ``step``.

    Nodes are the evolution nodes in ``layers[step]``; two are connected iff
    they share a parent in ``layers[step - 1]``. Edges are unlabeled and
    reported once, ordered by node position within the layer.
    """
    if not 0 <= step < len(ev.layers):
        raise ValueError(f"step {step} out of range 0..{len(ev.layers) - 1}")
    layer = ev.layers[step]
    if step == 0:
        return Graph(directed=False, nodes=tuple(layer), edges=())
    previous = set(ev.layers[step - 1])
    parents: dict[NodeId, set[NodeId]] = {n: set() for n in layer}
    members = set(layer)
    for src, dst, _ in ev.edges:
        if dst in members and src in previous:
            parents[dst].add(src)
    edges: list[tuple[NodeId, NodeId, str | None]] = []
    for i, a in enumerate(layer):
        for b in layer[i + 1 :]:
            if a != b and parents[a] & parents[b]:
                edges.append((a, b, None))
    return Graph(directed=False, nodes=tuple(layer), edges=tuple(edges))


def ancestors(ev: Evolution, node: NodeId) -> set[NodeId]:
    """All nodes with a directed path to ``node``."""
    incoming: dict[NodeId, list[NodeId]] = {}
    for src, dst, _ in ev.edges:
        incoming.setdefault(dst, []).append(src)
    return _reach(node, incoming)


def descendants(ev: Evolution, node: NodeId) -> set[NodeId]:
    """All nodes reachable from ``node`` by a directed path."""
    outgoing: dict[NodeId, list[NodeId]] = {}
    for src, dst, _ in ev.edges:
        outgoing.setdefault(src, []).append(dst)
    return _reach(node, outgoing)


def _reach(start: NodeId, adjacency: dict[NodeId, list[NodeId]]) -> set[NodeId]:
    # ``start`` itself is included only when a cycle leads back to it.
    seen: set[NodeId] = set()
    frontier = [start]
    while frontier:
        nxt: list[NodeId] = []
        for v in frontier:
            for w in adjacency.get(v, []):
                if w not in seen:
                    seen.add(w)
                    nxt.append(w)
        frontier = nxt
    return seen


def shortest_edge_path(ev: Evolution, target: NodeId) -> list[Edge] | None:
    """One shortest path from the initial layer to ``target``, as edges.

    Ties break toward earlier edges in discovery order, so the result is
    deterministic. An initial node has the empty path; an unreachable node
    gives ``None``.
    """
    roots = ev.layers[0] if ev.layers else []
    if target in roots:
        return []
    outgoing: dict[NodeId, list[Edge]] = {}
    for edge in ev.edges:
        outgoing.setdefault(edge.src, []).append(edge)
    via: dict[NodeId, Edge] = {}
    frontier = list(roots)
    while frontier and target not in via:
        nxt: list[NodeId] = []
        for node in frontier:
            for edge in outgoing.get(node, []):
                if edge.dst not in via and edge.dst not in roots:
                    via[edge.dst] = edge
                    nxt.append(edge.dst)
        frontier = nxt
    if target not in via:
        return None
    path: list[Edge] = []
    node = target
    while node not in roots:
        edge = via[node]
        path.append(edge)
        node = edge.src
    path.reverse()
    return path
