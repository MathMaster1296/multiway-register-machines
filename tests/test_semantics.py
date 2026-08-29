"""Tier-1 semantics tests: hand-computed successors and boundary cases."""

import pytest

from mrm import (
    Condition,
    Config,
    Machine,
    Rule,
    TerminalKind,
    Update,
    complexity,
    evolve,
    instructions_from_wfr,
    machine_from_wfr,
)

# The three-instruction example machine from the WFR documentation:
# 1: inc r1 -> {2, 3};  2: inc r2 -> {3};  3: dec r1 -> {1} else -> {2}
BRANCHING = [[1, 0, [2, 3]], [2, 0, [3]], [1, 1, [1], [2]]]


def successors(prog, config, n_registers=2):
    machine = machine_from_wfr(prog, n_registers)
    return [(rule.id, succ.pc, succ.registers) for rule, succ in machine.step(config)]


class TestStep:
    def test_increment_branches_in_listed_order(self):
        assert successors(BRANCHING, Config(1, (0, 0))) == [
            ("i1s1", 2, (1, 0)),
            ("i1s2", 3, (1, 0)),
        ]

    def test_single_target_increment(self):
        assert successors(BRANCHING, Config(2, (1, 0))) == [("i2s1", 3, (1, 1))]

    def test_decrement_when_positive(self):
        assert successors(BRANCHING, Config(3, (2, 5))) == [("i3s1", 1, (1, 5))]

    def test_decrement_at_zero_takes_fail_branch_unchanged(self):
        assert successors(BRANCHING, Config(3, (0, 5))) == [("i3f1", 2, (0, 5))]

    def test_decrement_at_zero_with_multiple_fail_targets(self):
        prog = [[1, 1, [1], [2, 3]]]
        assert successors(prog, Config(1, (0, 0))) == [
            ("i1f1", 2, (0, 0)),
            ("i1f2", 3, (0, 0)),
        ]

    def test_decrement_at_zero_with_empty_fail_branch_is_stuck(self):
        prog = [[1, 1, [1], []]]
        assert successors(prog, Config(1, (0, 0))) == []

    def test_pc_past_program_end_has_no_successors(self):
        machine = machine_from_wfr(BRANCHING, 2)
        assert machine.step(Config(4, (1, 1))) == []

    def test_duplicate_targets_give_duplicate_successors(self):
        prog = [[1, 0, [2, 2]]]
        assert successors(prog, Config(1, (0, 0))) == [
            ("i1s1", 2, (1, 0)),
            ("i1s2", 2, (1, 0)),
        ]


class TestGeneralRules:
    def test_modular_guard_selects_branch(self):
        machine = Machine(
            n_registers=1,
            rules=(
                Rule("even", 1, (Condition(1, "%==", 0, 2),), (), 2),
                Rule("odd", 1, (Condition(1, "%==", 1, 2),), (), 3),
            ),
        )
        assert [r.id for r in machine.applicable(Config(1, (4,)))] == ["even"]
        assert [r.id for r in machine.applicable(Config(1, (7,)))] == ["odd"]

    def test_guard_is_a_conjunction(self):
        rule = Rule("r", 1, (Condition(1, ">", 0), Condition(1, "<", 3)), (), 2)
        machine = Machine(n_registers=1, rules=(rule,))
        assert machine.applicable(Config(1, (2,))) != []
        assert machine.applicable(Config(1, (3,))) == []
        assert machine.applicable(Config(1, (0,))) == []

    def test_update_that_would_go_negative_disables_rule(self):
        machine = Machine(n_registers=1, rules=(Rule("d2", 1, (), (Update(1, -2),), 1),))
        assert machine.applicable(Config(1, (1,))) == []
        assert machine.step(Config(1, (2,))) == [(machine.rules[0], Config(1, (0,)))]

    def test_updates_apply_in_order_and_may_not_dip_negative(self):
        # r := r - 2 then r := r + 3 is rejected at r == 1 even though the
        # net change would be non-negative.
        machine = Machine(
            n_registers=1, rules=(Rule("dip", 1, (), (Update(1, -2), Update(1, 3)), 1),)
        )
        assert machine.applicable(Config(1, (1,))) == []
        assert machine.applicable(Config(1, (2,))) != []


class TestEvolve:
    def test_states_mode_merges_and_assigns_ids_in_discovery_order(self):
        machine = machine_from_wfr(BRANCHING, 2)
        ev = evolve(machine, Config(1, (0, 0)), mode="states", max_steps=5)
        assert ev.nodes[1] == Config(1, (0, 0))
        assert len(ev.nodes) == 7
        assert ev.simple_edges() == [
            (1, 2),
            (1, 3),
            (2, 4),
            (3, 1),
            (4, 5),
            (5, 6),
            (5, 4),
            (6, 7),
        ]

    def test_tree_mode_never_merges(self):
        machine = machine_from_wfr(BRANCHING, 2)
        states = evolve(machine, Config(1, (0, 0)), mode="states", max_steps=6)
        tree = evolve(machine, Config(1, (0, 0)), mode="tree", max_steps=6)
        assert len(states.nodes) < len(tree.nodes)
        # Every tree layer lists path-multiplicity copies.
        assert [tree.nodes[n] for n in tree.layers[2]] == [
            Config(3, (1, 1)),
            Config(1, (0, 0)),
        ]

    def test_self_loop_produces_edge_and_finite_states_graph(self):
        # dec at zero jumping to itself: 1 -> 1 with unchanged registers.
        machine = machine_from_wfr([[1, 1, [2], [1]]], 1)
        ev = evolve(machine, Config(1, (0,)), mode="states", max_steps=10)
        assert len(ev.nodes) == 1
        assert ev.simple_edges() == [(1, 1)]
        assert not ev.truncated
        assert ev.terminals == {}

    def test_halt_versus_stuck_classification(self):
        # instruction 1 jumps past the end (halt); a dec at zero with no fail
        # branch is stuck.
        machine = machine_from_wfr([[1, 0, [3]], [1, 0, [1]]], 1)
        ev = evolve(machine, Config(1, (0,)), mode="states")
        assert ev.terminals == {2: TerminalKind.HALT}
        stuck = machine_from_wfr([[1, 1, [1], []]], 1)
        ev = evolve(stuck, Config(1, (0,)), mode="states")
        assert ev.terminals == {1: TerminalKind.STUCK}
        assert not ev.truncated

    def test_layers_match_bfs_depth(self):
        machine = machine_from_wfr(BRANCHING, 2)
        ev = evolve(machine, Config(1, (0, 0)), mode="states", max_steps=5)
        assert ev.layers[0] == [1]
        assert ev.layers[1] == [2, 3]
        # layer 4 discovers only (2,(1,1)); the other successor (3,(1,1))
        # was already reached at layer 2 via instruction 2.
        assert ev.growth_series() == [1, 2, 1, 1, 1, 1]

    def test_multiple_initial_configurations(self):
        machine = machine_from_wfr(BRANCHING, 2)
        ev = evolve(
            machine,
            [Config(1, (0, 0)), Config(2, (0, 0)), Config(1, (0, 0))],
            mode="states",
            max_steps=0,
        )
        # canonical duplicates merge in states mode
        assert ev.layers[0] == [1, 2]

    def test_max_states_cap(self):
        machine = machine_from_wfr(BRANCHING, 2)
        ev = evolve(machine, Config(1, (0, 0)), mode="tree", max_steps=50, max_states=10)
        assert ev.truncated
        assert ev.truncation_reason == "max_states"
        assert len(ev.nodes) == 10

    def test_max_steps_cap_reported_only_when_work_remains(self):
        machine = machine_from_wfr(BRANCHING, 2)
        ev = evolve(machine, Config(1, (0, 0)), mode="tree", max_steps=2)
        assert ev.truncated
        assert ev.truncation_reason == "max_steps"
        assert TerminalKind.CUTOFF in ev.terminals.values()
        # A machine that finishes before the cap is complete, not truncated.
        halting = machine_from_wfr([[1, 0, [2]], [1, 0, [5]]], 1)
        ev = evolve(halting, Config(1, (0,)), mode="tree", max_steps=99)
        assert not ev.truncated
        assert ev.terminals == {3: TerminalKind.HALT}

    def test_max_frontier_cap(self):
        machine = machine_from_wfr(BRANCHING, 2)
        ev = evolve(machine, Config(1, (0, 0)), mode="tree", max_steps=50, max_frontier=1)
        assert ev.truncated
        assert ev.truncation_reason == "max_frontier"
        assert len(ev.layers) == 2

    def test_rejects_wrong_register_count(self):
        machine = machine_from_wfr(BRANCHING, 2)
        with pytest.raises(ValueError, match="registers"):
            evolve(machine, Config(1, (0, 0, 0)))


class TestValidationAndParsing:
    def test_flag_and_arity_mismatch_rejected(self):
        with pytest.raises(ValueError, match="does not match"):
            instructions_from_wfr([[1, 1, [2]]])
        with pytest.raises(ValueError, match="does not match"):
            instructions_from_wfr([[1, 0, [2], [3]]])

    def test_bad_flag_rejected(self):
        with pytest.raises(ValueError, match="flag"):
            instructions_from_wfr([[1, 2, [2]]])

    def test_nonpositive_jump_target_rejected(self):
        with pytest.raises(ValueError, match=">= 1"):
            instructions_from_wfr([[1, 0, [0]]])

    def test_validate_reports_out_of_range_registers(self):
        machine = Machine(
            n_registers=1, rules=(Rule("r", 1, (Condition(2, ">", 0),), (Update(3, 1),), 1),)
        )
        problems = machine.validate()
        assert any("r2" in p for p in problems)
        assert any("r3" in p for p in problems)

    def test_validate_reports_duplicate_rule_ids(self):
        rule = Rule("r", 1, (), (), 1)
        machine = Machine(n_registers=1, rules=(rule, Rule("r", 2, (), (), 1)))
        assert any("duplicate" in p for p in machine.validate())

    def test_validate_reports_bad_modular_condition(self):
        machine = Machine(n_registers=1, rules=(Rule("r", 1, (Condition(1, "%==", 5, 3),), (), 1),))
        assert any("residue" in p for p in machine.validate())

    def test_evolve_refuses_invalid_machine(self):
        machine = Machine(n_registers=0, rules=())
        with pytest.raises(ValueError, match="invalid machine"):
            evolve(machine, Config(1, ()))


class TestComplexity:
    def test_matches_wfr_formula(self):
        assert complexity(instructions_from_wfr(BRANCHING)) == pytest.approx(
            2 ** (1 / 3), abs=1e-15
        )

    def test_deterministic_machine_has_complexity_one(self):
        prog = [[1, 0, [2]], [1, 1, [1], [3]]]
        assert complexity(instructions_from_wfr(prog)) == 1.0


class TestSmallEdgeCases:
    def test_complexity_of_empty_program_is_an_error(self):
        with pytest.raises(ValueError, match="empty"):
            complexity(())

    def test_machine_needs_at_least_one_instruction(self):
        from mrm import machine_from_instructions

        with pytest.raises(ValueError, match="at least one"):
            machine_from_instructions(())

    def test_instruction_rejects_bad_register_and_inc_fail_branch(self):
        from mrm import Instruction

        with pytest.raises(ValueError, match=">= 1"):
            Instruction(0, "inc", (1,))
        with pytest.raises(ValueError, match="fail branch"):
            Instruction(1, "inc", (1,), (2,))

    def test_modular_condition_requires_modulus_at_evaluation(self):
        with pytest.raises(ValueError, match="modulus"):
            Condition(1, "%==", 1).holds((3,))

    def test_halt_pc_with_rules_is_reported(self):
        machine = Machine(
            n_registers=1,
            rules=(Rule("r", 2, (), (), 1),),
            halt_pcs=frozenset({2}),
        )
        assert any("halt pc" in p for p in machine.validate())

    def test_evolution_methods_delegate(self):
        ev = evolve(machine_from_wfr([[1, 0, [2]], [1, 0, [4]]], 1), Config(1, (0,)))
        assert ev.states_graph().nodes == (1, 2, 3)
        assert ev.branchial_graph(1).nodes == (2,)
        assert ev.path_counts()[3] == 1
        assert ev.to_json()["schema"] == "mrm/evolution/1"
