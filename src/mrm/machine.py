"""Core data model: configurations, rules, and machines.

Two layers:

* The general rule model (`Rule`, `Condition`, `Update`): guarded additive
  register updates with nondeterministic control flow. This is the engine's
  native representation.
* The WFR instruction model (`Instruction`): the ``{reg, 0|1, {next...},
  {fail...}}`` program format of the Wolfram Function Repository resource
  ``MultiwayRegisterMachine``. Instructions compile to rules via
  `machine_from_instructions`, so both layers share one evolution engine.

Register indices are 1-based throughout, matching the paper and the WFR code.
A configuration is `(pc, registers)` with ``pc`` 1-based.
"""

from __future__ import annotations

import functools
import operator
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

ConditionOp = Literal[">", ">=", "==", "<", "%=="]

_WFR_INC = 0
_WFR_DEC = 1


@dataclass(frozen=True)
class Condition:
    """One atomic guard condition on a register.

    For ``op`` in ``>``, ``>=``, ``==``, ``<`` the condition is
    ``r_reg <op> value`` and ``modulus`` must be ``None``. For ``op`` equal to
    ``%==`` the condition is ``r_reg % modulus == value``.
    """

    reg: int
    op: ConditionOp
    value: int
    modulus: int | None = None

    def holds(self, registers: tuple[int, ...]) -> bool:
        r = registers[self.reg - 1]
        if self.op == ">":
            return r > self.value
        if self.op == ">=":
            return r >= self.value
        if self.op == "==":
            return r == self.value
        if self.op == "<":
            return r < self.value
        if self.modulus is None:
            raise ValueError("condition with op '%==' requires a modulus")
        return r % self.modulus == self.value


@dataclass(frozen=True)
class Update:
    """One additive register assignment ``r_reg := r_reg + delta``."""

    reg: int
    delta: int


@dataclass(frozen=True)
class Rule:
    """One multiway rule ``(id, pc_from, guard, updates, pc_to)``.

    The rule is applicable to a configuration ``(pc, r)`` iff ``pc == pc_from``,
    every guard condition holds on ``r``, and applying the updates in order
    never takes any register below zero.
    """

    id: str
    pc_from: int
    guard: tuple[Condition, ...]
    updates: tuple[Update, ...]
    pc_to: int


@dataclass(frozen=True)
class Config:
    """A machine configuration: program counter plus register values."""

    pc: int
    registers: tuple[int, ...]


@dataclass(frozen=True)
class Instruction:
    """One WFR-style instruction.

    ``inc``: increment register ``reg``, then jump nondeterministically to any
    pc in ``next_pcs``. ``dec``: if ``r_reg > 0``, decrement it and jump to any
    pc in ``next_pcs``; otherwise leave the registers unchanged and jump to any
    pc in ``fail_pcs``. Empty target lists mean the machine stops on that
    branch.
    """

    reg: int
    op: Literal["inc", "dec"]
    next_pcs: tuple[int, ...]
    fail_pcs: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.reg < 1:
            raise ValueError(f"instruction register index must be >= 1, got {self.reg}")
        if self.op == "inc" and self.fail_pcs:
            raise ValueError("an inc instruction cannot have a fail branch")
        for pc in self.next_pcs + self.fail_pcs:
            if pc < 1:
                raise ValueError(f"jump target must be >= 1, got {pc}")


@dataclass(frozen=True)
class Machine:
    """A multiway register machine: a rule multiset over ``n_registers``.

    ``halt_pcs`` are program counters that are terminal by definition (for
    machines compiled from instructions these are the jump targets that lie
    outside the program). Any configuration with no applicable rule is
    terminal as well.

    ``instructions`` is set when the machine was compiled from WFR-style
    instructions and is kept for round-tripping and display; it does not
    affect evolution, which reads only ``rules``.
    """

    n_registers: int
    rules: tuple[Rule, ...]
    halt_pcs: frozenset[int] = frozenset()
    instructions: tuple[Instruction, ...] | None = field(default=None, compare=False)

    def validate(self) -> list[str]:
        """Return human-readable problems, empty if the machine is well formed."""
        problems: list[str] = []
        if self.n_registers < 1:
            problems.append(f"n_registers must be >= 1, got {self.n_registers}")
        seen_ids: set[str] = set()
        for rule in self.rules:
            where = f"rule {rule.id!r}"
            if not rule.id:
                problems.append("rule with empty id")
            elif rule.id in seen_ids:
                problems.append(f"duplicate rule id {rule.id!r}")
            seen_ids.add(rule.id)
            if rule.pc_from < 1:
                problems.append(f"{where}: pc_from must be >= 1, got {rule.pc_from}")
            if rule.pc_to < 1:
                problems.append(f"{where}: pc_to must be >= 1, got {rule.pc_to}")
            if rule.pc_from in self.halt_pcs:
                problems.append(f"{where}: pc_from {rule.pc_from} is declared as a halt pc")
            for cond in rule.guard:
                if not 1 <= cond.reg <= self.n_registers:
                    problems.append(f"{where}: condition register r{cond.reg} out of range")
                if cond.op == "%==":
                    if cond.modulus is None or cond.modulus < 1:
                        problems.append(f"{where}: '%==' condition needs a modulus >= 1")
                    elif not 0 <= cond.value < cond.modulus:
                        problems.append(
                            f"{where}: residue {cond.value} not in 0..{cond.modulus - 1}"
                        )
                else:
                    if cond.modulus is not None:
                        problems.append(f"{where}: modulus given for op {cond.op!r}")
                    if cond.value < 0:
                        problems.append(f"{where}: comparison with negative constant")
            for update in rule.updates:
                if not 1 <= update.reg <= self.n_registers:
                    problems.append(f"{where}: update register r{update.reg} out of range")
        return problems

    def _result_of(self, rule: Rule, registers: tuple[int, ...]) -> tuple[int, ...] | None:
        """Apply updates in order; None if any step takes a register below zero."""
        regs = list(registers)
        for update in rule.updates:
            regs[update.reg - 1] += update.delta
            if regs[update.reg - 1] < 0:
                return None
        return tuple(regs)

    def applicable(self, c: Config) -> list[Rule]:
        """Rules applicable to ``c``, in declaration order."""
        if c.pc in self.halt_pcs:
            return []
        result = []
        for rule in self.rules:
            if rule.pc_from != c.pc:
                continue
            if not all(cond.holds(c.registers) for cond in rule.guard):
                continue
            if self._result_of(rule, c.registers) is None:
                continue
            result.append(rule)
        return result

    def step(self, c: Config) -> list[tuple[Rule, Config]]:
        """All one-step successors of ``c`` with the rule that produced each.

        Successor order is rule declaration order; for machines compiled from
        instructions this matches the WFR ``MRMStep`` successor order exactly.
        """
        out = []
        for rule in self.applicable(c):
            regs = self._result_of(rule, c.registers)
            if regs is not None:
                out.append((rule, Config(rule.pc_to, regs)))
        return out


def instructions_from_wfr(prog: Sequence[Sequence[object]]) -> tuple[Instruction, ...]:
    """Parse a raw WFR program ``{{reg, 0|1, {next...}, {fail...}}, ...}``.

    The WFR ``MRMStep`` dispatches on instruction *length* (3 entries means
    increment, 4 means decrement) while the WFR plotting functions dispatch on
    the 0/1 flag. A program where the two disagree behaves inconsistently in
    the original, so it is rejected here; see ASSUMPTIONS.md.
    """
    instructions = []
    for i, raw in enumerate(prog, start=1):
        where = f"instruction {i}"
        if len(raw) not in (3, 4):
            raise ValueError(f"{where}: expected 3 or 4 entries, got {len(raw)}")
        reg, flag = raw[0], raw[1]
        if not isinstance(reg, int) or isinstance(reg, bool):
            raise ValueError(f"{where}: register index must be an integer")
        if flag not in (_WFR_INC, _WFR_DEC):
            raise ValueError(f"{where}: inc/dec flag must be 0 or 1, got {flag!r}")
        expected_len = 3 if flag == _WFR_INC else 4
        if len(raw) != expected_len:
            raise ValueError(
                f"{where}: flag {flag} does not match instruction length {len(raw)}"
                " (the WFR original executes by length but draws by flag,"
                " so mismatched instructions are rejected)"
            )
        branches: list[tuple[int, ...]] = []
        for part in raw[2:]:
            if not isinstance(part, Sequence) or isinstance(part, (str, bytes)):
                raise ValueError(f"{where}: jump targets must be lists of integers")
            targets = []
            for pc in part:
                if not isinstance(pc, int) or isinstance(pc, bool):
                    raise ValueError(f"{where}: jump targets must be integers")
                targets.append(pc)
            branches.append(tuple(targets))
        if flag == _WFR_INC:
            instructions.append(Instruction(reg, "inc", branches[0]))
        else:
            instructions.append(Instruction(reg, "dec", branches[0], branches[1]))
    return tuple(instructions)


def rules_from_instructions(instructions: Sequence[Instruction]) -> tuple[Rule, ...]:
    """Compile instructions to rules.

    Instruction ``i`` (1-based) becomes one rule per jump target: success
    branches ``i{i}s{j}`` and, for decrements, fail branches ``i{i}f{j}``, in
    listed order. Guards encode the decrement test (``r > 0`` on success,
    ``r == 0`` on failure), so at any configuration exactly one branch family
    of a decrement is applicable and successor order matches the WFR original.
    """
    rules: list[Rule] = []
    for i, ins in enumerate(instructions, start=1):
        if ins.op == "inc":
            for j, target in enumerate(ins.next_pcs, start=1):
                rules.append(Rule(f"i{i}s{j}", i, (), (Update(ins.reg, 1),), target))
        else:
            success_guard = (Condition(ins.reg, ">", 0),)
            fail_guard = (Condition(ins.reg, "==", 0),)
            for j, target in enumerate(ins.next_pcs, start=1):
                rules.append(Rule(f"i{i}s{j}", i, success_guard, (Update(ins.reg, -1),), target))
            for j, target in enumerate(ins.fail_pcs, start=1):
                rules.append(Rule(f"i{i}f{j}", i, fail_guard, (), target))
    return tuple(rules)


def machine_from_instructions(
    instructions: Sequence[Instruction], n_registers: int | None = None
) -> Machine:
    """Build a `Machine` from instructions.

    Jump targets outside ``1..len(instructions)`` become halt pcs, matching the
    WFR original where stepping past the program yields no successors. When
    ``n_registers`` is omitted, the highest register index used is taken.
    """
    instructions = tuple(instructions)
    if not instructions:
        raise ValueError("a machine needs at least one instruction")
    if n_registers is None:
        n_registers = max(ins.reg for ins in instructions)
    m = len(instructions)
    halt = frozenset(pc for ins in instructions for pc in ins.next_pcs + ins.fail_pcs if pc > m)
    return Machine(
        n_registers=n_registers,
        rules=rules_from_instructions(instructions),
        halt_pcs=halt,
        instructions=instructions,
    )


def machine_from_wfr(prog: Sequence[Sequence[object]], n_registers: int | None = None) -> Machine:
    """Build a `Machine` straight from a raw WFR program."""
    return machine_from_instructions(instructions_from_wfr(prog), n_registers)


def complexity(instructions: Sequence[Instruction]) -> float:
    """Branching complexity, matching WFR ``MultiwayRegisterMachine["Complexity", prog]``.

    Per instruction: the mean of the success branch count and the fail branch
    count, where increments count their success branches twice and a
    decrement's fail count is clamped to at least 1. The result is the
    geometric mean over all instructions.
    """
    if not instructions:
        raise ValueError("complexity of an empty program is undefined")
    means = []
    for ins in instructions:
        successes = len(ins.next_pcs)
        fails = max(1, len(ins.fail_pcs)) if ins.op == "dec" else successes
        means.append(Fraction(successes + fails, 2))
    product = functools.reduce(operator.mul, means, Fraction(1))
    return float(float(product) ** (1.0 / len(means)))
