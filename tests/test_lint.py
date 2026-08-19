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
