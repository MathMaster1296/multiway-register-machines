"""Multiway register machine evolution: engine, presets, and analysis."""

from .evolve import Edge, Evolution, EvolutionMode, NodeId, TerminalKind, evolve
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
    "Condition",
    "Config",
    "Edge",
    "Evolution",
    "EvolutionMode",
    "Instruction",
    "Machine",
    "NodeId",
    "Rule",
    "TerminalKind",
    "Update",
    "__version__",
    "complexity",
    "evolve",
    "instructions_from_wfr",
    "machine_from_instructions",
    "machine_from_wfr",
    "rules_from_instructions",
]
