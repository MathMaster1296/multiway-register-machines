"""Ensembles of random machines: does the complexity measure predict growth?

The paper's complexity measure is the geometric mean of per-instruction
branch counts, a static prediction of how fast the evolution tree should
multiply. This module tests that prediction empirically: sample seeded
random machines, run each one, and compare the predicted branching against
the realized per-step growth of the path tree. Everything is deterministic
for a fixed seed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .builders import random_program
from .evolve import evolve
from .machine import Config, complexity, machine_from_wfr


@dataclass(frozen=True)
class EnsembleRow:
    """One sampled machine and its measurements."""

    seed: int
    complexity: float
    mean_branching: float  # geometric mean of tree frontier growth per step
    states: int  # merged states discovered at the depth cap
    steps_alive: int  # tree depth actually reached before dying or the cap


def measure(seed: int, *, length: int = 4, n_registers: int = 2, depth: int = 8) -> EnsembleRow:
    """Measure one random machine."""
    program = random_program(seed, length=length, n_registers=n_registers)
    machine = machine_from_wfr(program, n_registers)
    init = Config(1, (0,) * n_registers)
    tree = evolve(
        machine, init, mode="tree", max_steps=depth, max_states=200_000, max_frontier=100_000
    )
    series = tree.growth_series()
    ratios = [series[i + 1] / series[i] for i in range(len(series) - 1) if series[i + 1] > 0]
    if ratios:
        product = 1.0
        for ratio in ratios:
            product *= ratio
        branching = product ** (1.0 / len(ratios))
    else:
        branching = 0.0
    states = evolve(
        machine, init, mode="states", max_steps=depth, max_states=200_000, max_frontier=100_000
    )
    return EnsembleRow(
        seed=seed,
        complexity=complexity(machine.instructions or ()),
        mean_branching=branching,
        states=len(states.nodes),
        steps_alive=len(series) - 1,
    )


def ensemble(
    count: int, *, seed: int = 1, length: int = 4, n_registers: int = 2, depth: int = 8
) -> list[EnsembleRow]:
    """Measure ``count`` machines seeded ``seed, seed + 1, ...``."""
    return [
        measure(seed + offset, length=length, n_registers=n_registers, depth=depth)
        for offset in range(count)
    ]


def to_csv(rows: list[EnsembleRow]) -> str:
    """The ensemble as CSV text, one row per machine."""
    lines = ["seed,complexity,mean_branching,states,steps_alive"]
    for row in rows:
        lines.append(
            f"{row.seed},{row.complexity:.6f},{row.mean_branching:.6f},"
            f"{row.states},{row.steps_alive}"
        )
    return "\n".join(lines) + "\n"
