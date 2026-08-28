"""write_metadata(): what this library writes, its own guards accept.

The write self-verifies: the bytes are parsed back through the same
parse_metadata the readers use and compared isomorphically before being
handed over, so "the validator can read what the SDK wrote" is enforced
at write time rather than discovered at delivery time.
"""
from __future__ import annotations

import pytest
from rdflib import BNode, Graph, Literal, URIRef

import iirds

RDF_TYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")


def _graph() -> Graph:
    graph = Graph()
    package = URIRef("urn:test:package")
    graph.add((package, RDF_TYPE, iirds.IIRDS["Package"]))
    graph.add((package, iirds.IIRDS["iiRDSVersion"], Literal("1.3")))
    anonymous = BNode()
    graph.add((anonymous, RDF_TYPE, iirds.IIRDS["Component"]))
    return graph


def test_what_is_written_reads_back_isomorphic(tmp_path):
    raw = iirds.write_metadata(_graph())
    parsed, error = iirds.parse_metadata(iirds.METADATA_RDF, raw,
                                         base=iirds.PACKAGE_BASE)
    assert error is None
    from rdflib.compare import isomorphic
    assert isomorphic(parsed, _graph())


def test_the_bytes_declare_their_encoding():
    raw = iirds.write_metadata(_graph())
    # rdflib 6.0.0 spells the encoding upper-case; the floor must stay green.
    assert raw[:60].lower().startswith(b'<?xml version="1.0" encoding="utf-8"?>')


def test_a_destination_writes_the_same_bytes(tmp_path):
    destination = tmp_path / "META-INF" / "metadata.rdf"
    raw = iirds.write_metadata(_graph(), destination)
    assert destination.read_bytes() == raw


def test_one_graph_object_writes_the_same_bytes_every_time():
    """The promise is exactly this narrow: repeated writes of the *same*
    Graph object are byte-identical. Two graphs built identically are
    not -- rdflib mints blank-node labels from a process-global counter,
    so even same-construction graphs serialise apart. The first draft of
    this test claimed more and failed honestly; the docstring shrank to
    what is true rather than the code growing to what was wished."""
    graph = _graph()
    assert iirds.write_metadata(graph) == iirds.write_metadata(graph)


def test_it_composes_with_pack_into_a_valid_container(tmp_path):
    root = tmp_path / "pkg"
    iirds.write_metadata(_graph(), root / "META-INF" / "metadata.rdf")
    packed = iirds.pack(root)
    with iirds.open(packed) as pkg:
        assert pkg.version == "1.3"
        assert len(pkg.instances_of(iirds.IIRDS["Component"])) == 1


def test_a_graph_built_on_the_package_base_writes_cleanly():
    """The most natural authoring idiom -- build on iirds.PACKAGE_BASE,
    the base this library exports -- must not make the self-verifying
    write reject its own bytes. rdflib cannot resolve a relative
    reference against an opaque urn base, so the base is neutralised
    before serialising."""
    graph = Graph()
    subject = URIRef(iirds.PACKAGE_BASE + "doc1")
    graph.add((subject, RDF_TYPE, iirds.IIRDS["Package"]))
    graph.add((subject, iirds.IIRDS["iiRDSVersion"], Literal("1.3")))
    graph.base = iirds.PACKAGE_BASE
    raw = iirds.write_metadata(graph)            # must not raise
    parsed, error = iirds.parse_metadata(iirds.METADATA_RDF, raw,
                                         base=iirds.PACKAGE_BASE)
    assert error is None
    assert (subject, RDF_TYPE, iirds.IIRDS["Package"]) in parsed


def test_unwritable_input_blames_the_input_not_the_library():
    """A predicate IRI RDF/XML cannot split is the caller's graph, not a
    bug in iirds; the error must say so."""
    graph = Graph()
    graph.add((URIRef("urn:s"), URIRef("http://example.com/"), Literal("x")))
    with pytest.raises(ValueError, match="cannot be written|split"):
        iirds.write_metadata(graph)


# ---------------------------------------------------------------------------
# The self-check has to stay affordable
#
# The comparison is what makes the write trustworthy, so it does not get to be
# optional. It does have to finish: iiRDS nests a rendition inside its
# information unit, so a package of a few hundred topics is a graph of a few
# hundred blank nodes, and a general graph-isomorphism check over those is not
# priced for the size of an ordinary manual.
# ---------------------------------------------------------------------------

IIRDS = iirds.IIRDS


def nested_renditions(count):
    """The shape the standard's own examples use: a blank-node Rendition
    hanging off each information unit."""
    from rdflib.namespace import RDF

    graph = Graph()
    package = URIRef("urn:test:package")
    graph.add((package, RDF.type, IIRDS["Package"]))
    graph.add((package, IIRDS["iiRDSVersion"], Literal("1.3")))
    for index in range(count):
        topic = URIRef("urn:test:topic%d" % index)
        graph.add((topic, RDF.type, IIRDS["Topic"]))
        graph.add((topic, IIRDS["title"], Literal("Topic %d" % index)))
        rendition = BNode()
        graph.add((topic, IIRDS["has-rendition"], rendition))
        graph.add((rendition, RDF.type, IIRDS["Rendition"]))
        graph.add((rendition, IIRDS["source"], Literal("content/t%d.xhtml" % index)))
        graph.add((rendition, IIRDS["format"], Literal("application/xhtml+xml")))
    return graph


def test_writing_an_ordinary_manual_does_not_take_minutes():
    """Eight hundred topics is a mid-sized manual, not a stress test. The
    ceiling is deliberately far above the measured cost: this is here to
    catch the shape of the curve changing, not to time the machine."""
    import time

    graph = nested_renditions(800)
    started = time.perf_counter()
    iirds.write_metadata(graph)
    elapsed = time.perf_counter() - started
    assert elapsed < 10, (
        "writing 800 topics took %.1fs; the self-check is priced per blank "
        "node and this is the size at which that stops being affordable"
        % elapsed)


# ---------------------------------------------------------------------------
# ...and it has to stay the same check
#
# A comparison that is cheap and wrong is worse than one that is slow and
# right, so the fast path is held against the general one: same answer, both
# directions, on the shapes where it applies -- and on the shapes where it
# does not, the general one has to be the thing that answers.
# ---------------------------------------------------------------------------

def relabelled(graph):
    """The same graph with every blank node freshly minted -- what a round
    trip through RDF/XML produces, and what must compare equal."""
    from rdflib.namespace import RDF  # noqa: F401  (kept for symmetry)

    fresh, minted = Graph(), {}
    for subject, predicate, obj in graph:
        left = minted.setdefault(subject, BNode()) if isinstance(subject, BNode) else subject
        right = minted.setdefault(obj, BNode()) if isinstance(obj, BNode) else obj
        fresh.add((left, predicate, right))
    return fresh


def shared_blank_node():
    """One blank node reached from two places -- not a forest, because two
    graphs can agree on every subtree and still differ in what is shared."""
    graph = Graph()
    shared = BNode()
    for name in ("urn:test:a", "urn:test:b"):
        graph.add((URIRef(name), IIRDS["has-rendition"], shared))
    graph.add((shared, IIRDS["source"], Literal("content/one.xhtml")))
    return graph


def cyclic_blanks():
    """Two blank nodes pointing at each other -- no subtree to name them by."""
    graph = Graph()
    first, second = BNode(), BNode()
    graph.add((URIRef("urn:test:a"), IIRDS["has-rendition"], first))
    graph.add((first, IIRDS["relates-to"], second))
    graph.add((second, IIRDS["relates-to"], first))
    return graph


@pytest.mark.parametrize("build", [
    lambda: nested_renditions(6),
    shared_blank_node,
    cyclic_blanks,
], ids=["forest", "shared-blank", "cycle"])
def test_the_fast_comparison_answers_what_the_general_one_answers(build):
    from rdflib.compare import isomorphic

    from iirds._metadata import _reads_back_the_same

    graph = build()
    same = relabelled(graph)
    assert _reads_back_the_same(same, graph) is isomorphic(same, graph) is True

    for changed in _one_off(graph):
        assert _reads_back_the_same(changed, graph) is isomorphic(changed, graph), (
            "the two comparisons disagree about %d triples" % len(changed))
        assert _reads_back_the_same(changed, graph) is False


def _one_off(graph):
    """The graph with one triple missing, and with one object altered."""
    triples = sorted(graph, key=lambda t: (str(t[0]), str(t[1]), str(t[2])))
    dropped = Graph()
    for triple in triples[1:]:
        dropped.add(triple)
    yield dropped
    altered = Graph()
    for index, (subject, predicate, obj) in enumerate(triples):
        altered.add((subject, predicate, Literal("changed") if index == 0 else obj))
    yield altered


def test_a_shape_the_fast_comparison_cannot_name_goes_to_the_general_one():
    """White box, on purpose, because neither direction of this shows up in
    an answer. Sending everything down the slow path is correct and only
    slow -- the size gate above would catch it, eventually and rudely.
    Sending a shared or cyclic blank node down the fast path may well
    produce the right answer on any particular graph, which is exactly why
    it cannot be left to a test that compares answers: the condition is
    what makes the fast path provably the same check, not the outcome on
    the fixtures that happen to be here."""
    from iirds._metadata import _blank_forest

    assert _blank_forest(nested_renditions(3)) is True
    assert _blank_forest(shared_blank_node()) is False
    assert _blank_forest(cyclic_blanks()) is False


# ---------------------------------------------------------------------------
# A reproducible-build stamp has to be one a ZIP can hold
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("epoch", ["0", "1", "315532799", "99999999999999", "-1"],
                         ids=["unix-epoch", "one-second", "just-before-1980",
                              "far-future", "negative"])
def test_a_source_date_epoch_a_zip_cannot_hold_does_not_kill_pack(monkeypatch, epoch, tmp_path):
    """`SOURCE_DATE_EPOCH=0` is the commonest value a reproducible build is
    given, and a ZIP cannot carry a date before 1980. The guard caught a bad
    *string*; it did not catch a good string naming a date the format has no
    room for -- so the packer this library exists to provide refused to run
    under the convention it exists to support."""
    import zipfile

    from iirds._pack import _timestamp

    monkeypatch.setenv("SOURCE_DATE_EPOCH", epoch)
    stamp = _timestamp()
    zipfile.ZipInfo("anything", date_time=stamp)      # must not raise
    assert 1980 <= stamp[0] <= 2107, stamp

    source = tmp_path / "pkg"
    (source / "META-INF").mkdir(parents=True)
    (source / "META-INF" / "metadata.rdf").write_bytes(
        iirds.write_metadata(nested_renditions(1)))
    iirds.pack(source, tmp_path / "out.iirds", overwrite=True)


def test_the_same_epoch_still_gives_the_same_stamp(monkeypatch):
    """Clamping must not cost determinism: two builds of one tree agree is
    the whole point of the variable."""
    from iirds._pack import _timestamp

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    assert _timestamp() == _timestamp()
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert _timestamp() == (2023, 11, 14, 22, 13, 20)
