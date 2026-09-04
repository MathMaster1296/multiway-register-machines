"""Explorer permalinks: the Python encoder mirrors the site's URL codec."""

from mrm import decode_fragment, explorer_link
from mrm.presets import load_preset
from mrm.serialize import machine_to_json
from mrm.weblink import app_state, encode_fragment


def test_round_trip_restores_the_state():
    doc = load_preset("grid_paths")
    state = app_state(doc, mode="tree", max_steps=12, preset="grid_paths")
    token = encode_fragment(state)
    assert decode_fragment(token) == state


def test_link_shape_and_charset():
    doc = load_preset("fibonacci")
    link = explorer_link(doc, preset="fibonacci")
    base, _, token = link.partition("#")
    assert base.endswith("/multiway-register-machines/")
    assert token
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert set(token) <= allowed


def test_state_carries_the_full_document_and_params():
    doc = load_preset("simple")
    state = decode_fragment(explorer_link(doc, max_steps=7).partition("#")[2])
    assert state["doc"] == machine_to_json(doc)
    assert state["params"]["max_steps"] == 7
    assert state["params"]["analyze"] is True
    assert state["preset"] is None
