"""A JSON-LD metadata file may put its statements in a named graph.

JSON-LD 1.1, which iiRDS names for the syntax, reads a document as a dataset:
a default graph and any number of named graphs, and a top-level object with an
`@id` beside its `@graph` puts everything in a graph of that name. iiRDS says
nothing about graph names; where both metadata files exist it asks that they
semantically match. So each question about what a file says -- L9's, C16.2's,
the details that name the file a statement is in -- is asked of the file's
statements whatever graph holds them. The merged graph every other rule reads
is made of default graphs, as it was.

A reader that asks for one graph gets the default one, and from such a file
gets less, or nothing -- rdflib's `Graph()` does exactly that. L17 says so, as a
warning: the package is not wrong, and the reader it would fail is real.
"""
from __future__ import annotations

import json

from rdflib import BNode, Graph, Literal, URIRef

import iirds
from conftest import DESCRIPTION_STYLE_RDF, MINIMAL_JSONLD, MINIMAL_RDF
from iirds_validate import runner
from iirds_validate.model import Severity

GRAPH = "urn:test:graph"


def _named(jsonld=MINIMAL_JSONLD, name=GRAPH):
    """Everything in one named graph: the `@graph` given an `@id`."""
    document = json.loads(jsonld)
    document["@id"] = name
    return json.dumps(document)


def _split(jsonld=MINIMAL_JSONLD, name=GRAPH):
    """The first node in the default graph, the others in a named graph."""
    document = json.loads(jsonld)
    first, rest = document["@graph"][0], document["@graph"][1:]
    document["@graph"] = [first, {"@id": name, "@graph": rest}]
    return json.dumps(document)


def _findings(report, rule_id):
    return [f for f in report.findings if f.rule.id == rule_id]


def _lint(make_package, jsonld):
    return runner.lint(make_package(metadata=DESCRIPTION_STYLE_RDF, jsonld=jsonld))


def test_the_same_statements_in_a_named_graph_are_the_same_content(make_package):
    report = _lint(make_package, _named())
    assert not _findings(report, "L9"), [f.violation.detail for f in _findings(report, "L9")]


def test_default_and_named_graphs_together_are_one_file(make_package):
    assert not _findings(_lint(make_package, _split()), "L9")


def test_a_named_graph_that_says_something_else_is_reported_with_what_differs(make_package):
    changed = _named(MINIMAL_JSONLD.replace('"title": "A topic"', '"title": "A different topic"'))
    [finding] = _findings(_lint(make_package, changed), "L9")
    detail = finding.violation.detail
    assert "1 statement(s) only in META-INF/metadata.jsonld" in detail, detail
    assert "1 statement(s) only in META-INF/metadata.rdf" in detail, detail


def test_a_named_graph_missing_a_statement_is_reported(make_package):
    thinner = _named(MINIMAL_JSONLD.replace('"iiRDSVersion": "1.3", ', ""))
    [finding] = _findings(_lint(make_package, thinner), "L9")
    assert "only in META-INF/metadata.rdf" in finding.violation.detail


def test_a_reader_of_the_default_graph_alone_is_warned_about(make_package):
    [finding] = _findings(_lint(make_package, _named()), "L17")
    assert finding.severity is Severity.WARNING
    detail = finding.violation.detail
    assert GRAPH in detail and "sees none of them" in detail, detail


def test_part_in_a_named_graph_is_warned_about_as_part(make_package):
    [finding] = _findings(_lint(make_package, _split()), "L17")
    assert "sees the other" in finding.violation.detail, finding.violation.detail


def test_a_default_graph_draws_no_warning(make_package):
    assert not _findings(_lint(make_package, MINIMAL_JSONLD), "L17")


def test_a_named_graph_repeating_the_default_graph_draws_no_warning(make_package):
    """Nothing is hidden from a reader of the default graph."""
    document = json.loads(MINIMAL_JSONLD)
    document["@graph"] = document["@graph"] + [{"@id": GRAPH, "@graph": document["@graph"]}]
    assert not _findings(_lint(make_package, json.dumps(document)), "L17")


def test_the_merged_graph_every_other_rule_reads_is_what_it_was(make_package):
    """A named graph's statements are the file's, not the merge's: with the
    JSON-LD all in a named graph, the rules that read the merge see what
    metadata.rdf alone gives them."""
    def others(report):
        return sorted((f.rule.id, f.violation.subject or "", f.violation.detail or "")
                      for f in report.findings if f.rule.id not in ("L9", "L17"))

    alone = runner.check(make_package(metadata=DESCRIPTION_STYLE_RDF))
    named = runner.check(make_package(metadata=DESCRIPTION_STYLE_RDF, jsonld=_named()))
    assert others(named) == others(alone)


def test_the_reader_hands_on_named_graphs_by_name():
    raw = _named().encode("utf-8")
    graph, named, error = iirds.parse_metadata_graphs(iirds.METADATA_JSONLD, raw,
                                                      base=iirds.PACKAGE_BASE)
    assert error is None and len(graph) == 0, error
    assert [str(key) for key in named] == [GRAPH] and len(named[URIRef(GRAPH)]) > 0
    default, error = iirds.parse_metadata(iirds.METADATA_JSONLD, raw, base=iirds.PACKAGE_BASE)
    assert error is None and len(default) == 0, "parse_metadata still hands on the default graph"


def test_rdfxml_names_no_graph():
    graph, named, error = iirds.parse_metadata_graphs(
        iirds.METADATA_RDF, DESCRIPTION_STYLE_RDF.encode("utf-8"), base=iirds.PACKAGE_BASE)
    assert error is None and len(graph) and named == {}


def test_handover_metadata_in_a_named_graph_is_iirds_metadata_in_json_ld(make_package):
    """C16.2 asks whether metadata.jsonld contains iiRDS metadata; in a named
    graph it does."""
    from test_silent_pass import HANDOVER_RDF

    report = runner.check(make_package(metadata=HANDOVER_RDF, jsonld=_named()))
    assert not _findings(report, "C16.2"), [f.violation.detail for f in _findings(report, "C16.2")]


def test_a_named_graph_with_no_iirds_metadata_is_still_c16_2s(make_package):
    from test_silent_pass import HANDOVER_RDF, NO_IIRDS_JSONLD

    report = runner.check(make_package(metadata=HANDOVER_RDF, jsonld=_named(NO_IIRDS_JSONLD)))
    assert _findings(report, "C16.2")


def _nodes():
    return json.loads(MINIMAL_JSONLD)["@graph"]


def _document(graph):
    return json.dumps({"@context": json.loads(MINIMAL_JSONLD)["@context"], "@graph": graph})


def test_any_number_of_named_graphs_under_any_names_are_one_file(make_package):
    first, second, third = _nodes()
    jsonld = _document([{"@id": "urn:a:first", "@graph": [first, second]},
                        {"@id": "https://example.org/second", "@graph": [third]}])
    report = _lint(make_package, jsonld)
    assert not _findings(report, "L9"), [f.violation.detail for f in _findings(report, "L9")]
    [finding] = _findings(report, "L17")
    assert finding.violation.subject == iirds.METADATA_JSONLD
    detail = finding.violation.detail
    assert "urn:a:first" in detail and "https://example.org/second" in detail, detail


def test_a_named_graph_that_says_more_than_the_default_graph_is_reported(make_package):
    """The default graph is metadata.rdf's; a named graph adds a title.
    The file says more than metadata.rdf, which L9 reports -- and the merged
    graph the other rules read does not take the title in."""
    more = {"@id": GRAPH, "@graph": [{"@id": "urn:test:topic1", "title": "Another title"}]}
    jsonld = _document(_nodes() + [more])
    [finding] = _findings(_lint(make_package, jsonld), "L9")
    assert "1 statement(s) only in META-INF/metadata.jsonld" in finding.violation.detail

    def others(report):
        return sorted((f.rule.id, f.violation.subject or "", f.violation.detail or "")
                      for f in report.findings if f.rule.id not in ("L9", "L17"))

    alone = runner.check(make_package(metadata=DESCRIPTION_STYLE_RDF))
    assert others(runner.check(make_package(metadata=DESCRIPTION_STYLE_RDF,
                                            jsonld=jsonld))) == others(alone)


def test_a_json_ld_file_with_only_named_graphs_gives_the_merge_nothing(make_package):
    """Without metadata.rdf, the rules that read the merge read what a reader
    of the default graph reads: nothing, as from an empty file."""
    def rules(jsonld):
        report = runner.check(make_package(metadata=None, jsonld=jsonld))
        return sorted({f.rule.id for f in report.findings} - {"L9", "L17"})

    assert rules(_named()) == rules(_document([]))


def test_a_named_graph_repeating_anonymous_nodes_does_not_double_them(make_package):
    """A rendition with no name is a blank node, a different one in each
    graph; a named graph repeating the default one is the same statements."""
    package, topic, rendition = _nodes()
    rendition = {k: v for k, v in rendition.items() if k != "@id"}
    topic = dict(topic, **{"has-rendition": rendition})
    single = [package, topic]
    alone = runner.lint(make_package(metadata=MINIMAL_RDF, jsonld=_document(single)))
    assert not _findings(alone, "L9"), "the fixture is not MINIMAL_RDF"
    repeated = _document(single + [{"@id": GRAPH, "@graph": single}])
    report = runner.lint(make_package(metadata=MINIMAL_RDF, jsonld=repeated))
    assert not _findings(report, "L9"), [f.violation.detail for f in _findings(report, "L9")]
    assert not _findings(report, "L17")


def test_a_named_graph_with_nothing_in_it_is_no_graph(make_package):
    jsonld = _document(_nodes() + [{"@id": GRAPH, "@graph": []}])
    graph, named, error = iirds.parse_metadata_graphs(iirds.METADATA_JSONLD, jsonld.encode(),
                                                      base=iirds.PACKAGE_BASE)
    assert error is None and named == {}
    assert not _findings(_lint(make_package, jsonld), "L17")


def test_a_graph_named_by_a_blank_node_is_reported_the_same_way_twice(make_package):
    jsonld = _named(name="_:g")
    details = {_findings(_lint(make_package, jsonld), "L17")[0].violation.detail for _ in range(2)}
    assert len(details) == 1 and "1 without a name" in details.pop()


def test_the_finding_names_the_file_a_named_graph_states_in(make_package):
    """M30 says which file redeclares the schema; a statement only a named
    graph of metadata.jsonld holds is in that file."""
    declared = ("http://iirds.tekom.de/iirds#Topic", "http://www.w3.org/2000/01/rdf-schema#Class")
    rdf = DESCRIPTION_STYLE_RDF.replace(
        "</rdf:RDF>", '  <rdf:Description rdf:about="%s">\n    <rdf:type rdf:resource="%s"/>\n'
                      '  </rdf:Description>\n</rdf:RDF>' % declared)
    jsonld = _document(_nodes() + [{"@id": GRAPH, "@graph": [{"@id": declared[0], "@type": declared[1]}]}])
    [finding] = [f for f in runner.check(make_package(metadata=rdf, jsonld=jsonld)).findings
                 if f.rule.id == "M30"]
    said = " ".join(str(value) for value in vars(finding.violation).values())
    assert "metadata.jsonld" in said and "metadata.rdf" in said, said


def test_many_named_graphs_cost_one_fingerprint_each_at_most(make_package, monkeypatch):
    """Each graph is fingerprinted at most once, and not at all where it holds
    no node without a name, since then a plain union is exact."""
    from iirds import _metadata

    asked = []
    fingerprint = _metadata._fingerprint
    monkeypatch.setattr(_metadata, "_fingerprint", lambda graph: asked.append(1) or fingerprint(graph))
    graphs = [{"@id": "urn:test:g%d" % n, "@graph": [{"@id": "urn:test:topic1", "title": "T%d" % n}]}
              for n in range(300)]
    report = _lint(make_package, _document(_nodes() + graphs))
    assert _findings(report, "L17") and len(asked) == 0, len(asked)


def test_the_warning_counts_what_it_does_not_name(make_package):
    first, second, third = _nodes()
    graphs = [{"@id": "urn:test:g%d" % n, "@graph": [node]} for n, node in enumerate(_nodes())]
    graphs += [{"@id": "urn:test:g3", "@graph": [dict(first, title="Other")]},
               {"@id": "_:a", "@graph": [dict(second, title="A")]},
               {"@id": "_:b", "@graph": [dict(third, source="content/b.xhtml")]}]
    [finding] = _findings(_lint(make_package, _document(graphs)), "L17")
    detail = finding.violation.detail
    assert "1 more" in detail and "2 without a name" in detail, detail


def test_a_graph_named_as_rdflib_names_its_default_is_a_named_graph(make_package):
    [finding] = _findings(_lint(make_package, _named(name="urn:x-rdflib:default")), "L17")
    assert "urn:x-rdflib:default" in finding.violation.detail


def test_the_file_a_described_extension_is_in_is_named(make_package):
    """R18 says where a proprietary class is described; a named graph of
    metadata.jsonld is metadata.jsonld."""
    document = json.loads(MINIMAL_JSONLD)
    document["@graph"].append({"@id": "iirds:Topic",
                               "http://www.w3.org/2002/07/owl#equivalentClass":
                                   {"@id": "http://example.com/my#Topic"}})
    document["@graph"].append({"@id": GRAPH, "@graph": [
        {"@id": "http://example.com/my#Topic", "http://www.w3.org/2000/01/rdf-schema#label": "My topic"}]})
    report = runner.check(make_package(metadata=DESCRIPTION_STYLE_RDF, jsonld=json.dumps(document)))
    [finding] = [f for f in report.findings if f.rule.id == "R18"]
    assert "metadata.jsonld" in (finding.violation.detail or ""), finding.violation.detail




def _graph(*triples):
    graph = Graph()
    for triple in triples:
        graph.add(triple)
    return graph


def test_a_graph_sharing_a_node_without_a_name_is_not_a_repeat():
    """A blank node's label names one node across a JSON-LD document, so a
    graph that has the default graph's shape but speaks of its nodes says
    something of its own; one with nodes of its own repeats it."""
    from iirds import merge_graphs_of

    t1, t2, has, fmt = (URIRef("urn:t1"), URIRef("urn:t2"), URIRef("urn:has"), URIRef("urn:fmt"))
    a, b, c = BNode("a"), BNode("b"), BNode("c")
    default = _graph((t1, has, a), (a, fmt, Literal("x")), (t2, has, b), (b, fmt, Literal("y")))
    swapped = _graph((t1, has, b), (b, fmt, Literal("x")), (t2, has, a), (a, fmt, Literal("y")))
    assert len(merge_graphs_of({None: default, URIRef("urn:g"): swapped})) == 8
    alone = _graph((t1, has, a), (a, fmt, Literal("x")))
    again = _graph((t1, has, c), (c, fmt, Literal("x")))
    assert len(merge_graphs_of({None: alone, URIRef("urn:g"): again})) == 2


def test_an_iri_spelled_like_a_blank_node_is_its_own_graph():
    nodes = _nodes()
    context = dict(json.loads(MINIMAL_JSONLD)["@context"], bn="_:")
    document = json.dumps({"@context": context, "@graph": [
        {"@id": "bn:g", "@graph": nodes[:2]}, {"@id": "_:g", "@graph": nodes[2:]}]})
    graph, named, error = iirds.parse_metadata_graphs(iirds.METADATA_JSONLD, document.encode(),
                                                      base=iirds.PACKAGE_BASE)
    assert error is None and len(named) == 2, named


def test_two_named_graphs_repeating_each_other_count_once(make_package):
    package, topic, rendition = _nodes()
    rendition = {k: v for k, v in rendition.items() if k != "@id"}
    single = [package, dict(topic, **{"has-rendition": rendition})]
    twice = _document([{"@id": "urn:test:v1", "@graph": single},
                       {"@id": "urn:test:v2", "@graph": single}])
    report = runner.lint(make_package(metadata=MINIMAL_RDF, jsonld=twice))
    assert not _findings(report, "L9"), [f.violation.detail for f in _findings(report, "L9")]
    assert _findings(report, "L17")


def test_graphs_with_nodes_of_their_own_are_fingerprinted_once_each(monkeypatch):
    """Where every named graph holds a node without a name of its own, each
    is fingerprinted, and once."""
    from iirds import _metadata, merge_graphs_of

    asked = []
    fingerprint = _metadata._fingerprint
    monkeypatch.setattr(_metadata, "_fingerprint", lambda graph: asked.append(1) or fingerprint(graph))
    has, fmt = URIRef("urn:has"), URIRef("urn:fmt")
    graphs = {None: _graph((URIRef("urn:t"), has, URIRef("urn:r")))}
    for n in range(50):
        node = BNode()
        graphs[URIRef("urn:g%d" % n)] = _graph((URIRef("urn:t%d" % n), has, node),
                                               (node, fmt, Literal("f%d" % n)))
    merged = merge_graphs_of(graphs)
    assert len(merged) == 101 and len(asked) == 50, (len(merged), len(asked))

