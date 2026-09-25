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

import iirds
import iirds._metadata as metadata
from iirds._metadata import _fingerprint, _reads_back_the_same, _term, write_metadata

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


@pytest.fixture
def searches(monkeypatch):
    """Every structure searched rather than walked once: none, where the fast
    path is the one on trial."""
    asked = []
    real = metadata._structure_name

    def counted(nodes, *rest):
        asked.append(len(nodes))
        return real(nodes, *rest)

    monkeypatch.setattr(metadata, "_structure_name", counted)
    return asked


@pytest.mark.parametrize("case", sorted(DISTINCT))
def test_the_fingerprint_separates_what_isomorphism_separates(case, searches):
    a, b = _pair(*DISTINCT[case])
    assert len(a) == len(b), "equal length, so the early reject is not what answers"
    assert not isomorphic(a, b), "the fixture must be two different graphs"
    assert _fingerprint(a) != _fingerprint(b)
    assert searches == [], "the fast path must be the one on trial"


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
    is not an aside -- it is why the fast path has to answer for them, and why
    what does reach rdflib's canonical form is a reduced structure holding no
    term of the caller's: a digest in place of what each blank node says.
    """
    a, b = _pair(URIRef(iri), Literal(iri))
    assert len(a) == len(b), "equal length, so the early reject is not what answers"
    assert _fingerprint(a) != _fingerprint(b)
    # The bare type is the finding, not an untidy assertion: rdflib raises
    # `Exception` itself here, which is why this cannot reach a caller as it is.
    with pytest.raises(Exception):  # noqa: B017
        isomorphic(a, b)


def test_a_blank_node_two_named_nodes_point_at_is_checked_whatever_they_are_named(searches):
    """One blank node hanging off two subjects, one of them an IRI rdflib
    will not render as N3. Before, the fast path stood down for any shared
    blank node and the general check raised a bare `Exception` on the IRI --
    past the `ValueError` `write_metadata` offers. Named nodes pointing at a
    blank node now join its name, so the fast path answers, and the graph is
    written."""
    graph = Graph()
    shared = BNode()
    graph.add((URIRef("http://example.org/a b"), P, shared))
    graph.add((URIRef("urn:other"), P, shared))
    graph.add((shared, P, Literal("x")))
    assert write_metadata(graph)
    assert searches == []


def test_a_cycle_past_the_limit_is_refused_by_the_documented_channel(searches):
    """Where the check does not run, the caller is told in the one way the
    signature offers, with the limit named, and nothing was searched."""
    graph = Graph()
    nodes = [BNode() for _ in range(iirds.MAX_COMPARED_BLANK_NODES + 1)]
    graph.add((URIRef("http://example.org/a b"), P, nodes[0]))
    for index, node in enumerate(nodes):
        graph.add((node, P, nodes[(index + 1) % len(nodes)]))
    with pytest.raises(ValueError, match="compares at most %d" % iirds.MAX_COMPARED_BLANK_NODES):
        write_metadata(graph)
    assert searches == []


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


def test_which_blank_node_two_named_nodes_share_is_part_of_the_graph(searches):
    """Four named nodes, two blank nodes alike, each pointed at by two of them
    -- paired one way, then the other. Every statement renders alike in both
    unless the named nodes pointing at a blank node join its name, and the
    two graphs are not the same: in one, `a` and `b` share a node."""
    a, b, c, d = (URIRef("urn:%s" % name) for name in "abcd")

    def shared(pairs):
        graph = Graph()
        for left, right in pairs:
            node = BNode()
            graph.add((left, P, node))
            graph.add((right, P, node))
            graph.add((node, P, Literal("alike")))
        return graph

    one, other = shared([(a, b), (c, d)]), shared([(a, c), (b, d)])
    assert not isomorphic(one, other), "the fixture must be two different graphs"
    assert _fingerprint(one) != _fingerprint(other)
    assert searches == []


def _random_graph(seed):
    import random

    chance = random.Random(seed)
    nodes = [BNode() for _ in range(chance.randint(1, 6))]
    named = [URIRef("urn:n%d" % index) for index in range(3)]
    predicates = [URIRef("urn:p%d" % index) for index in range(2)]
    values = [Literal("x"), Literal("x", lang="en"), URIRef("urn:v")]
    graph = Graph()
    for _ in range(chance.randint(1, 10)):
        roll = chance.random()
        subject = chance.choice(named) if roll < 0.3 else chance.choice(nodes)
        obj = chance.choice(nodes) if roll < 0.65 else chance.choice(values + named)
        graph.add((subject, chance.choice(predicates), obj))
    return graph, chance


def _relabelled(graph):
    minted, fresh = {}, Graph()
    for triple in graph:
        fresh.add(tuple(minted.setdefault(term, BNode()) if isinstance(term, BNode) else term
                        for term in triple))
    return fresh


def _moved(graph, chance):
    """The graph with one statement's object or subject moved to another
    term: the same length, and most often not the same graph."""
    triples = sorted(graph, key=lambda triple: tuple(map(str, triple)))
    index = chance.randrange(len(triples))
    subject, predicate, obj = triples[index]
    blanks = sorted({term for triple in triples for term in triple if isinstance(term, BNode)})
    if chance.random() < 0.5:
        obj = chance.choice(blanks + [Literal("x")])
    else:
        subject = chance.choice(blanks)
    moved = Graph()
    for position, triple in enumerate(triples):
        moved.add((subject, predicate, obj) if position == index else triple)
    return _relabelled(moved)


def _same_by_search(one, other):
    """Isomorphism decided by trying every map of one graph's blank nodes onto
    the other's: slow, exact, and nobody's heuristic. rdflib's `isomorphic` is
    not that -- on a structure with symmetry its search can end on either of
    two labellings -- so it cannot referee the comparison that replaces it."""
    from itertools import permutations

    if len(one) != len(other):
        return False
    mine = sorted({term for triple in one for term in triple if isinstance(term, BNode)})
    theirs = sorted({term for triple in other for term in triple if isinstance(term, BNode)})
    if len(mine) != len(theirs):
        return False
    target = set(other)
    for image in permutations(theirs):
        onto = dict(zip(mine, image))
        if all(tuple(onto.get(term, term) for term in triple) in target for triple in one):
            return True
    return False


@pytest.mark.parametrize("block", range(4))
def test_the_fingerprint_agrees_with_isomorphism_on_graphs_of_every_shape(block):
    """Trees, blank nodes shared by named nodes, by blank nodes, cycles: small
    graphs of every shape, each against itself relabelled and against itself
    with one statement moved, where the lengths still agree, refereed by
    trying every map of their blank nodes. Two hundred and fifty a block, the
    same ones every run."""
    for seed in range(block * 250, (block + 1) * 250):
        graph, chance = _random_graph(seed)
        for other in (_relabelled(graph), _moved(graph, chance)):
            if len(other) != len(graph):
                continue
            assert (_fingerprint(graph) == _fingerprint(other)) is _same_by_search(graph, other), seed


def _double_star(seed):
    """Two blank nodes linked to each other, each linked to two more, every
    link both ways, each node saying the same thing: six nodes, and symmetry
    enough that rdflib's canonical form named it two ways in different runs.
    `seed` decides which node is minted where."""
    import random

    nodes = [BNode() for _ in range(6)]
    random.Random(seed).shuffle(nodes)
    one, other, *leaves = nodes
    graph = Graph()
    for left, right in ((one, other), (one, leaves[0]), (one, leaves[1]),
                        (other, leaves[2]), (other, leaves[3])):
        graph.add((left, URIRef("urn:p"), right))
        graph.add((right, URIRef("urn:p"), left))
    for node in nodes:
        graph.add((node, URIRef("urn:t"), Literal("same")))
    return graph


def test_a_structure_with_symmetry_is_named_one_way_whatever_its_labels(searches):
    """Measured on the canonical form this replaced: four hundred copies of
    this structure, minted in different orders, took two names -- so two
    identical files compared different in some runs, L9 reported them, and
    the merge counted every anonymous statement twice."""
    names = {tuple(_fingerprint(_double_star(seed))) for seed in range(60)}
    assert len(names) == 1
    assert searches, "the structure is not a tree, so it is the search on trial"
    assert _same_by_search(_double_star(0), _double_star(1))
