"""One container layer, two projects, held together by `is`.

The validator wrote the metadata guards, the parser and the merge; they
moved to the iirds SDK so every tool shares them; the validator imports
them back. Equality tests would pass against a drifted fork -- these pin
object identity, so the seam cannot reopen without failing loudly.

Identity holds the seam shut. It says nothing about *which copy* of the
SDK was on the other side of it, and until the last two tests here that
was never asked -- so a green run was a fact about the machine rather
than about the commit. The two projects are repaired together, and the
suite that exercises the pair is this one.
"""
import os
import re
from pathlib import Path

import iirds
import pytest

from iirds_validate import context, model

ROOT = Path(__file__).resolve().parents[1]


def test_the_shared_constants_are_the_same_objects():
    assert context.MAX_METADATA_BYTES is iirds.MAX_METADATA_BYTES
    assert model.PACKAGE_BASE is iirds.PACKAGE_BASE
    assert model.METADATA_RDF is iirds.METADATA_RDF
    assert model.METADATA_JSONLD is iirds.METADATA_JSONLD


def test_the_shared_functions_are_the_same_objects():
    assert context.parse_metadata is iirds.parse_metadata
    assert context.merge_sources is iirds.merge_sources
    assert context.subclasses_of is iirds.subclasses_of


def test_the_error_string_contract_routes_findings():
    """The runner partitions each parse error on its first ": " to decide
    which per-file finding it becomes; the SDK documents the same shape as
    an interface. Whichever side moves first, this trips."""
    _, error = iirds.parse_metadata(model.METADATA_RDF, b"<broken",
                                    base=model.PACKAGE_BASE)
    name, sep, detail = error.partition(": ")
    assert (name, sep) == (model.METADATA_RDF, ": ")
    assert detail


def test_the_generated_shapes_speak_the_same_base():
    """emit_shacl embeds the base as literal TTL text (a generator emits
    text, not objects), so identity cannot hold there -- containment can."""
    import emit_shacl
    assert iirds.PACKAGE_BASE in emit_shacl.BASE_EXCLUSION


# ---------------------------------------------------------------------------
# Which SDK the run used
# ---------------------------------------------------------------------------

def _declared_floor():
    """The lowest `iirds` this project says it works with."""
    text = (ROOT / "pyproject.toml").read_text("utf-8")
    found = re.search(r'"iirds>=([0-9]+(?:\.[0-9]+)*)"', text)
    assert found, "pyproject.toml no longer declares an iirds floor in the expected shape"
    return tuple(int(part) for part in found.group(1).split("."))


def _version(text: str):
    parts = text.split(".")
    assert all(part.isdigit() for part in parts), (
        "iirds %s is not a plain release; this comparison cannot judge it" % text)
    return tuple(int(part) for part in parts)


def test_the_sdk_under_test_satisfies_what_this_project_declares():
    """A green run has to be a statement about a version, not about a laptop.

    `pyproject.toml` says `iirds>=0.2.0`, and nothing checked that the copy
    the suite actually imported honours it. CI does pin the floor in one of
    its rows, deliberately; a local run took whatever was installed and said
    nothing about it either way.
    """
    assert _version(iirds.__version__) >= _declared_floor(), (
        "the suite imported iirds %s from %s, below the floor pyproject declares"
        % (iirds.__version__, iirds.__file__))


def test_a_chosen_sdk_checkout_is_the_one_that_gets_imported():
    """`IIRDS_SRC=/path/to/iirds/src make check` must mean it.

    The Makefile assigned PYTHONPATH outright, discarding whatever the caller
    had exported, so `import iirds` found the installed release however the
    run was invoked. That is wrong in the one situation it matters most: the
    SDK and the validator are repaired in the same breath, and the validator's
    suite is the only place the pair is exercised together. Repairing the SDK
    and watching this suite go green proved nothing about the repair.

    Skipped when no checkout is named, which is the ordinary case -- then the
    installed release is under test and the assertion above is what holds.
    """
    chosen = os.environ.get("IIRDS_SRC")
    if not chosen:
        pytest.skip("no SDK checkout named; the installed release is under test")
    chosen = Path(chosen).resolve()
    imported = Path(iirds.__file__).resolve()
    assert imported.is_relative_to(chosen), (
        "IIRDS_SRC names %s but the suite imported iirds from %s" % (chosen, imported))


def test_the_makefile_still_builds_pythonpath_from_that_variable():
    """The affordance above is two halves in two files.

    A rename on either side fails quietly and in the worst direction: the
    Makefile stops honouring a variable nobody sets any more, and the test
    that guards it skips for ever. A skipping test and a passing one are the
    same line in a summary, which is how a gate stops being one without
    anybody deciding to remove it.
    """
    makefile = (ROOT / "Makefile").read_text("utf-8")
    assert "$(IIRDS_SRC)" in makefile, (
        "the Makefile no longer builds PYTHONPATH from IIRDS_SRC, so the test "
        "above would skip for ever instead of checking anything")
