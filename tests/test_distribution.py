"""What `pip` sees: one distribution named after the standard, and one command
that answers to three names.

The validator shipped as `iirds-validate` and the library as `iirds`; from
0.5.0 they are one distribution, and its name is the standard's. The two old
command names stay as aliases of the one command, so nothing anybody typed
stops working.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = (ROOT / "pyproject.toml").read_text("utf-8")

ENTRY = "iirds_validate.cli:main"


def _table(name: str) -> str:
    block = re.search(r"^\[%s\]\n(.*?)(?=^\[|\Z)" % re.escape(name), PYPROJECT, re.M | re.S)
    assert block, "pyproject.toml has no [%s] table" % name
    return block.group(1)


def test_the_distribution_is_named_after_the_standard():
    assert re.search(r'^name = "iirds"$', PYPROJECT, re.M), "the distribution is not `iirds`"


def test_one_command_answers_to_three_names():
    scripts = dict(re.findall(r'^([\w-]+) = "([^"]+)"$', _table("project.scripts"), re.M))
    assert scripts == {"iirds": ENTRY, "iirds-validate": ENTRY, "iirdsv": ENTRY}, scripts


def test_the_only_runtime_dependency_is_rdflib():
    """Stated here as well as by the library's own sweep: the checker adds
    nothing to what the library needs."""
    assert re.search(r'^dependencies = \["rdflib>=6"\]$', PYPROJECT, re.M)
