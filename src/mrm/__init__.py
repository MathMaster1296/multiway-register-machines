"""Multiway register machine evolution: engine, presets, and analysis."""

from .analysis import (
    AbsorptionResult,
    ProbabilityTable,
    ReconvergenceReport,
    absorption,
    probability_table,
    reconvergence,
)
from .counting import PathCount, cycle_witness, path_counts, terminal_path_counts
from .evolve import Edge, Evolution, EvolutionMode, NodeId, TerminalKind, evolve
from .graph import Graph, ancestors, branchial_graph, descendants, states_graph
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

__version__ = "0.1.0"

__all__ = [
    "AbsorptionResult",
    "Condition",
    "Config",
    "Edge",
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
    "ancestors",
    "branchial_graph",
    "complexity",
    "cycle_witness",
    "descendants",
    "evolve",
    "instructions_from_wfr",
    "layered_layout",
    "machine_from_instructions",
    "machine_from_wfr",
    "path_counts",
    "probability_table",
    "reconvergence",
    "rules_from_instructions",
    "states_graph",
    "terminal_path_counts",
]
