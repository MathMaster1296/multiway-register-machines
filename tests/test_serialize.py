"""Round trips for both JSON schemas and hash stability."""

import json

import pytest

from mrm import Config, evolve
from mrm.presets import available_presets, load_preset
from mrm.serialize import (
    MachineDocument,
    dumps,
    evolution_from_json,
    evolution_to_json,
    machine_from_json,
    machine_hash,
    machine_to_json,
)


@pytest.mark.parametrize("name", available_presets())
def test_machine_round_trip(name):
    doc = load_preset(name)
    data = machine_to_json(doc)
    again = machine_from_json(json.loads(dumps(data)))
    assert again.machine == doc.machine
    assert again.machine.instructions == doc.machine.instructions
    assert (again.name, again.description, again.initial) == (
        doc.name,
        doc.description,
        doc.initial,
    )
    assert machine_to_json(again) == data


@pytest.mark.parametrize("name", ["grid_paths", "simple", "collatz_forward"])
def test_evolution_round_trip(name):
    doc = load_preset(name)
    assert doc.initial is not None
    ev = evolve(doc.machine, doc.initial, max_steps=8)
    data = evolution_to_json(ev)
    rebuilt = evolution_from_json(json.loads(dumps(data)))
    assert evolution_to_json(rebuilt) == data


def test_machine_hash_ignores_metadata_but_not_rules():
    a = load_preset("grid_paths")
    renamed = MachineDocument(a.machine, name="other", initial=Config(1, (0, 0)))
    assert machine_hash(renamed.machine) == machine_hash(a.machine)
    b = load_preset("fibonacci")
    assert machine_hash(a.machine) != machine_hash(b.machine)


def test_schema_field_is_checked():
    with pytest.raises(ValueError, match="schema"):
        machine_from_json({"schema": "mrm/machine/999"})
    with pytest.raises(ValueError, match="schema"):
        evolution_from_json({"schema": "nope"})
