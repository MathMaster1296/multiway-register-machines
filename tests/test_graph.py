"""Graph derivations: states graph, branchial graph, reachability."""

from mrm import Config, ancestors, descendants, evolve, machine_from_wfr, states_graph
from mrm.builders import grid_paths_machine
from mrm.graph import branchial_graph

BRANCHING = [[1, 0, [2, 3]], [2, 0, [3]], [1, 1, [1], [2]]]


def grid22():
    return evolve(grid_paths_machine(2, 2), Config(1, (0, 0)))


def test_branchial_edges_require_shared_parent():
    ev = grid22()
    layer1 = branchial_graph(ev, 1)
    assert layer1.nodes == (2, 3)
    assert layer1.edges == ((2, 3, None),)
    layer2 = branchial_graph(ev, 2)
    # (2,0)-(1,1) share parent 2; (1,1)-(0,2) share parent 3; corners do not.
    assert layer2.edges == ((4, 5, None), (5, 6, None))


def test_branchial_step_zero_has_no_edges():
    ev = grid22()
    assert branchial_graph(ev, 0).edges == ()


def test_states_graph_from_tree_matches_states_run():
    machine = machine_from_wfr(BRANCHING, 2)
    tree = evolve(machine, Config(1, (0, 0)), mode="tree", max_steps=5)
    states = evolve(machine, Config(1, (0, 0)), mode="states", max_steps=5)
    merged = states_graph(tree)
    direct = states_graph(states)
    assert merged.nodes == direct.nodes
    assert set(merged.edges) == set(direct.edges)


def test_ancestors_and_descendants():
    ev = grid22()
    # node 5 is (1,1): reachable from the three corner-side nodes, and it
    # reaches the two remaining interior nodes plus the terminal.
    assert ancestors(ev, 5) == {1, 2, 3}
    assert descendants(ev, 5) == {7, 8, 9}


def test_cycle_makes_node_its_own_ancestor():
    machine = machine_from_wfr(BRANCHING, 2)
    ev = evolve(machine, Config(1, (0, 0)), mode="states", max_steps=4)
    assert 1 in ancestors(ev, 1)
    assert 1 in descendants(ev, 1)
