"""Absorption analysis, probability tables, and reconvergence."""

from fractions import Fraction

import pytest

from mrm import Config, absorption, evolve, machine_from_wfr, probability_table, reconvergence
from mrm.builders import (
    SIMPLE_MRM,
    collatz_forward_machine,
    fibonacci_machine,
    grid_paths_machine,
)


class TestAbsorption:
    def test_grid_expected_steps_is_path_length(self):
        ev = evolve(grid_paths_machine(2, 2), Config(1, (0, 0)))
        result = absorption(ev)
        assert result.halting_probability == 1
        assert result.never_halting == 0
        assert result.expected_steps == 4
        assert list(result.terminal_probabilities.values()) == [Fraction(1)]

    def test_fibonacci_base_case_split(self):
        ev = evolve(fibonacci_machine(), Config(1, (4,)))
        result = absorption(ev)
        by_value = {ev.nodes[n].registers[0]: p for n, p in result.terminal_probabilities.items()}
        assert by_value == {2: Fraction(3, 4), 1: Fraction(1, 4)}
        assert result.expected_steps == Fraction(3, 2)

    def test_closed_cycle_traps_all_mass(self):
        # dec at zero looping to itself: never terminates, never branches.
        ev = evolve(machine_from_wfr([[1, 1, [2], [1]]], 1), Config(1, (0,)))
        result = absorption(ev)
        assert result.never_halting == 1
        assert result.halting_probability == 0
        assert result.expected_steps is None

    def test_forward_collatz_cycles_at_one(self):
        ev = evolve(collatz_forward_machine(), Config(8, (0, 1)), max_steps=100)
        assert not ev.truncated
        result = absorption(ev)
        assert result.never_halting == 1

    def test_truncated_run_reports_unresolved_mass(self):
        ev = evolve(grid_paths_machine(3, 3), Config(1, (0, 0)), max_steps=2)
        result = absorption(ev)
        assert result.unresolved > 0
        assert result.expected_steps is None


class TestProbabilityTable:
    def test_matches_notebook_mrmproblist(self):
        # MRMProbList[simpleMRM, {1, {0, 0}}, 6] from the research notebook.
        machine = machine_from_wfr(SIMPLE_MRM, 2)
        ev = evolve(machine, Config(1, (0, 0)), mode="tree", max_steps=6)
        table = probability_table(ev, 6, max_value=20)
        assert table is not None
        assert table.pc_probs == (
            Fraction(1, 4),
            Fraction(0),
            Fraction(1, 4),
            Fraction(1, 2),
        )
        assert table.register_tails[0][:3] == (Fraction(3, 4), Fraction(3, 4), Fraction(0))
        assert table.register_tails[1][:3] == (Fraction(1), Fraction(1), Fraction(0))

    def test_requires_tree_mode(self):
        ev = evolve(grid_paths_machine(1, 1), Config(1, (0, 0)))
        with pytest.raises(ValueError, match="tree"):
            probability_table(ev, 1)

    def test_empty_frontier_gives_none(self):
        machine = machine_from_wfr([[1, 0, [5]]], 1)
        ev = evolve(machine, Config(1, (0,)), mode="tree", max_steps=6)
        assert probability_table(ev, 5) is None


class TestReconvergence:
    def test_grid_branches_always_merge(self):
        ev = evolve(grid_paths_machine(2, 2), Config(1, (0, 0)))
        report = reconvergence(ev, within=2)
        assert report.pairs == 4
        assert report.merged == 4
        assert report.fraction == 1

    def test_diverging_branches_reported(self):
        # pc 2 and pc 3 each loop on themselves; the initial branch never merges.
        machine = machine_from_wfr([[1, 0, [2, 3]], [1, 0, [2]], [1, 0, [3]]], 1)
        ev = evolve(machine, Config(1, (0,)), max_steps=6)
        report = reconvergence(ev, within=6)
        assert report.pairs == 1
        assert report.merged == 0
        assert report.unmerged[0][0] == 1


class TestOpenCycle:
    def test_self_loop_with_escape_solves_exactly(self):
        # At r1 = 0 the fail branch goes back to pc 1 or off the end: a
        # self-loop with escape probability 1/2 per visit. Expected visits to
        # the loop state are 2, so the expected step count is exactly 2 and
        # the machine still halts with probability 1.
        machine = machine_from_wfr([[1, 1, [2], [1, 3]]], 1)
        ev = evolve(machine, Config(1, (0,)))
        result = absorption(ev)
        assert result.halting_probability == 1
        assert result.never_halting == 0
        assert result.expected_steps == 2


class TestAbsorptionTimeDistribution:
    def test_fibonacci_matches_hand_computation(self):
        from mrm.analysis import absorption_time_distribution

        ev = evolve(fibonacci_machine(), Config(1, (4,)))
        dist = absorption_time_distribution(ev)
        assert dist.probabilities[:3] == (Fraction(0), Fraction(1, 2), Fraction(1, 2))
        assert dist.tail == 0
        assert dist.mean_within_horizon() == absorption(ev).expected_steps

    def test_grid_absorbs_exactly_at_path_length(self):
        from mrm.analysis import absorption_time_distribution

        ev = evolve(grid_paths_machine(2, 2), Config(1, (0, 0)))
        dist = absorption_time_distribution(ev)
        assert dist.probabilities[4] == Fraction(1)
        assert sum(dist.probabilities) == 1

    def test_closed_cycle_is_all_tail(self):
        from mrm.analysis import absorption_time_distribution

        ev = evolve(machine_from_wfr([[1, 1, [2], [1]]], 1), Config(1, (0,)))
        dist = absorption_time_distribution(ev, horizon=15)
        assert dist.tail == 1
        assert sum(dist.probabilities) == 0

    def test_float_mode_agrees_with_exact(self):
        from mrm.analysis import absorption_time_distribution

        ev = evolve(fibonacci_machine(), Config(1, (10,)))
        exact = absorption_time_distribution(ev)
        loose = absorption_time_distribution(ev, exact=False)
        for a, b in zip(exact.probabilities, loose.probabilities, strict=True):
            assert abs(float(a) - float(b)) < 1e-12
