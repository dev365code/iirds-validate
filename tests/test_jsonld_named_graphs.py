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

import iirds
from conftest import DESCRIPTION_STYLE_RDF, MINIMAL_JSONLD
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
    assert sorted(named) == [GRAPH] and len(named[GRAPH]) > 0
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
