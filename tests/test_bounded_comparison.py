"""Comparing two serialisations of one graph costs one pass where it can, and
is refused, not run, where it cannot.

Where a package carries both metadata.rdf and metadata.jsonld, the two are
compared twice: the merge asks whether the second is the first again, and L9
asks what each holds that the other lacks. Both asked rdflib's canonical form,
whose search grows faster than the file wherever blank nodes look alike: a
kilobyte of JSON-LD holding fifty anonymous nodes of one shape took the
checker the better part of a minute, and a hundred took eight.

What is held here is counts, not seconds: how often a structure that is not a
tree is searched, over how many nodes, and where the refusal starts. Seconds
are a fact about the machine; the number of searches is a fact about the code.
"""
from __future__ import annotations

import pytest
from rdflib import BNode, Graph, Literal, URIRef

import iirds
import iirds._metadata as metadata
from iirds_validate import runner

EX = "urn:test:"

RDF_HEAD = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#"
         xmlns:ex="urn:test:">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:title>Test package</iirds:title>
  </iirds:Package>
  <iirds:Topic rdf:about="urn:test:topic1">
    <iirds:title>A topic</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>application/xhtml+xml</iirds:format>
        <iirds:source>content/topic1.xhtml</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
%s  </iirds:Topic>
%s</rdf:RDF>
"""

JSONLD_HEAD = """{
  "@context": {
    "iirds": "http://iirds.tekom.de/iirds#",
    "ex": "urn:test:"
  },
  "@graph": [
    {"@id": "urn:test:package", "@type": "iirds:Package",
     "iirds:iiRDSVersion": "1.3", "iirds:title": "Test package"},
    {"@id": "urn:test:topic1", "@type": "iirds:Topic", "iirds:title": "A topic",
     "iirds:has-rendition": {"@type": "iirds:Rendition",
                             "iirds:format": "application/xhtml+xml",
                             "iirds:source": "content/topic1.xhtml"}%s}%s
  ]
}
"""


def alike(count):
    """`count` anonymous nodes of one shape under the topic, in both files --
    the shape the cost was reported on. They form trees."""
    rdf = "".join("    <ex:note><ex:Note><ex:kind>same</ex:kind></ex:Note></ex:note>\n"
                  for _ in range(count))
    jsonld = (',\n     "ex:note": [%s]' % ", ".join(
        '{"@type": "ex:Note", "ex:kind": "same"}' for _ in range(count))) if count else ""
    return RDF_HEAD % (rdf, ""), JSONLD_HEAD % (jsonld, "")


def ring(count):
    """`count` anonymous nodes pointing one to the next and the last to the
    first, hung off the topic, in both files: a cycle, so not a tree."""
    link = "    <ex:ring rdf:nodeID=\"n0\"/>\n"
    rdf = "".join('  <rdf:Description rdf:nodeID="n%d"><ex:next rdf:nodeID="n%d"/>'
                  '</rdf:Description>\n' % (index, (index + 1) % count)
                  for index in range(count))
    jsonld = ',\n     "ex:ring": {"@id": "_:n0"}'
    nodes = "".join(',\n    {"@id": "_:n%d", "ex:next": {"@id": "_:n%d"}}'
                    % (index, (index + 1) % count) for index in range(count))
    return RDF_HEAD % (link, rdf), JSONLD_HEAD % (jsonld, nodes)


@pytest.fixture
def searches(monkeypatch):
    """Every structure that is not a tree, by the blank nodes it holds: the
    one place the comparison tries orders rather than walking once."""
    asked = []
    real = metadata._structure_name

    def counted(nodes, *rest):
        asked.append(len(nodes))
        return real(nodes, *rest)

    monkeypatch.setattr(metadata, "_structure_name", counted)
    return asked


def _package(tmp_path, pair, name="test.iirds"):
    from conftest import build_package

    rdf, jsonld = pair
    return build_package(tmp_path, name, metadata=rdf, jsonld=jsonld)


def _ids(report):
    return sorted(finding.rule.id for finding in report.findings)


def test_the_fixtures_are_one_graph_in_two_files(tmp_path):
    """Everything below reads a difference or its absence; the pair has to be
    the same graph first, or the counts would be about a different question."""
    from rdflib.compare import isomorphic

    for pair in (alike(3), ring(3)):
        rdf, error = iirds.parse_metadata(iirds.METADATA_RDF, pair[0].encode(),
                                          base=iirds.PACKAGE_BASE)
        jsonld, other = iirds.parse_metadata(iirds.METADATA_JSONLD, pair[1].encode(),
                                             base=iirds.PACKAGE_BASE)
        assert error is None and other is None
        assert isomorphic(rdf, jsonld)


@pytest.mark.parametrize("count", [25, 50, 100])
def test_anonymous_nodes_alike_are_compared_without_a_search(tmp_path, searches, count):
    """The reported shape, at the sizes it was reported at. Before, each was
    one search per graph per question -- and the search was the cost."""
    report = runner.run(_package(tmp_path, alike(count)), runner.ALL_KINDS)
    assert searches == []
    assert not {"L9", "C16.2", "S3"} & set(_ids(report))
    assert any(iirds.METADATA_JSONLD in str(note) for note in report.notes), \
        "both files were read and merged, not one set aside"


def test_a_difference_among_them_is_still_found_and_counted(tmp_path, searches):
    """One pass is not a coarser pass: one more node of the same shape in one
    file is L9's, counted as the three statements it adds -- the one pointing
    at it and its own two."""
    rdf, _ = alike(50)
    _, jsonld = alike(51)
    report = runner.run(_package(tmp_path, (rdf, jsonld)), runner.ALL_KINDS)
    [finding] = [f for f in report.findings if f.rule.id == "L9"]
    assert finding.violation.detail.startswith(
        "3 statement(s) only in %s" % iirds.METADATA_JSONLD)
    assert searches == []


def test_a_structure_that_is_not_a_tree_is_compared_up_to_the_limit(tmp_path, searches):
    """At the limit the search runs, once per structure per graph, on the
    structure alone."""
    report = runner.run(_package(tmp_path, ring(iirds.MAX_COMPARED_BLANK_NODES)),
                        runner.ALL_KINDS)
    assert "C16.2" not in _ids(report) and "L9" not in _ids(report)
    assert searches and set(searches) == {iirds.MAX_COMPARED_BLANK_NODES}


def test_past_the_limit_the_second_file_is_refused_and_nothing_is_searched(tmp_path, searches):
    """One node past it: the merge leaves metadata.jsonld out, C16.2 says why
    and names the limit, and the run fails -- the files were not shown to be
    the same, so no rule read the second as if they were."""
    limit = iirds.MAX_COMPARED_BLANK_NODES
    report = runner.run(_package(tmp_path, ring(limit + 1)), runner.ALL_KINDS)
    [finding] = [f for f in report.findings if f.rule.id == "C16.2"]
    assert finding.violation.message.startswith("metadata.jsonld was not compared")
    assert "holds %d blank nodes outside trees" % (limit + 1) in finding.violation.detail
    assert "at most %d" % limit in finding.violation.detail
    assert "at most %d blank nodes" % limit in finding.violation.fix, \
        "the remedy is a literal, so the limit it names is held here"
    assert "L9" not in _ids(report)
    assert not report.ok
    assert searches == []


def test_the_refusal_reaches_a_lint_run_too(tmp_path, searches):
    """`lint` runs no container rule, so the runner reports it there."""
    report = runner.run(_package(tmp_path, ring(iirds.MAX_COMPARED_BLANK_NODES + 1)),
                        runner.LINT_KINDS)
    [finding] = [f for f in report.findings if f.rule.id == "C16.2"]
    assert finding.violation.message.startswith("metadata.jsonld was not compared")
    assert not report.ok
    assert searches == []


# --- the library, without the checker ----------------------------------------

def _graph(text, name):
    graph, error = iirds.parse_metadata(name, text.encode("utf-8"), base=iirds.PACKAGE_BASE)
    assert error is None
    return graph


def test_a_package_reports_the_refusal_before_the_graph_is_asked_for(tmp_path):
    limit = iirds.MAX_COMPARED_BLANK_NODES
    with iirds.open(_package(tmp_path, ring(limit + 1))) as package:
        [error] = package.parse_errors
        assert error.startswith("%s: %s: " % (iirds.METADATA_JSONLD, iirds.NOT_COMPARED))
        assert package.metadata_sources == [iirds.METADATA_RDF]
        assert list(package.metadata_graphs) == [iirds.METADATA_RDF]
        assert len(package.graph) == len(_graph(ring(limit + 1)[0], iirds.METADATA_RDF))


def test_merge_sources_without_a_list_raises_the_refusal():
    rdf, jsonld = ring(iirds.MAX_COMPARED_BLANK_NODES + 1)
    graphs = {iirds.METADATA_RDF: _graph(rdf, iirds.METADATA_RDF),
              iirds.METADATA_JSONLD: _graph(jsonld, iirds.METADATA_JSONLD)}
    with pytest.raises(ValueError, match="compares at most %d" % iirds.MAX_COMPARED_BLANK_NODES):
        iirds.merge_sources(graphs)
    refused = []
    merged = iirds.merge_sources(graphs, refused=refused)
    assert len(merged) == len(graphs[iirds.METADATA_RDF])
    assert refused and refused[0].startswith(iirds.METADATA_JSONLD + ": ")


def test_the_refusal_names_the_file_that_holds_the_structure():
    """Where the first file is the one past the limit, the second is still
    the one left out, and the reason names the first."""
    rdf, _ = ring(iirds.MAX_COMPARED_BLANK_NODES + 1)
    _, jsonld = alike(1)
    refused = []
    iirds.merge_sources({iirds.METADATA_RDF: _graph(rdf, iirds.METADATA_RDF),
                         iirds.METADATA_JSONLD: _graph(jsonld, iirds.METADATA_JSONLD)},
                        refused=refused)
    [reason] = refused
    assert reason.startswith("%s: %s: %s holds" % (iirds.METADATA_JSONLD, iirds.NOT_COMPARED,
                                                   iirds.METADATA_RDF))


def test_graph_difference_counts_a_repeat_and_prints_the_same_every_time():
    one, other = Graph(), Graph()
    subject, predicate, kind = URIRef(EX + "s"), URIRef(EX + "p"), URIRef(EX + "kind")
    for graph, repeats in ((one, 2), (other, 1)):
        for _ in range(repeats):
            node = BNode()
            graph.add((subject, predicate, node))
            graph.add((node, kind, Literal("same")))
    only_one, only_other = iirds.graph_difference(one, other)
    assert len(only_one) == 2 and only_other == []
    again, _ = iirds.graph_difference(one, other)
    assert [tuple(map(str, triple)) for triple in again] == \
        [tuple(map(str, triple)) for triple in only_one]
    assert iirds.graph_difference(one, one) == ([], [])


def test_graph_difference_refuses_past_the_limit():
    rdf, jsonld = ring(iirds.MAX_COMPARED_BLANK_NODES + 1)
    with pytest.raises(ValueError, match="at most %d" % iirds.MAX_COMPARED_BLANK_NODES):
        iirds.graph_difference(_graph(rdf, iirds.METADATA_RDF),
                               _graph(jsonld, iirds.METADATA_JSONLD))


def _chain(length):
    graph, node = Graph(), BNode()
    graph.add((URIRef(EX + "start"), URIRef(EX + "next"), node))
    for index in range(length):
        following = BNode()
        graph.add((node, URIRef(EX + "value"), Literal(index)))
        graph.add((node, URIRef(EX + "next"), following))
        node = following
    return graph


def test_a_chain_of_any_depth_is_a_tree(searches):
    """Named from the leaves up without recursion: a chain as long as the file
    makes it is one pass, not a search and not a recursion limit."""
    from iirds._metadata import _reads_back_the_same

    graph = _chain(5000)
    fresh = Graph()
    minted = {}
    for triple in graph:
        fresh.add(tuple(minted.setdefault(term, BNode()) if isinstance(term, BNode) else term
                        for term in triple))
    assert _reads_back_the_same(fresh, graph)
    assert searches == []


def test_write_metadata_refuses_past_the_limit_by_its_documented_channel(searches):
    rdf, _ = ring(iirds.MAX_COMPARED_BLANK_NODES + 1)
    with pytest.raises(ValueError, match="compares at most %d" % iirds.MAX_COMPARED_BLANK_NODES):
        iirds.write_metadata(_graph(rdf, iirds.METADATA_RDF))
    assert searches == []
