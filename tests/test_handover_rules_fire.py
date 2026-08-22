"""iiRDS/H, built correctly once and then broken one requirement at a time.

Ten handover rules had never been observed to fire. They are also the ones
hardest to reach by accident: iiRDS/H demands a particular shape -- documents
related to parties, product variants carrying two kinds of identity, each
identity domain tracing back to a named manufacturer -- and a fixture missing
any of it trips several rules at once, which is why none of them had a test.

So the fixture is assembled whole, asserted to be clean, and then each rule is
reached by removing exactly what that rule asks for. That gives both halves at
once: the rule fires on its own defect, and it is silent on a conformant
package. A rule that only ever demonstrates the first is a rule that might fire
on everything.
"""
from __future__ import annotations

import pytest

from conftest import build_package
from iirds_validate import runner

HOV = "http://iirds.tekom.de/iirds/domain/handover#"

#: A conformant iiRDS/H package. Every block carries the rule it satisfies, so
#: removing one to reach that rule is a matter of deleting a labelled line.
HANDOVER = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:vcard="http://www.w3.org/2006/vcard/ns#"
         xmlns:hov="%s"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:formatRestriction>H</iirds:formatRestriction>
    <iirds:title>Handover</iirds:title>
    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>
  </iirds:Package>

  <iirds:Document rdf:about="urn:test:doc1">
    <iirds:title>Operating instructions</iirds:title>
    <iirds:language>en</iirds:language>
    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>
    <hov:has-document-category rdf:resource="%sOperatingInstructions"/>
    <iirds:is-version-of rdf:resource="urn:test:io1"/>
    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>
    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>application/pdf</iirds:format>
        <iirds:source>content/doc1.pdf</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Document>

  <iirds:InformationObject rdf:about="urn:test:io1">
    <iirds:title>Operating instructions</iirds:title>
    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>
  </iirds:InformationObject>

  <iirds:ProductVariant rdf:about="urn:test:variant">
    <rdfs:label xml:lang="en">Rotor 3000</rdfs:label>
    <iirds:has-identity rdf:resource="urn:test:identity-instance"/>
    <iirds:has-identity rdf:resource="urn:test:identity-type"/>
  </iirds:ProductVariant>

  <iirds:Identity rdf:about="urn:test:identity-instance">
    <iirds:identifier>SN-00417</iirds:identifier>
    <iirds:has-identity-domain rdf:resource="urn:test:domain-instance"/>
  </iirds:Identity>
  <iirds:IdentityDomain rdf:about="urn:test:domain-instance">
    <rdfs:label xml:lang="en">Serial numbers</rdfs:label>
    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#SerialNumber"/>
    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>
  </iirds:IdentityDomain>

  <iirds:Identity rdf:about="urn:test:identity-type">
    <iirds:identifier>ROT-3000</iirds:identifier>
    <iirds:has-identity-domain rdf:resource="urn:test:domain-type"/>
  </iirds:Identity>
  <iirds:IdentityDomain rdf:about="urn:test:domain-type">
    <rdfs:label xml:lang="en">Product types</rdfs:label>
    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#ProductType"/>
    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>
  </iirds:IdentityDomain>

  <!-- One organisation in three roles, which is ordinary for a handover: the
       manufacturer wrote the documentation and shipped the package. The rules
       ask for a different role in each place. Author on the Document, Creator
       on the Package and InformationObject, Manufacturer on the identity
       domains.

       Three Party instances rather than one carrying three roles, because the
       ontology states "Cardinality: iirds:Party [0..1]" for has-party-role and
       the prose makes it mandatory, so a Party holds exactly one. Saying an
       organisation acts in several roles means several Party nodes pointing at
       the same vcard, and getting that wrong here was how this fixture first
       failed M22.1. -->
  <iirds:Party rdf:about="urn:test:party-manufacturer">
    <rdfs:label xml:lang="en">Rotor Works, as manufacturer</rdfs:label>
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>
    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>
  </iirds:Party>
  <iirds:Party rdf:about="urn:test:party-author">
    <rdfs:label xml:lang="en">Rotor Works, as author</rdfs:label>
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Author"/>
    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>
  </iirds:Party>
  <iirds:Party rdf:about="urn:test:party-creator">
    <rdfs:label xml:lang="en">Rotor Works, as creator</rdfs:label>
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Creator"/>
    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>
  </iirds:Party>
  <vcard:Organization rdf:about="urn:test:supplier-card">
    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>
  </vcard:Organization>
</rdf:RDF>
""" % (HOV, HOV)


def _jsonld(metadata: str) -> str:
    """The same graph, serialised. iiRDS/H requires metadata.jsonld as well as
    metadata.rdf, and L9 requires the two to agree -- so it is generated from
    the RDF rather than written twice, which is also the only way to be sure
    a change to the fixture reaches both."""
    from rdflib import Graph
    return Graph().parse(data=metadata, format="xml").serialize(format="json-ld")


def _package(tmp_path, name, metadata):
    return build_package(tmp_path, name, metadata=metadata, jsonld=_jsonld(metadata),
                         content=(), extra=(("content/doc1.pdf", b"%PDF-1.4"),
                                            ("index.html", "<html/>")))


def _ids(tmp_path, name, metadata):
    report = runner.run(_package(tmp_path, name, metadata), runner.ALL_KINDS)
    return {f.rule.id for f in report.findings}


def test_the_fixture_is_a_conformant_handover_package(tmp_path):
    """Asserted before anything is removed. Every case below reads "this rule
    fires when its requirement is missing", and that sentence is only true if
    the package is otherwise clean."""
    report = runner.run(_package(tmp_path, "clean.iirds", HANDOVER), runner.ALL_KINDS)
    errors = sorted({f.rule.id for f in report.findings if str(f.severity) == "error"})
    assert errors == [], errors
    assert report.variant == "H"


#: (rule, the line whose removal is exactly that rule's requirement)
#: The five named-party MUSTs, provoked by breaking the chain at its most
#: telling link: the Author party line for M15.8; the shared Creator role
#: for M15.9/M15.10 (one party serves Package and InformationObject, so one
#: removal provokes both -- each row asserts only its own rule); the shared
#: Manufacturer role for M15.7b/M15.7d likewise.
NAMED_PARTY_REMOVALS = [
    ("M15.8", '    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>'),
    ("M15.9", '    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Creator"/>'),
    ("M15.10", '    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Creator"/>'),
    ("M15.7b", '    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>'),
    ("M15.7d", '    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>'),
]

REMOVALS = NAMED_PARTY_REMOVALS + [
    ("M15.2",  '    <hov:has-document-category rdf:resource="%sOperatingInstructions"/>\n' % HOV),
    ("M15.3",  "    <iirds:language>en</iirds:language>\n"),
    ("M15.4",  "    <iirds:title>Operating instructions</iirds:title>\n"),
    ("M15.5",  '    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n'),
    ("M15.6",  """    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>application/pdf</iirds:format>
        <iirds:source>content/doc1.pdf</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>\n"""),
    ("M15.7a", '    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n'),
    ("M15.7c", '    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#ProductType"/>\n'),
]


@pytest.mark.parametrize("rule_id,line", REMOVALS, ids=[r[0] for r in REMOVALS])
def test_removing_what_a_rule_asks_for_makes_it_fire(rule_id, line, tmp_path):
    assert line in HANDOVER, "the fixture no longer contains %r" % line
    broken = HANDOVER.replace(line, "", 1)
    assert rule_id in _ids(tmp_path, "%s.iirds" % rule_id.replace(".", "_"), broken)


def test_m15_8_a_document_with_no_party(tmp_path):
    """Removed from the Document only: the Package and InformationObject keep
    theirs, so M15.9 and M15.10 stay quiet and this is M15.8 alone."""
    broken = HANDOVER.replace(
        '    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n'
        '    <iirds:relates-to-product-variant', "    <iirds:relates-to-product-variant", 1)
    found = _ids(tmp_path, "m15_8.iirds", broken)
    assert "M15.8" in found
    assert not {"M15.9", "M15.10"} & found


def test_m15_9_a_package_with_no_party(tmp_path):
    broken = HANDOVER.replace(
        '    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n'
        "  </iirds:Package>", "  </iirds:Package>", 1)
    assert "M15.9" in _ids(tmp_path, "m15_9.iirds", broken)


def test_m15_10_an_information_object_with_no_party(tmp_path):
    broken = HANDOVER.replace(
        '    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n'
        "  </iirds:InformationObject>", "  </iirds:InformationObject>", 1)
    assert "M15.10" in _ids(tmp_path, "m15_10.iirds", broken)


def test_m15_7b_an_instance_identity_domain_with_no_manufacturer(tmp_path):
    """Not reached by removing the identity type: without it the identity is no
    longer an instance identity, the rule has nothing to iterate over, and
    M15.7a reports the absence instead. The defect this rule is about is an
    instance identity that exists and whose domain traces back to nobody.
    """
    broken = HANDOVER.replace(
        '    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n'
        "  </iirds:IdentityDomain>\n\n  <iirds:Identity rdf:about=\"urn:test:identity-type\"",
        "  </iirds:IdentityDomain>\n\n  <iirds:Identity rdf:about=\"urn:test:identity-type\"", 1)
    found = _ids(tmp_path, "m15_7b.iirds", broken)
    assert "M15.7b" in found
    assert "M15.7d" not in found, "the ProductType domain still has its party"


def test_m15_7d_a_product_type_domain_with_no_manufacturer(tmp_path):
    """M15.7b and M15.7d ask the same question of two different domains, so
    only the ProductType one loses its party here."""
    broken = HANDOVER.replace(
        '    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n'
        "  </iirds:IdentityDomain>\n\n  <!-- One organisation",
        "  </iirds:IdentityDomain>\n\n  <!-- One organisation", 1)
    found = _ids(tmp_path, "m15_7d.iirds", broken)
    assert "M15.7d" in found
    assert "M15.7b" not in found, "the instance identity domain still has its party"


def test_m15_11c_a_selector_in_a_handover_package(tmp_path):
    """iiRDS/H delivers whole documents, so addressing a fragment inside one
    has no meaning on the receiving side."""
    broken = HANDOVER.replace("</rdf:RDF>", """  <iirds:FragmentSelector rdf:about="urn:test:sel">
    <rdf:value>//section[1]</rdf:value>
  </iirds:FragmentSelector>
</rdf:RDF>""")
    assert "M15.11c" in _ids(tmp_path, "m15_11c.iirds", broken)


def test_none_of_these_rules_apply_outside_the_handover_profile(tmp_path):
    """The profile axis, asserted rather than assumed. An iiRDS/H requirement
    reported against an unrestricted package would fail packages that are
    perfectly conformant for what they claim to be."""
    unrestricted = HANDOVER.replace(
        "    <iirds:formatRestriction>H</iirds:formatRestriction>\n", "")
    stripped = unrestricted.replace("    <iirds:language>en</iirds:language>\n", "")
    found = _ids(tmp_path, "unrestricted.iirds", stripped)
    assert not {r for r in found if r.startswith("M15.")}


def test_m15_5_accepts_a_proprietary_subclass_of_information_object(make_package):
    """Section 7 again: an object typed with the package's own subclass of
    iirds:InformationObject is an InformationObject. Exact-typing here made
    the Python side fire where SHACL (whose sh:class follows the data graph's
    subClassOf) was rightly silent — found by the round-2 adversarial pass."""
    subclassed = HANDOVER.replace(
        '<iirds:InformationObject rdf:about="urn:test:io1">',
        '''<rdf:Description rdf:about="urn:acme:SpecialIO">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#InformationObject"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:io1">
    <rdf:type rdf:resource="urn:acme:SpecialIO"/>''').replace(
        '</iirds:InformationObject>', '</rdf:Description>')
    package = make_package(name="sub.iirds", metadata=subclassed,
                           jsonld=_jsonld(subclassed), content=(),
                           extra=(("content/doc1.pdf", b"%PDF-1.4"), ("index.html", "<html/>")))
    report = runner.run(package, runner.ALL_KINDS)
    assert "M15.5" not in {f.rule.id for f in report.findings}
