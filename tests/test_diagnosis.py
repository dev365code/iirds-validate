"""Where the problem is, said as such.

A report that lists three symptoms of one cause sends a reader to three
places. A package whose metadata names no iiRDS term at all -- because the
namespace is spelled `iirds/` for `iirds#`, say -- used to get "declares no
iirds:Package" and three "proprietary class not linked": every finding true,
every one of them the wrong place to look. These tests hold the report to
naming the layer: nothing here is iiRDS; this namespace is nearly iiRDS's;
these rules did not run, and for which reason.
"""
from __future__ import annotations

import json

from conftest import MINIMAL_RDF
from iirds_validate import runner

FOREIGN = MINIMAL_RDF.replace("http://iirds.tekom.de/iirds#", "http://example.org/nothing-to-do-with-iirds#")
SLASH_FOR_HASH = MINIMAL_RDF.replace("http://iirds.tekom.de/iirds#", "http://iirds.tekom.de/iirds/")
HTTPS = MINIMAL_RDF.replace("http://iirds.tekom.de/iirds#", "https://iirds.tekom.de/iirds#")
ON_THE_HOST = MINIMAL_RDF.replace("http://iirds.tekom.de/iirds#", "http://iirds.tekom.de/iirds-ext#")


def ids(report):
    return {f.rule.id for f in report.findings}


def note_about(report, needle):
    return [n for n in report.notes if needle in n]


# --- nothing here is iiRDS -------------------------------------------------

def test_metadata_naming_no_iirds_term_is_said_so_in_one_sentence(make_package):
    report = runner.run(make_package(metadata=FOREIGN), runner.ALL_KINDS)
    notes = note_about(report, "no iiRDS term")
    assert notes, report.notes
    assert "namespace" in notes[0]


def test_a_package_with_iirds_terms_gets_no_such_note(make_package):
    report = runner.run(make_package(), runner.ALL_KINDS)
    assert not note_about(report, "no iiRDS term")


def test_the_note_travels_in_the_json_report(make_package):
    report = runner.run(make_package(metadata=FOREIGN), runner.ALL_KINDS)
    assert any("no iiRDS term" in n for n in json.loads(json.dumps(report.as_dict()))["notes"])


# --- a namespace that is nearly iiRDS's --------------------------------------

def test_a_slash_where_the_hash_belongs_is_named_as_the_near_miss_it_is(make_package):
    """`http://iirds.tekom.de/iirds/Topic` is not an iiRDS term to any
    consumer, and the package was reported as a set of proprietary classes.
    It is one namespace one character from the standard's, and every name
    under it is a name the standard has."""
    report = runner.lint(make_package(metadata=SLASH_FOR_HASH))
    assert "L14" in ids(report)
    finding = [f for f in report.findings if f.rule.id == "L14"][0]
    assert finding.violation.subject == "http://iirds.tekom.de/iirds/"
    assert "http://iirds.tekom.de/iirds#" in (finding.violation.detail or "")
    assert "of them iiRDS names" in (finding.violation.detail or "")


def test_https_for_http_is_a_near_miss_too(make_package):
    assert "L14" in ids(runner.lint(make_package(metadata=HTTPS)))


def test_anything_else_on_the_standards_host_is_reported_whatever_its_distance(make_package):
    """Nobody but the standard mints names under iirds.tekom.de; a namespace
    there that is not one of the four is wrong even when it is not close."""
    assert "L14" in ids(runner.lint(make_package(metadata=ON_THE_HOST)))


def test_a_genuinely_foreign_namespace_is_not_called_a_near_miss(make_package):
    """Somebody's own vocabulary is L5's business, not this rule's."""
    assert "L14" not in ids(runner.lint(make_package(metadata=FOREIGN)))


def test_the_reference_corpus_and_its_authors_own_vocabulary_trip_nothing():
    """plusmeta's `https://www.i4icm.de/pifan#` is the closest legitimate
    namespace in the reference corpus to iiRDS's by letters, at 0.55; it and
    every other foreign namespace there stay below the line."""
    import difflib

    from iirds_validate.model import IIRDS_NAMESPACES
    from iirds_validate.rules import lint as L

    for foreign in ("https://www.i4icm.de/pifan#", "http://myCompany.com/io/",
                    "http://www.w3.org/2000/01/rdf-schema#", "http://purl.org/dc/terms/"):
        best = max(difflib.SequenceMatcher(None, foreign, ns).ratio() for ns in IIRDS_NAMESPACES)
        assert best < L.NAMESPACE_NEAR_ENOUGH, (foreign, best)


def test_a_near_miss_namespace_is_reported_once_however_many_names_it_carries(make_package):
    report = runner.lint(make_package(metadata=SLASH_FOR_HASH))
    assert len([f for f in report.findings if f.rule.id == "L14"]) == 1


# --- the rules that did not run are named ------------------------------------

def test_the_footer_says_why_rules_were_not_applicable(make_package):
    """"21 not applicable" is a number; a reader asking whether the handover
    rules ran deserves the answer. Derived from the registry, not typed."""
    import io

    from iirds_validate import report as report_module
    from iirds_validate.registry import all_rules

    package = make_package()
    result = runner.run(package, runner.ALL_KINDS)
    for_variant = {r.id for r in all_rules() if r.variants and not r.applies_to("1.3", "unrestricted")
                   and r.applies_to("1.3", "H")}
    assert set(result.not_applicable["variant"]) == for_variant
    assert result.skipped == sum(len(v) for v in result.not_applicable.values())
    out = io.StringIO()
    report_module.render_text(result, out, verbose=True)
    assert "%d for iiRDS/H" % len(for_variant) in out.getvalue()
    assert "not applicable, for iiRDS/H:" in out.getvalue()


def test_the_not_applicable_rules_are_listed_by_id_in_the_json_report(make_package):
    result = runner.run(make_package(), runner.ALL_KINDS)
    listed = result.as_dict()["notApplicable"]
    assert set(listed) == {"variant", "version"}
    assert "M15.1" in listed["variant"] or any(i.startswith("M15") for i in listed["variant"])
