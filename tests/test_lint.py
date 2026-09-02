"""Interoperability rules — valid packages that a consumer still cannot use."""
from __future__ import annotations

from conftest import MINIMAL_RDF
from iirds_validate import runner

DANGLING = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    '    <iirds:relates-to-event rdf:resource="urn:test:event-that-does-not-exist"/>\n'
    "  </iirds:Topic>")


def ids(report):
    return {f.rule.id for f in report.findings}


def test_dangling_reference_is_caught_but_is_not_a_conformance_error(make_package):
    """The exact failure that motivated this project.

    Both forms are valid iiRDS, so `check` stays silent — as it should. `lint`
    is where you find out the reference goes nowhere.
    """
    package = make_package(metadata=DANGLING)

    conformance = runner.check(package)
    assert conformance.ok, "a reference to an undescribed IRI breaks no MUST"

    interop = runner.lint(package)
    assert "L1" in ids(interop)
    assert interop.ok, "L1 is a warning: the package is valid, just not usable"


def test_missing_content_file(make_package):
    report = runner.lint(make_package(content=()))
    assert "L2" in ids(report)
    assert not report.ok, "a rendition pointing at a file nobody packed is an error"


def test_clean_package_has_no_lint_findings(make_package):
    report = runner.lint(make_package())
    assert not report.findings, [f.violation.message for f in report.findings]


# ---------------------------------------------------------------------------
# A name in the iiRDS namespace that the vocabulary does not define
#
# The checker trusted the namespace and never the name: `is_iirds_term` is a
# prefix test, and `is_defined` -- which asks the bundled vocabulary -- was
# applied to iiRDS IRIs nowhere. So a typed name in the standard's own
# namespace passed every one of 173 rules, in any of the three positions a
# term can occupy, and a consumer resolving it finds no class, no property
# and no label.
# ---------------------------------------------------------------------------

#: `relates-to-component` with two letters swapped: a predicate that resolves
#: to nothing, on a package that is otherwise clean.
TYPO_PREDICATE = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    '    <iirds:relates-to-componnet rdf:resource="urn:test:component/spindle"/>\n'
    "  </iirds:Topic>")

#: A class of the standard's, misspelled, beside a real one -- so that the
#: rules which ask "does this package declare any Component at all" stay
#: silent and the typo is the only thing left to find.
TYPO_CLASS = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    "  </iirds:Topic>\n"
    '  <iirds:Component rdf:about="urn:test:component/spindle">\n'
    "    <iirds:title>Main spindle</iirds:title>\n"
    "  </iirds:Component>\n"
    '  <iirds:Componentt rdf:about="urn:test:component/guard">\n'
    "    <iirds:title>Guard</iirds:title>\n"
    "  </iirds:Componentt>")

#: The value half: a document type the standard does not have, written in the
#: standard's namespace. Singular where the vocabulary is plural.
TYPO_VALUE = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    '    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstruction"/>\n'
    "  </iirds:Topic>")

#: The one that is not a typo: the standard defines this in the machinery
#: domain, and this names it in core. Fifty-one files of the reference corpus
#: do the same, which is why this rule is a warning rather than an error.
WRONG_NAMESPACE = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    '    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#EnvironmentalProtectionInstruction"/>\n'
    "  </iirds:Topic>")


def findings_for(report, rule_id):
    return [f for f in report.findings if f.rule.id == rule_id]


def test_a_misspelled_predicate_in_the_iirds_namespace_is_reported(make_package):
    report = runner.lint(make_package(metadata=TYPO_PREDICATE))
    assert "L13" in ids(report)


def test_a_misspelled_class_in_the_iirds_namespace_is_reported(make_package):
    """Beside a correctly spelled sibling, so that this is the typo being
    found and not the absence of the class it belongs to."""
    report = runner.lint(make_package(metadata=TYPO_CLASS))
    assert "L13" in ids(report)


def test_a_value_the_vocabulary_does_not_define_is_reported(make_package):
    report = runner.lint(make_package(metadata=TYPO_VALUE))
    assert "L13" in ids(report)


def test_a_term_of_another_iirds_domain_named_in_core_is_reported(make_package):
    report = runner.lint(make_package(metadata=WRONG_NAMESPACE))
    assert "L13" in ids(report)


def test_the_undefined_term_finding_is_a_warning_and_not_a_conformance_error(make_package):
    """Fifty-one files of the reference corpus, and nineteen of the fixtures
    upstream calls passes, name one term this way. Whether section 7 forbids
    it is a question for the standard's editors; until it is answered this
    reports without failing a build."""
    package = make_package(metadata=TYPO_PREDICATE)
    assert runner.check(package).ok, "no MUST is broken by a name that resolves to nothing"
    assert runner.lint(package).ok, "L13 is advice until the standard's editors answer"


def test_a_clean_package_names_no_undefined_term(make_package):
    assert "L13" not in ids(runner.lint(make_package()))


def test_each_undefined_term_is_reported_once_however_often_it_occurs(make_package):
    twice = TYPO_PREDICATE.replace(
        "  </iirds:Topic>",
        '    <iirds:relates-to-componnet rdf:resource="urn:test:component/other"/>\n'
        "  </iirds:Topic>")
    assert len(findings_for(runner.lint(make_package(metadata=twice)), "L13")) == 1


def test_the_report_suggests_the_term_that_was_meant(make_package):
    """327 terms is a small enough vocabulary to search, and the suggestion is
    most of this rule's value: `relates-to-componnet` is unreadable as an
    error and obvious as a correction."""
    found = findings_for(runner.lint(make_package(metadata=TYPO_PREDICATE)), "L13")
    assert "relates-to-component" in (found[0].violation.detail or "")


def test_no_suggestion_is_offered_where_nothing_is_near(make_package):
    """A name with no neighbour gets none: a wrong suggestion costs more than
    no suggestion, because a reader acts on it."""
    far = MINIMAL_RDF.replace(
        "  </iirds:Topic>",
        '    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#Zzzzqqqxyw"/>\n'
        "  </iirds:Topic>")
    found = findings_for(runner.lint(make_package(metadata=far)), "L13")
    assert found and "did you mean" not in (found[0].violation.detail or "").lower()
