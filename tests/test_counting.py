"""Path counting, multiplicity, and the infinite sentinel."""

from math import comb

from mrm import Config, PathCount, cycle_witness, evolve, machine_from_wfr, path_counts
from mrm.builders import grid_paths_machine
from mrm.counting import terminal_path_counts

BRANCHING = [[1, 0, [2, 3]], [2, 0, [3]], [1, 1, [1], [2]]]


def test_grid_counts_are_binomials_everywhere():
    ev = evolve(grid_paths_machine(2, 2), Config(1, (0, 0)))
    counts = path_counts(ev)
    by_config = {ev.nodes[n].registers: c for n, c in counts.items()}
    for i in range(3):
        for j in range(3):
            assert by_config[(i, j)] == comb(i + j, i)


def test_duplicate_targets_count_as_distinct_paths():
    ev = evolve(machine_from_wfr([[1, 0, [2, 2]]], 1), Config(1, (0,)))
    assert terminal_path_counts(ev) == {2: 2}


def test_tree_mode_counts_are_all_one():
    ev = evolve(machine_from_wfr(BRANCHING, 2), Config(1, (0, 0)), mode="tree", max_steps=4)
    assert set(path_counts(ev).values()) == {1}


def test_cycle_yields_infinite_and_a_witness():
    machine = machine_from_wfr(BRANCHING, 2)
    ev = evolve(machine, Config(1, (0, 0)), mode="states", max_steps=5)
    counts = path_counts(ev)
    # The 1 -> 3 -> 1 cycle makes every explored node infinite.
    assert set(counts.values()) == {PathCount.INFINITE}
    witness = cycle_witness(ev)
    assert witness is not None and set(witness) == {1, 3}
    pairs = {(e.src, e.dst) for e in ev.edges}
    for a, b in zip(witness, witness[1:] + witness[:1], strict=True):
        assert (a, b) in pairs


def test_acyclic_graph_has_no_witness():
    ev = evolve(grid_paths_machine(2, 2), Config(1, (0, 0)))
    assert cycle_witness(ev) is None
