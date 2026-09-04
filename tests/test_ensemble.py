"""Random machine ensembles are deterministic and sensible."""

from mrm.builders import random_program
from mrm.ensemble import ensemble, to_csv
from mrm.machine import machine_from_wfr


def test_random_program_is_seed_deterministic_and_valid():
    a = random_program(7, length=5, n_registers=3)
    assert a == random_program(7, length=5, n_registers=3)
    assert a != random_program(8, length=5, n_registers=3)
    machine = machine_from_wfr(a, 3)
    assert not machine.validate()


def test_ensemble_rows_are_reproducible():
    first = ensemble(6, seed=3, depth=5)
    second = ensemble(6, seed=3, depth=5)
    assert first == second
    assert [row.seed for row in first] == [3, 4, 5, 6, 7, 8]
    assert all(row.complexity > 0 for row in first)
    assert all(row.mean_branching >= 0 for row in first)


def test_csv_shape():
    text = to_csv(ensemble(3, seed=1, depth=4))
    lines = text.strip().split("\n")
    assert lines[0] == "seed,complexity,mean_branching,states,steps_alive"
    assert len(lines) == 4
