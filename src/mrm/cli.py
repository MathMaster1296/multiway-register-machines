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
from .causal import causal_analysis
from .counting import PathCount, terminal_path_counts
from .ensemble import ensemble, to_csv
from .evolve import Evolution, EvolutionMode, TerminalKind
from .export import to_dot, to_graphml, to_wl
from .figures import make_figure, scatter_svg
from .graph import shortest_edge_path
from .machine import Config
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
from .weblink import explorer_link


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


def _cmd_link(args: argparse.Namespace) -> int:
    doc = _load_target(args.target)
    preset = args.target if args.target in available_presets() else None
    print(
        explorer_link(
            doc,
            mode=args.mode,
            max_steps=args.max_steps,
            max_states=args.max_states,
            max_frontier=args.max_frontier,
            preset=preset,
            base=args.base,
        )
    )
    return 0


def _parse_config(text: str) -> Config:
    pc_text, _, regs_text = text.replace(":", "|").partition("|")
    registers = tuple(int(r) for r in regs_text.split(",") if r.strip() != "")
    return Config(int(pc_text), registers)


def _cmd_path(args: argparse.Namespace) -> int:
    doc = _load_target(args.target)
    ev = run_document(
        doc,
        mode="states",
        max_steps=args.max_steps,
        max_states=args.max_states,
        max_frontier=args.max_frontier,
    )
    if args.to:
        wanted = _parse_config(args.to)
        matches = [n for n, c in ev.nodes.items() if c == wanted]
        if not matches:
            raise SystemExit(f"error: {args.to!r} was not reached within the caps")
        target = matches[0]
    else:
        halts = [n for n, k in ev.terminals.items() if k is TerminalKind.HALT]
        terminals = halts or list(ev.terminals)
        if not terminals:
            raise SystemExit("error: no terminal configuration was reached; try --to")
        target = terminals[0]
    path = shortest_edge_path(ev, target)
    if path is None:
        raise SystemExit(f"error: node {target} is unreachable")

    def label(n: int) -> str:
        config = ev.nodes[n]
        return f"{config.pc}|{','.join(map(str, config.registers))}"

    print(f"shortest path to {label(target)}: {len(path)} steps")
    for i, edge in enumerate(path, start=1):
        print(f"  {i:>3}. {edge.rule_id:<10} {label(edge.src)} -> {label(edge.dst)}")
    summary = causal_analysis(ev.machine, path)
    print(
        f"data dependencies: {len(summary.dependencies)}  "
        f"independent chains: {summary.chains}  "
        f"longest chain: {summary.longest_chain}"
    )
    banner = _truncation_banner(ev)
    if banner:
        print(banner)
    return 0


def _cmd_ensemble(args: argparse.Namespace) -> int:
    rows = ensemble(
        args.count,
        seed=args.seed,
        length=args.length,
        n_registers=args.registers,
        depth=args.depth,
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ensemble.csv").write_text(to_csv(rows))
    caption = f"{args.count} random machines: the complexity measure against realized branching"
    (out / "ensemble.svg").write_text(scatter_svg(rows, caption))
    alive = [row for row in rows if row.mean_branching > 0]
    print(f"measured {len(rows)} machines ({len(alive)} survive step 0)")
    if len(alive) >= 2:
        mean_x = sum(r.complexity for r in alive) / len(alive)
        mean_y = sum(r.mean_branching for r in alive) / len(alive)
        cov = sum((r.complexity - mean_x) * (r.mean_branching - mean_y) for r in alive)
        var_x = sum((r.complexity - mean_x) ** 2 for r in alive)
        var_y = sum((r.mean_branching - mean_y) ** 2 for r in alive)
        if var_x > 0 and var_y > 0:
            print(f"correlation among survivors: r = {cov / (var_x * var_y) ** 0.5:.3f}")
    print(f"wrote {out / 'ensemble.csv'} and {out / 'ensemble.svg'}")
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

    link = sub.add_parser("link", help="print a link that reopens this machine in the explorer")
    link.add_argument("target", help="preset name or path to a machine.json")
    link.add_argument("--mode", choices=["states", "tree"], default="states")
    link.add_argument("--max-steps", type=int, default=60)
    link.add_argument("--max-states", type=int, default=20_000)
    link.add_argument("--max-frontier", type=int, default=10_000)
    link.add_argument(
        "--base",
        default="https://mathmaster1296.github.io/multiway-register-machines/",
        help="explorer URL to link into",
    )
    link.set_defaults(func=_cmd_link)

    path = sub.add_parser("path", help="shortest rule path to a configuration, with causal summary")
    path.add_argument("target", help="preset name or path to a machine.json")
    path.add_argument("--to", help='target configuration, written like "pc|r1,r2"')
    path.add_argument("--max-steps", type=int, default=100)
    path.add_argument("--max-states", type=int, default=100_000)
    path.add_argument("--max-frontier", type=int, default=20_000)
    path.set_defaults(func=_cmd_path)

    ens = sub.add_parser("ensemble", help="measure random machines: complexity vs branching")
    ens.add_argument("--count", type=int, default=150)
    ens.add_argument("--seed", type=int, default=1)
    ens.add_argument("--length", type=int, default=4)
    ens.add_argument("--registers", type=int, default=2)
    ens.add_argument("--depth", type=int, default=8)
    ens.add_argument("--out", required=True, help="output directory for csv and svg")
    ens.set_defaults(func=_cmd_ensemble)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        # Downstream closed early (mrm ... | head); that is not an error.
        import os

        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
