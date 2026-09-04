"""Multiway register machine evolution: engine, presets, and analysis."""

from ._version import __version__
from .analysis import (
    AbsorptionResult,
    AbsorptionTimeDistribution,
    ProbabilityTable,
    ReconvergenceReport,
    absorption,
    absorption_time_distribution,
    probability_table,
    reconvergence,
)
from .causal import CausalAnalysis, Event, causal_analysis, causal_analysis_to
from .counting import PathCount, cycle_witness, path_counts, terminal_path_counts
from .ensemble import EnsembleRow, ensemble
from .evolve import Edge, Evolution, EvolutionMode, NodeId, TerminalKind, evolve
from .graph import (
    Graph,
    ancestors,
    branchial_graph,
    descendants,
    shortest_edge_path,
    states_graph,
)
from .layout import layered_layout
from .machine import (
    Condition,
    Config,
    Instruction,
    Machine,
    Rule,
    Update,
    complexity,
    instructions_from_wfr,
    machine_from_instructions,
    machine_from_wfr,
    rules_from_instructions,
)
from .weblink import decode_fragment, explorer_link

__all__ = [
    "AbsorptionResult",
    "AbsorptionTimeDistribution",
    "CausalAnalysis",
    "Condition",
    "Config",
    "Edge",
    "EnsembleRow",
    "Event",
    "Evolution",
    "EvolutionMode",
    "Graph",
    "Instruction",
    "Machine",
    "NodeId",
    "PathCount",
    "ProbabilityTable",
    "ReconvergenceReport",
    "Rule",
    "TerminalKind",
    "Update",
    "__version__",
    "absorption",
    "absorption_time_distribution",
    "ancestors",
    "branchial_graph",
    "causal_analysis",
    "causal_analysis_to",
    "complexity",
    "cycle_witness",
    "decode_fragment",
    "descendants",
    "ensemble",
    "evolve",
    "explorer_link",
    "instructions_from_wfr",
    "layered_layout",
    "machine_from_instructions",
    "machine_from_wfr",
    "path_counts",
    "probability_table",
    "reconvergence",
    "rules_from_instructions",
    "shortest_edge_path",
    "states_graph",
    "terminal_path_counts",
]
