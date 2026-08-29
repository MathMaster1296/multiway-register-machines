"""Tier-2 invariants: every closed-form check the models ship with."""

import time

import pytest

from mrm import Config, evolve
from mrm.builders import fibonacci_machine
from mrm.verification import run_all_checks


@pytest.fixture(scope="module")
def checks():
    return run_all_checks()


@pytest.mark.parametrize(
    "model",
    [
        "grid-paths",
        "fibonacci",
        "collatz-forward",
        "collatz-reverse",
        "fibonacci-paper",
        "polynomial-paper",
    ],
)
def test_model_invariants(checks, model):
    relevant = [c for c in checks if c.model == model]
    assert relevant, f"no checks ran for {model}"
    failures = [c for c in relevant if not c.ok]
    assert not failures, failures


def test_fibonacci_states_mode_performance_budget():
    start = time.perf_counter()
    ev = evolve(fibonacci_machine(), Config(1, (25,)))
    elapsed = time.perf_counter() - start
    assert len(ev.nodes) == 25
    assert elapsed < 2.0
