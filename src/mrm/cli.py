"""The ``mrm`` command line interface.

Subcommands: ``run`` (evolve a preset or machine.json), ``verify`` (the
invariant suite, exits nonzero on failure), ``export`` (DOT, GraphML, WL, or
evolution JSON), and ``figure`` (reproducible SVG figures).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from .analysis import absorption
from .counting import PathCount, terminal_path_counts
from .evolve import Evolution, EvolutionMode, TerminalKind
from .export import to_dot, to_graphml, to_wl
from .figures import make_figure
from .presets import available_presets, load_preset
from .serialize import (
    MachineDocument,
    dumps,
    evolution_from_json,
    evolution_to_json,
    machine_from_json,
    run_document,
)
from .verification import format_table, run_all_checks


def _load_target(target: str) -> MachineDocument:
    if target in available_presets():
        return load_preset(target)
    path = Path(target)
    if not path.exists():
        raise SystemExit(
            f"error: {target!r} is neither a preset ({', '.join(available_presets())}) nor a file"
        )
    return machine_from_json(json.loads(path.read_text()))


def _truncation_banner(ev: Evolution) -> str | None:
    if not ev.truncated:
        return None
    knob = {
        "max_steps": "--max-steps",
        "max_states": "--max-states",
        "max_frontier": "--max-frontier",
    }.get(ev.truncation_reason or "", "the caps")
    return (
        f"TRUNCATED by {ev.truncation_reason}: this is a prefix of the evolution,"
        f" not the whole thing. Raise {knob} to see more."
    )


def _summarize(ev: Evolution, analyze: bool) -> str:
    kinds = {kind: 0 for kind in TerminalKind}
    for kind in ev.terminals.values():
        kinds[kind] += 1
    lines = [
        f"mode={ev.mode}  nodes={len(ev.nodes)}  edges={len(ev.edges)}  layers={len(ev.layers)}",
        f"terminals: halt={kinds[TerminalKind.HALT]}"
        f" stuck={kinds[TerminalKind.STUCK]} cutoff={kinds[TerminalKind.CUTOFF]}",
        f"growth: {ev.growth_series()}",
    ]
    counts = terminal_path_counts(ev)
    if counts:
        rendered = ", ".join(
            f"node {n} {ev.nodes[n].pc}|{ev.nodes[n].registers} -> "
            + ("infinite" if isinstance(c, PathCount) else str(c))
            for n, c in counts.items()
        )
        lines.append(f"paths to terminals: {rendered}")
    if analyze:
        result = absorption(ev)
        lines.append(
            f"absorption: halting probability = {result.halting_probability},"
            f" never halting = {result.never_halting},"
            f" unresolved = {result.unresolved},"
            f" expected steps = {result.expected_steps}"
        )
    banner = _truncation_banner(ev)
    if banner:
        lines.append(banner)
    return "\n".join(lines)


def _cmd_run(args: argparse.Namespace) -> int:
    doc = _load_target(args.target)
    ev = run_document(
        doc,
        mode=cast(EvolutionMode, args.mode),
        max_steps=args.max_steps,
        max_states=args.max_states,
        max_frontier=args.max_frontier,
    )
    title = doc.name or args.target
    print(f"{args.target}: {title}")
    print(_summarize(ev, analyze=args.analyze))
    if args.json:
        Path(args.json).write_text(dumps(evolution_to_json(ev)))
        print(f"wrote {args.json}")
    if args.dot:
        Path(args.dot).write_text(to_dot(ev))
        print(f"wrote {args.dot}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    checks = run_all_checks()
    print(format_table(checks, full=args.full))
    return 0 if all(c.ok for c in checks) else 1


def _cmd_export(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.file).read_text())
    schema = data.get("schema")
    if schema == "mrm/evolution/1":
        ev = evolution_from_json(data)
    elif schema == "mrm/machine/1":
        ev = run_document(machine_from_json(data))
    else:
        raise SystemExit(f"error: unrecognized schema {schema!r} in {args.file}")
    banner = _truncation_banner(ev)
    if banner:
        print(banner, file=sys.stderr)
    content = {
        "json": lambda: dumps(evolution_to_json(ev)),
        "dot": lambda: to_dot(ev),
        "graphml": lambda: to_graphml(ev),
        "wl": lambda: to_wl(ev),
    }[args.format]()
    if args.out:
        Path(args.out).write_text(content)
        print(f"wrote {args.out}")
    else:
        print(content, end="")
    return 0


def _cmd_figure(args: argparse.Namespace) -> int:
    for path in make_figure(args.name, Path(args.out)):
        print(f"wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mrm", description="Multiway register machine explorer")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="evolve a preset or machine.json file")
    run.add_argument("target", help="preset name or path to a machine.json")
    run.add_argument("--mode", choices=["states", "tree"], default="states")
    run.add_argument("--max-steps", type=int, default=100)
    run.add_argument("--max-states", type=int, default=100_000)
    run.add_argument("--max-frontier", type=int, default=20_000)
    run.add_argument("--json", help="write the evolution as JSON to this path")
    run.add_argument("--dot", help="write the graph as DOT to this path")
    run.add_argument(
        "--analyze",
        action="store_true",
        help="also compute exact halting probabilities and expected steps",
    )
    run.set_defaults(func=_cmd_run)

    verify = sub.add_parser("verify", help="run all model invariants")
    verify.add_argument("--full", action="store_true", help="one row per check")
    verify.set_defaults(func=_cmd_verify)

    export = sub.add_parser("export", help="convert a machine or evolution file")
    export.add_argument("file", help="machine.json or evolution.json")
    export.add_argument("--format", required=True, choices=["json", "dot", "graphml", "wl"])
    export.add_argument("--out", help="output path (default: stdout)")
    export.set_defaults(func=_cmd_export)

    figure = sub.add_parser("figure", help="regenerate a paper figure")
    figure.add_argument("name", help="figure name, or 'all'")
    figure.add_argument("--out", required=True, help="output directory")
    figure.set_defaults(func=_cmd_figure)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
