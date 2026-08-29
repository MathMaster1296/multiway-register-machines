"""Golden parity tests against Mathematica outputs.

Fixtures under ``tests/golden/`` were extracted from the published definition
notebook of the Wolfram Function Repository resource ``MultiwayRegisterMachine``
(version 1.0.0), which records evaluated example outputs. Normalization is
explicit and minimal:

* ``Evolve``: the WFR result is one frontier list per depth with path
  multiplicity, states as ``{pc, {r...}}``. The tree-mode layers are compared
  exactly, including order and duplicates.
* ``EvolveGraph``: the WFR result is a graph with integer vertices numbered in
  discovery order and edges deduplicated by (src, dst) in first-occurrence
  order. States-mode results are compared after the same (src, dst)
  deduplication; vertex ids must match exactly.
* ``Complexity``: floats compared to within 1e-12.
"""

import json
from pathlib import Path

import pytest

from mrm import Config, complexity, evolve, instructions_from_wfr, machine_from_wfr

GOLDEN = Path(__file__).parent / "golden"


def load(kind: str) -> list:
    cases = []
    for path in sorted(GOLDEN.glob("*.json")):
        data = json.loads(path.read_text())
        assert data["schema"] == "mrm/golden/1"
        if data["function"] == kind:
            cases.append(pytest.param(data, id=path.stem))
    assert cases, f"no golden fixtures for {kind}"
    return cases


def initial(data: dict) -> Config:
    pc, registers = data["init"]
    return Config(pc, tuple(registers))


@pytest.mark.parametrize("data", load("Evolve"))
def test_evolve_matches_wfr_frontiers(data):
    machine = machine_from_wfr(data["program"], data["n_registers"])
    ev = evolve(
        machine,
        initial(data),
        mode="tree",
        max_steps=data["depth"],
        max_states=10**6,
        max_frontier=10**6,
    )
    actual = [[[ev.nodes[n].pc, list(ev.nodes[n].registers)] for n in layer] for layer in ev.layers]
    expected = data["expected_levels"]
    assert actual == expected[: len(actual)]
    # WFR pads exhausted evolutions with empty frontiers; nothing may be lost.
    assert all(level == [] for level in expected[len(actual) :])


@pytest.mark.parametrize("data", load("EvolveGraph"))
def test_states_graph_matches_wfr(data):
    machine = machine_from_wfr(data["program"], data["n_registers"])
    ev = evolve(
        machine,
        initial(data),
        mode="states",
        max_steps=data["depth"],
        max_states=10**6,
        max_frontier=10**6,
    )
    assert len(ev.nodes) == data["expected_vertex_count"]
    assert list(ev.nodes) == list(range(1, data["expected_vertex_count"] + 1))
    assert ev.simple_edges() == [tuple(edge) for edge in data["expected_edges"]]


@pytest.mark.parametrize("data", load("Complexity"))
def test_complexity_matches_wfr(data):
    actual = complexity(instructions_from_wfr(data["program"]))
    assert actual == pytest.approx(data["expected"], abs=1e-12)
