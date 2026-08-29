# Assumptions and reconciliation record

The engine was ported from the published source of the Wolfram Function
Repository resource `MultiwayRegisterMachine` (v1.0.0, definition notebook)
and the WSRP research notebook attached to the Wolfram Community post. Where
the recovered Wolfram code and the project specification disagree, or where
the original leaves behavior implicit, the decision is recorded here.

## Resolved against the Wolfram source

1. **Instruction model, not guarded rules, is the native input format.**
   The spec describes rules `(id, pc_from, guard, updates, pc_to)`. The WFR
   code instead uses instructions `{reg, 0|1, {next...}, {fail...}}` where
   nondeterminism comes from multiple jump targets. Both are kept: the engine
   evaluates the general rule model, and WFR instructions compile onto it
   (one rule per jump target). Golden tests pin the compiled behavior to the
   WFR outputs exactly.

2. **The WFR executes by instruction arity but draws by the 0/1 flag.**
   `MRMStep` treats any 3-entry instruction as an increment and any 4-entry
   instruction as a decrement, ignoring the flag; the plotting functions
   dispatch on the flag. A mismatched instruction would run one way and
   render the other. `instructions_from_wfr` rejects such programs instead of
   picking a side silently.

3. **`Evolve` is tree-mode layers with path multiplicity.** WFR
   `MRMStatesAtDepth` never deduplicates, so a state reached by `p` paths of
   length `t` appears `p` times in frontier `t`, in expansion order. Tree
   mode reproduces these lists exactly (golden-tested).

4. **`EvolveGraph` is states mode.** Nodes merge by canonical form
   `(pc, registers)`; node ids count up from 1 in discovery order. The WFR
   keeps at most one edge per `(src, dst)` pair and drops rule identity; this
   engine keeps one labeled edge per rule and collapses to the WFR edge set
   via `Evolution.simple_edges()` (golden-tested, including edge order).

5. **Jump targets past the program end are halt states.** `MRMStep` returns
   no successors when `pc > Length[prog]`. Compilation collects all such
   targets into `Machine.halt_pcs`. Targets `< 1` are rejected: Wolfram's
   `prog[[0]]` / negative parts would misbehave, and no published example
   uses them.

6. **Terminal classification** distinguishes `halt` (pc is a declared halt
   pc), `stuck` (no applicable rule, e.g. a decrement at zero with an empty
   fail list), and `cutoff` (applicable rules existed but a cap stopped
   exploration). The WFR does not classify terminals; the categories follow
   the spec.

## Deliberate differences (no observable change on WFR inputs)

7. **Visited states are not re-expanded.** The WFR level queue re-enqueues
   already-seen states and re-expands them; every edge and node this produces
   is a duplicate, so the result is identical. This engine expands each state
   once. Consequence: `layers[t]` here means "states first reached at step
   t", while the WFR queue at level `t` may also contain revisits.

8. **Truncation is explicit.** The WFR silently stops at `maxDepth`. Here
   every cap (`max_steps`, `max_states`, `max_frontier`) reports itself via
   `truncated` / `truncation_reason`, and `max_steps` counts as truncation
   only if unexplored non-terminal states remain.

9. **Update non-negativity is checked per update, in order.** Relevant only
   to the general rule model (compiled WFR rules have single updates guarded
   by the decrement test). A sequence like `r -= 2; r += 3` at `r == 1` is
   inapplicable even though the net change is non-negative.

10. **`Complexity` returns `float(product) ** (1/n)`.** Matches
    `N[GeometricMean[...]]` on all published values to full double precision;
    golden tests compare within 1e-12.

## Open items

* The research notebook's `collatzSimulate` extends `MRMStep` with a parity
  test outside the instruction format (at one pc it branches on whether a
  register is odd). The general rule model expresses this with `%==` guards;
  the Collatz preset will be built that way in Phase 2 and checked against
  the notebook's `collatzSequence` behavior.
* `RulePlot`, `CirclePlot`, and `ProbabilityPlot` are visualizations, not
  semantics; they map to the web explorer and `layout.py` in later phases.
  The probability tables (`MRMProbList`) are a pure function of the tree-mode
  frontiers and will be ported with the statistics pane.
