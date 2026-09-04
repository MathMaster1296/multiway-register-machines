"""Causal structure of a computation path.

Alongside the states graph (which configurations exist) and the branchial
graph (which coexist), the third classic multiway view asks how the
individual rule applications along a path depend on each other. Here an
event is one rule application, and event ``j`` depends on event ``i`` when
``i`` is the latest earlier event that wrote a register ``j`` reads (its
guard registers plus the registers its updates touch).

Control flow is left out on purpose: every event reads and writes the
program counter, so counting it would make every path a single chain and
say nothing. The data view is the informative one, and it separates the two
reasons multiway branches reconverge. In the grid model the two rules touch
disjoint registers, so any path's events split into two independent chains:
branches merge because the updates commute. In the Fibonacci recursion both
rules read and write the same register, so every path is one total chain:
merging happens only because different histories reach the same value.
"""

from __future__ import annotations

from dataclasses import dataclass

from .evolve import Edge, Evolution
from .machine import Machine, Rule


@dataclass(frozen=True)
class Event:
    """One rule application along a path: step index plus the edge taken."""

    index: int
    rule_id: str
    src: int
    dst: int


@dataclass(frozen=True)
class CausalAnalysis:
    """The data-dependency structure of one path.

    ``dependencies`` lists ``(earlier, later)`` event-index pairs where the
    later event reads a register the earlier one was the last to write.
    ``chains`` counts the connected components of that relation (independent
    lines of work), and ``longest_chain`` is the length, in events, of the
    longest dependency path.
    """

    events: tuple[Event, ...]
    dependencies: tuple[tuple[int, int], ...]
    chains: int
    longest_chain: int


def rule_reads(rule: Rule) -> frozenset[int]:
    """Registers whose values the rule's applicability and effect depend on."""
    return frozenset(c.reg for c in rule.guard) | frozenset(u.reg for u in rule.updates)


def rule_writes(rule: Rule) -> frozenset[int]:
    """Registers the rule changes."""
    return frozenset(u.reg for u in rule.updates)


def causal_analysis(machine: Machine, path: list[Edge]) -> CausalAnalysis:
    """Analyze the data dependencies of one edge path through an evolution."""
    by_id = {rule.id: rule for rule in machine.rules}
    events = tuple(
        Event(index=i, rule_id=e.rule_id, src=e.src, dst=e.dst) for i, e in enumerate(path)
    )
    last_writer: dict[int, int] = {}
    dependencies: list[tuple[int, int]] = []
    for i, event in enumerate(events):
        rule = by_id[event.rule_id]
        sources = {last_writer[reg] for reg in rule_reads(rule) if reg in last_writer}
        dependencies.extend(sorted((src, i) for src in sources))
        for reg in rule_writes(rule):
            last_writer[reg] = i

    # Connected components over events, dependency edges as the relation.
    parent = list(range(len(events)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in dependencies:
        parent[find(a)] = find(b)
    chains = len({find(i) for i in range(len(events))})

    # Longest dependency path, in events, by DP over the (sorted) DAG.
    depth = [1] * len(events)
    for a, b in dependencies:
        depth[b] = max(depth[b], depth[a] + 1)
    longest = max(depth, default=0)

    return CausalAnalysis(
        events=events,
        dependencies=tuple(dependencies),
        chains=chains,
        longest_chain=longest,
    )


def causal_analysis_to(ev: Evolution, target: int) -> CausalAnalysis:
    """Causal analysis of the shortest path from the initial node to ``target``."""
    from .graph import shortest_edge_path

    path = shortest_edge_path(ev, target)
    if path is None:
        raise ValueError(f"node {target} is not reachable from the initial layer")
    return causal_analysis(ev.machine, path)
