"""A party's vcard must be a vcard kind, not merely a thing it points at.

Section 6.8.3, the sentence after the one M22.1 and M22.2 share: "In addition
to the role, an `iirds:Party` MUST also have an associated description of
itself as compliant **vcard:kind object** which is assigned via
`iirds:relates-to-vcard`."

Two limbs, and only the property was counted. M23 asks whether the relation is
there; this asks whether what it points at is a vcard kind. Exactly the shape
R10 was written for one sentence earlier in the same section, which is how it
was found.

The vCard vocabulary declares `vcard:Kind` with four subclasses and no others:
Individual, Organization, Group, Location. Those four IRIs are facts, the way
iiRDS term IRIs are facts, so nothing needs bundling to know them.
"""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

IIRDS = "http://iirds.tekom.de/iirds#"
VCARD = "http://www.w3.org/2006/vcard/ns#"

PARTY = """
  <iirds:Party rdf:about="urn:test:party">
    <iirds:has-party-role rdf:resource="%sAuthor"/>
    <iirds:relates-to-vcard rdf:resource="urn:test:card"/>
  </iirds:Party>
%%s""" % IIRDS


def fired(tmp_path, name, card_block):
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", (PARTY % card_block) + "</rdf:RDF>")
    return {f.rule.id for f in runner.run(build_package(tmp_path, name, metadata=metadata),
                                          runner.ALL_KINDS).findings}


def typed(class_iri):
    return ('  <rdf:Description rdf:about="urn:test:card">\n'
            '    <rdf:type rdf:resource="%s"/>\n'
            '  </rdf:Description>\n' % class_iri)


@pytest.mark.parametrize("kind", ["Individual", "Organization", "Group", "Location", "Kind"],
                         ids=lambda k: k.lower())
def test_every_vcard_kind_the_vocabulary_declares_is_accepted(kind, tmp_path):
    """All four subclasses and the parent. A rule that knew only the two a
    handover package uses would reject a party described as a person."""
    assert "R12" not in fired(tmp_path, "kind_%s.iirds" % kind, typed(VCARD + kind))


def test_the_lower_case_organization_spelling_is_accepted(tmp_path):
    """The same accommodation ORGANISATION_TYPES records and for the same
    reason: every handover fixture the reference tool ships writes it."""
    assert "R12" not in fired(tmp_path, "kind_lower.iirds", typed(VCARD + "organization"))


def test_a_declared_subclass_of_a_kind_is_accepted(tmp_path):
    """Section 7 lets a package declare its own class beneath an existing one
    and requires consumers to treat instances as the parent."""
    card = ('  <rdf:Description rdf:about="http://my.co/ns#Supplier">\n'
            '    <rdfs:subClassOf rdf:resource="%sOrganization"/>\n'
            '  </rdf:Description>\n' % VCARD) + typed("http://my.co/ns#Supplier")
    assert "R12" not in fired(tmp_path, "kind_subclass.iirds", card)


def test_a_vcard_that_is_not_a_kind_at_all_is_reported(tmp_path):
    """The defect: the property is there, so M23 is silent, and what it points
    at is an information unit."""
    card = ('  <iirds:Topic rdf:about="urn:test:card">'
            "<iirds:title>not a vcard</iirds:title></iirds:Topic>\n")
    got = fired(tmp_path, "kind_topic.iirds", card)
    assert "R12" in got, sorted(got)
    assert "M23" not in got, "the property is present; this is the other limb"


def test_a_vcard_with_no_type_at_all_is_reported(tmp_path):
    """Described, and described as nothing. The sentence asks for a kind."""
    card = ('  <rdf:Description rdf:about="urn:test:card">\n'
            '    <vcard:organization-name>Rotor Works</vcard:organization-name>\n'
            "  </rdf:Description>\n")
    metadata = MINIMAL_RDF.replace(
        "xmlns:iirds=", 'xmlns:vcard="%s"\n         xmlns:iirds=' % VCARD, 1)
    metadata = metadata.replace("</rdf:RDF>", (PARTY % card) + "</rdf:RDF>")
    got = {f.rule.id for f in runner.run(
        build_package(tmp_path, "kind_untyped.iirds", metadata=metadata),
        runner.ALL_KINDS).findings}
    assert "R12" in got, sorted(got)


def test_a_vcard_the_package_never_describes_is_left_to_l1(tmp_path):
    """The same softening every rule in this family makes: one unresolvable
    pointer is one finding, and it belongs to the rule about pointers."""
    got = fired(tmp_path, "kind_dangling.iirds", "")
    assert "R12" not in got, sorted(got)
    assert "L1" in got, "the dangling pointer is still reported, by its own rule"


def test_a_literal_where_a_vcard_belongs_is_reported(tmp_path):
    """No literal is an instance of any class, and L1 says nothing about one."""
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", """
  <iirds:Party rdf:about="urn:test:party">
    <iirds:has-party-role rdf:resource="%sAuthor"/>
    <iirds:relates-to-vcard>Rotor Works GmbH</iirds:relates-to-vcard>
  </iirds:Party>
</rdf:RDF>""" % IIRDS)
    got = {f.rule.id for f in runner.run(
        build_package(tmp_path, "kind_literal.iirds", metadata=metadata),
        runner.ALL_KINDS).findings}
    assert "R12" in got, sorted(got)
