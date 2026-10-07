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

import pytest
from rdflib import BNode, Graph, Literal, URIRef

import iirds
import iirds._metadata as metadata
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


def test_graphs_without_nodes_of_their_own_are_not_fingerprinted(make_package, monkeypatch):
    """Each graph is fingerprinted at most once, and not at all where it holds
    no node without a name, since then a plain union is exact. The two calls
    there are are the merge's, asking once of each file's default graph
    whether the second repeats the first; none is for the three hundred
    named graphs."""
    from iirds import _metadata

    asked = []
    fingerprint = _metadata._fingerprint
    monkeypatch.setattr(_metadata, "_fingerprint", lambda graph: asked.append(1) or fingerprint(graph))
    graphs = [{"@id": "urn:test:g%d" % n, "@graph": [{"@id": "urn:test:topic1", "title": "T%d" % n}]}
              for n in range(300)]
    report = _lint(make_package, _document(_nodes() + graphs))
    assert _findings(report, "L17") and len(asked) == 2, len(asked)


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
    assert len(merge_graphs_of({None: default, URIRef("urn:g"): swapped})[0]) == 8
    alone = _graph((t1, has, a), (a, fmt, Literal("x")))
    again = _graph((t1, has, c), (c, fmt, Literal("x")))
    assert len(merge_graphs_of({None: alone, URIRef("urn:g"): again})[0]) == 2


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
    merged = merge_graphs_of(graphs)[0]
    assert len(merged) == 101 and len(asked) == 50, (len(merged), len(asked))


def test_named_graphs_are_graphs_of_their_own():
    """Read out of the parse's store and taken out of it, so that reading one
    graph does not list every graph a statement repeats in."""
    graphs = [{"@id": "urn:test:g%d" % n, "@graph": _nodes()[:1]} for n in range(50)]
    graph, named, error = iirds.parse_metadata_graphs(
        iirds.METADATA_JSONLD, _document(_nodes() + graphs).encode(), base=iirds.PACKAGE_BASE)
    assert error is None and len(named) == 50
    assert all(held.store is not graph.store for held in named.values())
    for triple in graph:
        assert [c.identifier for c in graph.store.contexts(triple)] == [graph.identifier]


def test_a_repeat_differing_only_in_a_language_tag_case_is_a_repeat(make_package):
    package, topic, rendition = _nodes()
    rendition = {k: v for k, v in rendition.items() if k != "@id"}
    tagged = dict(topic, title={"@value": "A topic", "@language": "de"},
                  **{"has-rendition": rendition})
    shouted = dict(tagged, title={"@value": "A topic", "@language": "DE"})
    graph = _document([package, tagged, {"@id": GRAPH, "@graph": [package, shouted]}])
    from iirds import merge_graphs_of
    _default, named, _error = iirds.parse_metadata_graphs(iirds.METADATA_JSONLD, graph.encode(),
                                                          base=iirds.PACKAGE_BASE)
    merged = merge_graphs_of(dict({None: _default}, **{str(k): v for k, v in named.items()}))[0]
    assert len(merged) == len(_default)


def test_the_warning_names_only_graphs_that_hide_something(make_package):
    first, second, third = _nodes()
    jsonld = _document([first, second, third,
                        {"@id": "urn:test:restates", "@graph": [first]},
                        {"@id": "urn:test:adds", "@graph": [dict(first, title="Else")]}])
    [finding] = _findings(_lint(make_package, jsonld), "L17")
    assert "urn:test:adds" in finding.violation.detail
    assert "urn:test:restates" not in finding.violation.detail, finding.violation.detail


def _sibling_chain(length):
    """A table of contents as iiRDS writes one without names: each directory
    node leads to the next through has-next-sibling."""
    node = {"@type": "iirds:DirectoryNode", "title": "entry %d" % length}
    for n in range(length - 1, 0, -1):
        node = {"@type": "iirds:DirectoryNode", "title": "entry %d" % n,
                "iirds:has-next-sibling": node}
    return {"@id": "urn:test:toc", "@type": "iirds:DirectoryNode", "iirds:has-first-child": node}


def test_a_repeat_of_any_depth_is_counted_once(make_package):
    """Sixty directory nodes without names, chained, and a named graph that
    repeats them whole. The chain is a tree, named from its leaves up however
    deep it goes, so the repeat is the same graph again and L9 finds nothing;
    before the comparison was bounded, a chain past forty could not be counted
    and the repeat read as more statements."""
    from rdflib import Graph as RDFGraph

    nodes = _nodes() + [_sibling_chain(60)]
    default_only = _document(nodes)
    rdf = RDFGraph()
    rdf.parse(data=default_only, format="json-ld", publicID=iirds.PACKAGE_BASE)
    metadata = rdf.serialize(format="xml")
    repeated = _document(nodes + [{"@id": GRAPH, "@graph": nodes}])
    report = runner.lint(make_package(metadata=metadata, jsonld=repeated))
    assert not _findings(report, "L9"), [f.violation.detail for f in _findings(report, "L9")]


def test_a_shallow_repeat_is_still_compared(make_package):
    from rdflib import Graph as RDFGraph

    nodes = _nodes() + [_sibling_chain(10)]
    rdf = RDFGraph()
    rdf.parse(data=_document(nodes), format="json-ld", publicID=iirds.PACKAGE_BASE)
    repeated = _document(nodes + [{"@id": GRAPH, "@graph": nodes}])
    report = runner.lint(make_package(metadata=rdf.serialize(format="xml"), jsonld=repeated))
    assert not _findings(report, "L9"), [f.violation.detail for f in _findings(report, "L9")]


def test_a_difference_beside_a_deep_repeat_is_reported_as_it_is(make_package):
    """Two named graphs holding the same deep chain, and a default graph
    lacking a statement metadata.rdf has: the chain counts once, and L9
    reports the one statement that differs and nothing about the chain."""
    from rdflib import Graph as RDFGraph

    nodes = _nodes()
    rdf = RDFGraph()
    rdf.parse(data=_document(nodes), format="json-ld", publicID=iirds.PACKAGE_BASE)
    chain = [_sibling_chain(60)]
    lacking = [dict(nodes[0], title=None)] + nodes[1:]
    lacking[0] = {k: v for k, v in lacking[0].items() if v is not None}
    jsonld = _document(lacking + [{"@id": "urn:test:v1", "@graph": chain},
                                  {"@id": "urn:test:v2", "@graph": chain}])
    for triple in RDFGraph().parse(data=_document(chain), format="json-ld", publicID=iirds.PACKAGE_BASE):
        rdf.add(triple)
    report = runner.lint(make_package(metadata=rdf.serialize(format="xml"), jsonld=jsonld))
    [finding] = _findings(report, "L9")
    assert finding.violation.detail.startswith(
        "1 statement(s) only in %s" % iirds.METADATA_RDF), finding.violation.detail
    assert "only in %s" % iirds.METADATA_JSONLD not in finding.violation.detail


def test_the_warning_does_not_name_a_whole_repeat(make_package):
    """A named graph repeating the default one, anonymous nodes and all, is
    left out as a repeat, and hides nothing."""
    package, topic, rendition = _nodes()
    rendition = {k: v for k, v in rendition.items() if k != "@id"}
    single = [package, dict(topic, **{"has-rendition": rendition})]
    report = runner.lint(make_package(metadata=MINIMAL_RDF,
                                      jsonld=_document(single + [{"@id": GRAPH, "@graph": single}])))
    assert not _findings(report, "L17"), [f.violation.detail for f in _findings(report, "L17")]


def _shared_node_graph(name, source):
    """Two topics sharing one rendition without a name: a tree, since only
    named nodes point at it, and they join its name."""
    node = "_:%s" % name.rsplit(":", 1)[1]
    return {"@id": name, "@graph": [
        {"@id": "urn:test:t1", "has-rendition": {"@id": node}},
        {"@id": "urn:test:t2", "has-rendition": {"@id": node}},
        {"@id": node, "format": "application/xhtml+xml", "source": source}]}


def test_graphs_sharing_a_node_and_differing_are_reported_the_same_every_time(make_package):
    """Two graphs of one size, each with a rendition two topics share, one of
    them in metadata.rdf too: the other is more statements, reported the same
    way whichever way the store orders them."""
    from rdflib import Graph as RDFGraph

    nodes = _nodes()
    first = _shared_node_graph("urn:test:v1", "content/one.xhtml")
    second = _shared_node_graph("urn:test:v2", "content/two.xhtml")
    rdf = RDFGraph()
    rdf.parse(data=_document(nodes + first["@graph"]), format="json-ld", publicID=iirds.PACKAGE_BASE)
    jsonld = _document(nodes + [first, second])
    details = set()
    for _ in range(3):
        report = runner.lint(make_package(metadata=rdf.serialize(format="xml"), jsonld=jsonld))
        [finding] = _findings(report, "L9")
        details.add(finding.violation.detail)
    [detail] = details
    assert detail.startswith("4 statement(s) only in %s" % iirds.METADATA_JSONLD), detail


def _ring_graph(name, count):
    """`count` nodes without names, each pointing at the next and the last at
    the first: a cycle, so not a tree."""
    return {"@id": name, "@graph": [
        {"@id": "_:r%d" % index, "urn:test:next": {"@id": "_:r%d" % ((index + 1) % count)}}
        for index in range(count)]}


def test_a_named_graph_past_the_comparison_limit_is_not_compared(make_package):
    """The default graphs are compared and merged, and a named graph takes
    the JSON-LD file past the limit: L9 says the files were not compared,
    names the limit, and the run fails rather than pass on files nobody
    compared."""
    limit = iirds.MAX_COMPARED_BLANK_NODES
    nodes = _nodes()
    jsonld = _document(nodes + [_ring_graph("urn:test:ring", limit + 1)])
    report = runner.lint(make_package(metadata=MINIMAL_RDF, jsonld=jsonld))
    [finding] = _findings(report, "L9")
    assert finding.violation.message == "the two metadata serialisations were not compared"
    assert "at most %d" % limit in finding.violation.detail, finding.violation.detail
    assert "at most %d blank nodes" % limit in finding.violation.fix
    assert not _findings(report, "C16.2")
    assert not report.ok


def _ring_of(name, count, tag):
    """`_ring_graph` with labels of its own, so that two of them are two
    structures and not one joined across graphs."""
    return {"@id": name, "@graph": [
        {"@id": "_:%s%d" % (tag, index),
         "urn:test:next": {"@id": "_:%s%d" % (tag, (index + 1) % count)}}
        for index in range(count)]}


def _counting_searches(monkeypatch):
    asked = []
    real = metadata._structure_name

    def counted(nodes, *rest):
        asked.append(len(nodes))
        return real(nodes, *rest)

    monkeypatch.setattr(metadata, "_structure_name", counted)
    return asked


def test_graphs_that_pass_the_limit_between_them_are_searched_nowhere(make_package, monkeypatch):
    """The limit is the file's, named graphs included. Three graphs each
    within it, past it between them: no order of any of them is tried, and
    L9 says the files were not compared -- where each graph was searched on
    its own, and a file of many such graphs cost a search apiece."""
    asked = _counting_searches(monkeypatch)
    size = iirds.MAX_COMPARED_BLANK_NODES // 2 + 1
    rings = [_ring_of("urn:test:ring%d" % index, size, "r%d_" % index) for index in range(3)]
    report = runner.lint(make_package(metadata=DESCRIPTION_STYLE_RDF,
                                      jsonld=_document(_nodes() + rings)))
    assert asked == [], asked
    [finding] = _findings(report, "L9")
    assert finding.violation.message == "the two metadata serialisations were not compared"


def test_graphs_within_the_limit_between_them_are_still_counted_once(monkeypatch):
    """Two graphs that repeat each other, each a ring, the two together at the
    limit: searched, and the second is a repeat."""
    asked = _counting_searches(monkeypatch)
    size = iirds.MAX_COMPARED_BLANK_NODES // 2
    graphs = {None: Graph()}
    for index in range(2):
        document = json.dumps({"@graph": [_ring_of("urn:test:ring%d" % index, size, "r%d_" % index)]})
        _default, named, error = iirds.parse_metadata_graphs(
            iirds.METADATA_JSONLD, document.encode("utf-8"), base=iirds.PACKAGE_BASE)
        assert error is None, error
        graphs.update(named)
    _merged, repeats, uncounted = iirds.merge_graphs_of(graphs)
    assert repeats == [URIRef("urn:test:ring1")] and uncounted == [], (repeats, uncounted)
    assert asked == [size, size], asked


def _tree_graph():
    graph = Graph()
    rendition = BNode()
    graph.add((URIRef("urn:test:topic1"), URIRef("urn:test:has"), rendition))
    graph.add((rendition, URIRef("urn:test:source"), Literal("content/topic1.xhtml")))
    return graph


def test_of_two_graphs_that_repeat_each_other_the_first_by_name_is_kept():
    """Which of two repeats is left out decides what L17 names, and the order
    the graphs arrive in follows the parser's blank-node labels and the hash
    seed -- so the same file named one graph on one run and the other on the
    next. The graph kept is the first by name, and a graph with a name before
    one without."""
    for order in ((URIRef("urn:test:v2"), URIRef("urn:test:v1")),
                  (URIRef("urn:test:v1"), URIRef("urn:test:v2"))):
        graphs = {None: Graph()}
        graphs.update((name, _tree_graph()) for name in order)
        assert iirds.merge_graphs_of(graphs)[1] == [URIRef("urn:test:v2")], order
    unnamed = BNode()
    for order in ((unnamed, URIRef("urn:test:z")), (URIRef("urn:test:z"), unnamed)):
        graphs = {None: Graph()}
        graphs.update((name, _tree_graph()) for name in order)
        assert iirds.merge_graphs_of(graphs)[1] == [unnamed], order


def test_a_language_tag_is_compared_without_regard_to_case(make_package):
    """Case carries no meaning in a language tag (RFC 5646, section 2.1.1),
    and RDF lets a reader write every tag in lower case. `de` in one file and
    `DE` in the other are one statement: L9 does not report it, and the merge
    reads it once -- where it read two, and a rule counting what hung off an
    anonymous node counted twice."""
    rdf = DESCRIPTION_STYLE_RDF.replace("<ii:title>A topic</ii:title>",
                                        '<ii:title xml:lang="de">A topic</ii:title>')
    document = json.loads(MINIMAL_JSONLD)
    for node in document["@graph"]:
        if node.get("title") == "A topic":
            node["title"] = {"@value": "A topic", "@language": "DE"}
    assert rdf != DESCRIPTION_STYLE_RDF and "DE" in json.dumps(document)
    report = runner.check(make_package(metadata=rdf, jsonld=json.dumps(document)))
    assert not _findings(report, "L9"), [f.violation.detail for f in _findings(report, "L9")]
    one, _error = iirds.parse_metadata(iirds.METADATA_RDF, rdf.encode("utf-8"),
                                       base=iirds.PACKAGE_BASE)
    other, _error = iirds.parse_metadata(iirds.METADATA_JSONLD,
                                         json.dumps(document).encode("utf-8"),
                                         base=iirds.PACKAGE_BASE)
    assert iirds.graph_difference(one, other) == ([], [])
    assert len(iirds.merge_sources({iirds.METADATA_RDF: one,
                                    iirds.METADATA_JSONLD: other})) == len(one)


_TOC_RDF = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:title>Test package</iirds:title>
  </iirds:Package>
  <iirds:Topic rdf:about="urn:test:topic1">
    <iirds:title xml:lang="de">Ein Thema</iirds:title>
    <iirds:has-rendition rdf:resource="urn:test:rendition1"/>
  </iirds:Topic>
  <iirds:Rendition rdf:about="urn:test:rendition1">
    <iirds:format>application/xhtml+xml</iirds:format>
    <iirds:source>content/topic1.xhtml</iirds:source>
  </iirds:Rendition>
  <iirds:DirectoryNode rdf:about="urn:test:toc">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
    <iirds:has-first-child>
      <iirds:DirectoryNode>
        <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
        <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
      </iirds:DirectoryNode>
    </iirds:has-first-child>
  </iirds:DirectoryNode>
</rdf:RDF>
"""


def _toc_jsonld(language):
    ii = "http://iirds.tekom.de/iirds#"
    return json.dumps({"@graph": [
        {"@id": "urn:test:package", "@type": ii + "Package",
         ii + "iiRDSVersion": "1.3", ii + "title": "Test package"},
        {"@id": "urn:test:topic1", "@type": ii + "Topic",
         ii + "title": {"@value": "Ein Thema", "@language": language},
         ii + "has-rendition": {"@id": "urn:test:rendition1"}},
        {"@id": "urn:test:rendition1", "@type": ii + "Rendition",
         ii + "format": "application/xhtml+xml", ii + "source": "content/topic1.xhtml"},
        {"@id": "urn:test:toc", "@type": ii + "DirectoryNode",
         ii + "has-directory-structure-type": {"@id": ii + "TableOfContents"},
         ii + "has-next-sibling": {"@id": ii + "nil"},
         ii + "has-first-child": {"@type": ii + "DirectoryNode",
                                  ii + "relates-to-information-unit": {"@id": "urn:test:topic1"},
                                  ii + "has-next-sibling": {"@id": ii + "nil"}}}]})


def test_a_language_tag_case_does_not_double_what_hangs_off_an_anonymous_node(make_package):
    """The merge reads a file that repeats the one before it once. Read as two
    files, the anonymous node under the table of contents was two nodes, and
    M24.3 counted two first children where each file has one."""
    same = runner.check(make_package(metadata=_TOC_RDF, jsonld=_toc_jsonld("de")))
    assert same.ok, [(f.rule.id, f.violation.message) for f in same.findings]
    upper = runner.check(make_package(metadata=_TOC_RDF, jsonld=_toc_jsonld("DE")))
    assert upper.ok, [(f.rule.id, f.violation.message) for f in upper.findings]
    package = iirds.open(make_package(metadata=_TOC_RDF, jsonld=_toc_jsonld("DE")))
    alone = iirds.open(make_package(name="alone.iirds", metadata=_TOC_RDF))
    assert len(package.graph) == len(alone.graph), (len(package.graph), len(alone.graph))


def _anonymous():
    """The package, a topic, and a rendition with no name: MINIMAL_RDF's
    statements, its rendition a blank node."""
    package, topic, rendition = _nodes()
    return package, topic, {k: v for k, v in rendition.items() if k != "@id"}


def _labelled(label="_:r"):
    """The same, the rendition given a blank-node label a graph can share."""
    package, topic, rendition = _anonymous()
    return [package, dict(topic, **{"has-rendition": dict(rendition, **{"@id": label})})]


#: What a graph beside the default one says of the default graph's labelled
#: rendition: a statement the default graph makes too, held from the topic's
#: side, the rendition's, or both.
SHARING = {
    "the topic's side": [{"@id": "urn:test:topic1", "has-rendition": "_:r"}],
    "the rendition's side": [{"@id": "_:r", "format": "application/xhtml+xml"}],
    "both sides": [{"@id": "urn:test:topic1",
                    "has-rendition": {"@id": "_:r", "format": "application/xhtml+xml"}}],
}


@pytest.mark.parametrize("side", list(SHARING))
def test_a_whole_repeat_counts_once_where_the_default_graph_shares_a_label(make_package, side):
    """J05 and its twins. The default graph's rendition label is used in
    another graph too, which made the default graph one never fingerprinted,
    so a third graph repeating it whole -- a rendition without a name of its
    own -- was taken for more statements, a second rendition, and L9 failed
    the package. A label names one node across the document, so the graph
    sharing it is joined as it is; the default graph is still the graph it
    is, and a graph repeating it is left out."""
    package, topic, rendition = _anonymous()
    repeat = {"@id": "urn:test:g2", "@graph": [package, dict(topic, **{"has-rendition": rendition})]}
    jsonld = _document(_labelled() + [{"@id": "urn:test:g1", "@graph": SHARING[side]}, repeat])
    package = make_package(metadata=MINIMAL_RDF, jsonld=jsonld)
    checked, linted = runner.check(package), runner.lint(package)
    assert checked.ok, [(f.rule.id, f.violation.detail) for f in checked.findings]
    assert not _findings(linted, "L9"), [f.violation.detail for f in _findings(linted, "L9")]
    assert not _findings(linted, "L17"), [f.violation.detail for f in _findings(linted, "L17")]


def _j(extra, labelled=False):
    """A document after jl's J cases: the default graph, then `extra`."""
    package, topic, rendition = _anonymous()
    default = _labelled() if labelled else [package, dict(topic, **{"has-rendition": rendition})]
    return _document(default + extra)


def _repeat(**changed):
    package, topic, rendition = _anonymous()
    return [package, dict(topic, **dict({"has-rendition": rendition}, **changed))]


#: (the named graphs, whether the default graph's rendition is labelled,
#: whether the package passes)
J_CASES = {
    "J02 a named graph that says another title": (
        [{"@id": "urn:test:g", "@graph": _repeat(title="Other")}], False, False),
    "J03 a whole repeat": ([{"@id": "urn:test:g", "@graph": _repeat()}], False, True),
    "J04 a partial repeat, its rendition a second one": (
        [{"@id": "urn:test:g", "@graph": _repeat()[1:]}], False, False),
    "J05 a whole repeat, the default graph's label shared": (
        [{"@id": "urn:test:g1", "@graph": SHARING["the rendition's side"]},
         {"@id": "urn:test:g2", "@graph": _repeat()}], True, True),
    "J05c the same without the graph that shares it": (
        [{"@id": "urn:test:g2", "@graph": _repeat()}], True, True),
    "J05 with the repeat saying another title": (
        [{"@id": "urn:test:g1", "@graph": SHARING["the rendition's side"]},
         {"@id": "urn:test:g2", "@graph": _repeat(title="Other")}], True, False),
    "J05 with the repeat holding a second rendition": (
        [{"@id": "urn:test:g1", "@graph": SHARING["the rendition's side"]},
         {"@id": "urn:test:g2", "@graph": _repeat(**{"has-rendition": [
             _anonymous()[2], dict(_anonymous()[2], source="content/topic2.xhtml")]})}],
        True, False),
    "J05 with the shared label saying something only it says": (
        [{"@id": "urn:test:g1", "@graph": [{"@id": "_:r", "source": "content/other.xhtml"}]},
         {"@id": "urn:test:g2", "@graph": _repeat()}], True, False),
}


@pytest.mark.parametrize("case", list(J_CASES))
def test_what_only_one_file_says_is_still_l9s(make_package, case):
    """A repeat is left out only where it is the same statements; a value
    changed, a node more, or a statement only the shared label's graph makes
    is in metadata.jsonld and not metadata.rdf, and L9 says so."""
    extra, labelled, passes = J_CASES[case]
    report = runner.check(make_package(metadata=MINIMAL_RDF, jsonld=_j(extra, labelled)))
    assert report.ok is passes, (case, [(f.rule.id, f.violation.detail) for f in report.findings])
    assert bool(_findings(report, "L9")) is not passes, case
