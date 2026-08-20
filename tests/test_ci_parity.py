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
