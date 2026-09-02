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
    assert "S3" not in {f.rule.id for f in report.findings}, "L15 raised"
    return [f for f in report.findings if f.rule.id == "L15"]


def ids(report):
    return {f.rule.id for f in report.findings}


HANDOVER_OPERATION = "http://iirds.tekom.de/iirds/domain/handover#Operation"


def test_a_domain_name_is_named_with_its_domain(make_package):
    """`Operation` is a core name since 1.0 and a handover name since 1.3.
    "Operation is not in iiRDS 1.2" was false of the standard; the message
    says which one it means."""
    findings = l15(runner.lint(make_package(metadata=declaring("1.2", HANDOVER_OPERATION))))
    assert [f.violation.message for f in findings] == [
        "Operation in iirds/domain/handover# is not in iiRDS 1.2"]
    assert findings[0].violation.subject == HANDOVER_OPERATION
    assert type(findings[0].violation.subject) is str


def test_the_edition_validated_against_is_the_one_the_names_are_held_to(make_package):
    """`--iirds-version` asks for a run against another edition, and every
    other version-scoped rule follows it. So does this one, and it says
    which edition the run used when that is not the one declared."""
    package = make_package(metadata=declaring("1.3", IS_BASED_ON))
    findings = l15(runner.lint(package, version="1.0"))
    assert [f.violation.detail for f in findings] == [
        "defined from iiRDS 1.3 on; this run validates against 1.0, the package declares 1.3"]
    assert not l15(runner.lint(make_package(metadata=declaring("1.0", IS_BASED_ON)), version="1.3"))


def test_a_name_the_inventory_lags_behind_is_not_a_crash(make_package, monkeypatch):
    """The bundle and the inventory are refreshed separately; a bundle one
    name ahead used to raise inside the rule, and the run reported S3 on a
    clean package. The name is left alone until the inventory catches up,
    and the inventory test below is what keeps the two together."""
    from iirds_validate import resources
    from iirds_validate.rules import lint as L

    editions = {k: set(v) for k, v in version_terms().items()}
    for edition in editions:
        editions[edition].discard(IS_BASED_ON)
    monkeypatch.setattr(L, "version_terms", lambda: {k: frozenset(v) for k, v in editions.items()})
    monkeypatch.setattr(resources, "version_terms", L.version_terms)
    report = runner.lint(make_package(metadata=declaring("1.0", IS_BASED_ON)))
    assert report.ok and not l15(report)


def test_the_newest_editions_inventory_is_the_bundled_vocabulary():
    """What the rule holds a name against and what L13 holds it against
    must be the same list, or a name is defined to one and unknown to the
    other."""
    from iirds_validate import ontology

    bundled = ontology.load("1.3")
    ours = {str(t) for t in bundled.defined_terms() if bundled.is_iirds_term(t)}
    assert ours == set(version_terms()["1.3"])


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
