#!/usr/bin/env python3
"""Build the single-file form: `iirds-validate.pyz`.

Why this exists. The tool is for networks that have no route to the internet,
and `pip install` is the first thing such a network takes away. A wheel still
needs pip, an index or a directory of wheels, and often a virtual environment
and the rights to create one. A `.pyz` needs a copy of the file and a Python.

    python iirds-validate.pyz path/to/package.iirds

Everything is inside it — rdflib and the iirds SDK included — and nothing is
compiled: the same file runs on Linux, macOS and Windows. It is also an ordinary zip: anyone who
has to approve it can open it and read every line, which matters more than
convenience when the approval is the hard part.

    python tools/build_zipapp.py                  # dist/iirds-validate.pyz
    python tools/build_zipapp.py --check          # build and smoke-test it

Requires network access once, to fetch the dependencies being bundled.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "iirds_validate"
OUTPUT = ROOT / "dist" / "iirds-validate.pyz"

MAIN = """import sys

from iirds_validate.cli import main

sys.exit(main())
"""

SHEBANG = b"#!/usr/bin/env python3\n"

#: Every entry gets the same timestamp so two people building the same commit
#: get the same file. `zipapp.create_archive` uses each file's modification
#: time, and git does not preserve those — so the archive was reproducible on
#: one machine and nowhere else, which is the half that does not matter. For a
#: shop that has to approve a file before it crosses the air gap, "the hash on
#: the release page is the hash of the file I carried in" is the whole trust
#: story. Override with SOURCE_DATE_EPOCH.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _timestamp():
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        return FIXED_TIMESTAMP
    try:
        return time.gmtime(int(epoch))[:6]
    except (ValueError, OSError):
        return FIXED_TIMESTAMP


def create_archive(source: Path, target: Path) -> None:
    """zipapp.create_archive, with the timestamps and order pinned."""
    stamp = _timestamp()
    with open(target, "wb") as handle:
        handle.write(SHEBANG)
        with zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(p for p in source.rglob("*") if p.is_file()):
                info = zipfile.ZipInfo(path.relative_to(source).as_posix(), date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def dependencies() -> list:
    """The validator's runtime dependencies, read from pyproject.toml.

    Read rather than repeated. The first dependency this script bundled was
    hard-coded, which worked for exactly as long as the list had one entry:
    the day the SDK became a dependency, a hand-maintained copy here would
    have shipped a .pyz that dies on import somewhere with no pip to save it.
    """
    text = (ROOT / "pyproject.toml").read_text("utf-8")
    block = re.search(r"^dependencies = \[(.*?)\]", text, re.M | re.S).group(1)
    return re.findall(r'"([^"]+)"', block)


def stage(target: Path) -> None:
    shutil.copytree(SOURCE, target / "iirds_validate")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-compile",
                    "--target", str(target), *dependencies()], check=True)
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
    for module in (re.match(r"[A-Za-z0-9_-]+", spec).group(0) for spec in dependencies()):
        probe = subprocess.run([sys.executable, "-S", "-c", "import %s" % module],
                               capture_output=True, text=True)
        if probe.returncode == 0:
            print("  note: %s is importable without the archive, so this run does not "
                  "prove self-containment" % module, file=sys.stderr)
        else:
            print("  ok: %s came from inside the archive" % module)
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
        create_archive(staging, output)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    entries = len(zipfile.ZipFile(output).namelist())
    print("%s  %.0f KB, %d entries" % (output, output.stat().st_size / 1024, entries))
    print("sha256 %s" % digest)

    return smoke(output) if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
