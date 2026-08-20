#!/usr/bin/env python3
"""Build the single-file form: `iirds-validate.pyz`.

Why this exists. The tool is for networks that have no route to the internet,
and `pip install` is the first thing such a network takes away. A wheel still
needs pip, an index or a directory of wheels, and often a virtual environment
and the rights to create one. A `.pyz` needs a copy of the file and a Python.

    python iirds-validate.pyz path/to/package.iirds

Everything is inside it, rdflib included, and nothing is compiled — the same
file runs on Linux, macOS and Windows. It is also an ordinary zip: anyone who
has to approve it can open it and read every line, which matters more than
convenience when the approval is the hard part.

    python tools/build_zipapp.py                  # dist/iirds-validate.pyz
    python tools/build_zipapp.py --check          # build and smoke-test it

Requires network access once, to fetch the dependencies being bundled.
"""
from __future__ import annotations

import argparse
import compileall  # noqa: F401  (documents the deliberate choice not to use it)
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipapp
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "iirds_validate"
OUTPUT = ROOT / "dist" / "iirds-validate.pyz"

MAIN = """import sys

from iirds_validate.cli import main

sys.exit(main())
"""


def stage(target: Path) -> None:
    shutil.copytree(SOURCE, target / "iirds_validate")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-compile",
                    "--target", str(target), "rdflib"], check=True)
    (target / "__main__.py").write_text(MAIN, "utf-8")

    for cache in target.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    # Keep every dependency's licence. This archive redistributes rdflib and
    # its dependencies, and dropping the dist-info to save a few kilobytes
    # would drop the terms they are redistributed under with it.
    kept = sorted(p.name for p in target.glob("*.dist-info"))
    print("bundled: %s" % ", ".join(kept))


def smoke(pyz: Path) -> int:
    """Run it the way a locked-down machine would: no site-packages, no path."""
    fixture = Path(tempfile.mkdtemp()) / "smoke.iirds"
    sys.path.insert(0, str(ROOT / "tools"))
    from make_fixture_package import build_package
    build_package(fixture.parent, fixture.name)

    checks = [
        (["--version"], "version"),
        ([str(fixture)], "validating a package"),
    ]
    for argv, what in checks:
        result = subprocess.run([sys.executable, "-S", str(pyz), *argv],
                                capture_output=True, text=True)
        if result.returncode not in (0, 1):
            print("smoke test failed (%s): %s%s" % (what, result.stdout, result.stderr),
                  file=sys.stderr)
            return 1
        print("  ok: %s" % what)

    # The point of the exercise: it must not need anything installed.
    probe = subprocess.run([sys.executable, "-S", "-c", "import rdflib"],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        print("  note: rdflib is importable without the archive, so this run does not "
              "prove self-containment", file=sys.stderr)
    else:
        print("  ok: rdflib came from inside the archive")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", default=str(OUTPUT))
    ap.add_argument("--check", action="store_true", help="smoke-test the result")
    args = ap.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="iirds-zipapp-"))
    try:
        stage(staging)
        zipapp.create_archive(staging, target=str(output),
                              interpreter="/usr/bin/env python3", compressed=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    entries = len(zipfile.ZipFile(output).namelist())
    print("%s  %.0f KB, %d entries" % (output, output.stat().st_size / 1024, entries))
    print("sha256 %s" % digest)

    return smoke(output) if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
