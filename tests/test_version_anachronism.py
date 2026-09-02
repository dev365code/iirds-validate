"""A name the declared edition of iiRDS does not have yet (L15).

Only the newest ontology ships, so every package is judged against the 1.3
vocabulary whatever it declares -- a package declaring 1.0 that uses
`iirds:is-based-on` (1.3) passes L13, since the standard does define the
name. But a consumer that reads the package as 1.0 has no definition for
it. The per-edition inventory, a list of term IRIs the generator reads off
the Consortium's published schemas, says when each name arrived; this
rule says so to the author, once per name.
"""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import runner
from iirds_validate.model import VERSIONS
from iirds_validate.resources import version_terms

IS_BASED_ON = "http://iirds.tekom.de/iirds#is-based-on"          # arrives in 1.3
EXTERNAL_CLASSIFICATION = "http://iirds.tekom.de/iirds#ExternalClassification"  # 1.2
ACTION = "http://iirds.tekom.de/iirds#Action"                      # 1.1


def declaring(version, *terms):
    metadata = MINIMAL_RDF.replace("<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
                                   "<iirds:iiRDSVersion>%s</iirds:iiRDSVersion>" % version
                                   if version else "")
    nodes = "".join('  <rdf:Description rdf:about="urn:test:n%d"><rdf:type rdf:resource="%s"/>'
                    '</rdf:Description>\n' % (i, term) for i, term in enumerate(terms))
    return metadata.replace("</rdf:RDF>", nodes + "</rdf:RDF>")


def l15(report):
    return [f for f in report.findings if f.rule.id == "L15"]


def ids(report):
    return {f.rule.id for f in report.findings}


def test_a_name_the_declared_edition_lacks_is_reported_with_the_edition_it_arrived_in(make_package):
    report = runner.lint(make_package(metadata=declaring("1.0", IS_BASED_ON)))
    findings = l15(report)
    assert len(findings) == 1
    assert findings[0].violation.message == "is-based-on is not in iiRDS 1.0"
    assert str(findings[0].violation.subject) == IS_BASED_ON
    assert findings[0].violation.detail == "defined from iiRDS 1.3 on; this package declares 1.0"
    assert "L13" not in ids(report)


@pytest.mark.parametrize("declared,term,arrived", [
    ("1.0", ACTION, "1.1"), ("1.0.1", ACTION, "1.1"),
    ("1.1", EXTERNAL_CLASSIFICATION, "1.2"), ("1.2", IS_BASED_ON, "1.3"),
])
def test_the_edition_named_is_the_first_that_has_the_name(make_package, declared, term, arrived):
    findings = l15(runner.lint(make_package(metadata=declaring(declared, term))))
    assert [f.violation.detail for f in findings] == [
        "defined from iiRDS %s on; this package declares %s" % (arrived, declared)]


def test_the_same_name_in_a_package_declaring_that_edition_is_not_reported(make_package):
    assert not l15(runner.lint(make_package(metadata=declaring("1.3", IS_BASED_ON))))
    assert not l15(runner.lint(make_package(metadata=declaring("1.1", ACTION))))


def test_a_package_declaring_no_edition_has_no_anachronism(make_package):
    """The version note already says such a package is judged as 1.3."""
    report = runner.lint(make_package(metadata=declaring(None, IS_BASED_ON)))
    assert not l15(report)


def test_a_name_no_edition_has_is_l13_not_l15(make_package):
    report = runner.lint(make_package(
        metadata=declaring("1.0", "http://iirds.tekom.de/iirds#is-based-onn")))
    assert "L13" in ids(report) and not l15(report)


def test_each_name_is_reported_once_however_often_it_occurs(make_package):
    findings = l15(runner.lint(make_package(
        metadata=declaring("1.0", IS_BASED_ON, IS_BASED_ON, ACTION))))
    assert [str(f.violation.subject) for f in findings] == [ACTION, IS_BASED_ON]


def test_the_finding_is_a_warning_and_the_package_still_passes(make_package):
    """Whether an anachronism breaks conformance is the standard's editors'
    question (§7 says nothing about editions); until it is answered this
    reports without failing a build, like L13."""
    from iirds_validate.model import Severity

    package = make_package(metadata=declaring("1.0", IS_BASED_ON))
    report = runner.lint(package)
    assert report.ok
    assert [f.severity for f in l15(report)] == [Severity.WARNING]
    assert "L15" not in ids(runner.check(package))


def test_every_name_a_later_edition_added_is_reported_against_1_0(make_package):
    """Forty-six names arrived after 1.0 -- fifteen in 1.1, eleven in 1.2,
    twenty in 1.3 -- and every one of them is an anachronism in a package
    declaring 1.0. The inventory never shrinks between editions, which is
    what makes "defined from X on" a single edition rather than a list."""
    editions = version_terms()
    later = sorted(editions["1.3"] - editions["1.0"])
    assert len(later) == 46
    for earlier, edition in zip(VERSIONS, VERSIONS[1:]):
        assert editions[earlier] <= editions[edition], (earlier, edition)
    report = runner.lint(make_package(metadata=declaring("1.0", *later)))
    assert sorted(str(f.violation.subject) for f in l15(report)) == later
