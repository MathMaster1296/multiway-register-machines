"""The invariant suite behind ``mrm verify``.

Every check compares an engine result against an independent closed form:
binomial coefficients for grid paths, Fibonacci numbers for the recursion
model, the arithmetic Collatz map for both Collatz models, and the research
notebook's recorded values for the paper's machines. All checks are exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb

from . import builders
from .counting import terminal_path_counts
from .evolve import evolve
from .machine import Config, machine_from_wfr


@dataclass(frozen=True)
class Check:
    model: str
    parameter: str
    expected: str
    actual: str
    ok: bool


def _fib(k: int) -> int:
    a, b = 1, 1
    for _ in range(k - 1):
        a, b = b, a + b
    return a


def _collatz_reference(n: int) -> list[int]:
    values = [n]
    while values[-1] != 1:
        v = values[-1]
        values.append(3 * v + 1 if v % 2 else v // 2)
    return values


def _grid_checks() -> list[Check]:
    checks = []
    for m in range(9):
        for n in range(9):
            ev = evolve(builders.grid_paths_machine(m, n), Config(1, (0, 0)))
            counts = terminal_path_counts(ev)
            actual = counts.get(next(iter(counts), -1), 0) if counts else 0
            expected = comb(m + n, m)
            checks.append(
                Check(
                    "grid-paths",
                    f"m={m}, n={n}",
                    f"paths = {expected}",
                    f"paths = {actual}",
                    actual == expected and len(counts) == 1,
                )
            )
    return checks


def _fibonacci_checks() -> list[Check]:
    checks = []
    machine = builders.fibonacci_machine()
    for k in range(1, 21):
        ev = evolve(machine, Config(1, (k,)))
        total = sum(c for c in terminal_path_counts(ev).values() if isinstance(c, int))
        expected = _fib(k)
        checks.append(
            Check(
                "fibonacci",
                f"k={k}",
                f"paths = {expected}",
                f"paths = {total}",
                total == expected,
            )
        )
    return checks


def _collatz_forward_checks() -> list[Check]:
    checks = []
    for n in [*range(1, 16), 27, 101]:
        expected = _collatz_reference(n)
        actual = builders.collatz_trajectory(n)
        checks.append(
            Check(
                "collatz-forward",
                f"n={n}",
                f"trajectory of {len(expected)} values",
                "matches" if actual == expected else f"differs: {actual[:6]}...",
                actual == expected,
            )
        )
    return checks


def _reverse_value_closure(depth: int) -> dict[int, int]:
    """Value -> first reverse step at which it appears, from root 1."""
    seen = {1: 0}
    frontier = [1]
    for d in range(1, depth + 1):
        nxt = []
        for v in frontier:
            for w in builders.collatz_reverse_values(v):
                if w not in seen:
                    seen[w] = d
                    nxt.append(w)
        frontier = nxt
    return seen


def _collatz_reverse_checks() -> list[Check]:
    checks = []
    closure = _reverse_value_closure(14)
    bad = [v for v, depth in closure.items() if len(_collatz_reference(v)) - 1 != depth]
    checks.append(
        Check(
            "collatz-reverse",
            "values to depth 14",
            f"{len(closure)} values return to 1 in exactly their reverse depth",
            "all do" if not bad else f"failures: {sorted(bad)[:5]}",
            not bad,
        )
    )
    ev = evolve(
        builders.collatz_reverse_machine(),
        Config(1, (1, 0)),
        max_steps=500,
        max_states=200_000,
        max_frontier=50_000,
    )
    odometer = {
        ev.nodes[n].registers[0]
        for layer in ev.layers
        for n in layer
        if ev.nodes[n].pc == 1 and ev.nodes[n].registers[1] == 0
    }
    # Soundness: every odometer value must be producible from another
    # odometer value by the arithmetic reverse map (1 is the root).
    sound = all(
        any(v in builders.collatz_reverse_values(p) for p in odometer) for v in odometer if v != 1
    )
    depth6 = {v for v, d in closure.items() if d <= 6}
    complete = depth6 <= odometer
    checks.append(
        Check(
            "collatz-reverse",
            "machine odometer, 500 steps",
            "reverse-map sound, all values of depth <= 6 present",
            f"{len(odometer)} values, sound={sound}, complete={complete}",
            sound and complete,
        )
    )
    return checks


def _paper_machine_checks() -> list[Check]:
    checks = []
    machine = machine_from_wfr(builders.fibonacci_instructions(), 4)
    ev = evolve(machine, Config(1, (1, 1, 0, 0)), max_steps=2500, max_states=10**6)
    odometer = [
        ev.nodes[n].registers[0]
        for layer in ev.layers
        for n in layer
        if ev.nodes[n].pc == 1 and ev.nodes[n].registers[2] == 0 and ev.nodes[n].registers[3] == 0
    ]
    expected = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
    checks.append(
        Check(
            "fibonacci-paper",
            "first 10 odometer values",
            str(expected),
            str(odometer[:10]),
            odometer[:10] == expected,
        )
    )
    machine = machine_from_wfr(builders.polynomial_creater(), 5)
    ev = evolve(machine, Config(1, (2, 2, 0, 0, 3)), max_steps=1000)
    terminals = [ev.nodes[n] for n in ev.terminals]
    expected_config = Config(13, (18, 0, 0, 0, 0))
    checks.append(
        Check(
            "polynomial-paper",
            "x=2, y=3",
            "halts at (13, (18, 0, 0, 0, 0)); 2*2^3 + 2 = 18",
            f"halts at {terminals}",
            terminals == [expected_config] and not ev.truncated,
        )
    )
    return checks


def run_all_checks() -> list[Check]:
    """Every invariant check, in a stable order."""
    return (
        _grid_checks()
        + _fibonacci_checks()
        + _collatz_forward_checks()
        + _collatz_reverse_checks()
        + _paper_machine_checks()
    )


def format_table(checks: list[Check], *, full: bool = False) -> str:
    """A plain-text report. Aggregates passing groups unless ``full``."""
    lines = []
    header = f"{'model':<18} {'parameter':<26} {'expected':<44} {'actual':<32} result"
    lines.append(header)
    lines.append("-" * len(header))

    def row(check: Check) -> str:
        mark = "pass" if check.ok else "FAIL"
        return (
            f"{check.model:<18} {check.parameter:<26} "
            f"{check.expected:<44} {check.actual:<32} {mark}"
        )

    if full:
        lines.extend(row(c) for c in checks)
    else:
        by_model: dict[str, list[Check]] = {}
        for check in checks:
            by_model.setdefault(check.model, []).append(check)
        for model, group in by_model.items():
            failures = [c for c in group if not c.ok]
            if not failures:
                first, last = group[0].parameter, group[-1].parameter
                span = first if first == last else f"{first} .. {last}"
                if len(span) > 26:
                    span = span[:23] + "..."
                count = f"{len(group)} check" + ("s" if len(group) != 1 else "")
                lines.append(f"{model:<18} {span:<26} {count:<44} {'all pass':<32} pass")
            else:
                lines.extend(row(c) for c in failures)
    passed = sum(1 for c in checks if c.ok)
    lines.append("-" * len(header))
    lines.append(f"{passed}/{len(checks)} checks passed")
    return "\n".join(lines)
