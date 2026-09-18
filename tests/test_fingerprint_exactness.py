"""The fast graph comparison must agree with the slow one, not approximate it.

`_reads_back_the_same` guards a round trip: metadata is written, read back, and
the two graphs compared. Under the forest condition it uses `_fingerprint`
rather than rdflib's `isomorphic`, and its docstring says the two "agree by
construction" there. They did not. `_fingerprint` rendered every non-blank term
with `str()`, which keeps the lexical form and drops the datatype, the language
tag, and whether the term was a URI or a literal -- a coarsening, so a graph
that differs only in one of those read back as the same.

Measured: all three pairs below are forests on both sides, of equal length, and
`isomorphic` separates every one of them.
"""
from __future__ import annotations

import pytest
from rdflib import XSD, BNode, Graph, Literal, URIRef
from rdflib.compare import isomorphic

from iirds._metadata import _blank_forest, _fingerprint, _reads_back_the_same, _term, write_metadata

S, P = URIRef("urn:s"), URIRef("urn:p")

DISTINCT = {
    "language tag": (Literal("Getriebe", lang="en"), Literal("Getriebe", lang="de")),
    "datatype": (Literal("1", datatype=XSD.integer), Literal("1", datatype=XSD.decimal)),
    "datatype against none": (Literal("2024-01-01", datatype=XSD.date),
                              Literal("2024-01-01")),
    "resource against text": (URIRef("http://example.org/o"),
                              Literal("http://example.org/o")),
}


def _pair(left, right):
    a, b = Graph(), Graph()
    a.add((S, P, left))
    b.add((S, P, right))
    return a, b


@pytest.mark.parametrize("case", sorted(DISTINCT))
def test_the_fingerprint_separates_what_isomorphism_separates(case):
    a, b = _pair(*DISTINCT[case])
    assert _blank_forest(a) and _blank_forest(b), "the fast path must be the one on trial"
    assert len(a) == len(b), "equal length, so the early reject is not what answers"
    assert not isomorphic(a, b), "the fixture must be two different graphs"
    assert _fingerprint(a) != _fingerprint(b)


@pytest.mark.parametrize("case", sorted(DISTINCT))
def test_the_round_trip_guard_separates_them_too(case):
    """The guard is what ships; the fingerprint is how it decides."""
    a, b = _pair(*DISTINCT[case])
    assert not _reads_back_the_same(a, b)


def test_the_same_graph_still_reads_back_the_same():
    """The control. Exactness must not become refusing everything."""
    a = Graph()
    a.add((S, P, Literal("Getriebe", lang="en")))
    b = Graph()
    b.parse(data=a.serialize(format="xml"), format="xml")
    assert isomorphic(a, b) and _reads_back_the_same(b, a)


#: IRIs rdflib parses, holds, and writes as RDF/XML, and refuses to render as
#: N3: the characters RFC 3987 leaves out of an IRI. Nothing on the way in
#: rejects them -- a supplier's metadata.rdf can carry one and be read here --
#: so a graph built from a package that arrived is free to contain them.
UNRENDERABLE = ("http://example.org/a b", "http://example.org/a{b}",
                "http://example.org/a|b")


@pytest.mark.parametrize("iri", UNRENDERABLE)
def test_a_graph_that_can_be_written_is_not_refused_by_the_check_on_writing(iri):
    """Exactness must not be bought with a serialiser's opinion.

    `n3()` is a writer: asked for a term it could not write as N3 it raises,
    and this is not writing, it is comparing. The refusal arrives as a bare
    `Exception` from inside `_reads_back_the_same`, so `write_metadata` --
    which documents `ValueError` for a graph it will not write -- fails
    through a channel no caller can catch by kind, on graphs it wrote before
    and whose RDF/XML rdflib still produces.
    """
    graph = Graph()
    graph.add((URIRef(iri), P, Literal("x")))
    assert graph.serialize(format="xml"), "the fixture must be a graph rdflib writes"
    assert _fingerprint(graph), "the comparison must answer rather than refuse"
    assert write_metadata(graph), "written before the fingerprint was made exact"


@pytest.mark.parametrize("iri", UNRENDERABLE)
def test_those_terms_are_still_told_apart_from_the_text_that_spells_them(iri):
    """And the exactness is still there for them: the point of the change was
    that a resource and the string naming it are two different graphs.

    `isomorphic` is the referee everywhere else in this file and cannot be one
    here: it canonicalises through N3 and raises on exactly these terms. That
    is not an aside -- it is why the fast path has to answer for them. Where
    the blank nodes are not a forest there is no fast path, nothing can answer,
    and `_reads_back_the_same` says so through `ValueError` rather than
    letting a serialiser's refusal out as itself.
    """
    a, b = _pair(URIRef(iri), Literal(iri))
    assert len(a) == len(b), "equal length, so the early reject is not what answers"
    assert _fingerprint(a) != _fingerprint(b)
    # The bare type is the finding, not an untidy assertion: rdflib raises
    # `Exception` itself here, which is why this cannot reach a caller as it is.
    with pytest.raises(Exception):  # noqa: B017
        isomorphic(a, b)


def test_a_graph_nothing_can_check_is_refused_by_the_documented_channel():
    """Where neither check can answer, the caller is told in the one way the
    signature offers.

    One blank node hanging off two subjects is not a forest, so the fast path
    stands down; the IRI beside it is one the general check refuses. Before,
    that refusal left `write_metadata` as a bare `Exception` -- past the
    `ValueError` its docstring offers, and past any caller catching by kind.
    """
    graph = Graph()
    shared = BNode()
    graph.add((URIRef("http://example.org/a b"), P, shared))
    graph.add((URIRef("urn:other"), P, shared))
    graph.add((shared, P, Literal("x")))
    assert not _blank_forest(graph), "the fixture must leave the fast path standing down"
    with pytest.raises(ValueError):
        write_metadata(graph)


def test_a_subclass_of_a_term_is_not_a_different_term():
    """The fast path must not split what the referee joins.

    rdflib defines `Genid`, a `URIRef` subclass for skolemised blank nodes.
    `isomorphic` treats one as the URI it is; a rendering keyed on the Python
    class name calls it something else, and `_reads_back_the_same` then
    refuses a graph that round-tripped perfectly. The kind this renders is the
    RDF one -- resource, literal, blank -- for that reason.
    """
    from rdflib.term import Genid

    plain = URIRef("http://example.org/x")
    skolem = Genid("http://example.org/x")
    assert _term(plain) == _term(skolem)
    a, b = _pair(plain, skolem)
    assert isomorphic(a, b), "the referee calls these the same graph"
    assert _reads_back_the_same(a, b), "and the fast path has to agree with it"
