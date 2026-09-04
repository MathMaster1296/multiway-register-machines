"""Exports, deterministic layout, and figure generation."""

import xml.etree.ElementTree as ET

from mrm import Config, evolve, layered_layout, machine_from_wfr
from mrm.builders import grid_paths_machine
from mrm.export import to_dot, to_graphml, to_wl
from mrm.figures import FIGURES, make_figure


def tiny():
    return evolve(machine_from_wfr([[1, 0, [2]], [1, 0, [1, 5]]], 1), Config(1, (0,)), max_steps=3)


def test_dot_contains_nodes_edges_and_labels():
    dot = to_dot(tiny())
    assert "digraph mrm" in dot
    assert 'n1 [label="1: 1 | (0)"]' in dot
    assert 'n1 -> n2 [label="i1s1"]' in dot
    assert to_dot(tiny()) == dot


def test_graphml_is_well_formed_xml():
    xml = to_graphml(tiny())
    root = ET.fromstring(xml)
    assert root.tag.endswith("graphml")
    assert xml.count("<node ") == len(tiny().nodes)


def test_wl_export_mirrors_wfr_shapes():
    wl = to_wl(tiny())
    assert '"Nodes" -> <|1 -> {1, {0}}' in wl
    assert '{1, 2, "i1s1"}' in wl
    assert '"Layers" ->' in wl


def test_layout_is_deterministic_and_layered():
    ev = evolve(grid_paths_machine(3, 3), Config(1, (0, 0)))
    first = layered_layout(ev)
    second = layered_layout(ev)
    assert first == second
    assert set(first) == set(ev.nodes)
    for r, layer in enumerate(ev.layers):
        ys = {first[n][1] for n in layer}
        assert ys == {float(r)}
        xs = [first[n][0] for n in layer]
        assert len(set(xs)) == len(xs)


def test_figures_render_valid_svg(tmp_path):
    written = make_figure("all", tmp_path)
    assert len(written) >= len(FIGURES)
    for path in written:
        root = ET.fromstring(path.read_text())
        assert root.tag.endswith("svg")


def test_figures_are_reproducible(tmp_path):
    first = {p.name: p.read_text() for p in make_figure("all", tmp_path / "a")}
    second = {p.name: p.read_text() for p in make_figure("all", tmp_path / "b")}
    assert first == second


def test_rule_and_circle_plots_render(tmp_path):
    written = {p.name for p in make_figure("rule-diagrams", tmp_path)}
    assert written == {"collatz-rule-plot.svg", "collatz-circle-plot.svg"}
    for path in tmp_path.iterdir():
        root = ET.fromstring(path.read_text())
        assert root.tag.endswith("svg")


def test_animated_reveal_contains_keyframes(tmp_path):
    (path,) = make_figure("fibonacci-reveal", tmp_path)
    text = path.read_text()
    assert "@keyframes reveal0" in text
    assert 'class="layer0"' in text
    ET.fromstring(text)
