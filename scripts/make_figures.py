"""Regenerate every paper figure. Usage: python scripts/make_figures.py [OUT_DIR]"""

import sys
from pathlib import Path

from mrm.figures import make_figure

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("figures")
for path in make_figure("all", out):
    print(f"wrote {path}")
