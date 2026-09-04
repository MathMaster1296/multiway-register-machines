"""Assemble the static explorer site into web/dist.

Expects the TypeScript to be compiled already (``npm run build`` in web/)
and a wheel to exist in dist/. Copies the page, styles, compiled modules,
preset machine files, and the wheel, and writes the manifest files the page
fetches at startup. Usage: python scripts/build_site.py [OUT_DIR]
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PRESETS = ROOT / "src" / "mrm" / "presets"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else WEB / "dist"
    if not (WEB / "js" / "main.js").exists():
        raise SystemExit("error: compile the TypeScript first (npm run build in web/)")
    wheels = sorted((ROOT / "dist").glob("mrm-*-py3-none-any.whl"))
    if not wheels:
        raise SystemExit("error: no wheel in dist/; run python -m build first")
    wheel = wheels[-1]

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Cache busting without a bundler: every build's modules live in a
    # content-hashed directory, so a new page version can never mix with
    # stale cached modules; relative imports keep working inside it.
    digest = hashlib.sha256()
    for path in sorted((WEB / "js").glob("*.js")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    digest.update((WEB / "static" / "styles.css").read_bytes())
    stamp = digest.hexdigest()[:10]

    html = (WEB / "index.html").read_text()
    html = html.replace('src="js/main.js"', f'src="js-{stamp}/main.js"')
    html = html.replace('href="static/styles.css"', f'href="static/styles.css?v={stamp}"')
    (out / "index.html").write_text(html)
    shutil.copytree(WEB / "static", out / "static")
    shutil.copytree(WEB / "js", out / f"js-{stamp}")

    presets_out = out / "public" / "presets"
    presets_out.mkdir(parents=True)
    sys.path.insert(0, str(ROOT / "src"))
    from mrm.presets import PRESET_ORDER

    manifest = []
    for path in PRESETS.glob("*.json"):
        shutil.copy2(path, presets_out / path.name)
    for name in PRESET_ORDER:
        data = json.loads((PRESETS / f"{name}.json").read_text())
        manifest.append(
            {
                "id": name,
                "name": data.get("name", name),
                "description": data.get("description", ""),
            }
        )
    (presets_out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")

    wheels_out = out / "public" / "wheels"
    wheels_out.mkdir(parents=True)
    shutil.copy2(wheel, wheels_out / wheel.name)
    (out / "public" / "site-meta.json").write_text(json.dumps({"wheel": wheel.name}) + "\n")
    print(f"assembled {out} (wheel: {wheel.name})")


if __name__ == "__main__":
    main()
