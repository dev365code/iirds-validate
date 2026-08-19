"""One violating case and one clean case for each interoperability rule.

Six of these had no direct test at all. That matters more here than anywhere
else in the suite: the M* rules can be checked against another implementation,
and doing so found sixteen of them implementing the wrong thing. The L rules
are this project's own, so nothing outside these tests says whether they work.

Each test names the failure it protects against rather than restating the rule.
"""
from __future__ import annotations

from conftest import MINIMAL_RDF
from iirds_validate import runner

HEAD = MINIMAL_RDF.replace("</rdf:RDF>", "")


def pkg(make_package, body, name=None, **kw):
    return make_package(name=name or "lint.iirds", metadata=HEAD + body + "</rdf:RDF>\n", **kw)


def ids(report):
    return {f.rule.id for f in report.findings}


def lint(make_package, body, **kw):
    return ids(runner.lint(pkg(make_package, body, **kw)))


TOC = """
  <iirds:DirectoryNode rdf:about="urn:test:root">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-first-child rdf:resource="urn:test:n1"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n1">
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
  </iirds:DirectoryNode>
"""


# --- L3: unreachable navigation --------------------------------------------

def test_l3_a_node_no_root_leads_to_is_invisible(make_package):
    """It exists in the metadata and appears in no viewer. Nothing about it
    breaks a MUST, which is exactly why a conformance checker will not say so."""
    orphan = TOC + """
  <iirds:DirectoryNode rdf:about="urn:test:orphan">
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
    <rdfs:label xml:lang="en">Nobody links here</rdfs:label>
  </iirds:DirectoryNode>
"""
    assert "L3" in lint(make_package, orphan)
    assert "L3" not in lint(make_package, TOC, name="ok3.iirds")


# --- L4: cycles ------------------------------------------------------------

def test_l4_a_cycle_would_hang_a_consumer(make_package):
    cyclic = """
  <iirds:DirectoryNode rdf:about="urn:test:a">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-first-child rdf:resource="urn:test:b"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:b">
    <iirds:has-next-sibling rdf:resource="urn:test:c"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:c">
    <iirds:has-next-sibling rdf:resource="urn:test:b"/>
  </iirds:DirectoryNode>
"""
    assert "L4" in lint(make_package, cyclic)
    assert "L4" not in lint(make_package, TOC, name="ok4.iirds")


def test_l4_a_node_reached_by_two_paths_is_not_a_cycle(make_package):
    """A diamond is reachable twice and terminates. Marking it as a cycle would
    make the rule useless on any real table of contents."""
    diamond = """
  <iirds:DirectoryNode rdf:about="urn:test:top">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-first-child rdf:resource="urn:test:shared"/>
    <iirds:has-next-sibling rdf:resource="urn:test:shared"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:shared">
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
  </iirds:DirectoryNode>
"""
    assert "L4" not in lint(make_package, diamond)


# --- L5: proprietary classes -----------------------------------------------

def test_l5_a_class_of_your_own_must_hang_off_the_standard(make_package):
    """A receiving system can store an unlinked class and can do nothing with
    it."""
    unlinked = """
  <acme:Widget xmlns:acme="http://acme.example/ns#" rdf:about="urn:test:w1">
    <rdfs:label xml:lang="en">Widget</rdfs:label>
  </acme:Widget>
"""
    assert "L5" in lint(make_package, unlinked)

    linked = """
  <acme:Widget xmlns:acme="http://acme.example/ns#" rdf:about="urn:test:w1">
    <rdfs:label xml:lang="en">Widget</rdfs:label>
  </acme:Widget>
  <rdf:Description rdf:about="http://acme.example/ns#Widget">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Component"/>
  </rdf:Description>
"""
    assert "L5" not in lint(make_package, linked, name="ok5.iirds")


def test_l5_leaves_the_vocabularies_the_specification_names_alone(make_package):
    """vcard is required by M23. Reporting it as a proprietary extension would
    fire on every conformant package that names a party."""
    body = """
  <iirds:Party rdf:about="urn:test:p">
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Author"/>
    <iirds:relates-to-vcard rdf:resource="urn:test:card"/>
  </iirds:Party>
  <vcard:Organization xmlns:vcard="http://www.w3.org/2006/vcard/ns#" rdf:about="urn:test:card">
    <vcard:organization-name xmlns:vcard="http://www.w3.org/2006/vcard/ns#">ACME</vcard:organization-name>
  </vcard:Organization>
"""
    assert "L5" not in lint(make_package, body)


# --- L6: labels ------------------------------------------------------------

def test_l6_a_metadata_value_with_no_label_cannot_be_shown_or_matched(make_package):
    """An IRI ending in `main-spindle` will never match a query written in
    another language. The label travels inside the package; nothing else does."""
    unlabelled = """
  <iirds:Topic rdf:about="urn:test:topic1">
    <iirds:relates-to-component rdf:resource="urn:test:c1"/>
  </iirds:Topic>
  <iirds:Component rdf:about="urn:test:c1"/>
"""
    assert "L6" in lint(make_package, unlabelled)

    labelled = unlabelled.replace(
        '<iirds:Component rdf:about="urn:test:c1"/>',
        '<iirds:Component rdf:about="urn:test:c1">'
        '<rdfs:label xml:lang="ko">주축</rdfs:label></iirds:Component>')
    assert "L6" not in lint(make_package, labelled, name="ok6.iirds")


def test_l6_accepts_a_label_one_level_down(make_package):
    """iiRDS routinely puts the readable string on a child node — an event
    carries none itself, its event code does."""
    body = """
  <iirds:Topic rdf:about="urn:test:topic1">
    <iirds:relates-to-event rdf:resource="urn:test:e1"/>
  </iirds:Topic>
  <iirds:Event rdf:about="urn:test:e1">
    <iirds:has-event-code rdf:parseType="Resource">
      <rdfs:label xml:lang="en">3X333</rdfs:label>
    </iirds:has-event-code>
    <iirds:has-event-type rdf:parseType="Resource">
      <rdfs:label xml:lang="en">Defect</rdfs:label>
    </iirds:has-event-type>
  </iirds:Event>
"""
    assert "L6" not in lint(make_package, body)


# --- L7: titles ------------------------------------------------------------

def test_l7_an_untitled_information_unit_is_valid_and_unusable(make_package):
    untitled = '  <iirds:Topic rdf:about="urn:test:t2"/>\n'
    assert "L7" in lint(make_package, untitled)
    assert "L7" not in lint(
        make_package,
        '  <iirds:Topic rdf:about="urn:test:t2"><iirds:title>T</iirds:title></iirds:Topic>\n',
        name="ok7.iirds")


def test_l7_does_not_ask_a_package_for_a_title(make_package):
    """iirds:Package is an InformationUnit subclass but is not a thing with a
    title in the same sense."""
    findings = lint(make_package, "")
    assert "L7" not in findings


# --- L8: external references -----------------------------------------------

def test_l8_notes_what_an_offline_consumer_cannot_resolve(make_package):
    external = """
  <iirds:Topic rdf:about="urn:test:topic1">
    <iirds:relates-to-component rdf:resource="https://vendor.example/ontology#Pump"/>
  </iirds:Topic>
  <iirds:Component rdf:about="urn:test:c1">
    <rdfs:label xml:lang="en">Local</rdfs:label>
  </iirds:Component>
"""
    assert "L8" in lint(make_package, external)
    assert "L1" not in lint(make_package, external), "a web IRI is L8's business, not L1's"


def test_l8_is_advisory_and_l1_is_not(make_package):
    """Pointing at an external vocabulary is a legitimate thing to do. Pointing
    at a urn nobody defined is a mistake."""
    external = pkg(make_package, """
  <iirds:Topic rdf:about="urn:test:topic1">
    <iirds:relates-to-component rdf:resource="https://vendor.example/ontology#Pump"/>
  </iirds:Topic>
  <iirds:Component rdf:about="urn:test:c1"><rdfs:label>L</rdfs:label></iirds:Component>
""", name="ext.iirds")
    dangling = pkg(make_package, """
  <iirds:Topic rdf:about="urn:test:topic1">
    <iirds:relates-to-event rdf:resource="urn:test:no-such-event"/>
  </iirds:Topic>
""", name="dangle.iirds")

    assert runner.lint(external).ok, "an external reference must not fail a run"
    report = runner.lint(dangling)
    assert "L1" in ids(report)
