"""Export evolutions to DOT, GraphML, and Wolfram Language text.

All output is deterministic: nodes in id order, edges in discovery order.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from .evolve import Evolution
from .machine import Config


def _label(config: Config) -> str:
    registers = ", ".join(str(r) for r in config.registers)
    return f"{config.pc} | ({registers})"


def to_dot(ev: Evolution) -> str:
    """Graphviz DOT with rule ids as edge labels."""
    lines = ["digraph mrm {", "  rankdir=TB;", '  node [shape=box, fontname="monospace"];']
    for node_id, config in ev.nodes.items():
        lines.append(f'  n{node_id} [label="{node_id}: {_label(config)}"];')
    for edge in ev.edges:
        lines.append(f'  n{edge.src} -> n{edge.dst} [label="{edge.rule_id}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_graphml(ev: Evolution) -> str:
    """GraphML with pc, registers, and rule id attributes."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="pc" for="node" attr.name="pc" attr.type="int"/>',
        '  <key id="registers" for="node" attr.name="registers" attr.type="string"/>',
        '  <key id="rule" for="edge" attr.name="rule" attr.type="string"/>',
        '  <graph id="mrm" edgedefault="directed">',
    ]
    for node_id, config in ev.nodes.items():
        registers = ",".join(str(r) for r in config.registers)
        lines.append(f'    <node id="n{node_id}">')
        lines.append(f'      <data key="pc">{config.pc}</data>')
        lines.append(f'      <data key="registers">{escape(registers)}</data>')
        lines.append("    </node>")
    for i, edge in enumerate(ev.edges):
        lines.append(f'    <edge id="e{i}" source="n{edge.src}" target="n{edge.dst}">')
        lines.append(f"      <data key={quoteattr('rule')}>{escape(edge.rule_id)}</data>")
        lines.append("    </edge>")
    lines.extend(["  </graph>", "</graphml>"])
    return "\n".join(lines) + "\n"


def to_wl(ev: Evolution) -> str:
    """A Wolfram Language association mirroring the WFR conventions.

    ``Nodes`` maps ids to ``{pc, {registers}}`` states, ``Edges`` lists
    ``{src, dst, rule}`` triples, and ``Layers`` is the layer index, so the
    result can be checked against ``MultiwayRegisterMachine`` output directly.
    """
    nodes = ", ".join(
        f"{node_id} -> {{{config.pc}, {{{', '.join(str(r) for r in config.registers)}}}}}"
        for node_id, config in ev.nodes.items()
    )
    edges = ", ".join(f'{{{edge.src}, {edge.dst}, "{edge.rule_id}"}}' for edge in ev.edges)
    layers = ", ".join("{" + ", ".join(str(n) for n in layer) + "}" for layer in ev.layers)
    return f'<|"Nodes" -> <|{nodes}|>, "Edges" -> {{{edges}}}, "Layers" -> {{{layers}}}|>\n'
