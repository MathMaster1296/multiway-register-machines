"""The paper's machine builders and named machines, ported from the research
notebook ("Modeling Polynomials Using Register Machines" and onward).

Builders produce raw WFR-style instruction lists so they compose exactly the
way the Wolfram originals compose with ``Join`` and pc shifts. Every builder
and composed machine below is pinned by tests to the evaluated outputs
recorded in the notebook.

Conventions carried over from the originals: ``shift`` offsets every jump
target for composition, ``nxt`` is where the routine exits when its work
register runs out (``None`` means stop), and ``regs`` names the registers the
routine touches. The original ``divide`` compares its default exit against
the string ``"None"``, which in practice yields the same empty fail branch
this port produces; see docs/porting-notes.md.
"""

from __future__ import annotations

from .machine import Condition, Config, Machine, Rule, Update, machine_from_wfr

RawProgram = list[list[object]]

_TargetSpec = int | tuple[int, ...] | None


def _targets(nxt: _TargetSpec) -> list[int]:
    if nxt is None:
        return []
    if isinstance(nxt, int):
        return [nxt]
    return list(nxt)


def scalar(
    k: int = 3, shift: int = 0, nxt: _TargetSpec = None, regs: tuple[int, int] = (1, 2)
) -> RawProgram:
    """Multiply-accumulate: drains ``regs[0]`` adding ``k`` per unit to ``regs[1]``."""
    a, b = regs
    body: RawProgram = [[b, 0, [i + 2 + shift]] for i in range(1, k)]
    return [[a, 1, [2 + shift], _targets(nxt)], *body, [b, 0, [1 + shift]]]


def divide(
    k: int = 3, shift: int = 0, nxt: _TargetSpec = None, regs: tuple[int, int] = (1, 2)
) -> RawProgram:
    """Integer division: drains ``regs[0]`` adding one to ``regs[1]`` per ``k``."""
    a, b = regs
    body: RawProgram = [[a, 1, [i + 2 + shift], _targets(nxt)] for i in range(1, k)]
    return [[b, 0, [2 + shift]], *body, [a, 1, [1 + shift], _targets(nxt)]]


def multiply(
    shift: int = 0, nxt: _TargetSpec = None, regs: tuple[int, int, int, int] = (1, 2, 3, 4)
) -> RawProgram:
    """Multiplication: ``r4 += r1 * r2``, consuming ``r1`` and using ``r3`` as scratch."""
    a, b, c, d = regs
    return [
        [a, 1, [2 + shift], _targets(nxt)],
        [b, 1, [3 + shift], [5 + shift]],
        [c, 0, [4 + shift]],
        [d, 0, [2 + shift]],
        [c, 1, [6 + shift], [1 + shift]],
        [b, 0, [5 + shift]],
    ]


def power(
    shift: int = 0,
    nxt: _TargetSpec = None,
    regs: tuple[int, int, int, int, int] = (1, 2, 3, 4, 5),
) -> RawProgram:
    """Exponentiation built on `multiply`, with the exponent in ``regs[4]``."""
    a, b, c, d, e = regs
    return [
        [e, 1, [2 + shift], _targets(nxt)],
        *multiply(1 + shift, 8 + shift, (a, b, c, d)),
        [d, 1, [9 + shift], [1 + shift]],
        [a, 0, [8 + shift]],
    ]


def add(shift: int = 0, nxt: _TargetSpec = None, regs: tuple[int, int] = (1, 2)) -> RawProgram:
    """Addition: drains ``regs[0]`` into ``regs[1]``."""
    a, b = regs
    return [[a, 1, [2 + shift], _targets(nxt)], [b, 0, [1 + shift]]]


def subtract(shift: int = 0, nxt: _TargetSpec = None, regs: tuple[int, int] = (1, 2)) -> RawProgram:
    """Subtraction: drains both registers in lockstep."""
    a, b = regs
    return [[a, 1, [2 + shift], _targets(nxt)], [b, 1, [1 + shift], _targets(nxt)]]


def polynomial_creater() -> RawProgram:
    """The paper's polynomial machine: computes ``2 * x**y + x``.

    From the initial configuration ``(1, (x, x, 0, 0, y))`` the machine halts
    with the value in register 1. The notebook's name is kept as is.
    """
    return power(0, 10) + scalar(2, 9, 13, (4, 1)) + add(12, None, (2, 1))


def collatz_instructions() -> RawProgram:
    """The paper's Collatz machine.

    Registers ``(r1, r2)``; the value lives in ``r2`` at the odometer states
    ``pc == 8, r1 == 0``. Instruction 8 branches multiway to both the
    ``3n + 1`` section (pc 4) and the halving section (pc 6); the
    deterministic variant replaces that branch with a parity test, see
    `collatz_forward_machine`.
    """
    return scalar(3, 0, 8, (2, 1)) + divide(2, 4, 8, (2, 1)) + scalar(1, 7, (4, 6), (1, 2))


def fibonacci_instructions() -> RawProgram:
    """The paper's Fibonacci machine.

    From ``(1, (1, 1, 0, 0))`` the odometer states ``pc == 1, r3 == r4 == 0``
    carry successive Fibonacci numbers in register 1.
    """
    return [
        [2, 1, [2], [4]],
        [3, 0, [3]],
        [4, 0, [1]],
        *add(3, 6, (1, 3)),
        *add(5, 8, (3, 2)),
        *add(7, 1, (4, 1)),
    ]


# Named machines from the notebook, verbatim.
SINGLE_WAY = [[1, 0, [2]], [2, 0, [3]], [1, 0, [4]], [1, 1, [1], []]]
TEST_INSTRUCTIONS = [
    [1, 0, [2, 3]],
    [2, 1, [1], [3, 4]],
    [2, 0, [5]],
    [1, 1, [3, 5], [1, 5]],
    [2, 1, [1, 2], []],
]
SIMPLE_MRM = [[1, 0, [2]], [2, 0, [3, 4]], [1, 0, [4]], [1, 1, [1], []]]
COMPLETE_GRAPH = [[1, 0, [2, 3]], [1, 0, [1, 3]], [1, 0, [1, 2]]]
HALTING_MACHINE = [
    [1, 0, [2, 3]],
    [1, 0, [4, 5]],
    [2, 0, [4]],
    [1, 1, [5], [1]],
    [2, 0, [3, 6]],
    [2, 1, [], [1, 2]],
]
NON_HALTING_MACHINE = [
    [1, 0, [2, 3]],
    [1, 0, [4, 5]],
    [2, 0, [4]],
    [1, 1, [5], [1]],
    [2, 0, [3, 6]],
    [2, 1, [1], []],
]


def collatz_forward_machine() -> Machine:
    """The deterministic Collatz machine.

    Identical to `collatz_instructions` except that the multiway branch at
    the odometer (instruction 8's fail branch to pcs 4 and 6) is replaced by
    the notebook's ``collatzSimulate`` parity test, expressed as guarded
    rules: odd values take the ``3n + 1`` section, even values the halving
    section.
    """
    base = machine_from_wfr(collatz_instructions(), 2)
    replacements = {
        "i8f1": Rule("i8odd", 8, (Condition(1, "==", 0), Condition(2, "%==", 1, 2)), (), 4),
        "i8f2": Rule("i8even", 8, (Condition(1, "==", 0), Condition(2, "%==", 0, 2)), (), 6),
    }
    rules = tuple(replacements.get(rule.id, rule) for rule in base.rules)
    return Machine(n_registers=2, rules=rules, halt_pcs=base.halt_pcs)


def collatz_trajectory(n: int, max_steps: int = 5_000_000) -> list[int]:
    """The Collatz value sequence the machine computes, notebook-style.

    Runs `collatz_forward_machine` from ``(8, (0, n))`` and reads register 2
    at each odometer state, stopping once the value 1 appears (matching the
    notebook's ``collatzSequence``).
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    machine = collatz_forward_machine()
    config = Config(8, (0, n))
    values = [n]
    for _ in range(max_steps):
        if values[-1] == 1:
            return values
        steps = machine.step(config)
        if len(steps) != 1:
            raise RuntimeError(f"forward Collatz machine is stuck at {config}")
        config = steps[0][1]
        if config.pc == 8 and config.registers[0] == 0:
            values.append(config.registers[1])
    raise RuntimeError(f"no return to 1 within {max_steps} machine steps from {n}")


def grid_paths_machine(m: int, n: int) -> Machine:
    """The grid-paths model: walk from (0, 0) to (m, n) by unit steps."""
    if m < 0 or n < 0:
        raise ValueError("grid dimensions must be non-negative")
    return Machine(
        n_registers=2,
        rules=(
            Rule("right", 1, (Condition(1, "<", m),), (Update(1, 1),), 1),
            Rule("up", 1, (Condition(2, "<", n),), (Update(2, 1),), 1),
        ),
    )


def fibonacci_machine() -> Machine:
    """The Fibonacci recursion model: ``k -> k - 1`` and ``k -> k - 2``.

    Base cases are ``k == 1`` and ``k == 2``, so the number of distinct paths
    from ``(1, (k,))`` to the terminals is the k-th Fibonacci number
    (``F(1) = F(2) = 1``). In states mode the graph has one node per value:
    the exponential recursion tree collapses to a linear DAG whose path
    count is still ``F(k)``.
    """
    return Machine(
        n_registers=1,
        rules=(
            Rule("f1", 1, (Condition(1, ">=", 3),), (Update(1, -1),), 1),
            Rule("f2", 1, (Condition(1, ">=", 3),), (Update(1, -2),), 1),
        ),
    )


def collatz_reverse_machine() -> Machine:
    """The reverse Collatz model: grow the Collatz tree from 1.

    Value states are ``(1, (v, 0))``. Two branches: double (always), and
    undo ``3n + 1`` when ``v % 6 == 4`` and ``v > 4`` (exactly when the
    predecessor is odd and greater than 1). Both branches run as loops, so
    one value step takes several machine steps; the odometer states are the
    configurations at pc 1 with the scratch register empty.
    """
    return Machine(
        n_registers=2,
        rules=(
            Rule("double", 1, (), (), 2),
            Rule(
                "undo3n1",
                1,
                (Condition(1, "%==", 4, 6), Condition(1, ">", 4)),
                (Update(1, -1),),
                4,
            ),
            Rule("dbl.loop", 2, (Condition(1, ">", 0),), (Update(1, -1), Update(2, 2)), 2),
            Rule("dbl.done", 2, (Condition(1, "==", 0),), (), 3),
            Rule("copy.loop", 3, (Condition(2, ">", 0),), (Update(2, -1), Update(1, 1)), 3),
            Rule("copy.done", 3, (Condition(2, "==", 0),), (), 1),
            Rule("third.loop", 4, (Condition(1, ">=", 3),), (Update(1, -3), Update(2, 1)), 4),
            Rule("third.done", 4, (Condition(1, "==", 0),), (), 3),
        ),
    )


def collatz_reverse_values(n: int) -> list[int]:
    """Value-level predecessors of ``n`` under the reverse Collatz map."""
    values = [2 * n]
    if n % 6 == 4 and n > 4:
        values.append((n - 1) // 3)
    return values
