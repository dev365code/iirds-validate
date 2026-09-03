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


def test_a_vcard_the_package_never_describes_is_reported_here_too(tmp_path):
    """This test asserted the opposite when it was written, and the reading it
    encoded was wrong.

    The softening it copied belongs to section 8.3.2's five named-party MUSTs,
    where one unresolvable pointer would otherwise arrive five times and R4
    owns the cause. Here one rule asks the question, R4 is gated to iiRDS/H,
    and the softening left `iirds check` silent about a party described as
    nothing at all -- L1 reports the pointer and L1 is a lint that `check`
    does not run.

    A pointer at nothing is not a description of the party as a vcard kind.
    Both rules speak now: L1 about the pointer, this about the sentence.
    """
    got = fired(tmp_path, "kind_dangling.iirds", "")
    assert "R12" in got, sorted(got)
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


def test_a_vcard_the_vocabulary_calls_a_kind_by_its_other_name_is_accepted(tmp_path):
    """`vcard:VCard` is not a fifth subclass; it is the same class under the
    older name, and the vocabulary says so itself:

        <#VCard> a owl:Class;
          rdfs:comment "The vCard class is equivalent to the new Kind class,
                        which is the parent for the four explicit types of
                        vCards (Individual, Organization, Location, Group)";
          owl:equivalentClass <#Kind>.

    Reading the file for `rdfs:subClassOf` alone found four and missed this,
    and a card typed with it is conformant and was the rule's only finding --
    failure mode three in docs/scope.md, on a shape no corpus here contains
    and no oracle could have caught.
    """
    assert "R12" not in fired(tmp_path, "kind_vcard.iirds", typed(VCARD + "VCard"))


#: What the rule must report, and what each would have been mistaken for.
NOT_A_KIND = [
    ("a term of the standard's own vocabulary", IIRDS + "Topic"),
    ("a named individual of the standard's", IIRDS + "Manufacturer"),
    ("the vcard class itself rather than an instance of it", VCARD + "Organization"),
    ("an IRI the package never describes", "urn:test:nowhere"),
    ("an http IRI the package never describes", "http://example.com/card"),
]


@pytest.mark.parametrize("what,iri", NOT_A_KIND, ids=[w.replace(" ", "-") for w, _ in NOT_A_KIND])
def test_a_card_that_is_not_a_kind_is_reported_whoever_else_describes_it(what, iri, tmp_path):
    """The rule kept two of the three guards the shared helper carries, and
    the one it dropped is the one the helper's docstring exists to explain: a
    term the standard defines is not a dangling pointer, it is the wrong term.

    Nothing else covers these. L1 exempts iiRDS terms by design and exempts
    the vcard namespace by name (`WELL_KNOWN`), L8 is a MAY, and both are
    lints that `check` does not run -- so `iirds check` reported nothing at
    all for every row here.
    """
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", (PARTY % "") + "</rdf:RDF>").replace(
        'rdf:resource="urn:test:card"', 'rdf:resource="%s"' % iri)
    package = build_package(tmp_path, "notkind_%d.iirds" % abs(hash(what)), metadata=metadata)
    for kinds, mode in ((runner.ALL_KINDS, "everything"), (runner.CONFORMANCE_KINDS, "check")):
        got = {f.rule.id for f in runner.run(package, kinds).findings}
        assert "R12" in got, (what, mode, sorted(got))


def test_a_blank_node_card_with_no_type_is_reported(tmp_path):
    """The worst of them: `<iirds:relates-to-vcard><rdf:Description/></...>`
    produced no finding anywhere. R12 read it as undescribed, L1 requires a
    URIRef and never sees a blank node, and M23 counts one value and is
    satisfied."""
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", """
  <iirds:Party rdf:about="urn:test:p">
    <iirds:has-party-role rdf:resource="%sAuthor"/>
    <iirds:relates-to-vcard><rdf:Description/></iirds:relates-to-vcard>
  </iirds:Party>
</rdf:RDF>""" % IIRDS)
    got = {f.rule.id for f in runner.run(
        build_package(tmp_path, "blank_card.iirds", metadata=metadata),
        runner.CONFORMANCE_KINDS).findings}
    assert "R12" in got, sorted(got)
