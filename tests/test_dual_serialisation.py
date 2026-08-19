"""L9 — the two metadata files must describe the same graph.

iiRDS 1.3 lets a package carry its metadata twice, as RDF/XML and as JSON-LD.
Nothing requires a consumer to read both, so if they disagree, two conformant
readers get different data from the same package and neither can tell. The
validator merges them into one graph, which is right for every other rule and
makes exactly this defect invisible — hence a rule that looks at them apart.
"""
from __future__ import annotations

from conftest import DESCRIPTION_STYLE_RDF, MINIMAL_JSONLD, MINIMAL_RDF
from iirds_validate import runner


def ids(report):
    return {f.rule.id for f in report.findings}


def test_matching_serialisations_are_clean(make_package):
    """DESCRIPTION_STYLE_RDF and MINIMAL_JSONLD are the same graph written two
    ways — different syntax, different prefixes, identical triples."""
    report = runner.lint(make_package(metadata=DESCRIPTION_STYLE_RDF, jsonld=MINIMAL_JSONLD))
    assert "L9" not in ids(report), [f.violation.detail for f in report.findings]


def test_a_blank_node_where_the_other_names_a_resource_is_a_difference(make_package):
    """MINIMAL_RDF nests its Rendition as a blank node; MINIMAL_JSONLD gives it
    the IRI urn:test:rendition1. Those are not the same graph, and the
    difference is one a consumer would see: a reader of the JSON-LD can
    reference that rendition from elsewhere and a reader of the RDF/XML
    cannot. Reported, not excused."""
    report = runner.lint(make_package(metadata=MINIMAL_RDF, jsonld=MINIMAL_JSONLD))
    assert "L9" in ids(report)


def test_divergent_serialisations_are_reported(make_package):
    diverged = MINIMAL_JSONLD.replace('"title": "A topic"', '"title": "A different topic"')
    report = runner.lint(make_package(metadata=DESCRIPTION_STYLE_RDF, jsonld=diverged))
    assert "L9" in ids(report)


def test_a_missing_statement_in_one_serialisation_is_reported(make_package):
    thinner = MINIMAL_JSONLD.replace('"iiRDSVersion": "1.3", ', "")
    report = runner.lint(make_package(metadata=DESCRIPTION_STYLE_RDF, jsonld=thinner))
    assert "L9" in ids(report)


def test_one_serialisation_alone_is_not_a_finding(make_package):
    assert "L9" not in ids(runner.lint(make_package(metadata=MINIMAL_RDF)))
