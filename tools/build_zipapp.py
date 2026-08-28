#!/usr/bin/env python3
"""Build the single-file form: `iirds.pyz`.

Why this exists. The tool is for networks that have no route to the internet,
and `pip install` is the first thing such a network takes away. A wheel still
needs pip, an index or a directory of wheels, and often a virtual environment
and the rights to create one. A `.pyz` needs a copy of the file and a Python.

    python iirds.pyz path/to/package.iirds

Everything is inside it — the checker, the `iirds` library it is built on, and
rdflib — and nothing is
compiled: the same file runs on Linux, macOS and Windows. It is also an ordinary zip: anyone who
has to approve it can open it and read every line, which matters more than
convenience when the approval is the hard part.

    python tools/build_zipapp.py                  # dist/iirds.pyz
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
#: Both first-party packages, copied from the tree rather than installed: the
#: library is not a dependency any more, it is the other half of the same
#: distribution, and pip has nothing to fetch for it.
SOURCES = (ROOT / "src" / "iirds", ROOT / "src" / "iirds_validate")
OUTPUT = ROOT / "dist" / "iirds.pyz"

MAIN = """import sys

from iirds_validate.cli import main

sys.exit(main())
"""

SHEBANG = b"#!/usr/bin/env python3\n"

#: Every entry gets the same timestamp so two builds of one commit, against
#: the same index with the same pip, give the same file. `zipapp.create_archive` uses each
#: file's modification time, and git does not preserve those -- so the archive
#: was reproducible on one machine and nowhere else, which is the half that
#: does not matter. For a shop that has to approve a file before it crosses
#: the air gap, "the hash on the release page is the hash of the file I
#: carried in" is the whole trust story. Override with SOURCE_DATE_EPOCH.
#: (The dependencies' versions are what the index offers on the day; the
#: release workflow proves the two builds it makes agree, and records the
#: hash beside the file.)
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


#: What a ZIP entry can carry. The format keeps the year as an offset from
#: 1980 in seven bits, so anything outside this is not a stamp it can hold --
#: and `SOURCE_DATE_EPOCH=0`, the commonest value a reproducible build is
#: given, is outside it. Clamping keeps the promise the variable makes (two
#: builds of one tree agree) where refusing would break the build instead.
ZIP_EARLIEST = (1980, 1, 1, 0, 0, 0)
ZIP_LATEST = (2107, 12, 31, 23, 59, 58)


def _timestamp():
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        return FIXED_TIMESTAMP
    try:
        stamp = time.gmtime(int(epoch))[:6]
    except (ValueError, OSError, OverflowError):
        # OverflowError is neither of the other two and used to escape: a
        # value large enough gave a year in the millions rather than a stamp.
        return FIXED_TIMESTAMP
    return min(max(stamp, ZIP_EARLIEST), ZIP_LATEST)


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


#: What travels beside the code, read from the same declaration the wheel is
#: built from so the two artefacts cannot carry different terms. Apache-2.0
#: asks that a copy of the licence and the NOTICE go with the work, and the
#: .pyz is the copy that reaches a machine with no index behind it to look
#: anything up in -- every dependency's dist-info is kept here for exactly
#: that reason, and this project's own terms were the ones left behind.
def _licence_files() -> tuple:
    block = re.search(r"^license-files = \[(.*?)\]",
                      (ROOT / "pyproject.toml").read_text("utf-8"), re.M | re.S)
    names = tuple(re.findall(r"""["']([^"']+)["']""", block.group(1))) if block else ()
    # Empty is not "nothing to carry", it is "this stopped being able to read
    # the declaration" -- a glob or a quote style it does not parse leaves an
    # archive with no licence in it and every check about them agreeing green,
    # because they would be agreeing about an empty list.
    assert names, ("pyproject.toml no longer declares license-files in a shape "
                   "this can read; the archive would ship without them")
    return names


REDISTRIBUTED = _licence_files()


def copy_licences(target: Path) -> None:
    """Put them at the root of the archive, where `unzip -l` shows them."""
    for name in REDISTRIBUTED:
        shutil.copy2(ROOT / name, target / name)


def distribution_name(dist_info: str) -> str:
    """`rdflib-7.6.0.dist-info` -> `rdflib`.

    The suffix comes off before the version does. Splitting on the last
    hyphen first leaves `rdflib-7.6.0.dist`, which matches no row in any
    table -- and the test that would have caught it was reading a list of
    names written by hand, so it never ran this at all.
    """
    stem = dist_info[:-len(".dist-info")] if dist_info.endswith(".dist-info") else dist_info
    return stem.rsplit("-", 1)[0]


def unattributed(distributions) -> list:
    """Of these, the ones THIRD_PARTY.md has no row for.

    Asked of what was actually staged, not of what pyproject declares: pip
    brings a dependency's dependencies too, and the table says it lists
    "everything bundled here". Reading the declared list would only ever
    confirm the names somebody had already thought of.
    """
    table = (ROOT / "THIRD_PARTY.md").read_text("utf-8")
    return sorted(name for name in distributions if ("`%s`" % name) not in table)


def copy_sources(target: Path) -> None:
    """Both packages, as they are in `src/`, without any compiled cache."""
    for source in SOURCES:
        shutil.copytree(source, target / source.name,
                        ignore=shutil.ignore_patterns("__pycache__"))


def python_floor(text: str = None) -> str:
    """The oldest Python pyproject says this runs on, as "X.Y"."""
    if text is None:
        text = (ROOT / "pyproject.toml").read_text("utf-8")
    found = re.search(r'^requires-python = ">=([0-9]+\.[0-9]+)"$', text, re.M)
    assert found, ("pyproject.toml no longer declares requires-python as \">=X.Y\"; "
                   "the archive would be resolved for whichever Python built it")
    return found.group(1)


def pip_arguments(target: Path) -> list:
    """How the dependencies are fetched: resolved for the oldest Python this
    runs on, not for the one doing the building.

    rdflib asks for isodate only below 3.11. A build on 3.12 -- the release
    runner -- therefore left it out, and the archive died on 3.9 and 3.10
    with `No module named 'isodate'`: the one file that is supposed to run
    on every Python it names ran on the newest ones. Pinning the resolver to
    the floor puts the floor's closure in the archive; a newer Python simply
    carries a module it does not import. Pure wheels only, which is what
    every dependency here is and what a cross-version resolve requires.
    """
    return [sys.executable, "-m", "pip", "install", "--quiet", "--no-compile",
            "--target", str(target), "--only-binary=:all:",
            "--python-version", python_floor(), *dependencies()]


def _requirement_class():
    # pip carries its own copy of `packaging`; a machine that has pip has it,
    # and a build script that already needs pip may lean on it.
    try:
        from packaging.requirements import Requirement
    except ImportError:  # pragma: no cover - depends on the machine
        from pip._vendor.packaging.requirements import Requirement
    return Requirement


def missing_for_floor(metadata_texts, staged, floor: str) -> list:
    """Of the requirements the staged distributions declare, those the floor
    Python would need and the builder's resolve did not stage.

    `--python-version` steers wheel selection only; a dependency's
    environment markers are evaluated for the Python that runs pip, so a
    marker like `python_version < "3.11"` is false on the release runner
    and true on the floor. Each `Requires-Dist` line is asked again with
    the floor's version in the environment. Extras are never wanted.
    """
    Requirement = _requirement_class()
    environment = {"python_version": floor, "python_full_version": floor + ".0", "extra": ""}
    wanted = []
    for text in metadata_texts:
        for line in text.splitlines():
            if not line.startswith("Requires-Dist:"):
                continue
            requirement = Requirement(line.partition(":")[2].strip())
            if requirement.marker is None or not requirement.marker.evaluate(environment):
                continue
            if requirement.name.lower() in {name.lower() for name in staged}:
                continue
            spec = str(requirement.specifier)
            wanted.append("%s (%s)" % (requirement.name, spec) if spec else requirement.name)
    return sorted(set(wanted))


def _staged_metadata(target: Path):
    return [(path.name[:-len(".dist-info")].rsplit("-", 1)[0], (path / "METADATA").read_text("utf-8"))
            for path in sorted(target.glob("*.dist-info"))]


def complete_for_floor(target: Path) -> None:
    """Install what the floor needs and the builder's Python did not, until
    nothing is missing -- a dependency added this way may declare more."""
    while True:
        staged = _staged_metadata(target)
        wanted = missing_for_floor([text for _, text in staged], {name for name, _ in staged},
                                   python_floor())
        if not wanted:
            return
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-compile",
                        "--target", str(target), "--only-binary=:all:", "--no-deps",
                        "--python-version", python_floor(), *wanted], check=True)


def stage(target: Path) -> None:
    copy_sources(target)
    copy_licences(target)
    subprocess.run(pip_arguments(target), check=True)
    complete_for_floor(target)
    # pip leaves the dependencies' console scripts in bin/, each with the
    # building machine's interpreter path in its first line. The archive has
    # no use for them, and they are why two machines' builds of one commit
    # used to differ.
    shutil.rmtree(target / "bin", ignore_errors=True)
    (target / "__main__.py").write_text(MAIN, "utf-8")

    for cache in target.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    # Keep every dependency's licence. This archive redistributes rdflib and
    # its dependencies, and dropping the dist-info to save a few kilobytes
    # would drop the terms they are redistributed under with it.
    kept = sorted(p.name for p in target.glob("*.dist-info"))
    print("bundled: %s" % ", ".join(kept))
    print("licences: %s" % ", ".join(REDISTRIBUTED))

    # The build is the only place that knows what is really in the archive.
    missing = unattributed(distribution_name(name) for name in kept)
    if missing:
        raise SystemExit(
            "THIRD_PARTY.md has no row for %s, and this archive redistributes "
            "them" % ", ".join(missing))


def inspect(pyz: Path) -> list:
    """What is wrong with the archive as built, read out of the archive.

    Everything else here checks the staging directory, which is a proxy: it
    is what was *meant* to be written. This opens the file that ships and
    asks the two questions a recipient of it can ask -- are the terms it is
    redistributed under in here, and are they where opening it shows them.
    """
    with zipfile.ZipFile(pyz) as archive:
        names = set(archive.namelist())
        empty = {name for name in REDISTRIBUTED
                 if name in names and not archive.read(name).strip()}
    missing = sorted(name for name in REDISTRIBUTED if name not in names)
    return ([f"{name} is not in the archive" for name in missing]
            + [f"{name} is in the archive and empty" for name in sorted(empty)])


def smoke(pyz: Path) -> int:
    """Run it the way a locked-down machine would: no site-packages, no path."""
    problems = inspect(pyz)
    for problem in problems:
        print("archive: %s" % problem, file=sys.stderr)
    if problems:
        return 1
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
    modules = [re.match(r"[A-Za-z0-9_-]+", spec).group(0) for spec in dependencies()]
    modules += [source.name for source in SOURCES]
    for module in modules:
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
