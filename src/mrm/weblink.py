"""Shareable links into the browser explorer.

The explorer keeps its whole state (machine document plus evolution
parameters) in the URL hash, deflate-compressed and base64url-encoded. This
module produces the same tokens from Python, so a figure in the paper can
carry a link that reopens the exact view that produced it:

    mrm link fibonacci --max-steps 40

The encoding must stay in lockstep with ``web/src/urlstate.ts``: raw
deflate (no zlib header) and unpadded base64url, decoded in the browser by
``DecompressionStream("deflate-raw")``.
"""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any

from .serialize import MachineDocument, machine_to_json

SITE = "https://mathmaster1296.github.io/multiway-register-machines/"


def app_state(
    doc: MachineDocument,
    *,
    mode: str = "states",
    max_steps: int = 60,
    max_states: int = 20_000,
    max_frontier: int = 10_000,
    preset: str | None = None,
) -> dict[str, Any]:
    """The AppState object the page stores in its URL."""
    return {
        "doc": machine_to_json(doc),
        "params": {
            "mode": mode,
            "max_steps": max_steps,
            "max_states": max_states,
            "max_frontier": max_frontier,
            "analyze": True,
        },
        "preset": preset,
    }


def encode_fragment(state: dict[str, Any]) -> str:
    """Compress and encode a state object into a URL fragment token."""
    raw = json.dumps(state, separators=(",", ":")).encode()
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = compressor.compress(raw) + compressor.flush()
    return base64.urlsafe_b64encode(packed).decode().rstrip("=")


def decode_fragment(token: str) -> dict[str, Any]:
    """Invert `encode_fragment` (also accepts tokens minted by the page)."""
    padded = token + "=" * (-len(token) % 4)
    packed = base64.urlsafe_b64decode(padded)
    raw = zlib.decompress(packed, wbits=-15)
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("fragment does not hold an explorer state object")
    return result


def explorer_link(
    doc: MachineDocument,
    *,
    mode: str = "states",
    max_steps: int = 60,
    max_states: int = 20_000,
    max_frontier: int = 10_000,
    preset: str | None = None,
    base: str = SITE,
) -> str:
    """A link that reopens the explorer on exactly this machine and settings."""
    state = app_state(
        doc,
        mode=mode,
        max_steps=max_steps,
        max_states=max_states,
        max_frontier=max_frontier,
        preset=preset,
    )
    return base + "#" + encode_fragment(state)
