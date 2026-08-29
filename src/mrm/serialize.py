"""JSON serialization for machines and evolutions.

Two versioned document types, both round-trip tested:

* ``mrm/machine/1``: a machine, optionally with a name, description, and
  initial configuration. Rules are authoritative; when the machine came from
  WFR-style instructions those are carried alongside for display and
  round-tripping.
* ``mrm/evolution/1``: a full evolution result plus the machine, the
  parameters that produced it, derived data (terminal path counts, growth
  series), and a generator block hashing the machine so figures are
  traceable to their exact input.

Serialization is canonical: dictionaries are emitted in a fixed key order and
lists in the engine's deterministic order, so equal inputs give equal bytes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast

from . import __version__
from .counting import PathCount, terminal_path_counts
from .evolve import Edge, Evolution, EvolutionMode, TerminalKind, evolve
from .machine import (
    Condition,
    ConditionOp,
    Config,
    Instruction,
    Machine,
    Rule,
    Update,
    instructions_from_wfr,
)

MACHINE_SCHEMA = "mrm/machine/1"
EVOLUTION_SCHEMA = "mrm/evolution/1"


@dataclass(frozen=True)
class MachineDocument:
    """A machine plus the presentation data a ``machine.json`` carries."""

    machine: Machine
    name: str | None = None
    description: str | None = None
    initial: Config | None = None


def _condition_to_json(cond: Condition) -> dict[str, Any]:
    out: dict[str, Any] = {"reg": cond.reg, "op": cond.op, "value": cond.value}
    if cond.modulus is not None:
        out["modulus"] = cond.modulus
    return out


def _condition_from_json(data: dict[str, Any]) -> Condition:
    return Condition(
        reg=int(data["reg"]),
        op=cast(ConditionOp, data["op"]),
        value=int(data["value"]),
        modulus=int(data["modulus"]) if "modulus" in data else None,
    )


def _rule_to_json(rule: Rule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "pc_from": rule.pc_from,
        "guard": [_condition_to_json(c) for c in rule.guard],
        "updates": [{"reg": u.reg, "delta": u.delta} for u in rule.updates],
        "pc_to": rule.pc_to,
    }


def _rule_from_json(data: dict[str, Any]) -> Rule:
    return Rule(
        id=str(data["id"]),
        pc_from=int(data["pc_from"]),
        guard=tuple(_condition_from_json(c) for c in data["guard"]),
        updates=tuple(Update(int(u["reg"]), int(u["delta"])) for u in data["updates"]),
        pc_to=int(data["pc_to"]),
    )


def _instruction_to_raw(ins: Instruction) -> list[Any]:
    raw: list[Any] = [ins.reg, 0 if ins.op == "inc" else 1, list(ins.next_pcs)]
    if ins.op == "dec":
        raw.append(list(ins.fail_pcs))
    return raw


def machine_to_json(doc: MachineDocument) -> dict[str, Any]:
    machine = doc.machine
    out: dict[str, Any] = {"schema": MACHINE_SCHEMA}
    if doc.name is not None:
        out["name"] = doc.name
    if doc.description is not None:
        out["description"] = doc.description
    out["n_registers"] = machine.n_registers
    out["rules"] = [_rule_to_json(r) for r in machine.rules]
    out["halt_pcs"] = sorted(machine.halt_pcs)
    if machine.instructions is not None:
        out["instructions"] = [_instruction_to_raw(i) for i in machine.instructions]
    if doc.initial is not None:
        out["initial"] = [doc.initial.pc, list(doc.initial.registers)]
    return out


def machine_from_json(data: dict[str, Any]) -> MachineDocument:
    if data.get("schema") != MACHINE_SCHEMA:
        raise ValueError(f"expected schema {MACHINE_SCHEMA!r}, got {data.get('schema')!r}")
    instructions: tuple[Instruction, ...] | None = None
    if "instructions" in data:
        instructions = instructions_from_wfr(data["instructions"])
    machine = Machine(
        n_registers=int(data["n_registers"]),
        rules=tuple(_rule_from_json(r) for r in data["rules"]),
        halt_pcs=frozenset(int(pc) for pc in data.get("halt_pcs", [])),
        instructions=instructions,
    )
    initial: Config | None = None
    if "initial" in data:
        pc, registers = data["initial"]
        initial = Config(int(pc), tuple(int(r) for r in registers))
    return MachineDocument(
        machine=machine,
        name=data.get("name"),
        description=data.get("description"),
        initial=initial,
    )


def machine_hash(machine: Machine) -> str:
    """A stable content hash of the mathematical machine (not its metadata)."""
    core = {
        "n_registers": machine.n_registers,
        "rules": [_rule_to_json(r) for r in machine.rules],
        "halt_pcs": sorted(machine.halt_pcs),
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def evolution_to_json(ev: Evolution) -> dict[str, Any]:
    counts = terminal_path_counts(ev)
    return {
        "schema": EVOLUTION_SCHEMA,
        "machine": machine_to_json(MachineDocument(ev.machine)),
        "parameters": {
            "mode": ev.mode,
            "max_steps": ev.max_steps,
            "max_states": ev.max_states,
            "max_frontier": ev.max_frontier,
            "initial": [[ev.nodes[n].pc, list(ev.nodes[n].registers)] for n in ev.layers[0]]
            if ev.layers
            else [],
        },
        "nodes": [
            [node_id, config.pc, list(config.registers)] for node_id, config in ev.nodes.items()
        ],
        "edges": [[e.src, e.dst, e.rule_id] for e in ev.edges],
        "layers": [list(layer) for layer in ev.layers],
        "terminals": {str(n): kind.value for n, kind in ev.terminals.items()},
        "path_counts": {
            str(n): "infinite" if isinstance(c, PathCount) else c for n, c in counts.items()
        },
        "growth_series": ev.growth_series(),
        "truncated": ev.truncated,
        "truncation_reason": ev.truncation_reason,
        "generator": {
            "package": "mrm",
            "version": __version__,
            "machine_hash": machine_hash(ev.machine),
        },
    }


def evolution_from_json(data: dict[str, Any]) -> Evolution:
    if data.get("schema") != EVOLUTION_SCHEMA:
        raise ValueError(f"expected schema {EVOLUTION_SCHEMA!r}, got {data.get('schema')!r}")
    doc = machine_from_json(data["machine"])
    params = data["parameters"]
    return Evolution(
        machine=doc.machine,
        mode=cast(EvolutionMode, params["mode"]),
        nodes={
            int(node_id): Config(int(pc), tuple(int(r) for r in registers))
            for node_id, pc, registers in data["nodes"]
        },
        edges=[Edge(int(s), int(d), str(r)) for s, d, r in data["edges"]],
        layers=[[int(n) for n in layer] for layer in data["layers"]],
        terminals={int(n): TerminalKind(kind) for n, kind in data["terminals"].items()},
        truncated=bool(data["truncated"]),
        truncation_reason=data["truncation_reason"],
        max_steps=int(params["max_steps"]),
        max_states=int(params["max_states"]),
        max_frontier=int(params["max_frontier"]),
    )


def run_document(
    doc: MachineDocument,
    *,
    mode: EvolutionMode = "states",
    max_steps: int = 100,
    max_states: int = 100_000,
    max_frontier: int = 20_000,
    initial: Config | None = None,
) -> Evolution:
    """Evolve a machine document using its stored initial configuration."""
    start = initial or doc.initial
    if start is None:
        raise ValueError("no initial configuration: pass one or store it in the document")
    return evolve(
        doc.machine,
        start,
        mode=mode,
        max_steps=max_steps,
        max_states=max_states,
        max_frontier=max_frontier,
    )


def dumps(data: dict[str, Any]) -> str:
    """Canonical, deterministic JSON text (stable key order as constructed)."""
    return json.dumps(data, indent=1) + "\n"
