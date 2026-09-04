"""Causal structure: data dependencies along paths."""

import pytest

from mrm import Config, causal_analysis, causal_analysis_to, evolve, shortest_edge_path
from mrm.builders import fibonacci_machine, grid_paths_machine
from mrm.causal import rule_reads, rule_writes
from mrm.machine import Condition, Machine, Rule, Update


def test_grid_path_splits_into_independent_chains():
    # right touches only r1, up only r2: the two families never interact.
    ev = evolve(grid_paths_machine(3, 2), Config(1, (0, 0)))
    terminal = next(iter(ev.terminals))
    analysis = causal_analysis_to(ev, terminal)
    assert len(analysis.events) == 5
    assert analysis.chains == 2
    assert analysis.longest_chain == 3
    rights = {i for i, e in enumerate(analysis.events) if e.rule_id == "right"}
    for a, b in analysis.dependencies:
        assert (a in rights) == (b in rights)


def test_fibonacci_path_is_one_total_chain():
    ev = evolve(fibonacci_machine(), Config(1, (9,)))
    terminal = next(iter(ev.terminals))
    analysis = causal_analysis_to(ev, terminal)
    assert analysis.chains == 1
    assert analysis.longest_chain == len(analysis.events)


def test_dependency_points_to_latest_writer_only():
    # Two writes to r1 in sequence; the reader depends on the second only.
    machine = Machine(
        n_registers=2,
        rules=(
            Rule("w1", 1, (), (Update(1, 1),), 2),
            Rule("w2", 2, (), (Update(1, 1),), 3),
            Rule("read", 3, (Condition(1, ">", 0),), (Update(2, 1),), 4),
        ),
        halt_pcs=frozenset({4}),
    )
    ev = evolve(machine, Config(1, (0, 0)))
    path = shortest_edge_path(ev, 4)
    assert path is not None
    analysis = causal_analysis(machine, path)
    assert analysis.dependencies == ((0, 1), (1, 2))


def test_reads_include_guards_and_update_registers():
    rule = Rule("r", 1, (Condition(2, "%==", 1, 2),), (Update(1, -1),), 1)
    assert rule_reads(rule) == {1, 2}
    assert rule_writes(rule) == {1}


def test_unreachable_target_raises():
    ev = evolve(grid_paths_machine(1, 1), Config(1, (0, 0)))
    with pytest.raises(ValueError, match="not reachable"):
        causal_analysis_to(ev, 999)


def test_shortest_path_edge_cases():
    ev = evolve(grid_paths_machine(1, 1), Config(1, (0, 0)))
    assert shortest_edge_path(ev, 1) == []
    assert shortest_edge_path(ev, 999) is None
