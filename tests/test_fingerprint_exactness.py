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
from rdflib import XSD, Graph, Literal, URIRef
from rdflib.compare import isomorphic

from iirds._metadata import _blank_forest, _fingerprint, _reads_back_the_same

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
