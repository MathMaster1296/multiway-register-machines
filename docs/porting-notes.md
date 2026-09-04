# Porting notes: WFR `MultiwayRegisterMachine` to Python

The Wolfram Function Repository resource is one function with six usage
forms. Source was recovered from the published definition notebook (v1.0.0)
and from the research notebook attached to [the Wolfram Community article](https://community.wolfram.com/groups/-/m/t/3499350).
Golden fixtures in `tests/golden/` hold the evaluated outputs recorded in
those notebooks; the parity tests compare against them without loosening.

## The six usage forms

| WFR usage form | Internal WL function | Python equivalent | Status | Notes |
| --- | --- | --- | --- | --- |
| `[prog, depth, init]` (Evolve) | `MRMStatesAtDepth`, `MultiwayRegisterMachineEvolve` | `evolve(machine, init, mode="tree").layers` | ported, golden-tested | Frontier lists with path multiplicity, order preserved. |
| `["EvolveGraph", prog, depth, init, show]` | `MRMEvolveGraph` | `evolve(machine, init, mode="states")` + `Evolution.simple_edges()` | ported, golden-tested | Node ids in discovery order; WFR drops edge labels, engine keeps them. |
| `["Complexity", prog]` | `MultiwayRegisterMachineComplexity` | `mrm.complexity(instructions)` | ported, golden-tested | Geometric mean of per-instruction branch means. |
| `["ProbabilityPlot", prog, depth, init, maxTokens]` | `MRMProbList`, `MultiwayRegisterMachineProbabilityPlot` | `mrm.probability_table(ev, depth, max_value)` | tables ported, tested against the notebook's `MRMProbList` output | Exact rationals instead of machine floats; rendering goes to the web explorer. |
| `["RulePlot", prog, nreg]` | `MultiwayRegisterMachineRulePlot` | `mrm.figures.rule_plot_svg`, shown in the explorer | ported | Same geometry conventions; success and fail arcs are blue and orange here instead of green and red. `splitInstructions` corresponds to `rules_from_instructions`. |
| `["CirclePlot", prog, nreg]` | `MultiwayRegisterMachineCirclePlot` | `mrm.figures.circle_plot_svg`, shown in the explorer | ported | Halt targets past the program end are drawn as open dashed nodes; colors as above. |

The one execution-relevant helper, `MRMStep`, corresponds to
`Machine.step`. Its dispatch quirk (arity vs flag) and every other observed
difference is documented in [ASSUMPTIONS.md](../ASSUMPTIONS.md).

## The research notebook's builders and machines

| Notebook definition | Python equivalent | Status |
| --- | --- | --- |
| `scalar`, `divide`, `multiply`, `power`, `add`, `subtract` | `mrm.builders` functions of the same names | ported; output lists pinned to the notebook's evaluated outputs |
| `polynomialCreater` | `builders.polynomial_creater()` | ported; halt state `(13, (18, 0, 0, 0, 0))` verified |
| `collatzInstructions` | `builders.collatz_instructions()` | ported; instruction list pinned |
| `collatzSimulate` (parity oracle) | `builders.collatz_forward_machine()` | oracle expressed as `%==` guard rules; `collatzSequence[101]` reproduced exactly |
| `fibonacciInstructions` | `builders.fibonacci_instructions()` | ported; first ten odometer values reproduced |
| `SingleWayRM`, `testInstructions`, `simpleMRM`, `completeGraph`, `haltingMachine`, `nonHaltingMachine` | constants in `mrm.builders` | ported verbatim |

One quirk worth knowing: the notebook's `divide` compares its default exit
parameter against the string `"None"` in its last instruction, where every
other builder compares against `-1`. On the recorded evaluations both forms
produce an empty fail branch, which is what this port does for a missing
exit; when an exit is passed explicitly (as in `collatzInstructions`), the
behaviors agree exactly.
