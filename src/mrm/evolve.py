"""Breadth-first multiway evolution in two modes.

``states`` mode canonicalizes configurations and merges repeats into a single
node, giving a general directed graph (possibly cyclic). Node ids are assigned
in discovery order starting from 1, matching the WFR ``EvolveGraph`` id
assignment exactly. ``tree`` mode never merges: every path gets its own node,
and the configurations of layer ``t`` in creation order equal the WFR
``Evolve`` frontier list at depth ``t``, including duplicates.

Everything is deterministic: iteration only ever walks lists and
insertion-ordered dicts.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Literal, NamedTuple

from .machine import Config, Machine

NodeId = int

EvolutionMode = Literal["states", "tree"]


class TerminalKind(Enum):
    """Why a node has no outgoing edges."""

    HALT = "halt"  # pc is a declared halt pc
    STUCK = "stuck"  # no rule is applicable
    CUTOFF = "cutoff"  # rules were applicable but a cap stopped exploration


class Edge(NamedTuple):
    src: NodeId
    dst: NodeId
    rule_id: str


class _Truncated(Exception):
    def __init__(self, reason: str):
        self.reason = reason


@dataclass
class Evolution:
    """The result of `evolve`. See the module docstring for mode semantics."""

    machine: Machine
    mode: EvolutionMode
    nodes: dict[NodeId, Config]
    edges: list[Edge]
    layers: list[list[NodeId]]
    terminals: dict[NodeId, TerminalKind]
    truncated: bool
    truncation_reason: str | None
    max_steps: int
    max_states: int
    max_frontier: int

    def growth_series(self) -> list[int]:
        """``|layer[t]|`` for each step ``t``."""
        return [len(layer) for layer in self.layers]

    def simple_edges(self) -> list[tuple[NodeId, NodeId]]:
        """Edges collapsed to ``(src, dst)`` pairs, first occurrence order.

        This is the edge set the WFR ``EvolveGraph`` reports; the full
        ``edges`` list additionally keeps one labeled edge per rule.
        """
        seen: set[tuple[NodeId, NodeId]] = set()
        out: list[tuple[NodeId, NodeId]] = []
        for edge in self.edges:
            pair = (edge.src, edge.dst)
            if pair not in seen:
                seen.add(pair)
                out.append(pair)
        return out


class _Run:
    """Shared bookkeeping for one evolution run."""

    def __init__(self, machine: Machine, max_states: int):
        self.machine = machine
        self.max_states = max_states
        self.nodes: dict[NodeId, Config] = {}
        self.edges: list[Edge] = []
        self.layers: list[list[NodeId]] = []

    def new_node(self, config: Config) -> NodeId:
        if len(self.nodes) >= self.max_states:
            raise _Truncated("max_states")
        node_id = len(self.nodes) + 1
        self.nodes[node_id] = config
        return node_id


def evolve(
    machine: Machine,
    initial: Config | Iterable[Config],
    *,
    mode: EvolutionMode = "states",
    max_steps: int = 100,
    max_states: int = 100_000,
    max_frontier: int = 20_000,
) -> Evolution:
    """Evolve ``machine`` from ``initial`` for at most ``max_steps`` steps.

    Any cap that fires sets ``truncated`` and names itself in
    ``truncation_reason``; ``max_steps`` only counts as a truncation when
    unexplored non-terminal configurations remain.
    """
    problems = machine.validate()
    if problems:
        raise ValueError("invalid machine: " + "; ".join(problems))
    if mode not in ("states", "tree"):
        raise ValueError(f"mode must be 'states' or 'tree', got {mode!r}")
    initials = [initial] if isinstance(initial, Config) else list(initial)
    if not initials:
        raise ValueError("at least one initial configuration is required")
    for config in initials:
        if config.pc < 1:
            raise ValueError(f"initial pc must be >= 1, got {config.pc}")
        if len(config.registers) != machine.n_registers:
            raise ValueError(
                f"initial configuration has {len(config.registers)} registers,"
                f" machine has {machine.n_registers}"
            )
        if any(r < 0 for r in config.registers):
            raise ValueError("registers must be non-negative")
    for cap_name, cap in (
        ("max_steps", max_steps),
        ("max_states", max_states),
        ("max_frontier", max_frontier),
    ):
        if cap < 0 or (cap_name != "max_steps" and cap < 1):
            raise ValueError(f"{cap_name} must be positive, got {cap}")

    run = _Run(machine, max_states)
    truncation_reason: str | None = None
    ids: dict[Config, NodeId] = {}

    try:
        layer0: list[NodeId] = []
        for config in initials:
            if mode == "states":
                if config in ids:
                    continue
                ids[config] = run.new_node(config)
                layer0.append(ids[config])
            else:
                layer0.append(run.new_node(config))
        run.layers.append(layer0)

        frontier = layer0
        for _ in range(max_steps):
            if not frontier:
                break
            next_frontier: list[NodeId] = []
            for node_id in frontier:
                for rule, successor in machine.step(run.nodes[node_id]):
                    if mode == "states":
                        known = ids.get(successor)
                        if known is None:
                            known = run.new_node(successor)
                            ids[successor] = known
                            next_frontier.append(known)
                        run.edges.append(Edge(node_id, known, rule.id))
                    else:
                        child = run.new_node(successor)
                        run.edges.append(Edge(node_id, child, rule.id))
                        next_frontier.append(child)
            if next_frontier:
                run.layers.append(next_frontier)
                if len(next_frontier) > max_frontier:
                    raise _Truncated("max_frontier")
            frontier = next_frontier
    except _Truncated as t:
        truncation_reason = t.reason

    has_outgoing = {edge.src for edge in run.edges}
    terminals: dict[NodeId, TerminalKind] = {}
    for node_id, config in run.nodes.items():
        if node_id in has_outgoing:
            continue
        if config.pc in machine.halt_pcs:
            terminals[node_id] = TerminalKind.HALT
        elif not machine.applicable(config):
            terminals[node_id] = TerminalKind.STUCK
        else:
            terminals[node_id] = TerminalKind.CUTOFF

    if truncation_reason is None and any(
        kind is TerminalKind.CUTOFF for kind in terminals.values()
    ):
        truncation_reason = "max_steps"

    return Evolution(
        machine=machine,
        mode=mode,
        nodes=run.nodes,
        edges=run.edges,
        layers=run.layers,
        terminals=terminals,
        truncated=truncation_reason is not None,
        truncation_reason=truncation_reason,
        max_steps=max_steps,
        max_states=max_states,
        max_frontier=max_frontier,
    )
