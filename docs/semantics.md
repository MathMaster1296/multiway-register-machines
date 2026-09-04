# Formal semantics

This document specifies the model the `mrm` package implements, precisely
enough that the implementation can be checked against the paper without
reading Python. Where the Wolfram original left behavior implicit, the
resolution is recorded in [ASSUMPTIONS.md](../ASSUMPTIONS.md); the mapping
from Wolfram functions to Python is in [porting-notes.md](porting-notes.md).

## Configurations

A machine operates on `n >= 1` registers holding non-negative integers. A
configuration is a pair `(pc, r)` where `pc >= 1` is the program counter and
`r = (r_1, ..., r_n)` is the register vector. Registers and program counters
are 1-indexed throughout.

## The instruction model

This is the paper's model, and the input format of the Wolfram Function
Repository resource `MultiwayRegisterMachine`. A program is a list
`I_1, ..., I_m` of instructions of two shapes:

* increment: `(a, inc, T)` with `a` a register index and `T` a list of jump
  targets;
* decrement: `(a, dec, T, F)` with success targets `T` and fail targets `F`.

The successor set of a configuration `(pc, r)` is defined case by case:

* If `pc > m`, there are no successors; the configuration halts.
* If `I_pc = (a, inc, T)`: the successors are `(t, r')` for each `t` in `T`
  in listed order, where `r'` increments `r_a`.
* If `I_pc = (a, dec, T, F)` and `r_a > 0`: the successors are `(t, r')` for
  each `t` in `T`, where `r'` decrements `r_a`.
* If `I_pc = (a, dec, T, F)` and `r_a = 0`: the successors are `(f, r)` for
  each `f` in `F`, registers unchanged.

Multiway branching therefore comes only from multiple jump targets; each
branch of one instruction applies the same register update. An empty target
list in the active case leaves the configuration with no successors. Target
lists are multisets: a target listed twice yields two successors.

Jump targets must be at least 1. Targets greater than `m` are legal and act
as explicit halt states. An instruction whose inc/dec flag disagrees with
its shape is rejected (the Wolfram original executes by shape but renders by
flag, so such programs have no consistent meaning).

## The rule model

The engine's native representation generalizes instructions to rules

    rule = (id, pc_from, guard, updates, pc_to)

where the guard is a finite conjunction of atomic conditions on single
registers, each of the form `r_a > c`, `r_a >= c`, `r_a == c`, `r_a < c`, or
`r_a mod k == c`, and the updates are a sequence of additive assignments
`r_a := r_a + d` with `d` any integer.

A rule is applicable to `(pc, r)` iff `pc = pc_from`, every guard condition
holds on `r`, and applying the updates in sequence never takes any register
below zero (the check is per update, in order, not on the net effect). The
successors of a configuration are obtained by applying every applicable rule,
in rule declaration order.

Each instruction compiles to one rule per jump target: an increment
`(a, inc, T)` at position `p` yields unguarded rules with update `r_a += 1`
targeting each `t` in `T`; a decrement yields rules guarded by `r_a > 0` with
update `r_a -= 1` for the success targets, followed by rules guarded by
`r_a == 0` with no update for the fail targets. Exactly one guard family of
a decrement is applicable at any configuration, so the compiled successor
sequence equals the instruction model's successor sequence, element for
element. Golden tests pin this equality to the published Wolfram outputs.

The rule model is strictly more expressive: the modular conditions express
the parity dispatch the paper's `collatzSimulate` performs outside the
instruction format, and multi-register updates shorten arithmetic loops.
Everything expressible remains a counter machine with conjunctive guards and
additive updates.

## Evolution

Fix a machine and an initial configuration set `S_0` (usually a singleton).
Write `succ(s)` for the successor sequence of `s`. Evolution is breadth
first and comes in two modes.

In tree mode nothing is merged. Level 0 lists the initial configurations;
level `t + 1` is the concatenation of `succ(s)` over the level-`t` entries in
order. A configuration reached by `p` distinct paths of length `t` appears
`p` times at level `t`. These levels equal the Wolfram `Evolve` frontiers
exactly, duplicates and order included.

In states mode configurations are canonicalized as the pair
`(pc, register tuple)` and merged: a configuration seen at any earlier point
is the same node. Nodes are numbered from 1 in discovery order (initials
first, then successors in expansion order), matching the Wolfram
`EvolveGraph` numbering. Every rule application contributes a labeled edge;
collapsing parallel edges by (source, target) recovers the Wolfram edge set
in first-occurrence order. Layer `t` is the set of nodes first reached at
step `t`.

Three caps bound every run: `max_steps` on BFS depth, `max_states` on total
nodes, and `max_frontier` on any single level. A cap that fires marks the
result truncated and names itself; `max_steps` counts as truncation only
when unexplored non-terminal configurations remain. Truncated results are
never presented as complete.

Terminal nodes split into three kinds: `halt` (the pc is a declared halt
pc), `stuck` (no rule is applicable, for example a decrement at zero with an
empty fail list), and `cutoff` (rules were applicable but a cap stopped
exploration).

## Derived structures

The branchial graph at step `t` has the layer-`t` nodes as vertices and
connects two of them iff they share a parent in layer `t - 1`.

Path counts assign to each node the number of distinct directed paths from
the initial configuration, counting parallel edges separately, so the count
of a node equals its multiplicity in the tree-mode level of its depth. On
graphs where a directed cycle is reachable, every node on or downstream of a
cycle receives an explicit infinite marker, and a concrete cycle witness is
available; counts are never silently wrong.

The growth series is the sequence of layer sizes.

## Causal structure of a path

Fix one path through an evolution and call each rule application along it
an event. Event ``j`` depends on event ``i`` when ``i`` is the latest
earlier event that wrote a register ``j`` reads, where a rule reads its
guard registers together with the registers its updates touch, and writes
the registers its updates touch. Control flow is excluded deliberately:
every event reads and writes the program counter, so including it collapses
every path to a single chain.

This data view separates the two mechanisms behind state merging. When the
rules of a branch touch disjoint registers, the events of any path split
into independent chains and different interleavings commute, which is why
grid paths reconverge. When every rule touches the same register, a path is
one total chain and merging can only come from different histories reaching
equal values, which is what happens in the Fibonacci recursion. The
implementation reports the dependency pairs, the number of independent
chains, and the longest chain of a path.

## The uniform branching measure

Interpreting each applicable rule of a node as equally probable turns the
states graph into a Markov chain whose absorbing states are the terminal
nodes. The package solves this chain exactly over the rationals (linear
time on the acyclic part; Gaussian elimination per strongly connected
component otherwise) and reports the absorption probability of each
terminal, the probability of remaining forever in closed cycles, the mass
cut off by caps, and, when the run is complete and every trajectory halts,
the exact expected number of steps. The Wolfram probability tables are the
transient distributions of the same chain: the pc distribution and the
register tail distributions of the tree-mode frontier at each depth.

## Determinism

Same input, same bytes out. All iteration follows list order or insertion
order, node ids are discovery-ordered, serialization emits keys in a fixed
order, and the layered layout uses a fixed number of median-heuristic passes
with no randomness. Running anything twice, in CPython or in the browser
through Pyodide, produces identical output including coordinates.
