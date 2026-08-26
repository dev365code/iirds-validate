"""`make check` and CI must run the same commands.

Three red builds in this project came from the same shape of mistake: a check
that existed in one place and not the other. `make check` was created to close
that, and within a day of its creation two gates had been added to it that CI
did not run -- so the Makefile said the tree was good and CI was not asking.

The failure is quiet in the dangerous direction. A gate only in CI is noisy and
gets fixed. A gate only in the Makefile means CI is not checking something
somebody believes it checks, and nothing says so.

This is a text comparison, not a build system, on purpose: something that
understands both files would be a third thing to keep in step.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = (ROOT / "Makefile").read_text("utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")

#: Commands `make check` runs that CI is not expected to, with the reason.
#: Empty today. An entry here is a deliberate exemption and needs justifying.
LOCAL_ONLY: dict = {}


def _check_targets():
    """The targets `check:` depends on, in order."""
    line = re.search(r"^check:(.*)$", MAKEFILE, re.M)
    assert line, "the Makefile has no check target"
    return line.group(1).split()


def _commands_of(target: str):
    """The $(PYTHON) recipe lines of one target."""
    body = re.search(r"^%s:.*?\n((?:\t.*\n|\n)*)" % re.escape(target), MAKEFILE, re.M)
    if not body:
        return []
    out = []
    for raw in body.group(1).splitlines():
        stripped = raw.strip()
        if stripped.startswith("$(PYTHON)"):
            out.append(stripped.replace("$(PYTHON)", "").strip())
    return out


def _normalise(command: str) -> str:
    """What the command is, ignoring how the interpreter is spelled.

    CI reaches for `/tmp/v/bin/python` in the installed-wheel job and plain
    `python` elsewhere; the Makefile uses `$(PYTHON)`. None of that is the
    thing being compared.
    """
    command = command.replace("-m pytest", "pytest").replace("-m ruff", "ruff")
    return re.sub(r"\s+", " ", command).strip()


CHECKS = [(target, _normalise(command))
          for target in _check_targets()
          for command in _commands_of(target)
          if "$@" not in command]           # fixture-building recipes, not gates


def test_the_check_target_has_recipes_to_compare():
    assert len(CHECKS) >= 8, CHECKS


@pytest.mark.parametrize("target,command", CHECKS, ids=[c for _t, c in CHECKS])
def test_ci_runs_everything_make_check_runs(target, command):
    if command in LOCAL_ONLY:
        pytest.skip(LOCAL_ONLY[command])
    assert command in _normalise(WORKFLOW), \
        "`make %s` runs %r and no CI job does" % (target, command)


# ---------------------------------------------------------------------------
# The platforms the README names are the platforms CI runs
#
# The same shape of mistake one level out: a claim that exists in one place and
# a check that exists in another. The badge line names three operating systems
# and the matrix ran two, and nothing said so -- the tool does work on the
# third, which is exactly why nobody would have noticed it going wrong.
# ---------------------------------------------------------------------------

#: What a runner label calls each of them.
RUNNERS = {"Linux": "ubuntu", "macOS": "macos", "Windows": "windows"}


def claimed_platforms():
    """The operating systems README.md tells a reader this runs on."""
    badge = re.search(r"(?m)^&nbsp;\*\*Apache-2\.0\*\*.*$",
                      (ROOT / "README.md").read_text("utf-8"))
    assert badge, "README.md no longer carries the badge line in the expected shape"
    return sorted(name for name in RUNNERS if name in badge.group(0))


def test_the_readme_names_the_platforms_ci_actually_runs():
    named = claimed_platforms()
    assert named, "the badge line names no operating system at all"
    missing = sorted(name for name in named if RUNNERS[name] not in WORKFLOW)
    assert missing == [], (
        "README.md says this runs on %s and no CI row does: a claim nobody "
        "checks is a claim that goes wrong quietly" % ", ".join(missing))


def test_make_actually_switches_the_differential_gate_on():
    """conftest.shacl_or_skip reads IIRDS_REQUIRE_SHACL and turns a missing
    pyshacl from a skip into a failure. It was read in one place and set in
    none: the commit that added it said "under make the absence is now a
    failure", and it was not. A gate whose switch nobody checks is a gate
    that is off, so the switch is checked here."""
    assert re.search(r"(?m)^export IIRDS_REQUIRE_SHACL\s*:?=\s*1\s*$", MAKEFILE), (
        "the Makefile does not export IIRDS_REQUIRE_SHACL, so `make check` "
        "skips the differential gate in silence when pyshacl is absent")


def test_make_dev_installs_what_make_check_requires():
    """Requiring it is only reasonable if `make dev` provides it."""
    assert "pyshacl" in MAKEFILE, "make dev does not install pyshacl"
