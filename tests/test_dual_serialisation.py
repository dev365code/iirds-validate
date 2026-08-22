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


def test_matching_serialisations_do_not_double_blank_nodes(make_package):
    """Two serialisations of the same graph must count as one graph.

    Blank nodes cannot be co-identified across documents, so merging both
    files naively doubles every blank-node-rooted structure — and a package
    that legitimately ships RDF/XML and JSON-LD then fails count rules
    (one inline IdentityDomain becomes "2 domains") that the same metadata
    passes when shipped alone. Found by the round-4 adversarial pass; the
    SHACL shapes, which read one file, were the side that was right."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_handover_rules_fire import _jsonld

    with_bnode = MINIMAL_RDF.replace("</rdf:RDF>", """  <iirds:Identity rdf:about="urn:test:id1">
    <iirds:identifier>SN-1</iirds:identifier>
    <iirds:has-identity-domain>
      <iirds:IdentityDomain>
        <rdfs:label xml:lang="en">Serials</rdfs:label>
      </iirds:IdentityDomain>
    </iirds:has-identity-domain>
  </iirds:Identity>
</rdf:RDF>""")
    alone = runner.check(make_package(metadata=with_bnode, name="alone.iirds"))
    both = runner.check(make_package(metadata=with_bnode, jsonld=_jsonld(with_bnode),
                                     name="both.iirds"))
    assert ids(alone) == ids(both), (
        "the same graph, shipped once vs twice, must not change what fires; "
        "diff: %s" % sorted(ids(both) ^ ids(alone)))
    assert "M19.3" not in ids(both) and "M36" not in ids(both)
