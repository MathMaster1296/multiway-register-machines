"""CLI behavior: run summaries, exports, figures, and error handling."""

import json

import pytest

from mrm.cli import main


def test_run_preset_prints_paths_and_writes_files(tmp_path, capsys):
    json_out = tmp_path / "ev.json"
    dot_out = tmp_path / "ev.dot"
    code = main(["run", "grid_paths", "--analyze", "--json", str(json_out), "--dot", str(dot_out)])
    out = capsys.readouterr().out
    assert code == 0
    assert "paths to terminals" in out and "20" in out
    assert "expected steps = 6" in out
    assert "TRUNCATED" not in out
    assert json.loads(json_out.read_text())["schema"] == "mrm/evolution/1"
    assert "digraph" in dot_out.read_text()


def test_run_reports_truncation(capsys):
    code = main(["run", "collatz", "--max-steps", "5"])
    out = capsys.readouterr().out
    assert code == 0
    assert "TRUNCATED by max_steps" in out
    assert "--max-steps" in out


def test_export_evolution_to_dot(tmp_path, capsys):
    json_out = tmp_path / "ev.json"
    main(["run", "simple", "--json", str(json_out)])
    capsys.readouterr()
    code = main(["export", str(json_out), "--format", "dot"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("digraph")


def test_export_machine_file_evolves_first(tmp_path, capsys):
    machine_file = tmp_path / "machine.json"
    from mrm.presets import load_preset
    from mrm.serialize import dumps, machine_to_json

    machine_file.write_text(dumps(machine_to_json(load_preset("grid_paths"))))
    code = main(["export", str(machine_file), "--format", "wl"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith('<|"Nodes"')


def test_figure_writes_svg(tmp_path, capsys):
    code = main(["figure", "growth", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert (tmp_path / "growth.svg").exists()
    assert "wrote" in out


def test_unknown_target_is_a_clean_error():
    with pytest.raises(SystemExit, match="neither a preset"):
        main(["run", "no_such_preset"])


def test_link_prints_a_decodable_url(capsys):
    from mrm.weblink import decode_fragment

    code = main(["link", "grid_paths", "--max-steps", "9"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    state = decode_fragment(out.partition("#")[2])
    assert state["params"]["max_steps"] == 9
    assert state["preset"] == "grid_paths"


def test_path_prints_rule_sequence_and_causal_summary(capsys):
    code = main(["path", "grid_paths"])
    out = capsys.readouterr().out
    assert code == 0
    assert "shortest path to 1|3,3: 6 steps" in out
    assert "right" in out and "up" in out
    assert "independent chains: 2" in out


def test_path_to_specific_configuration(capsys):
    code = main(["path", "fibonacci", "--to", "1|2"])
    out = capsys.readouterr().out
    assert code == 0
    assert "shortest path to 1|2: 9 steps" in out


def test_ensemble_writes_csv_and_svg(tmp_path, capsys):
    code = main(["ensemble", "--count", "8", "--seed", "2", "--depth", "5", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert (tmp_path / "ensemble.csv").exists()
    assert (tmp_path / "ensemble.svg").exists()
    assert "measured 8 machines" in out
