"""Path counting, cycle detection, and strongly connected components.

Path counts respect edge multiplicity: two rules producing the same successor
contribute two paths, exactly as the tree-mode evolution would duplicate the
node. On cyclic graphs a count is not a number; affected nodes get the
explicit `PathCount.INFINITE` sentinel and `cycle_witness` names a cycle.
"""

from __future__ import annotations

from enum import Enum

from .evolve import Evolution, NodeId


class PathCount(Enum):
    """Sentinel for nodes whose path count diverges through a cycle."""

    INFINITE = "infinite"


def successor_lists(ev: Evolution) -> dict[NodeId, list[NodeId]]:
    """Successors with multiplicity, in edge discovery order."""
    succ: dict[NodeId, list[NodeId]] = {n: [] for n in ev.nodes}
    for edge in ev.edges:
        succ[edge.src].append(edge.dst)
    return succ


def strongly_connected_components(
    order: list[NodeId], succ: dict[NodeId, list[NodeId]]
) -> list[list[NodeId]]:
    """Tarjan's algorithm, iterative. Components come out in reverse
    topological order of the condensation; node order inside a component is
    completion order. Deterministic for a fixed ``order`` and ``succ``."""
    index: dict[NodeId, int] = {}
    low: dict[NodeId, int] = {}
    onstack: set[NodeId] = set()
    stack: list[NodeId] = []
    components: list[list[NodeId]] = []
    counter = 0
    for root in order:
        if root in index:
            continue
        work: list[tuple[NodeId, int]] = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                onstack.add(v)
            descended = False
            succs = succ.get(v, [])
            while i < len(succs):
                w = succs[i]
                i += 1
                if w not in index:
                    work.append((v, i))
                    work.append((w, 0))
                    descended = True
                    break
                if w in onstack and index[w] < low[v]:
                    low[v] = index[w]
            if descended:
                continue
            if low[v] == index[v]:
                component: list[NodeId] = []
                while True:
                    w = stack.pop()
                    onstack.discard(w)
                    component.append(w)
                    if w == v:
                        break
                components.append(component)
            if work:
                parent = work[-1][0]
                if low[v] < low[parent]:
                    low[parent] = low[v]
    return components


def _is_cyclic(component: list[NodeId], succ: dict[NodeId, list[NodeId]]) -> bool:
    if len(component) > 1:
        return True
    v = component[0]
    return v in succ.get(v, [])


def path_counts(ev: Evolution) -> dict[NodeId, int | PathCount]:
    """Distinct directed paths from the initial configuration(s) to each node.

    A node lying on, or downstream of, a cycle gets `PathCount.INFINITE`.
    Initial nodes count the empty path; in tree mode every node's count is 1.
    """
    succ = successor_lists(ev)
    order = list(ev.nodes)
    components = strongly_connected_components(order, succ)
    counts: dict[NodeId, int] = dict.fromkeys(ev.nodes, 0)
    infinite: set[NodeId] = set()
    for node in ev.layers[0] if ev.layers else []:
        counts[node] += 1
    for component in reversed(components):  # topological order
        if _is_cyclic(component, succ) or any(m in infinite for m in component):
            infinite.update(component)
        for member in component:
            if member in infinite:
                for w in succ[member]:
                    infinite.add(w)
            else:
                for w in succ[member]:
                    counts[w] += counts[member]
    return {n: PathCount.INFINITE if n in infinite else counts[n] for n in ev.nodes}


def terminal_path_counts(ev: Evolution) -> dict[NodeId, int | PathCount]:
    """Path counts restricted to the terminal nodes."""
    all_counts = path_counts(ev)
    return {n: all_counts[n] for n in ev.terminals}


def cycle_witness(ev: Evolution) -> list[NodeId] | None:
    """One directed cycle (as a node list) if the explored graph has any."""
    succ = successor_lists(ev)
    for component in reversed(strongly_connected_components(list(ev.nodes), succ)):
        if not _is_cyclic(component, succ):
            continue
        members = set(component)
        start = component[0]
        # Walk inside the component until a node repeats, then cut the loop.
        trail: list[NodeId] = [start]
        positions = {start: 0}
        v = start
        while True:
            v = next(w for w in succ[v] if w in members)
            if v in positions:
                return trail[positions[v] :]
            positions[v] = len(trail)
            trail.append(v)
    return None
