"""Tier-3 property tests over random machines."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from mrm import Config, evolve, layered_layout, machine_from_wfr
from mrm.serialize import dumps, evolution_from_json, evolution_to_json

N_REGISTERS = 2
MAX_PC = 6


@st.composite
def machines(draw):
    length = draw(st.integers(1, 4))
    program = []
    targets = st.lists(st.integers(1, MAX_PC), max_size=3)
    for _ in range(length):
        reg = draw(st.integers(1, N_REGISTERS))
        if draw(st.booleans()):
            program.append([reg, 0, draw(targets)])
        else:
            program.append([reg, 1, draw(targets), draw(targets)])
    return machine_from_wfr(program, N_REGISTERS)


def both_modes(machine):
    init = Config(1, (0, 0))
    caps = {"max_steps": 5, "max_states": 5000, "max_frontier": 5000}
    return (
        evolve(machine, init, mode="states", **caps),
        evolve(machine, init, mode="tree", **caps),
    )


@settings(max_examples=60, deadline=None)
@given(machines())
def test_states_mode_never_exceeds_tree_mode(machine):
    states, tree = both_modes(machine)
    assert len(states.nodes) <= len(tree.nodes)
    assert len(states.edges) <= len(tree.edges)


@settings(max_examples=60, deadline=None)
@given(machines())
def test_every_edge_is_a_legal_step(machine):
    states, tree = both_modes(machine)
    for ev in (states, tree):
        for edge in ev.edges:
            successors = [(rule.id, config) for rule, config in machine.step(ev.nodes[edge.src])]
            assert (edge.rule_id, ev.nodes[edge.dst]) in successors


@settings(max_examples=60, deadline=None)
@given(machines())
def test_layers_agree_with_bfs_depth(machine):
    states, _ = both_modes(machine)
    depth = {n: r for r, layer in enumerate(states.layers) for n in layer}
    assert set(depth) == set(states.nodes)
    reached = {n: None for n in states.layers[0]}
    frontier = list(states.layers[0])
    level = 0
    while frontier:
        level += 1
        nxt = []
        for src, dst, _rule in states.edges:
            if src in dict.fromkeys(frontier) and dst not in reached:
                reached[dst] = None
                nxt.append(dst)
                assert depth[dst] == level
        frontier = nxt


@settings(max_examples=40, deadline=None)
@given(machines())
def test_evolution_json_round_trips(machine):
    states, _ = both_modes(machine)
    data = evolution_to_json(states)
    rebuilt = evolution_from_json(json.loads(dumps(data)))
    assert evolution_to_json(rebuilt) == data


@settings(max_examples=40, deadline=None)
@given(machines())
def test_layout_is_deterministic_and_complete(machine):
    states, _ = both_modes(machine)
    first = layered_layout(states)
    assert first == layered_layout(states)
    assert set(first) == set(states.nodes)
