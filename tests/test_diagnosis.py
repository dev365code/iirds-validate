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
    notes = note_about(report, "no iiRDS name")
    assert notes, report.notes
    assert "namespace" in notes[0]


def test_a_package_with_iirds_terms_gets_no_such_note(make_package):
    report = runner.run(make_package(), runner.ALL_KINDS)
    assert not note_about(report, "no iiRDS name")


def test_the_note_travels_in_the_json_report(make_package):
    report = runner.run(make_package(metadata=FOREIGN), runner.ALL_KINDS)
    assert any("no iiRDS name" in n for n in json.loads(json.dumps(report.as_dict()))["notes"])


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
    """Every foreign namespace in the reference corpus, read off the files
    rather than typed here, stays below the line. The nearest legitimate one
    by letters is an example's own package namespace, and the number is
    pinned so that a change in the measure is a change in this test."""
    import difflib

    from rdflib import Graph, URIRef
    from tools import vendor_corpus

    from iirds_validate.model import IIRDS_NAMESPACES
    from iirds_validate.rules import lint as L

    nearest = {}
    for path in sorted(vendor_corpus.FILES.iterdir()):
        graph = Graph()
        try:
            graph.parse(path, format="xml")
        except Exception:
            continue
        for triple in graph:
            for term in triple:
                if isinstance(term, URIRef) and not str(term).startswith(IIRDS_NAMESPACES):
                    namespace = L._namespace_part(term)
                    if namespace and namespace not in nearest:
                        nearest[namespace] = max(
                            difflib.SequenceMatcher(None, namespace, ns).ratio()
                            for ns in IIRDS_NAMESPACES)
    assert len(nearest) > 10
    assert max(nearest.values()) < L.NAMESPACE_NEAR_ENOUGH
    closest = max(nearest, key=nearest.get)
    assert (closest, round(nearest[closest], 3)) == ("http://myCompany.de/iirds/myPackage/", 0.575)


NO_SEPARATOR = MINIMAL_RDF.replace("http://iirds.tekom.de/iirds#", "http://iirds.tekom.de/iirds")
EXTRA_SLASH = MINIMAL_RDF.replace("http://iirds.tekom.de/iirds#", "http://iirds.tekom.de/iirds#/")
MACHINERY_NO_SEPARATOR = MINIMAL_RDF.replace(
    '</rdf:RDF>',
    '  <m:Assembly xmlns:m="http://iirds.tekom.de/iirds/domain/machinery" rdf:about="urn:test:c1"/>\n'
    '</rdf:RDF>')
DOMAIN_ONLY = MACHINERY_NO_SEPARATOR.replace("http://iirds.tekom.de/iirds/domain/machinery",
                                             "http://iirds.tekom.de/iirds/domain/")


def l14(report):
    return [f for f in report.findings if f.rule.id == "L14"]


def test_a_namespace_written_without_its_separator_names_the_separator(make_package):
    """The standard's own prose writes the core namespace without the `#`
    ("iiRDS Core: http://iirds.tekom.de/iirds"). Written that way in a
    document, every name runs into the namespace -- `iirdsPackage` -- and
    the nearest namespace by letters was the wrong one. The names decide."""
    findings = l14(runner.lint(make_package(metadata=NO_SEPARATOR)))
    assert len(findings) == 1
    assert findings[0].violation.subject == "http://iirds.tekom.de/iirds"
    assert findings[0].violation.detail == (
        "8 names under it, 8 of them iiRDS names; did you mean http://iirds.tekom.de/iirds#?")


def test_a_domain_namespace_without_its_separator_is_matched_by_its_names(make_package):
    """`.../domain/machinery` + `Assembly` runs into `.../domain/machineryAssembly`,
    and by letters `handover#` and `software#` are as near as `machinery#`.
    A wrong suggestion costs more than none; the name says which domain."""
    findings = l14(runner.lint(make_package(metadata=MACHINERY_NO_SEPARATOR)))
    assert [f.violation.subject for f in findings] == ["http://iirds.tekom.de/iirds/domain/machinery"]
    assert findings[0].violation.detail == (
        "1 name under it, 1 of them iiRDS names; "
        "did you mean http://iirds.tekom.de/iirds/domain/machinery#?")


def test_a_namespace_that_several_iirds_namespaces_begin_with_is_offered_all_of_them(make_package):
    findings = l14(runner.lint(make_package(metadata=DOMAIN_ONLY)))
    assert [f.violation.subject for f in findings] == ["http://iirds.tekom.de/iirds/domain/"]
    detail = findings[0].violation.detail
    assert detail.startswith("1 name under it, 1 of them iiRDS names; did you mean one of ")
    for domain in ("handover", "machinery", "software"):
        assert "http://iirds.tekom.de/iirds/domain/%s#" % domain in detail


def test_an_extra_slash_after_the_separator_is_one_near_miss_not_eight_unknown_names(make_package):
    """`iirds#/Package` begins with the core namespace, so a prefix test
    called it an iiRDS term and L13 reported eight unknown names, each with
    "did you mean Package?". It is one namespace one character off."""
    report = runner.lint(make_package(metadata=EXTRA_SLASH))
    assert "L13" not in ids(report)
    findings = l14(report)
    assert len(findings) == 1
    assert findings[0].violation.subject == "http://iirds.tekom.de/iirds#/"
    assert findings[0].violation.detail.endswith("did you mean http://iirds.tekom.de/iirds#?")


def test_the_bare_host_and_the_vocabulary_iri_are_not_names_under_a_namespace(make_package):
    """A value of `http://iirds.tekom.de/` on rdfs:seeAlso, or owl:imports of
    the vocabulary IRI itself, has no local name to be near or far from."""
    metadata = MINIMAL_RDF.replace(
        "<iirds:title>Test package</iirds:title>",
        '<iirds:title>Test package</iirds:title>\n'
        '    <rdfs:seeAlso rdf:resource="http://iirds.tekom.de/"/>\n'
        '    <rdfs:seeAlso rdf:resource="http://iirds.tekom.de/iirds#"/>')
    assert not l14(runner.lint(make_package(metadata=metadata)))


def test_the_vocabulary_iri_alone_does_not_make_a_package_iirds(make_package):
    """owl:imports of the vocabulary names no term; the note still fires."""
    metadata = FOREIGN.replace(
        "</rdf:RDF>",
        '  <rdf:Description rdf:about="urn:test:onto">\n'
        '    <rdfs:seeAlso rdf:resource="http://iirds.tekom.de/iirds#"/>\n'
        '  </rdf:Description>\n</rdf:RDF>')
    report = runner.run(make_package(metadata=metadata), runner.ALL_KINDS)
    assert note_about(report, "no iiRDS name"), report.notes


def test_the_no_iirds_note_is_the_first_line_of_the_report(make_package):
    """The version note came first and said "no iirds:iiRDSVersion in the
    package" -- true, and the wrong layer again: the version is there,
    under the misspelt namespace. The layer is named before anything else."""
    report = runner.run(make_package(metadata=SLASH_FOR_HASH), runner.ALL_KINDS)
    assert report.notes[0].startswith("no iiRDS name appears in the metadata"), report.notes
    assert any("no iirds:iiRDSVersion" in n for n in report.notes[1:])


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


def test_the_footer_names_no_profile_the_standard_does_not_have(make_package):
    """On an iiRDS/H package the one rule that does not apply is for the
    other two profiles, which the registry spells ("unrestricted", "A").
    Joined with a slash that read "for iiRDS/A/unrestricted" -- a profile
    name nobody published. "unrestricted" is the absence of a restriction."""
    import io

    from iirds_validate import report as report_module

    metadata = MINIMAL_RDF.replace(
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        "    <iirds:formatRestriction>H</iirds:formatRestriction>")
    result = runner.run(make_package(metadata=metadata), runner.ALL_KINDS)
    assert result.not_applicable["variant"] == ["C11.1"]
    out = io.StringIO()
    report_module.render_text(result, out, verbose=True)
    text = out.getvalue()
    assert "1 for packages that are not iiRDS/H" in text
    assert "not applicable, for packages that are not iiRDS/H: C11.1" in text
    assert "unrestricted" not in text


def test_the_not_applicable_rules_are_listed_by_id_in_the_json_report(make_package):
    result = runner.run(make_package(), runner.ALL_KINDS)
    listed = result.as_dict()["notApplicable"]
    assert set(listed) == {"variant", "version"}
    assert "M15.1" in listed["variant"] or any(i.startswith("M15") for i in listed["variant"])
