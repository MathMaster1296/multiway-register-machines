# Porting notes: WFR `MultiwayRegisterMachine` to Python

The Wolfram Function Repository resource is one function with six usage
forms. Source was recovered from the published definition notebook (v1.0.0).
Golden fixtures in `tests/golden/` hold the evaluated outputs recorded in
that notebook; the parity tests compare against them without loosening.

| WFR usage form | Internal WL function | Python equivalent | Status | Notes |
| --- | --- | --- | --- | --- |
| `[prog, depth, init]` (Evolve) | `MRMStatesAtDepth`, `MultiwayRegisterMachineEvolve` | `evolve(machine, init, mode="tree").layers` | ported, golden-tested | Frontier lists with path multiplicity, order preserved. |
| `["EvolveGraph", prog, depth, init, show]` | `MRMEvolveGraph` | `evolve(machine, init, mode="states")` + `Evolution.simple_edges()` | ported, golden-tested | Node ids in discovery order; WFR drops edge labels, engine keeps them. |
| `["Complexity", prog]` | `MultiwayRegisterMachineComplexity` | `mrm.complexity(instructions)` | ported, golden-tested | Geometric mean of per-instruction branch means. |
| `["ProbabilityPlot", prog, depth, init, maxTokens]` | `MRMProbList`, `MultiwayRegisterMachineProbabilityPlot` | statistics pane (Phase 4) | pending | The numeric tables are a pure function of tree-mode layers. |
| `["RulePlot", prog, nreg]` | `MultiwayRegisterMachineRulePlot` | web rule visualization (Phase 4) | pending | Pure rendering; `splitInstructions` corresponds to `rules_from_instructions`. |
| `["CirclePlot", prog, nreg]` | `MultiwayRegisterMachineCirclePlot` | web rule visualization (Phase 4) | pending | Pure rendering. |

The one execution-relevant helper, `MRMStep`, corresponds to
`Machine.step`. Its dispatch quirk (arity vs flag) and every other observed
difference is documented in [ASSUMPTIONS.md](../ASSUMPTIONS.md).
