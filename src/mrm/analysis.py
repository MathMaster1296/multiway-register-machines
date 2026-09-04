"""Quantitative analysis of multiway evolutions.

Three tools, all exact (rational arithmetic, no floating point until the
caller asks for it) and deterministic:

* `absorption` treats the states graph as a Markov chain in which every
  applicable rule is taken with equal probability, and computes the exact
  probability of ending in each terminal configuration, the probability of
  running forever, and the expected number of steps to termination. This
  makes precise the intuition behind the WFR probability plots: those tables
  are the transient distribution of the same chain.

* `probability_table` ports the WFR ``MRMProbList``: the distribution of the
  program counter and the tail distribution of each register across the
  frontier at a given depth, weighted by path multiplicity.

* `reconvergence` measures how often the two sides of a multiway branch meet
  again within a bounded number of steps. A machine whose branches always
  reconverge has a states graph that stays narrow no matter how bushy the
  tree is; this is the property state merging exploits.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .counting import strongly_connected_components, successor_lists
from .evolve import Evolution, NodeId, TerminalKind
from .machine import Config


@dataclass(frozen=True)
class AbsorptionResult:
    """Exact absorption analysis of a states-mode evolution.

    ``terminal_probabilities[t]`` is the probability of halting in terminal
    node ``t``. ``never_halting`` is the mass trapped in closed cycles.
    ``unresolved`` is the mass that reached configurations the caps cut off,
    so it is zero exactly when the evolution is complete. ``expected_steps``
    is the mean number of rule applications before termination, or ``None``
    when it is not defined (some mass never halts or is unresolved).
    """

    terminal_probabilities: dict[NodeId, Fraction]
    never_halting: Fraction
    unresolved: Fraction
    expected_steps: Fraction | None

    @property
    def halting_probability(self) -> Fraction:
        return sum(self.terminal_probabilities.values(), Fraction(0))


def absorption(ev: Evolution) -> AbsorptionResult:
    """Solve the uniform-branching Markov chain of an evolution exactly.

    Every outgoing edge of a node (rules, with multiplicity) is taken with
    equal probability. Terminal nodes absorb. The system is solved by
    processing strongly connected components in topological order; acyclic
    regions cost linear time and each cyclic component is solved by Gaussian
    elimination over rationals, so results are exact.
    """
    succ = successor_lists(ev)
    outdeg = {n: len(succ[n]) for n in ev.nodes}
    visits: dict[NodeId, Fraction] = dict.fromkeys(ev.nodes, Fraction(0))
    inflow: dict[NodeId, Fraction] = dict.fromkeys(ev.nodes, Fraction(0))
    roots = ev.layers[0]
    for root in roots:
        inflow[root] += Fraction(1, len(roots))

    never_halting = Fraction(0)
    components = strongly_connected_components(list(ev.nodes), succ)
    for component in reversed(components):  # topological order
        members = set(component)
        cyclic = len(component) > 1 or component[0] in succ[component[0]]
        if not cyclic:
            v = component[0]
            visits[v] = inflow[v]
            if outdeg[v]:
                share = visits[v] / outdeg[v]
                for w in succ[v]:
                    inflow[w] += share
            continue
        leaves = any(w not in members for m in component for w in succ[m])
        if not leaves:
            never_halting += sum((inflow[m] for m in component), Fraction(0))
            continue
        solved = _solve_component(component, succ, outdeg, inflow)
        for m, value in solved.items():
            visits[m] = value
            share = value / outdeg[m]
            for w in succ[m]:
                if w not in members:
                    inflow[w] += share

    terminal_probabilities: dict[NodeId, Fraction] = {}
    unresolved = Fraction(0)
    for node, kind in ev.terminals.items():
        if kind is TerminalKind.CUTOFF:
            unresolved += visits[node]
        else:
            terminal_probabilities[node] = visits[node]

    expected: Fraction | None = None
    if never_halting == 0 and unresolved == 0 and not ev.truncated:
        expected = sum((visits[n] for n in ev.nodes if outdeg[n]), Fraction(0))
    return AbsorptionResult(
        terminal_probabilities=terminal_probabilities,
        never_halting=never_halting,
        unresolved=unresolved,
        expected_steps=expected,
    )


def _solve_component(
    component: list[NodeId],
    succ: dict[NodeId, list[NodeId]],
    outdeg: dict[NodeId, int],
    inflow: dict[NodeId, Fraction],
) -> dict[NodeId, Fraction]:
    """Solve ``x = inflow + P_internal x`` for one open cyclic component."""
    pos = {m: i for i, m in enumerate(component)}
    n = len(component)
    # Rows: x_i - sum_j P[j -> i] x_j = inflow_i
    matrix = [[Fraction(0)] * n + [inflow[m]] for m in component]
    for i in range(n):
        matrix[i][i] += 1
    for j, m in enumerate(component):
        share = Fraction(1, outdeg[m])
        for w in succ[m]:
            if w in pos:
                matrix[pos[w]][j] -= share
    # Gaussian elimination with exact pivoting (first nonzero pivot).
    for col in range(n):
        pivot = next(r for r in range(col, n) if matrix[r][col] != 0)
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        inv = 1 / matrix[col][col]
        matrix[col] = [entry * inv for entry in matrix[col]]
        for r in range(n):
            if r != col and matrix[r][col] != 0:
                factor = matrix[r][col]
                matrix[r] = [a - factor * b for a, b in zip(matrix[r], matrix[col], strict=True)]
    return {m: matrix[i][n] for i, m in enumerate(component)}


@dataclass(frozen=True)
class ProbabilityTable:
    """The WFR ``MRMProbList`` tables at one depth, as exact rationals.

    ``pc_probs[i - 1]`` is the fraction of depth-``t`` paths sitting at
    program counter ``i`` (up to the largest pc observed). ``register_tails
    [j - 1][k - 1]`` is the fraction of paths whose register ``j`` is at
    least ``k``, for ``k`` up to ``max_value``.
    """

    depth: int
    pc_probs: tuple[Fraction, ...]
    register_tails: tuple[tuple[Fraction, ...], ...]


def probability_table(ev: Evolution, depth: int, max_value: int = 20) -> ProbabilityTable | None:
    """Frontier statistics at ``depth`` for a tree-mode evolution.

    Matches ``MRMProbList`` including its conventions: path-multiplicity
    weighting, pc range up to the per-depth maximum, and tail (not point)
    distributions for registers. Returns ``None`` where the WFR returns an
    empty list because the frontier is empty.
    """
    if ev.mode != "tree":
        raise ValueError("probability_table needs a tree-mode evolution")
    if depth >= len(ev.layers) or not ev.layers[depth]:
        return None
    states: list[Config] = [ev.nodes[n] for n in ev.layers[depth]]
    total = len(states)
    max_pc = max(state.pc for state in states)
    pc_probs = tuple(
        Fraction(sum(1 for s in states if s.pc == i), total) for i in range(1, max_pc + 1)
    )
    tails = tuple(
        tuple(
            Fraction(sum(1 for s in states if s.registers[j] >= k), total)
            for k in range(1, max_value + 1)
        )
        for j in range(ev.machine.n_registers)
    )
    return ProbabilityTable(depth=depth, pc_probs=pc_probs, register_tails=tails)


@dataclass(frozen=True)
class ReconvergenceReport:
    """How often multiway branch pairs merge back together.

    ``pairs`` counts ordered-by-position unordered pairs of distinct
    successors over all branching nodes; ``merged`` counts those with a
    common descendant within the window. ``unmerged`` lists up to ten
    ``(node, a, b)`` witnesses that failed to merge.
    """

    within: int
    pairs: int
    merged: int
    unmerged: tuple[tuple[NodeId, NodeId, NodeId], ...]

    @property
    def fraction(self) -> Fraction | None:
        return Fraction(self.merged, self.pairs) if self.pairs else None


def reconvergence(ev: Evolution, within: int = 8) -> ReconvergenceReport:
    """Check every branch pair in a states-mode evolution for reconvergence.

    Two branches reconverge when the successors have a common descendant
    within ``within`` further steps. Branch pairs at the exploration edge of
    a truncated evolution may be reported as unmerged simply because their
    joint future was cut off; rerun with larger caps to resolve those.
    """
    succ = successor_lists(ev)
    reach_cache: dict[NodeId, set[NodeId]] = {}

    def bounded_reach(start: NodeId) -> set[NodeId]:
        cached = reach_cache.get(start)
        if cached is None:
            cached = {start}
            frontier = [start]
            for _ in range(within):
                nxt = [w for v in frontier for w in succ[v] if w not in cached]
                if not nxt:
                    break
                cached.update(nxt)
                frontier = nxt
            reach_cache[start] = cached
        return cached

    pairs = 0
    merged = 0
    unmerged: list[tuple[NodeId, NodeId, NodeId]] = []
    for node in ev.nodes:
        branches: list[NodeId] = []
        for w in succ[node]:
            if w not in branches:
                branches.append(w)
        for i, a in enumerate(branches):
            for b in branches[i + 1 :]:
                pairs += 1
                if bounded_reach(a) & bounded_reach(b):
                    merged += 1
                elif len(unmerged) < 10:
                    unmerged.append((node, a, b))
    return ReconvergenceReport(within=within, pairs=pairs, merged=merged, unmerged=tuple(unmerged))


@dataclass(frozen=True)
class AbsorptionTimeDistribution:
    """The distribution of the halting time under the uniform branching measure.

    ``probabilities[t]`` is the probability of reaching a halt or stuck state
    at exactly step ``t``. ``tail`` is the mass not absorbed within the
    horizon: mass still in flight, trapped in cycles, or stalled at states a
    cap cut off. When every trajectory halts within the horizon, the mean of
    the distribution equals `AbsorptionResult.expected_steps`.
    """

    probabilities: tuple[Fraction, ...]
    tail: Fraction
    horizon: int

    def mean_within_horizon(self) -> Fraction:
        return sum((t * p for t, p in enumerate(self.probabilities)), Fraction(0))


def absorption_time_distribution(
    ev: Evolution, horizon: int = 200, *, exact: bool = True
) -> AbsorptionTimeDistribution:
    """Propagate the uniform-branching mass forward and record absorptions.

    With ``exact`` (the default) all arithmetic is rational. ``exact=False``
    computes in floats, which is what the web explorer asks for: on cyclic
    graphs exact denominators grow like ``outdeg ** t``, and floats keep long
    horizons cheap. Float results are wrapped back into fractions verbatim.
    """
    succ = successor_lists(ev)
    outdeg = {n: len(succ[n]) for n in ev.nodes}
    absorbing = {n for n, kind in ev.terminals.items() if kind is not TerminalKind.CUTOFF}
    roots = ev.layers[0] if ev.layers else []
    mass: dict[NodeId, Fraction | float]
    if exact:
        mass = dict.fromkeys(roots, Fraction(1, max(len(roots), 1)))
        zero: Fraction | float = Fraction(0)
    else:
        mass = dict.fromkeys(roots, 1.0 / max(len(roots), 1))
        zero = 0.0

    probabilities: list[Fraction | float] = []
    stalled = zero
    for _ in range(horizon + 1):
        absorbed = zero
        moving: dict[NodeId, Fraction | float] = {}
        for node, amount in mass.items():
            if node in absorbing:
                absorbed = absorbed + amount
            elif outdeg[node] == 0:
                stalled = stalled + amount  # cut off by a cap: fate unknown
            else:
                moving[node] = amount
        probabilities.append(absorbed)
        if not moving:
            mass = {}
            break
        nxt: dict[NodeId, Fraction | float] = {}
        for node, amount in moving.items():
            share = amount / outdeg[node]
            for target in succ[node]:
                nxt[target] = nxt.get(target, zero) + share
        mass = nxt
    in_flight = sum(mass.values(), zero)
    tail = stalled + in_flight
    return AbsorptionTimeDistribution(
        probabilities=tuple(Fraction(p) for p in probabilities),
        tail=Fraction(tail),
        horizon=horizon,
    )
