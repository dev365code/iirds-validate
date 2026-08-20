"""Lock in what was learned from the reference tool's corpus.

`tools/crossvalidate.py` no longer needs the network — the corpus is vendored —
and `docs/agreement.json` now pins its verdict for every rule/fixture pair. But
a moved baseline says only that a number changed. These tests say *what* was
learned, using fixtures rebuilt from the shapes that mattered, so a regression
names the divergence rather than a count.

docs/divergences.md is the prose version and should be updated with any change
that moves one of these.
"""
from __future__ import annotations

from conftest import MINIMAL_RDF
from iirds_validate import runner
from iirds_validate.model import Severity

HEAD = MINIMAL_RDF.replace("</rdf:RDF>", "")


def pkg(make_package, body, **kw):
    return make_package(metadata=HEAD + body + "</rdf:RDF>\n", **kw)


def ids(report):
    return {f.rule.id for f in report.findings}


def test_a_relative_iri_is_a_recommendation_not_an_error(make_package):
    """"Must have an IRI" and "should be absolute" are different rules, and
    only the second is RECOMMENDED. Conflating them made sixty MUST rules fire
    on packages the reference tool accepts."""
    report = runner.check(pkg(make_package, """
  <iirds:Component rdf:about="component/spindle">
    <rdfs:label xml:lang="en">Spindle</rdfs:label>
  </iirds:Component>
"""))
    assert "M38" not in ids(report), "a relative IRI still identifies the resource"
    assert "M5" in ids(report)
    assert all(f.severity is Severity.WARNING for f in report.findings if f.rule.id == "M5")
    assert report.ok, "a relative IRI must not fail a build"


def test_an_empty_rdf_about_is_not_an_identifier(make_package):
    """It resolves to the document base and comes back looking absolute."""
    report = runner.check(pkg(make_package, '  <iirds:Component rdf:about=""/>\n'))
    assert "M38" in ids(report)


def test_a_range_selector_needs_no_rdf_value(make_package):
    """It addresses content by its endpoints, which M14.1 and M14.2 check."""
    report = runner.check(pkg(make_package, """
  <iirds:RangeSelector rdf:about="urn:test:range">
    <iirds:has-start-selector rdf:resource="urn:test:s1"/>
    <iirds:has-end-selector rdf:resource="urn:test:s2"/>
  </iirds:RangeSelector>
"""))
    assert "M13.1" not in ids(report) and "M13.2" not in ids(report)


def test_duplicate_identical_statements_are_one_statement(make_package):
    """RDF is a set. Two identical empty values are not a cardinality breach —
    two *different* values are."""
    same = runner.check(pkg(make_package, """
  <iirds:Topic rdf:about="urn:test:t9">
    <iirds:title>A</iirds:title>
    <iirds:title>A</iirds:title>
  </iirds:Topic>
"""))
    assert "M2.6" not in ids(same)

    different = runner.check(pkg(make_package, """
  <iirds:Topic rdf:about="urn:test:t9">
    <iirds:title>A</iirds:title>
    <iirds:title>B</iirds:title>
  </iirds:Topic>
"""))
    assert "M2.6" in ids(different)


def test_the_swapped_identity_rules_check_different_things(make_package):
    """M19.1 counts identifiers and M19.3 counts domains, following the
    reference rather than the wording, because otherwise one of the two checks
    would not exist at all."""
    no_identifier = runner.check(pkg(make_package, """
  <iirds:Identity rdf:about="urn:test:i1">
    <iirds:has-identity-domain rdf:resource="urn:test:d1"/>
  </iirds:Identity>
  <iirds:IdentityDomain rdf:about="urn:test:d1"/>
"""))
    assert "M19.1" in ids(no_identifier) and "M19.3" not in ids(no_identifier)

    two_domains = runner.check(pkg(make_package, """
  <iirds:Identity rdf:about="urn:test:i2">
    <iirds:identifier>X1</iirds:identifier>
    <iirds:has-identity-domain rdf:resource="urn:test:d1"/>
    <iirds:has-identity-domain rdf:resource="urn:test:d2"/>
  </iirds:Identity>
  <iirds:IdentityDomain rdf:about="urn:test:d1"/>
  <iirds:IdentityDomain rdf:about="urn:test:d2"/>
"""))
    assert "M19.3" in ids(two_domains) and "M19.1" not in ids(two_domains)


def test_date_of_status_is_checked_by_something(make_package):
    """Taking the wording for both M21.4 and M21.5 would check purpose twice
    and dateOfStatus never."""
    report = runner.check(pkg(make_package, """
  <iirds:ContentLifeCycleStatus rdf:about="urn:test:cls">
    <iirds:has-content-lifecycle-status-value rdf:resource="http://iirds.tekom.de/iirds#Released"/>
    <iirds:dateOfStatus>2026-01-01</iirds:dateOfStatus>
    <iirds:dateOfStatus>2026-02-02</iirds:dateOfStatus>
  </iirds:ContentLifeCycleStatus>
"""))
    assert "M21.4" in ids(report)


def test_an_undescribed_reference_is_reported_once_not_five_times(make_package):
    """A party pointing at a vcard nobody describes is one problem. It used to
    produce the same complaint from every handover rule at once."""
    package = pkg(make_package, """
  <iirds:Party rdf:about="urn:test:p1">
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Author"/>
    <iirds:relates-to-vcard rdf:resource="urn:test:missing-card"/>
  </iirds:Party>
""")
    conformance = ids(runner.check(package))
    assert not {"M15.8", "M15.9", "M15.10"} & conformance
    assert "L1" in ids(runner.lint(package))


def test_the_second_half_of_the_party_sentence_is_checked_by_something(make_package):
    """M22.1 and M22.2 come from one sentence and ask two things: that a Party
    has `has-party-role`, and that what it points at is a PartyRole. The
    reference implements both as the same check, and its only fixture for the
    pair carries a Party with no `has-party-role` at all -- so the second
    question is exercised by nothing in its corpus.

    Cross-validation therefore cannot tell a working M22.2 from a dead one, and
    that distinction is the whole value of the rule. This test is the substitute
    oracle: the three cases, and which id each produces.
    """
    missing = runner.check(pkg(make_package, '  <iirds:Party rdf:about="urn:test:p1"/>\n',
                               name="missing.iirds"))
    assert "M22.1" in ids(missing) and "M22.2" not in ids(missing)

    wrong = runner.check(pkg(make_package, '''
  <iirds:Party rdf:about="urn:test:p2">
    <iirds:has-party-role rdf:resource="urn:test:not-a-role"/>
  </iirds:Party>
  <vcard:Organization xmlns:vcard="http://www.w3.org/2006/vcard/ns#"
                      rdf:about="urn:test:not-a-role"/>
''', name="wrong.iirds"))
    assert "M22.2" in ids(wrong) and "M22.1" not in ids(wrong)

    right = runner.check(pkg(make_package, '''
  <iirds:Party rdf:about="urn:test:p3">
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>
  </iirds:Party>
''', name="right.iirds"))
    assert not {"M22.1", "M22.2"} & ids(right)
