"""Exercise every version and profile the README claims to support.

Until this file existed the suite declared iiRDS 1.3 and nothing else, while
the README listed five versions and three profiles. Four of the five were
supported only in the sense that nobody had tried them.

The interesting failures here are not "a rule is wrong" but "a whole axis is
inert": a version nobody runs, a profile that switches rules off in both
directions, a rule that crashes only on the combination nobody tried.
"""
from __future__ import annotations

import itertools

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import runner
from iirds_validate.model import VARIANTS, VERSIONS

#: Enough of a package to be worth checking: a package node, a topic, a
#: rendition, a party, an identity and a directory node, so that rules across
#: several families have something to look at on every combination.
BODY = """
  <iirds:Party rdf:about="urn:test:party">
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Author"/>
    <iirds:relates-to-vcard rdf:resource="urn:test:card"/>
  </iirds:Party>
  <vcard:Organization rdf:about="urn:test:card">
    <vcard:organization-name>Test GmbH</vcard:organization-name>
  </vcard:Organization>
  <iirds:Identity rdf:about="urn:test:identity">
    <iirds:identifier>X-1</iirds:identifier>
    <iirds:has-identity-domain rdf:resource="urn:test:domain"/>
  </iirds:Identity>
  <iirds:IdentityDomain rdf:about="urn:test:domain"/>
  <iirds:DirectoryNode rdf:about="urn:test:root">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-first-child rdf:resource="urn:test:n1"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n1">
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:DirectoryNode>
"""


def metadata(version, variant=None, body=BODY):
    head = MINIMAL_RDF.replace(
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
        '<rdf:RDF xmlns:vcard="http://www.w3.org/2006/vcard/ns#"\n'
        '         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"')
    head = head.replace("<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
                        "<iirds:iiRDSVersion>%s</iirds:iiRDSVersion>" % version)
    if variant:
        head = head.replace("</iirds:Package>",
                            "  <iirds:formatRestriction>%s</iirds:formatRestriction>\n"
                            "  </iirds:Package>" % variant)
    return head.replace("</rdf:RDF>", body + "</rdf:RDF>\n")


def build(make_package, version, variant=None, name=None, **kw):
    return make_package(name=name or ("%s-%s.iirds" % (version, variant or "plain")),
                        metadata=metadata(version, variant), **kw)


def crashes(report):
    return [f.violation.detail for f in report.findings if f.rule.id == "S3"]


# --- every combination must at least run cleanly ---------------------------

@pytest.mark.parametrize("version,variant",
                         list(itertools.product(VERSIONS, (None, "A", "H"))),
                         ids=lambda v: str(v))
def test_no_rule_crashes_on_any_version_and_profile(make_package, version, variant):
    """A rule that raises is a rule that checked nothing. The combination
    nobody runs is where that hides."""
    extra = (("index.html", "<html/>"),) if variant == "H" else ()
    report = runner.run(build(make_package, version, variant, extra=extra,
                              jsonld="{}" if variant == "H" else None),
                        runner.ALL_KINDS)
    assert not crashes(report), crashes(report)
    assert report.checked > 30, "almost nothing ran for %s/%s" % (version, variant)


@pytest.mark.parametrize("version", VERSIONS)
def test_every_published_version_is_recognised(make_package, version):
    report = runner.check(build(make_package, version))
    assert report.version == version
    assert report.effective_version == version
    assert "S4" not in {f.rule.id for f in report.findings}


@pytest.mark.parametrize("variant", ("A", "H"))
def test_every_published_profile_is_recognised(make_package, variant):
    extra = (("index.html", "<html/>"),) if variant == "H" else ()
    report = runner.check(build(make_package, "1.3", variant, extra=extra,
                                jsonld="{}" if variant == "H" else None))
    assert report.variant == variant
    assert "S5" not in {f.rule.id for f in report.findings}


# --- the axes must actually do something -----------------------------------

def test_the_version_axis_changes_which_rules_run(make_package):
    """If it did not, filtering by version would be dead code and nobody would
    know. Everything 1.3 added belongs to the handover profile, so the
    difference only shows on an H package."""
    old = runner.check(build(make_package, "1.2", "H", name="h12.iirds",
                             jsonld="{}", extra=(("index.html", "<html/>"),)))
    new = runner.check(build(make_package, "1.3", "H", name="h13.iirds",
                             jsonld="{}", extra=(("index.html", "<html/>"),)))
    assert old.checked < new.checked, "1.3 must run more handover rules than 1.2"


def test_the_profile_axis_changes_which_rules_run(make_package):
    plain = runner.check(build(make_package, "1.3", None, name="plain.iirds"))
    handover = runner.check(build(make_package, "1.3", "H", name="hov.iirds",
                                  jsonld="{}", extra=(("index.html", "<html/>"),)))
    assert plain.checked != handover.checked


def test_a_rule_introduced_after_1_0_does_not_run_against_1_0(make_package):
    """M8 is catalogued as 1.1 and later. Running it against a 1.0 package
    would be reporting a requirement that did not exist yet."""
    report = runner.check(build(make_package, "1.0"))
    assert "M8" not in {f.rule.id for f in report.findings}
    assert report.skipped > 0


# --- and must not be dodgeable ---------------------------------------------

@pytest.mark.parametrize("declared", ["9.9", "banana", "1", ""])
def test_a_version_the_standard_never_published_is_a_finding(make_package, declared):
    report = runner.check(build(make_package, declared))
    assert "S4" in {f.rule.id for f in report.findings}, declared
    assert not report.ok


def test_an_unknown_profile_is_a_finding_not_a_way_out(make_package):
    """Rules are filtered by profile, so an unrecognised one matched neither
    the unrestricted set nor the handover set: it skipped both and reported
    clean. One line of metadata to switch off validation."""
    report = runner.check(build(make_package, "1.3", "Z", name="z.iirds"))
    assert "S5" in {f.rule.id for f in report.findings}
    assert not report.ok


def test_substituting_an_ontology_is_stated_in_the_report(make_package):
    """Only the 1.3 ontology is bundled, so a 1.0 run borrows its class
    hierarchy. That is defensible; doing it silently is not."""
    report = runner.check(build(make_package, "1.0"))
    assert any("no ontology bundled" in note for note in report.notes)


def test_an_override_says_it_overrode(make_package):
    report = runner.run(build(make_package, "1.3", name="ovr.iirds"),
                        runner.CONFORMANCE_KINDS, version="1.0")
    assert report.effective_version == "1.0"
    assert any("because it was asked for" in note for note in report.notes)
    assert not any("is not one this standard has published" in note for note in report.notes)


def test_variants_constant_matches_what_the_rules_expect():
    assert set(VARIANTS) == {"unrestricted", "A", "H"}
