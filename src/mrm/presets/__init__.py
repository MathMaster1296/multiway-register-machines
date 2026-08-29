"""Preset machines, each shipped as a ``machine.json`` document.

The JSON files are the source of truth: the web explorer offers exactly the
same files, and new models can be added without touching Python. Loading
goes through `mrm.serialize.machine_from_json`, so anything expressible
there is a valid preset.
"""

from __future__ import annotations

import json
from importlib import resources

from ..serialize import MachineDocument, machine_from_json

# Display order: the three headline models first, then the paper's machines.
PRESET_ORDER = [
    "grid_paths",
    "fibonacci",
    "collatz_reverse",
    "collatz",
    "collatz_forward",
    "fibonacci_paper",
    "polynomial",
    "simple",
    "complete_graph",
    "halting",
    "non_halting",
    "custom",
]


def available_presets() -> list[str]:
    """Preset names, in display order."""
    found = {
        entry.name.removesuffix(".json")
        for entry in resources.files(__name__).iterdir()
        if entry.name.endswith(".json")
    }
    ordered = [name for name in PRESET_ORDER if name in found]
    return ordered + sorted(found - set(ordered))


def load_preset(name: str) -> MachineDocument:
    """Load one preset by name."""
    if name not in available_presets():
        raise KeyError(f"unknown preset {name!r}; available: {available_presets()}")
    text = resources.files(__name__).joinpath(f"{name}.json").read_text("utf-8")
    return machine_from_json(json.loads(text))
