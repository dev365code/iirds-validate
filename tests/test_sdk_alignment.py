"""One container layer, two packages, held together by `is`.

The checker wrote the metadata guards, the parser and the merge; they moved
to the `iirds` library so every tool shares them; the checker imports them
back. Equality tests would pass against a drifted copy -- these pin object
identity, so the seam cannot reopen without failing loudly.

Both packages ship from this tree, and the tests under "which copies" say so:
a green run is a statement about `src/`, not about whichever copy of either
package a machine happens to have installed.
"""
import importlib
from pathlib import Path

import pytest

import iirds
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
    which per-file finding it becomes; the library documents the same shape
    as an interface. Whichever side moves first, this trips."""
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
# Which copies the run used
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", ["iirds", "iirds_validate"])
def test_the_packages_under_test_are_the_ones_in_this_tree(module):
    """A green run has to be a statement about this tree, not about a laptop.

    Both packages ship from `src/`, and an installed copy of either -- a
    release in site-packages, or the reader this checker used to depend on
    -- resolves first the moment `src/` is not ahead of it on the path. Then
    the suite passes or fails on code nobody is looking at. Asserted for
    every run, without a variable to set: the path that finds the wrong
    copy is the one a person did not know they had.
    """
    imported = Path(importlib.import_module(module).__file__).resolve()
    assert imported.is_relative_to(ROOT / "src"), (
        "%s was imported from %s, not from this tree" % (module, imported))


# ---------------------------------------------------------------------------
# The one piece of shared logic that is duplicated instead of imported
#
# `iirds.source_of` and `iirds_validate.package.entry_named` resolve the same
# value the same way on purpose, and are two copies in one tree: the library
# reads a node's property and refuses a value that escapes the package; the
# checker takes the string and answers None, so that a rule can report it.
# Until `entry_named` becomes a call into the library -- an addition to the
# library's public surface, made on its own -- this table holds the seam:
# every spelling the two are asked about, and the name each answers with.
#
# The difference the table allows is the documented one: the library refuses
# to resolve a value that escapes the package, and the checker answers None
# and reports it. The *name* either resolves to must be identical.
# ---------------------------------------------------------------------------

SPELLINGS = (
    # plain, and the ways of writing the same entry
    "content/topic1.xhtml", "/content/topic1.xhtml", "./content/topic1.xhtml",
    "content//topic1.xhtml", "content/extra/../topic1.xhtml", ".config/a.xhtml",
    "//content/topic1.xhtml", "", "   ", "..", "../outside.xhtml",
    "..\\..\\etc\\passwd",
    # percent-encoding, a fragment, a query, or a value carrying a colon that
    # section 5.1.3 excludes from a file name
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
    """(what the library names, what the checker names) -- the library's
    refusal to resolve an escaping value read as None, which is the one
    difference."""
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


@pytest.mark.parametrize("spelling", SPELLINGS, ids=range(len(SPELLINGS)))
def test_the_two_resolvers_answer_alike(spelling):
    theirs, ours = _both_answer(spelling)
    assert theirs == ours, (
        "iirds.source_of and entry_named disagree about %r: %r vs %r"
        % (spelling, theirs, ours))
