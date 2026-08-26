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
from pathlib import Path

import iirds
import pytest

from conftest import declared_sdk_floor, sdk_version, version_tuple
from iirds_validate import context, model

ROOT = Path(__file__).resolve().parents[1]

#: The name of the variable that names an SDK checkout. One thing in two
#: files, so it is spelled once here and the Makefile is required to use the
#: same word: two literals could be renamed apart, and the direction that
#: fails quietly is the Makefile honouring a variable nobody sets while the
#: test guarding it skips for ever.
SDK_SRC_VAR = "IIRDS_SRC"


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

def test_the_sdk_under_test_satisfies_what_this_project_declares():
    """A green run has to be a statement about a version, not about a laptop.

    `pyproject.toml` says `iirds>=0.3.1`, and nothing checked that the copy
    the suite actually imported honours it. CI does pin the floor in one of
    its rows, deliberately; a local run took whatever was installed and said
    nothing about it either way.
    """
    assert version_tuple(iirds.__version__) >= declared_sdk_floor(), (
        "the suite imported iirds %s from %s, below the floor pyproject declares"
        % (iirds.__version__, iirds.__file__))


@pytest.mark.parametrize("lower,higher", [
    ("0.1.0", "0.2.0"), ("0.2.0", "0.3.0"), ("0.9.0", "0.10.0"), ("1.2.9", "1.10.0"),
])
def test_versions_compare_as_numbers_and_not_as_text(lower, higher):
    """The comparison above is a tuple compare, and it had to be.

    "0.10.0" sorts below "0.2.0" as text and above it as a release, so a
    string comparison would report an environment as below the floor when it
    is two minor versions past it. The choice was mutation-checked by hand
    once; a hand check that leaves no gate is a hand check nobody repeats.
    """
    assert version_tuple(lower) < version_tuple(higher)


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
    chosen = os.environ.get(SDK_SRC_VAR)
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
    assert "$(%s)" % SDK_SRC_VAR in makefile, (
        "the Makefile no longer builds PYTHONPATH from %s, so the test above "
        "would skip for ever instead of checking anything" % SDK_SRC_VAR)


# ---------------------------------------------------------------------------
# The one piece of shared logic that is duplicated instead of imported
#
# `iirds.source_of` and `iirds_validate.package.entry_named` resolve the same
# value the same way on purpose, and cannot be the same object yet: the
# repaired resolution is not in any published `iirds`, so this project's floor
# cannot name it. The seam is held by a table instead of by `is`, until the
# floor moves and `entry_named` becomes a call into the SDK.
#
# The table is in two halves, and the split is the honest one: twelve
# spellings the two projects have always answered alike, asserted for every
# reader; fifteen that need the repair, gated on the reader actually under
# test. Gated with a strict xfail rather than a skip -- green against a
# reader that does not carry the repair, red the day it regresses, and red
# the day a reader carries it and the two still disagree. A skip would be
# none of those things.
#
# Gated on what the reader *does*, not on its version, because the version
# cannot answer: a reader keeps the version of its last release until the
# day it ships, so the worktree this project is developed against carries
# the repair while still calling itself the release before it. The probe
# asks one spelling; the table then holds all fifteen, so a reader that
# half-carries the repair is caught rather than excused.
#
# The difference the table allows either way is the documented one: a reader
# refuses to resolve a value that escapes the package, and a validator answers
# None and reports it. The *name* either resolves to must be identical.
# ---------------------------------------------------------------------------

#: The reader release that first publishes the shared resolution.
RESOLVED_ALIKE_FROM = (0, 3, 3)

#: Spellings the two have always answered alike.
SETTLED_SPELLINGS = (
    "content/topic1.xhtml", "/content/topic1.xhtml", "./content/topic1.xhtml",
    "content//topic1.xhtml", "content/extra/../topic1.xhtml", ".config/a.xhtml",
    "//content/topic1.xhtml", "", "   ", "..", "../outside.xhtml",
    "..\\..\\etc\\passwd",
)

#: Spellings that need the repair: percent-encoding, a fragment, a query, or a
#: value carrying a colon that section 5.1.3 excludes from a file name.
REPAIRED_SPELLINGS = (
    "content/a%20b.xhtml", "content/a%23b.xhtml", "content/%74opic1.xhtml",
    "content/topic1.xhtml#section-2", "content/topic1.xhtml?revision=2",
    "content/topic1.xhtml?revision=2#section-2",
    "http://example.com/a.xhtml", "https://example.com/a.xhtml",
    "file:///etc/passwd", "mailto:someone@example.com",
    "urn:uuid:2c2d4f2e-0000-0000-0000-000000000000", "content/a%3Ab.xhtml",
    "content/%2e%2e/%2e%2e/etc/passwd", "%2e%2e/%2e%2e/etc/passwd",
    "content/%2e%2e/topic1.xhtml",
)


def _both_answer(spelling):
    """(what the SDK names, what this project names) -- the SDK's refusal to
    resolve an escaping value read as None, which is the one difference."""
    from rdflib import Graph, Literal, URIRef

    from iirds_validate.package import entry_named

    node = URIRef("urn:test:rendition")
    graph = Graph()
    graph.add((node, iirds.IIRDS["source"], Literal(spelling)))
    try:
        theirs = iirds.source_of(graph, node)
    except iirds.IirdsError:
        theirs = None
    return theirs, entry_named(spelling)


@pytest.mark.parametrize("spelling", SETTLED_SPELLINGS,
                         ids=range(len(SETTLED_SPELLINGS)))
def test_the_two_resolvers_have_always_answered_these_alike(spelling):
    theirs, ours = _both_answer(spelling)
    assert theirs == ours, (
        "iirds.source_of and entry_named disagree about %r: %r vs %r"
        % (spelling, theirs, ours))


def reader_carries_the_repair():
    """Does the reader under test decode a percent-encoded name?

    One probe, chosen because it is the plainest thing the repair does. It
    decides whether the fifteen below are expected to agree; it does not
    decide whether they do.
    """
    theirs, _ = _both_answer("content/a%20b.xhtml")
    return theirs == "content/a b.xhtml"


@pytest.mark.parametrize("spelling", REPAIRED_SPELLINGS,
                         ids=range(len(REPAIRED_SPELLINGS)))
@pytest.mark.xfail(not reader_carries_the_repair(), strict=True,
                   reason="the shared resolution lives in the reader, and this "
                          "one does not carry it yet; iirds %s publishes it"
                          % ".".join(map(str, RESOLVED_ALIKE_FROM)))
def test_the_two_resolvers_answer_the_repaired_spellings_alike(spelling):
    theirs, ours = _both_answer(spelling)
    assert theirs == ours, (
        "iirds.source_of and entry_named disagree about %r: %r vs %r"
        % (spelling, theirs, ours))


def test_the_release_that_publishes_the_repair_actually_carries_it():
    """The version half of the same question, kept because the probe above
    cannot ask it: once a reader says it is at or past the release that
    publishes the shared resolution, not carrying it is a defect in that
    reader rather than a state this project tolerates."""
    if sdk_version() >= RESOLVED_ALIKE_FROM:
        assert reader_carries_the_repair(), (
            "iirds %s is at or past %s and does not resolve a percent-encoded "
            "source; the two projects have diverged at the seam"
            % (iirds.__version__, ".".join(map(str, RESOLVED_ALIKE_FROM))))
