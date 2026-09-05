"""A `covers=` claim is earned by a package, not by a reading.

`docs/scope.md` publishes "coverage of the standard is N of 280". A reader
takes that to mean: for each of those N sentences, a package that breaks it
gets a finding. Until this file existed, nothing checked that. Claims were
added by reading a sentence and a rule side by side and judging them to be
about the same thing, and the only mechanical gate on them --
`test_a_rule_and_the_requirement_it_claims_are_about_the_same_thing` --
skips any requirement whose subject is not a qualified name, which is 78 of
the 80 claims it saw. It asserted nothing about them and read like a gate over
all of them.

Ten claims failed that criterion -- five withdrawn, five repaired -- and each
failed it in silence:

  * three sentences of section 8.3.2 ask for a `vcard:Organization`, and the
    rules deliberately did not check the class, so a card typed
    `vcard:Individual` broke all three and the package passed;
  * one of those three was claimed by a rule that stays quiet in exactly the
    case its partner rule exists to report, and the partner did not claim it;
  * two sentences name a class and a property -- section 6.8.2's status value
    and section 6.8.3's vcard kind -- and the rule for each counted the
    property. The first got the missing half; the second needs a vocabulary
    this tool does not ship, so its claim went instead;
  * section 6.7.2's obligation begins "If an external product ontology is
    ... used", and the rule triggers on an iiRDS-internal relation instead;
  * section 6.7.4 and section 7.1 name `metadata.rdf`, and the rules read the
    merged graph;
  * section 6.12 asks whether a package *contains* iiRDS metadata in JSON-LD,
    and the rule asks whether the file parses;
  * section 6.9.1 binds every node in a list level, and the rule exempts
    roots -- which `docs/divergences.md` said, in those words, before the
    claim was added over it.

And one claim was withdrawn that should not have been, which is the same
failure pointing the other way: `iirds:RangeSelector` is exempt from M13.1 and
M13.2, and that is not a narrowing -- the specification's own Example 13 is a
range selector carrying neither property, with both on the fragment selectors
it points at, and those these rules do check. Restored, with the package.

So the criterion is written down, here and in `docs/scope.md`:

    A rule covers an obligation when every package that violates the
    obligation's sentence is reported by that rule, or by one of the other
    rules claiming the same id. Reporting more than the sentence asks does
    not disqualify a claim; reporting less does. A divergence that narrows
    what a rule checks withdraws the claim -- keeping both is how a
    documented exemption becomes an undocumented hole.

And the evidence is a package. Each entry below breaks one sentence and
asserts that a rule claiming that sentence fires on it. That is the only
form of evidence a reading cannot fake: `test_a_rule_and_the_requirement…`
compares two English texts, and two English texts that match are exactly
what a plausible-but-wrong mapping looks like.

The rest of the claims are named in UNAUDITED. That list is the honest part
of the coverage figure and it is meant to shrink.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.registry import all_rules

ROOT = Path(__file__).resolve().parents[1]
CLAIMED = {rid: sorted(r.id for r in all_rules() if rid in r.covers)
           for r in all_rules() for rid in r.covers}
HEAD = MINIMAL_RDF.replace("</rdf:RDF>", "")


def toc(body: str) -> str:
    return HEAD + body + "</rdf:RDF>\n"


def fired(tmp_path, name, **kwargs) -> set:
    return {f.rule.id for f in runner.run(build_package(tmp_path, name, **kwargs),
                                          runner.ALL_KINDS).findings}


# ---------------------------------------------------------------------------
# The counterexamples
#
# Each is a package that breaks exactly one sentence. Kept as data so the
# table reads as what it is: the evidence behind seven rows of a published
# coverage figure.
# ---------------------------------------------------------------------------

def _handover(kind):
    """The conformant iiRDS/H fixture with one thing broken.

    Built from `test_handover_rules_fire.HANDOVER`, which is asserted clean
    there, so a finding here is the break and not the fixture.
    """
    from test_handover_rules_fire import HANDOVER

    if kind == "individual":
        # Every conjunct of the sentence satisfied but the class: the card
        # states an organisation name and declares itself a person.
        return HANDOVER.replace("<vcard:Organization ", "<vcard:Individual ").replace(
            "</vcard:Organization>", "</vcard:Individual>")
    if kind == "untyped":
        # No vcard class at all. The sentence asks for one.
        return HANDOVER.replace("<vcard:Organization ", "<rdf:Description ").replace(
            "</vcard:Organization>", "</rdf:Description>")
    if kind == "subclass":
        # NOT a breach: the package declares its own class beneath
        # vcard:Organization and types the card with it, which section 7
        # sanctions and which says the card is an organisation. Here so that
        # the class check cannot be satisfied by comparing rdf:type values,
        # which is the form it took first and which reported this beside the
        # vcard:Individual case.
        return HANDOVER.replace(
            '  <vcard:Organization rdf:about="urn:test:supplier-card">',
            '  <rdf:Description rdf:about="http://my.co/ns#Supplier">\n'
            '    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>\n'
            '    <rdfs:subClassOf rdf:resource="http://www.w3.org/2006/vcard/ns#Organization"/>\n'
            '  </rdf:Description>\n'
            '  <rdf:Description rdf:about="urn:test:supplier-card">\n'
            '    <rdf:type rdf:resource="http://my.co/ns#Supplier"/>'
        ).replace("</vcard:Organization>", "</rdf:Description>")
    if kind == "a vocabulary term":
        # A name out of a published vocabulary: not a vcard, and not a pointer
        # at nothing either. Neither the five nor R4 speak for it -- R4 must
        # not, because "this package never describes it" is false about
        # `iirds:Topic` and its remedy would send the reader to write one.
        # R12 reports it, which is why R12 claims these sentences beside them.
        return HANDOVER.replace(
            '<iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>',
            '<iirds:relates-to-vcard '
            'rdf:resource="http://iirds.tekom.de/iirds#Topic"/>')
    if kind == "a literal":
        # The shape the specification's own Example 63 has, where a JSON-LD
        # context without "@type":"@id" turns an intended reference into a
        # string. It points at no vcard at all.
        return HANDOVER.replace(
            '<iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>',
            '<iirds:relates-to-vcard>https://suppco.example/about'
            '</iirds:relates-to-vcard>')
    if kind == "undescribed":
        # The pointer resolves to nothing. The five named-party rules soften
        # here by agreement and R4 owns it -- which is why R4 has to claim
        # the same three sentences they do.
        return HANDOVER.replace(
            '  <vcard:Organization rdf:about="urn:test:supplier-card">\n'
            "    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>\n"
            "  </vcard:Organization>\n", "")
    raise AssertionError(kind)


#: requirement id -> (what the package does wrong, how to build it)
#: The builders take tmp_path and return the set of rule ids that fired.
COUNTEREXAMPLES = {
    "x8-3-2-metadata-requirements#9": [
        ("a product variant's instance-identity domain names a manufacturer "
         "whose vcard is typed vcard:Individual", "individual"),
        ("...whose vcard carries no vcard class at all", "untyped"),
        ("...whose vcard the package never describes", "undescribed"),
        ("...whose vcard reference names a vocabulary term instead",
         "a vocabulary term"),
        ("...whose vcard reference is a literal, so it points at no vcard",
         "a literal"),
    ],
    "x8-3-2-metadata-requirements#12": [
        ("a product variant's ProductType domain names a manufacturer whose "
         "vcard is typed vcard:Individual", "individual"),
        ("...whose vcard carries no vcard class at all", "untyped"),
        ("...whose vcard the package never describes", "undescribed"),
        ("...whose vcard reference names a vocabulary term instead",
         "a vocabulary term"),
        ("...whose vcard reference is a literal, so it points at no vcard",
         "a literal"),
    ],
    "x8-3-2-metadata-requirements#13": [
        ("an information object's identity domain names a creator whose vcard "
         "is typed vcard:Individual", "individual"),
        ("...whose vcard carries no vcard class at all", "untyped"),
        ("...whose vcard the package never describes", "undescribed"),
        ("...whose vcard reference names a vocabulary term instead",
         "a vocabulary term"),
        ("...whose vcard reference is a literal, so it points at no vcard",
         "a literal"),
    ],
}


@pytest.mark.parametrize("requirement,what,kind", [
    (rid, what, kind) for rid, cases in COUNTEREXAMPLES.items() for what, kind in cases],
    ids=["%s:%s" % (rid.rpartition("#")[2], kind)
         for rid, cases in COUNTEREXAMPLES.items() for _what, kind in cases])
def test_a_package_that_breaks_the_sentence_is_reported_by_a_rule_claiming_it(
        requirement, what, kind, tmp_path):
    """The whole point. `what` is prose for the failure message; `kind` builds
    the package."""
    from test_handover_rules_fire import _package

    claimants = set(CLAIMED[requirement])
    report = runner.run(_package(tmp_path, "%s.iirds" % kind, _handover(kind)),
                        runner.ALL_KINDS)
    got = {f.rule.id for f in report.findings}
    assert claimants & got, (
        "%s: %s, and no rule claiming it fired (claimed by %s; fired: %s)"
        % (requirement, what, sorted(claimants), sorted(got)))


def wrong_status_value(tmp_path, claimants, what, value, extra=""):
    """A status whose value is `value`; True when a claiming rule reports it."""
    metadata = toc("""
  <iirds:ContentLifeCycleStatus rdf:about="urn:test:status">
    %s
  </iirds:ContentLifeCycleStatus>
  %s""" % (value, extra))
    return bool(claimants & fired(tmp_path, "lifecycle_%d.iirds" % abs(hash(what)),
                                  metadata=metadata))


def test_a_card_typed_with_a_declared_subclass_of_an_organisation_is_one(tmp_path):
    """The other side of the class check, and the one a package pays for.

    Section 7 lets a package declare its own class beneath an existing one and
    requires consumers to treat instances of it as the parent. A card typed
    with such a subclass of `vcard:Organization`, stating an organisation name,
    satisfies section 8.3.2 -- and the first form of this check compared
    `rdf:type` values directly, so it reported that package beside the one
    typed `vcard:Individual`. `Context.is_instance` says why in one line:
    "exact typing is how section 7 gets forgotten one rule at a time".
    """
    from test_handover_rules_fire import _package

    report = runner.run(_package(tmp_path, "vcard_subclass.iirds", _handover("subclass")),
                        runner.ALL_KINDS)
    errors = sorted({f.rule.id for f in report.findings if str(f.severity) == "error"})
    assert errors == [], errors


def test_the_lifecycle_status_value_sentence_is_covered_in_both_halves(tmp_path):
    """Section 6.8.2 names a class and a property: "An
    iirds:ContentLifecyleStatus MUST have an iirds:ContentLifecyleStatusValue
    which is assigned by the iirds:has-content-lifecycle-status-value
    property". Breaking either half breaks the sentence.

    The property half was M21.1's from the start. The class half was nobody's,
    for as long as the claim stood -- while section 6.8.3's identically shaped
    sentence had M22.1 and M22.2, one for each half, and M22.2 exists
    *because* one rule was found not to be enough for that shape.
    """
    claimants = set(CLAIMED["x6-8-2-content-lifecycle-status#2"])

    absent = fired(tmp_path, "lifecycle_absent.iirds", metadata=toc("""
  <iirds:ContentLifeCycleStatus rdf:about="urn:test:status">
    <rdfs:label>x</rdfs:label>
  </iirds:ContentLifeCycleStatus>"""))
    assert claimants & absent, ("the property is absent", sorted(absent))

    # Four wrong referents, not one. The first is what a rule catches almost by
    # accident; the other three are the exemptions, and each let this sentence
    # through while the claim stood. `iirds:Topic` and `iirds:Manufacturer` are
    # terms the ontology defines and neither is a status value; a literal is
    # not an instance of anything.
    assert wrong_status_value(tmp_path, claimants, "a local instance of another class",
                              '<iirds:has-content-lifecycle-status-value '
                              'rdf:resource="urn:test:notavalue"/>',
                              extra='<iirds:Topic rdf:about="urn:test:notavalue">'
                                    "<iirds:title>x</iirds:title></iirds:Topic>")
    for what, iri in (("the ontology's own class iirds:Topic", "Topic"),
                      ("an ontology term of the wrong kind", "Manufacturer")):
        assert wrong_status_value(tmp_path, claimants, what,
                                  '<iirds:has-content-lifecycle-status-value '
                                  'rdf:resource="http://iirds.tekom.de/iirds#%s"/>' % iri)
    assert wrong_status_value(tmp_path, claimants, "a literal",
                              "<iirds:has-content-lifecycle-status-value>Approved"
                              "</iirds:has-content-lifecycle-status-value>")

    # And the right referent stays silent, or the rule is not checking a kind.
    assert not wrong_status_value(
        tmp_path, claimants, "iirds:Approved, which is one",
        '<iirds:has-content-lifecycle-status-value '
        'rdf:resource="http://iirds.tekom.de/iirds#Approved"/>')


SELECTOR_NS = MINIMAL_RDF.replace(
    "xmlns:iirds=", 'xmlns:dcterms="http://purl.org/dc/terms/"\n         xmlns:iirds=', 1)

RANGE = """
  <iirds:Topic rdf:about="urn:test:t">
    <iirds:title>T</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>application/pdf</iirds:format>
        <iirds:source>content/topic1.xhtml</iirds:source>
        <iirds:has-selector>
          <iirds:RangeSelector>
            <iirds:has-start-selector>
              <iirds:FragmentSelector>%s</iirds:FragmentSelector>
            </iirds:has-start-selector>
            <iirds:has-end-selector>
              <iirds:FragmentSelector>
                <dcterms:conformsTo rdf:resource="http://tools.ietf.org/rfc/rfc3778"/>
                <rdf:value>page=17</rdf:value>
              </iirds:FragmentSelector>
            </iirds:has-end-selector>
          </iirds:RangeSelector>
        </iirds:has-selector>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Topic>
"""


def test_the_selector_sentence_is_covered_through_the_selectors_that_select(tmp_path):
    """"To select parts of a file, an iirds:Selector MUST have an rdf:value and
    dcterms:conformsTo" -- two limbs, M13.1 and M13.2 one each.

    This claim was withdrawn once, on the ground that M13.1 and M13.2 exempt
    `iirds:RangeSelector` and the sentence names every Selector. The exemption
    is right and the withdrawal was not: the specification's own Example 13 is
    a range selector carrying neither property, with both on the two fragment
    selectors it points at, and those are Selectors that these rules do check.
    A range does not select by a value; it selects by its endpoints, and the
    endpoints are where the sentence bites.

    So all three shapes: the specification's own example is clean, and a
    missing property on an endpoint is reported -- one rule for each limb.
    """
    claimants = set(CLAIMED["x6-3-1-reference-part-of-file-by-selector#3"])

    def run(name, start):
        metadata = SELECTOR_NS.replace("</rdf:RDF>", (RANGE % start) + "</rdf:RDF>")
        return {f.rule.id for f in runner.run(build_package(tmp_path, name, metadata=metadata),
                                              runner.ALL_KINDS).findings}

    both = ('<dcterms:conformsTo rdf:resource="http://tools.ietf.org/rfc/rfc3778"/>'
            "<rdf:value>page=10</rdf:value>")
    assert not claimants & run("selector_example13.iirds", both), \
        "the specification's own Example 13 must not be reported"
    # Through `claimants`, not by naming M13.1 and M13.2 directly: asserting
    # the rule id says the rule fires, which it would go on doing after the
    # claim was dropped. The claim is what this file is about.
    no_value = run("selector_no_value.iirds",
                   '<dcterms:conformsTo rdf:resource="http://tools.ietf.org/rfc/rfc3778"/>')
    assert claimants & no_value, ("no rdf:value on the start selector", sorted(no_value))
    no_conforms = run("selector_no_conforms.iirds", "<rdf:value>page=10</rdf:value>")
    assert claimants & no_conforms, ("no dcterms:conformsTo", sorted(no_conforms))
    assert claimants == {"M13.1", "M13.2"}, sorted(claimants)
    assert "M13.1" in no_value and "M13.2" in no_conforms, "one rule per limb"


def test_the_all_metadata_limb_belongs_to_the_rule_that_can_see_it(tmp_path):
    """"The META-INF directory MUST contain the file metadata.rdf containing
    **all metadata** in RDF 1.1 XML syntax."

    C8, C9 and C16.1 hold the file's presence and its syntax. The "all
    metadata" limb is not a fact about metadata.rdf alone -- it is only
    observable against the other serialisation, and L9 is the one rule that
    reads the two files apart instead of merged. Where only metadata.rdf
    exists the limb is satisfied by construction; where both exist and one
    carries something the other does not, L9 reports it. So L9 claims this
    sentence as well as the one about the two agreeing.
    """
    claimants = set(CLAIMED["x5-1-1-metadata-location-and-rdf-serializations#2"])
    jsonld = json.dumps({
        "@context": {"iirds": "http://iirds.tekom.de/iirds#"},
        "@graph": [{"@id": "urn:test:package", "@type": "iirds:Package",
                    "iirds:iiRDSVersion": "1.3", "iirds:title": "Test package"},
                   {"@id": "urn:test:extra", "@type": "iirds:Topic",
                    "iirds:title": "stated only in the JSON-LD"}]})
    got = fired(tmp_path, "all_metadata.iirds", metadata=MINIMAL_RDF, jsonld=jsonld)
    assert claimants & got, ("a statement metadata.rdf does not carry", sorted(got))


def test_the_one_information_object_sentence_is_covered_as_it_is_read(tmp_path):
    """"If information objects are used, each information unit MUST only be
    related to exactly one information object via iirds:is-version-of."

    M6 reads that as "at most one", for the reason recorded in its docstring:
    the other reading makes the `iirds:Package` -- an information unit, and a
    version of nothing -- fail every package that uses information objects.
    Under the reading, the sentence has one violation and M6 reports it.

    Both directions, because the reading is the claim: a unit that is a version
    of two things is reported, and a unit that is a version of none is not.
    """
    claimants = set(CLAIMED["x6-2-2-information-objects#2"])
    objects = """
  <iirds:InformationObject rdf:about="urn:test:io1"><iirds:title>A</iirds:title></iirds:InformationObject>
  <iirds:InformationObject rdf:about="urn:test:io2"><iirds:title>B</iirds:title></iirds:InformationObject>
"""
    two = fired(tmp_path, "two_objects.iirds", metadata=MINIMAL_RDF.replace("</rdf:RDF>", objects + """
  <iirds:Topic rdf:about="urn:test:t1">
    <iirds:title>a version of two things</iirds:title>
    <iirds:is-version-of rdf:resource="urn:test:io1"/>
    <iirds:is-version-of rdf:resource="urn:test:io2"/>
  </iirds:Topic>
</rdf:RDF>"""))
    assert claimants & two, sorted(two)

    none = fired(tmp_path, "no_object.iirds", metadata=MINIMAL_RDF.replace("</rdf:RDF>", objects + """
  <iirds:Topic rdf:about="urn:test:t1">
    <iirds:title>a version of nothing</iirds:title>
    <iirds:is-version-of rdf:resource="urn:test:io1"/>
  </iirds:Topic>
  <iirds:Topic rdf:about="urn:test:t2"><iirds:title>plain</iirds:title></iirds:Topic>
</rdf:RDF>"""))
    assert not claimants & none, ("the reading admits this package", sorted(none))


def test_the_party_role_sentence_is_covered_in_both_halves(tmp_path):
    """The twin of the above, and the reason it was found: this one already
    had both halves. Pinned so the pair cannot quietly become one rule
    again -- which is the state it was in before M22.2 was split out."""
    claimants = set(CLAIMED["x6-8-3-parties-and-roles#2"])

    absent = fired(tmp_path, "role_absent.iirds", metadata=toc("""
  <iirds:Party rdf:about="urn:test:party">
    <iirds:relates-to-vcard rdf:resource="urn:test:card"/>
  </iirds:Party>"""))
    assert claimants & absent, ("the property is absent", sorted(absent))

    wrong_type = fired(tmp_path, "role_wrong_type.iirds", metadata=toc("""
  <iirds:Party rdf:about="urn:test:party">
    <iirds:has-party-role rdf:resource="urn:test:notarole"/>
    <iirds:relates-to-vcard rdf:resource="urn:test:card"/>
  </iirds:Party>
  <iirds:Topic rdf:about="urn:test:notarole"><iirds:title>T</iirds:title></iirds:Topic>"""))
    assert claimants & wrong_type, (
        "the property points at something that is not a PartyRole", sorted(wrong_type))


def test_the_schema_prohibition_names_the_file_it_found_the_schema_in(tmp_path):
    """Section 7.1 names one file: "The file metadata.rdf MUST NOT contain the
    iiRDS schema or iiRDS domain extensions." A finding about a file-named
    sentence has to say which file, and this one asserted "metadata.rdf"
    whatever it found -- so a schema restated only in metadata.jsonld sent a
    reader to open a file that was clean.

    Both directions, because a message that always says metadata.jsonld would
    pass a test that only looked at the second case.
    """
    claimants = set(CLAIMED["x7-1-iirds-extension-scenarios#5"])
    restated = """
  <rdf:Description rdf:about="http://iirds.tekom.de/iirds#Component">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#InformationObject"/>
  </rdf:Description>"""

    report = runner.run(build_package(tmp_path, "schema_in_rdf.iirds",
                                      metadata=toc(restated)), runner.ALL_KINDS)
    hits = [f for f in report.findings if f.rule.id in claimants]
    assert hits, sorted({f.rule.id for f in report.findings})
    assert "metadata.rdf must not redeclare" in hits[0].violation.message

    jsonld = json.dumps({
        "@context": {"iirds": "http://iirds.tekom.de/iirds#",
                     "rdfs": "http://www.w3.org/2000/01/rdf-schema#"},
        "@graph": [{"@id": "urn:test:package", "@type": "iirds:Package",
                    "iirds:iiRDSVersion": "1.3", "iirds:title": "T"},
                   {"@id": "iirds:Component",
                    "rdfs:subClassOf": {"@id": "iirds:InformationObject"}}]})
    report = runner.run(build_package(tmp_path, "schema_in_jsonld.iirds",
                                      metadata=MINIMAL_RDF, jsonld=jsonld),
                        runner.ALL_KINDS)
    hits = [f for f in report.findings if f.rule.id in claimants]
    assert hits, sorted({f.rule.id for f in report.findings})
    assert "metadata.jsonld must not redeclare" in hits[0].violation.message

    # And the case that survived naming one file: the same subject declared a
    # property in metadata.rdf and a class in metadata.jsonld is one finding
    # belonging to both, and naming whichever came first named metadata.jsonld
    # -- the file section 7.1 does not name -- while metadata.rdf carried the
    # breach.
    both = json.dumps({
        "@context": {"iirds": "http://iirds.tekom.de/iirds#",
                     "rdfs": "http://www.w3.org/2000/01/rdf-schema#"},
        "@graph": [{"@id": "urn:test:package", "@type": "iirds:Package",
                    "iirds:iiRDSVersion": "1.3", "iirds:title": "Test package"},
                   {"@id": "iirds:Component", "@type": "rdfs:Class"}]})
    as_property = toc("""
  <rdf:Description rdf:about="http://iirds.tekom.de/iirds#Component">
    <rdf:type rdf:resource="http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"/>
  </rdf:Description>""")
    report = runner.run(build_package(tmp_path, "schema_in_both.iirds",
                                      metadata=as_property, jsonld=both), runner.ALL_KINDS)
    hits = [f for f in report.findings if f.rule.id in claimants]
    assert hits, sorted({f.rule.id for f in report.findings})
    assert "metadata.jsonld and metadata.rdf must not redeclare" in hits[0].violation.message, \
        hits[0].violation.message


# ---------------------------------------------------------------------------
# What is not held by a package yet
# ---------------------------------------------------------------------------

#: Claims with no counterexample in this file. Every one of them may be
#: perfectly good; none of them is *known* to be, and the seven that turned
#: out not to be looked exactly like these until a package was built.
#:
#: Adding a claim without a counterexample means writing its id here, which
#: is the point: the cost of an unevidenced claim is now a line in a list
#: called UNAUDITED rather than nothing at all.
UNAUDITED = frozenset((
    "dfn-iirds-package#1", "dfn-iirds-zip-archive#2",
    "dfn-iirds-zip-archive#3", "dfn-iirds-zip-archive#4",
    "rdfclasses_core_ClassificationType#1",
    "rdfclasses_handover_DocumentCategory#1",
    "x5-1-1-metadata-location-and-rdf-serializations#1",
    "x5-1-1-metadata-location-and-rdf-serializations#4",
    "x5-1-2-content-location#1", "x5-1-2-content-location#2",
    "x5-1-3-names-of-files-and-directories#2",
    "x5-1-3-names-of-files-and-directories#3", "x5-2-2-content-encoding#1",
    "x5-2-2-content-encoding#2", "x5-3-nested-iirds-packages#3",
    "x6-12-rdf-serialization#1", "x6-2-information-units#1",
    "x6-2-information-units#2", "x6-2-information-units#7",
    "x6-3-1-reference-part-of-file-by-selector#1",
    "x6-3-1-reference-part-of-file-by-selector#2",
    "x6-3-3-metadata-of-nested-iirds-packages#2",
    "x6-3-3-metadata-of-nested-iirds-packages#4",
    "x6-3-content-references-of-information-units#2",
    "x6-3-content-references-of-information-units#3",
    "x6-3-content-references-of-information-units#4",
    "x6-3-content-references-of-information-units#5",
    "x6-7-3-packages-related-to-component-trees#5",
    "x6-8-1-complex-identity#3", "x6-8-4-external-classification#7",
    "x6-9-1-directory-nodes#5", "x6-9-2-hierarchical-navigation#1",
    "x6-9-2-hierarchical-navigation#2", "x8-3-1-1-mandatory-content-list#2",
    "x8-3-1-2-nesting-of-packages#2",
    "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#4",
    "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#6",
    "x8-3-2-metadata-requirements#11", "x8-3-2-metadata-requirements#8",
))


#: The claims a package stands behind that are not in COUNTEREXAMPLES: each
#: needs a shape the table cannot express, so each has a test of its own. The
#: test's name is here so that deleting the test is not a way of keeping the
#: id -- a claim held by a function nobody runs is a claim held by nothing.
#: `module:name` where the test lives in another file, which is where it
#: belongs when the rule has a file of its own.
NAMED_CASES = {
    "rdfclasses_core_IdentityDomain#2":
        "test_identity_domain_cardinality:test_two_identity_types_are_reported",
    # Section 8.3.2's Package list: the six sentences its Document list
    # repeats word for word, and which nothing read until R13 to R16.
    # The Document half of #1 and #4, held by the same package as they are.
    "x8-3-2-metadata-requirements#7":
        "test_package_product_variant:test_a_variant_identity_without_a_domain_is_reported_for_both_classes",
    "x8-3-2-metadata-requirements#10":
        "test_package_product_variant:test_a_variant_identity_without_a_domain_is_reported_for_both_classes",
    "x8-3-2-metadata-requirements#1":
        "test_package_product_variant:test_each_package_bullet_is_reported",
    "x8-3-2-metadata-requirements#2":
        "test_package_product_variant:"
        "test_the_conformant_fixture_needs_the_packages_own_variant",
    "x8-3-2-metadata-requirements#3":
        "test_package_product_variant:test_the_manufacturer_bullets_are_reported",
    "x8-3-2-metadata-requirements#4":
        "test_package_product_variant:test_each_package_bullet_is_reported",
    "x8-3-2-metadata-requirements#5":
        "test_package_product_variant:test_each_package_bullet_is_reported",
    "x8-3-2-metadata-requirements#6":
        "test_package_product_variant:test_the_manufacturer_bullets_are_reported",
    "x6-12-rdf-serialization#3":
        "test_silent_pass:test_a_handover_jsonld_that_carries_no_iirds_metadata_is_reported",
    "x6-8-3-parties-and-roles#3":
        "test_party_vcard_kind:test_a_vcard_that_is_not_a_kind_at_all_is_reported",
    "x6-7-4-product-variants#1":
        "test_extensions_in_metadata_rdf:test_a_product_variant_only_in_the_json_ld_is_reported",
    "x6-7-1-component-trees-in-the-package#2":
        "test_extensions_in_metadata_rdf:test_a_component_only_in_the_json_ld_is_reported",
    # Two sentences of the same shape, held by one parametrised case so the
    # readings cannot drift apart again.
    # Appendix B, all nine, held by one case list: every sentence with
    # every shape that breaks it, and a clean control beside them.
    "b-3-conformance-criteria#2":
        "test_appendix_b_claims:test_every_way_of_breaking_an_appendix_b_sentence_is_reported",
    "b-3-conformance-criteria#4":
        "test_appendix_b_claims:test_every_way_of_breaking_an_appendix_b_sentence_is_reported",
    "b-3-conformance-criteria#5":
        "test_appendix_b_claims:test_every_way_of_breaking_an_appendix_b_sentence_is_reported",
    "b-5-2-document-metadata#1":
        "test_appendix_b_claims:test_every_way_of_breaking_an_appendix_b_sentence_is_reported",
    "b-5-7-scripting#1":
        "test_appendix_b_claims:test_every_way_of_breaking_an_appendix_b_sentence_is_reported",
    "b-5-10-forms#1":
        "test_appendix_b_claims:test_every_way_of_breaking_an_appendix_b_sentence_is_reported",
    "b-5-11-svg-mathml-and-iframes#1":
        "test_appendix_b_claims:test_every_way_of_breaking_an_appendix_b_sentence_is_reported",
    "b-6-additional-semantic-tagging-of-content#5":
        "test_appendix_b_claims:test_every_way_of_breaking_an_appendix_b_sentence_is_reported",
    "b-6-additional-semantic-tagging-of-content#6":
        "test_appendix_b_claims:test_every_way_of_breaking_an_appendix_b_sentence_is_reported",
    "x6-8-1-complex-identity#2": "test_remaining_rules_fire:test_the_non_empty_string_sentence_is_covered_in_every_limb",
    "x6-8-4-external-classification#4": "test_remaining_rules_fire:test_the_non_empty_string_sentence_is_covered_in_every_limb",
    "x6-2-information-units#5":
        "test_remaining_rules_fire:"
        "test_the_one_package_per_container_sentence_is_covered_in_both_limbs",
    "dfn-iirds-zip-archive#5": "test_the_mimetype_sentence_is_covered_in_both_limbs",
    "dfn-iirds-zip-archive#6": "test_the_mimetype_sentence_is_covered_in_both_limbs",
    "dfn-iirds-container#1": "test_the_single_root_directory_sentence_is_covered",
    "x6-2-information-units#3":
        "test_the_information_unit_iri_sentence_is_covered_in_both_limbs",
    "x6-2-information-units#4":
        "test_the_information_unit_iri_sentence_is_covered_in_both_limbs",
    "x8-3-1-1-mandatory-content-list#1":
        "test_the_handover_content_list_sentence_is_covered",
    "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#1":
        "test_the_handover_class_restriction_sentence_is_covered",
    "x6-3-1-reference-part-of-file-by-selector#3":
        "test_the_selector_sentence_is_covered_through_the_selectors_that_select",
    "x5-1-1-metadata-location-and-rdf-serializations#2":
        "test_the_all_metadata_limb_belongs_to_the_rule_that_can_see_it",
    "x6-2-2-information-objects#2":
        "test_the_one_information_object_sentence_is_covered_as_it_is_read",
    "x6-8-2-content-lifecycle-status#2":
        "test_the_lifecycle_status_value_sentence_is_covered_in_both_halves",
    "x6-8-3-parties-and-roles#2":
        "test_the_party_role_sentence_is_covered_in_both_halves",
    # Section 7.1's general sentence, claimed again after a withdrawal --
    # the reading it was waiting for is `vocabulary_classes`, and the
    # module holds a package for each of section 7.3's three kinds in
    # both shapes: described only in metadata.jsonld, and described in
    # no file at all.
    "x7-1-iirds-extension-scenarios#4":
        "test_proprietary_extensions:test_every_shape_of_the_sentence_is_reported",
    "x7-1-iirds-extension-scenarios#5":
        "test_the_schema_prohibition_names_the_file_it_found_the_schema_in",
}


def held():
    """The claims with evidence behind them, derived rather than listed.

    This was a set literal written by hand beside the two sources it was
    supposed to summarise, and it summarised nothing: an entry could be added
    to COUNTEREXAMPLES with an empty list of cases, or a named test deleted, or
    an id put here that no rule claims at all, and this file stayed green while
    `docs/scope.md` went on publishing the number. The literal is gone; what is
    left asserts.
    """
    for requirement, cases in COUNTEREXAMPLES.items():
        assert cases, "%s is listed with no counterexample at all" % requirement
    for requirement, test_name in NAMED_CASES.items():
        module, _, name = test_name.rpartition(":")
        where = __import__(module) if module else sys.modules[__name__]
        assert callable(getattr(where, name, None)), \
            "%s is held by %s, which does not exist" % (requirement, test_name)
    return set(COUNTEREXAMPLES) | set(NAMED_CASES)


def test_every_claim_is_either_held_by_a_package_or_named_as_unaudited():
    """No third category. A claim that is neither evidenced nor listed is a
    claim nobody decided about, which is how all seven arrived."""
    evidenced = held()
    unexplained = sorted(set(CLAIMED) - evidenced - UNAUDITED)
    assert unexplained == [], (
        "claimed with neither a counterexample nor a place in UNAUDITED: %s" % unexplained)
    stale = sorted(UNAUDITED - set(CLAIMED))
    assert stale == [], "listed as unaudited but no longer claimed: %s" % stale
    assert sorted(UNAUDITED & evidenced) == [], "both audited and listed as unaudited"
    unclaimed = sorted(evidenced - set(CLAIMED))
    assert unclaimed == [], "held by a package but claimed by no rule: %s" % unclaimed


def test_the_audited_share_is_what_the_scope_document_publishes():
    """Two numbers, and the second is the one a reader should weigh. Read out
    of the document rather than compared to a constant, because pinning the
    document to a literal 6 pins the document and not the set: the two moved
    apart the first time somebody tried it."""
    scope = (ROOT / "docs" / "scope.md").read_text("utf-8")
    assert len(CLAIMED) == 81, len(CLAIMED)
    assert len(UNAUDITED) == 39, len(UNAUDITED)
    assert len(CLAIMED) == len(held()) + len(UNAUDITED), "the three numbers do not add up"

    published = re.search(r"\*\*Coverage of the standard is (\d+) of (\d+)\.\*\*", scope)
    assert published, "docs/scope.md no longer states coverage in the expected shape"
    assert int(published.group(1)) == len(CLAIMED), published.group(0)

    evidenced = re.search(r"(\d+) of the (\d+) are held by a\s+package", scope)
    assert evidenced, "docs/scope.md no longer states how many claims are evidenced"
    assert (int(evidenced.group(1)), int(evidenced.group(2))) == (len(held()), len(CLAIMED)), \
        evidenced.group(0)


# ---------------------------------------------------------------------------
# A withdrawal has to stay withdrawn
# ---------------------------------------------------------------------------

#: A rule whose source says `# not <requirement id>: <reason>` has had that
#: claim considered and refused. The comment sits on the line a future edit
#: would put the claim back on, so it is the right place to guard from.
#:
#: Deliberately not anchored to the rule id: the first version of this
#: expression required the comment to follow `@rule("M25",` immediately, and a
#: mutation that inserted `covers=(...)` in between matched nothing and passed
#: -- a gate that disappears under precisely the edit it exists to catch. It
#: now finds the comment anywhere in the decorator and attributes it to the
#: `@rule(` above it, and the count is pinned so deleting one is an edit
#: somebody has to make on purpose rather than a silent loss of the guard.
RULE_HEAD = re.compile(r'@rule\(\s*"([^"]+)"')
REFUSAL = re.compile(r'#\s*not\s+([\w.-]+#\d+)\s*:')

#: Rules the leniency table lists as withdrawn whose sentence went to another
#: rule rather than becoming a gap: rule -> (the sentence, the rule that has
#: it now). M18's claim on section 6.7.4 is R11's, so M18 carries no refusal
#: comment and the table row would otherwise assert nothing at all.
#:
#: A set of ids was the first form and it asserted nothing either -- the
#: grounds were in the comment above it, which is exactly the shape of the row
#: this exemption was added to repair. Both halves are read by the test at the
#: foot of this file.
WITHDRAWN_ELSEWHERE = {"M18": ("x6-7-4-product-variants#1", "R11")}

#: The withdrawals, by name and not by count. Counting was the second version
#: of this guard and it was bypassable in one move: carry the refusal comment
#: over to another rule's decorator, restore the claim on its own, and the
#: count is still five while the sentence explaining the withdrawal now sits
#: above a rule it says nothing about. Pinned as pairs, so a comment that
#: moves has moved away from its pin.
REFUSED = frozenset((
    ("M17", "x6-7-2-external-product-ontology#6"),
    ("M25", "x6-9-1-directory-nodes#3"),
))


def refusals():
    """(rule id, requirement id) for every refusal comment in the rules."""
    for path in sorted((ROOT / "src" / "iirds_validate" / "rules").glob("*.py")):
        current = None
        for line in path.read_text("utf-8").splitlines():
            head = RULE_HEAD.search(line)
            if head:
                current = head.group(1)
            refused = REFUSAL.search(line)
            if refused:
                assert current, "%s: refusal comment before any @rule: %s" % (path.name, line)
                yield current, refused.group(1)


def test_a_claim_a_rule_refuses_in_its_own_source_is_not_made_elsewhere():
    """Four claims were withdrawn after a package showed they were not
    covered, and the reason is written where the claim would go. A later pass
    that adds one back -- to raise a number, most likely -- has to delete the
    sentence saying why it was refused."""
    index = json.loads((ROOT / "docs" / "requirements.json").read_text("utf-8"))
    known = {r["id"] for r in index["requirements"]}
    found = set(refusals())
    assert found == REFUSED, (
        "refusal comments moved: extra %s, missing %s"
        % (sorted(found - REFUSED), sorted(REFUSED - found)))
    for rule_id, requirement in sorted(found):
        rule = next((r for r in all_rules() if r.id == rule_id), None)
        assert rule is not None, "%s: no such rule" % rule_id
        # A mistyped id refuses nothing, and reads as though it refused
        # something. Checked against the index the claims are made against.
        assert requirement in known, "%s refuses %s, which is not an obligation" % (
            rule_id, requirement)
        assert requirement not in rule.covers, (
            "%s says it does not claim %s and claims it" % (rule_id, requirement))


#: The `claim` column of the leniency table in docs/divergences.md, read as
#: an assertion. A row saying "withdrawn" whose rules still claim something
#: from that section is the shape the M25 paragraph was in.
#: The two regions whose claim language is legitimate and is read elsewhere:
#: the leniency table (its `claim` column, by the test above) and the M25
#: paragraph (by the test below). Cut out, not filtered -- see the docstring.
#: Ends at the end of the *table*, meaning the last line that is a table
#: row. It used to end at the first blank line, which is where the author
#: stops pressing return rather than where the table stops: a sentence
#: appended under the last row with no blank line was inside the cut and
#: therefore unread. Cutting out was the repair for a filtering bug and
#: brought its own, which is the argument for testing a gate against the
#: ways round it rather than against one mutation.
#: The two regions this gate cuts out, and each is anchored so that nothing can
#: be appended *into* it. The table used to end at the last line starting with a
#: pipe, so a sentence written as `| M17 no longer claims x… |` was inside the
#: table as far as the regex could tell; it now consumes only lines shaped like
#: one of its rows. And `search` takes the first match, so a second copy of the
#: header anywhere earlier in the document moved the cut off the real table —
#: `_without_the_cut_regions` asserts each region occurs exactly once.
LENIENCY_TABLE = re.compile(
    r"\| rule \| kind of leniency \| claim \|\n\|[-| ]+\|"
    r"(?:\n\| [^|\n]+ \| \*\*[^|\n]+\*\*[^|\n]*\| [^|\n]+ \|)*")
M25_PARAGRAPH = re.compile(r"The rule does not claim `covers=.*?(?=\n\n)", re.S)

#: The one region cut whole rather than by shape, so its size is pinned: a
#: sentence appended inside it would be cut with it and read by nobody, which
#: is the fifth way found past this gate.
M25_PARAGRAPH_LENGTH = 503

#: A rule id and an obligation id within 200 characters of each other, in
#: either order, over whitespace-collapsed text.
#:
#: The verb is deliberately not part of it any more. It was a list --
#: withdrew, withdrawn, no longer claims, does not claim -- and a list of
#: phrasings is a list of the phrasings somebody thought of: "no longer
#: covers" walked past it, and so did the passive. What makes a sentence a
#: statement about a claim is not its verb; it is that it names a rule and a
#: sentence of the standard in one breath, which is what `covers=` says and
#: what this document undertook to stop saying.
#:
#: Ordinary prose here names rules constantly and obligations rarely, and
#: never both together outside the cut regions -- which is why the pairing,
#: not the verb, is the signal. `test_the_control_is_caught` holds the other
#: half: a gate that matched nothing would pass this file too.
#: The obligation ids are not enumerated either, for the reason the verbs were
#: not: a list of id shapes is a list of the shapes somebody thought of. Four
#: were written out and sixty-five of the standard's four hundred and thirty-nine
#: ids matched none of them -- every `rdfobjects_`, `rdfproperties_`,
#: `rdfrelations_`, appendix `a-` and `iirds-h-` id -- so a sentence naming one
#: of those walked past. They come from the index the ids come from.
_OBLIGATION_PREFIXES = sorted(
    {r["id"].partition("#")[0] for r in
     json.loads((ROOT / "docs" / "requirements.json").read_text("utf-8"))["requirements"]},
    key=len, reverse=True)
_AN_OBLIGATION = r"(?:%s)#\d+" % "|".join(re.escape(p) for p in _OBLIGATION_PREFIXES)

#: Scoped to a paragraph rather than to a window of characters. Two hundred
#: was a number, and a number is a distance somebody guessed: the same sentence
#: written with a clause in the middle walked past it. A paragraph is the unit
#: the document is written in, and over this document exactly one paragraph
#: contains both -- which turned out not to be a false positive but a
#: restatement the window had been missing.
A_RULE_ID = re.compile(r"\b[CMLBRS]\d+(?:\.\d+[a-z]?)?\b")
AN_OBLIGATION_ID = re.compile(_AN_OBLIGATION)
PARAGRAPH = re.compile(r"\n\s*\n")

LENIENCY_ROW = re.compile(r"^\| ([^|]+?) \| \*\*[^|]+\*\*[^|]*\| (withdrawn|kept|never claimed) \|$",
                          re.M)


def _without_the_cut_regions(text):
    """The document with the two places claim language is legitimate removed.

    Each has to occur exactly once. `re.search` takes the first match, so a
    second copy of either header -- a fenced example, a quotation, a line
    somebody added -- moves the cut off the real region and leaves it read
    while hiding whatever sits under the copy.
    """
    for cut in (LENIENCY_TABLE, M25_PARAGRAPH):
        found = list(cut.finditer(text))
        assert len(found) == 1, (
            "the region this test cuts out occurs %d times, and it has to occur "
            "once: %s" % (len(found), cut.pattern[:48]))
        block = found[0]
        if cut is M25_PARAGRAPH:
            assert len(" ".join(block.group(0).split())) == M25_PARAGRAPH_LENGTH, (
                "the paragraph this test cuts out has changed length. It is cut "
                "whole, so anything appended inside it goes unread — which is a "
                "way past this gate. Re-read it, and move the pin on purpose.")
        text = text[:block.start()] + text[block.end():]
    return text


def test_the_leniency_table_says_what_the_rules_do():
    """`docs/divergences.md` records every place a reading was narrowed, and
    each row now says whether the rule still claims the sentence. The first
    version of that paragraph said all of them had been withdrawn, which was
    false of three rows -- written confidently, contradicted by the tree it
    described, and read by nothing. Read here.

    Only the claim's presence is checkable, not its correctness: whether a
    kept claim deserves to be kept is what the counterexamples above are for.
    """
    text = (ROOT / "docs" / "divergences.md").read_text("utf-8")
    rows = LENIENCY_ROW.findall(text)
    assert len(rows) == 7, [r[0] for r in rows]
    by_id = {rule.id: rule for rule in all_rules()}
    for names, verdict in rows:
        # Every prefix this project uses, not the three that happened to be in
        # the table when it was written: L9 could be added to a `withdrawn`
        # row and the test would read the row and see no rules in it.
        ids = re.findall(r"\b[CMLBRS]\d+(?:\.\d+[a-z]?)?(?![\w/])", names)
        assert ids, names
        for rule_id in ids:
            assert rule_id in by_id, "%s names %s, which is not a rule" % (names, rule_id)
        claims = {rule_id: set(by_id[rule_id].covers) for rule_id in ids}
        if verdict in ("withdrawn", "never claimed"):
            for rule_id, claimed in claims.items():
                refused = {req for rid, req in refusals() if rid == rule_id}
                assert not (claimed & refused), \
                    "%s is listed %s and claims %s" % (rule_id, verdict, sorted(claimed & refused))
                # And a row that says "withdrawn" has to be about something.
                # A rule whose refusal comment was rewritten has an empty
                # `refused` set, so the line above stops asserting and the row
                # goes on saying it with nothing behind it -- which is what
                # happened to M18 when its sentence moved to R11. "never
                # claimed" is a different statement: there was no claim to
                # refuse, so there is no comment to expect.
                assert verdict != "withdrawn" or refused or rule_id in WITHDRAWN_ELSEWHERE, (
                    "%s is listed withdrawn and no longer says so in its own source; "
                    "either restore the comment or record where the sentence went"
                    % rule_id)
        else:
            # The row's reading is shared; the claim sits on whichever rules
            # have a sentence in the index. M15.8 and M15.9 have none -- their
            # sentences carry no RFC 2119 markup, so the parse never saw them.
            assert any(claims.values()), \
                "%s is listed as keeping a claim and none of them claims anything" % names


def test_the_divergence_document_and_the_claims_agree():
    """`docs/divergences.md` said, in these words, "The rule does not claim
    `covers=x6-9-1-directory-nodes#3`, because it does not cover all of it" --
    and the mapping pass added the claim without touching the paragraph. The
    document was right and nothing read it."""
    text = (ROOT / "docs" / "divergences.md").read_text("utf-8")
    refused = re.findall(r"does not claim `covers=([\w.#-]+)`", text)
    assert refused, "docs/divergences.md no longer records a refused claim"
    for requirement in refused:
        claimants = CLAIMED.get(requirement)
        assert not claimants, (
            "docs/divergences.md says %s is not claimed; %s claims it"
            % (requirement, claimants))


def test_the_scope_document_says_which_claims_do_not_fail_a_package():
    """A claim means "a violation is reported", not "the package fails".

    The runner demotes content findings to warnings outside profile iiRDS/A,
    so a package breaching one of appendix B's rules is reported and still
    exits 0. That is deliberate and argued in docs/divergences.md -- and the
    coverage figure is the line a reader quotes, so the count has to be beside
    it and has to be the measured one.
    """
    scope = (ROOT / "docs" / "scope.md").read_text("utf-8")
    demoted = sorted(rule.id for rule in all_rules() if rule.covers and rule.kind == "content")
    stated = re.search(r"(\w+) of the (\d+) are appendix B's rules", scope)
    assert stated, "docs/scope.md no longer states how many claims are demoted outside iiRDS/A"
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    said = words.get(stated.group(1).lower())
    assert said == len(demoted), (stated.group(0), demoted)
    assert int(stated.group(2)) == len(CLAIMED), stated.group(0)

    # The same count is stated a second time two lines down, and the two said
    # eight and nine — a document contradicting itself about the number this
    # paragraph exists to publish, with nothing reading the second one.
    again = re.search(r"breaching one of those (\w+) is reported", scope)
    assert again, "docs/scope.md no longer states how many are demoted, the second time"
    assert words.get(again.group(1).lower()) == len(demoted), again.group(0)


# ---------------------------------------------------------------------------
# The claims the risk ranking put first
#
# The 58 that had no package behind them were not worked in id order. They
# were ranked by the shapes that actually failed -- a sentence with two limbs
# and one rule, a conditional, a sentence naming a file, a rule with several
# exemptions -- and the top of that ranking is here. All of it held, which is
# worth as much as a hole: it says the shapes that failed were found, not that
# the ranking was wrong.
# ---------------------------------------------------------------------------

def repacked(tmp_path, name, source, order=None, deflate=(), prefix=""):
    """`source` rebuilt: entries reordered, some deflated, all under a prefix."""
    import zipfile

    with zipfile.ZipFile(source) as archive:
        items = [(info.filename, archive.read(info.filename)) for info in archive.infolist()]
    if order is not None:
        items.sort(key=order)
    out = tmp_path / name
    with zipfile.ZipFile(out, "w") as archive:
        for filename, data in items:
            archive.writestr(prefix + filename, data,
                             zipfile.ZIP_DEFLATED if filename in deflate else zipfile.ZIP_STORED)
    return out


def test_the_mimetype_sentence_is_covered_in_both_limbs(tmp_path):
    """"The file MUST be the first entry in the ZIP file and it MUST be stored
    uncompressed ("Stored" mode)." Two limbs, one rule, which is the shape
    that failed three times today -- so it is asked twice."""
    claimants = set(CLAIMED["dfn-iirds-zip-archive#5"])
    assert claimants == set(CLAIMED["dfn-iirds-zip-archive#6"]), "the two ids share a rule"
    source = build_package(tmp_path, "mimetype_good.iirds", metadata=MINIMAL_RDF)
    assert not claimants & {f.rule.id for f in
                            runner.run(source, runner.ALL_KINDS).findings}

    late = repacked(tmp_path, "mimetype_late.iirds", source,
                    order=lambda item: item[0] == "mimetype")
    assert claimants & {f.rule.id for f in runner.run(late, runner.ALL_KINDS).findings}

    squashed = repacked(tmp_path, "mimetype_deflated.iirds", source, deflate=("mimetype",))
    assert claimants & {f.rule.id for f in runner.run(squashed, runner.ALL_KINDS).findings}


def test_the_single_root_directory_sentence_is_covered(tmp_path):
    """"An iiRDS container MUST have a single root directory." For a ZIP that
    is the archive root, so the breach is an archive built from the parent
    directory -- everything one folder down, which is what most zip tools do
    by default and the commonest way a package arrives unreadable."""
    claimants = set(CLAIMED["dfn-iirds-container#1"])
    source = build_package(tmp_path, "root_good.iirds", metadata=MINIMAL_RDF)
    nested = repacked(tmp_path, "root_nested.iirds", source, prefix="mypackage/")
    assert claimants & {f.rule.id for f in runner.run(nested, runner.ALL_KINDS).findings}


def test_the_information_unit_iri_sentence_is_covered_in_both_limbs(tmp_path):
    """"An instance of an iirds:InformationUnit subclass MUST have an IRI and
    MUST NOT be a blank node." One rule, and it answers both: a blank node has
    no IRI, and `rdf:about=""` resolves to the parsing base, which is an IRI
    of sorts and names nothing."""
    claimants = set(CLAIMED["x6-2-information-units#3"])
    for what, subject in (("a blank node", ""), ("an empty rdf:about", ' rdf:about=""')):
        metadata = toc('  <iirds:Topic%s><iirds:title>x</iirds:title></iirds:Topic>' % subject)
        got = fired(tmp_path, "iri_%d.iirds" % abs(hash(what)), metadata=metadata)
        assert claimants & got, (what, sorted(got))


def test_the_handover_content_list_sentence_is_covered(tmp_path):
    """"An iiRDS/H package MUST contain a content list as HTML file named
    index.html". Both halves: absent, and present but not HTML."""
    claimants = set(CLAIMED["x8-3-1-1-mandatory-content-list#1"])
    handover = MINIMAL_RDF.replace(
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        "    <iirds:formatRestriction>H</iirds:formatRestriction>")
    jsonld = json.dumps({"@context": {"iirds": "http://iirds.tekom.de/iirds#"},
                         "@id": "urn:test:package", "@type": "iirds:Package",
                         "iirds:iiRDSVersion": "1.3", "iirds:title": "Test package"})
    absent = fired(tmp_path, "index_absent.iirds", metadata=handover, jsonld=jsonld)
    assert claimants & absent, sorted(absent)
    unusable = fired(tmp_path, "index_unusable.iirds", metadata=handover, jsonld=jsonld,
                     extra=(("index.html", "plain text, not a content list"),))
    assert claimants & unusable, sorted(unusable)


def test_the_handover_class_restriction_sentence_is_covered(tmp_path):
    """"An iiRDS/H package MUST contain only information units of the
    subclasses iirds:Document and iirds:Package." A Topic is neither."""
    claimants = set(CLAIMED[
        "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#1"])
    handover = MINIMAL_RDF.replace(
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        "    <iirds:formatRestriction>H</iirds:formatRestriction>").replace(
        "</rdf:RDF>",
        '  <iirds:Topic rdf:about="urn:test:t"><iirds:title>T</iirds:title></iirds:Topic>\n'
        "</rdf:RDF>")
    jsonld = json.dumps({"@context": {"iirds": "http://iirds.tekom.de/iirds#"},
                         "@id": "urn:test:package", "@type": "iirds:Package",
                         "iirds:iiRDSVersion": "1.3", "iirds:title": "Test package"})
    got = fired(tmp_path, "handover_topic.iirds", metadata=handover, jsonld=jsonld,
                extra=(("index.html", "<html><body><p>list</p></body></html>"),))
    assert claimants & got, sorted(got)


def test_the_divergence_document_does_not_restate_what_the_code_claims(tmp_path):
    """Prose about which claims stand is a copy of the code, and it drifted
    twice: the M25 paragraph, and then a paragraph naming two rules as having
    withdrawn claims they had been given back.

    Both times the document was written carefully and read by nothing. The fix
    that holds is not a better sentence -- it is that the document stops making
    the statement. Withdrawals live in `# not <id>:` comments pinned above;
    claims live in `covers=`, held by a package or listed as unaudited.

    The first version of this test could not have caught either. Its window
    was `[^.\n]{0,80}?`, which crosses neither a newline nor a full stop, and
    this document is hard-wrapped at 75-odd characters: the sentence it was
    written to keep out has `withdrawn` at the end of one line and `M23` at the
    start of the next, and a rule id like `C16.2` carries a full stop of its
    own. It was verified against a mutation, and the mutation was the sentence
    reflowed onto one line -- so the test proved something about a text that
    had never existed. Whitespace is collapsed before matching now.

    Two regions are cut out rather than filtered. The leniency table's `claim`
    column legitimately says "withdrawn" and is read by the test above; the
    M25 paragraph is read by the one below. Filtering matches by content
    instead let a drift hide behind them: `re.finditer` is leftmost and
    non-overlapping, so naming M25 earlier in the same window swallowed the
    match that came after it.
    """
    text = (ROOT / "docs" / "divergences.md").read_text("utf-8")
    named = _restates(text)
    assert named == [], (
        "docs/divergences.md restates a claim's status in prose: %s" % named)


def test_the_instrument_checks_every_claim_it_counts():
    """`tools/held_claims.py` exists because a claim held by a function nobody
    runs is a claim held by nothing. It counted NAMED_CASES + COUNTEREXAMPLES
    and iterated NAMED_CASES, so three of the claims it reported as held --
    section 8.3.2's three named-party sentences, the ones with the most cases
    behind them -- were never looked at. Marking their one parametrised test
    `skip` left the tool printing "39 claims held in all" and exiting 0.

    Checked here rather than only in the tool, because the tool runs after the
    suite and this is a property of the tool.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import held_claims

    counted, checked = held_claims.claims_counted_and_checked()
    assert counted == checked, (
        "counted but not checked: %s" % sorted(counted - checked))
    assert counted == held(), (counted ^ held())


# ---------------------------------------------------------------------------
# Section 8.3.2 states its six product-variant sentences twice, word for word:
# once for iirds:Package and once for iirds:Document. The rules were
# parameterised so one builder answers both -- R13 and M15.7a are
# `_variant_instance_identity` with a different class, R15 and M15.7c are
# `_variant_product_type_identity` -- and the point of doing that was that the
# two readings could not drift apart.
#
# The readings did not drift. The *claims* did: R13 covers #1 and #2, and
# M15.7a covers #8 alone, so #7 -- the same sentence as #1, about the other
# class -- was claimed by nobody while its own rule reported it. Same for #10
# beside #4.
#
# Checked as a symmetry rather than as two more rows, because the asymmetry is
# what a reader of `covers=` cannot see and what a copy of the table would
# reproduce.
# ---------------------------------------------------------------------------

#: Package-half sentence -> the Document-half sentence that repeats it.
REPEATED_SENTENCES = {
    "x8-3-2-metadata-requirements#%d" % n: "x8-3-2-metadata-requirements#%d" % (n + 6)
    for n in range(1, 7)
}


def _sentence(requirement):
    index = json.loads((ROOT / "docs" / "requirements.json").read_text("utf-8"))
    return next(r["sentence"] for r in index["requirements"]
                if r["id"] == requirement)


@pytest.mark.parametrize("package_half", sorted(REPEATED_SENTENCES),
                         ids=sorted(REPEATED_SENTENCES))
def test_the_two_halves_of_section_8_3_2_are_claimed_alike(package_half):
    document_half = REPEATED_SENTENCES[package_half]
    assert _sentence(package_half) == _sentence(document_half), (
        "the premise of this test is that the section says it twice; if that "
        "stops being true, the symmetry below is the wrong check")

    claimed_here = set(CLAIMED.get(package_half, ()))
    claimed_there = set(CLAIMED.get(document_half, ()))
    assert bool(claimed_here) == bool(claimed_there), (
        "%s is claimed by %s and the identical %s by %s"
        % (package_half, sorted(claimed_here) or "nobody",
           document_half, sorted(claimed_there) or "nobody"))


#: How a statement about a claim's status can be written so the gate above
#: misses it. Each is a real sentence, placed or worded a way the first
#: version of the gate let through; the control is the same sentence in
#: ordinary prose, which it catches.
#:
#: The first two hide *inside* the regions the gate cuts out. Cutting out was
#: the fix for a filtering bug, and it brought its own: a region that ends at
#: the first blank line ends wherever the author stops pressing return, so a
#: line appended to the table with no blank line before it is inside the
#: table as far as the regex is concerned. The third is the verb list, which
#: is closed and therefore a list of the phrasings somebody thought of.
GATE_EVASIONS = {
    "a row appended to the leniency table that is not a row": (
        "| B6 | **a spelling** — the extension is compared case-insensitively, "
        "so `.XHTML` passes where B.3 writes `.xhtml` | kept |",
        "\n| M17 no longer claims x6-7-1-component-trees-in-the-package#1. |"),
    "an obligation id whose prefix the gate was not told about": (
        "| B6 | **a spelling** — the extension is compared case-insensitively, "
        "so `.XHTML` passes where B.3 writes `.xhtml` | kept |",
        "\n\nM13.1 no longer claims rdfrelations_core_has-start-selector#1."),
    "the rule and the obligation more than a window apart": (
        "| B6 | **a spelling** — the extension is compared case-insensitively, "
        "so `.XHTML` passes where B.3 writes `.xhtml` | kept |",
        "\n\nM17 " + "padding words " * 20
        + "x6-7-1-component-trees-in-the-package#1."),
    "appended to the leniency table with no blank line": (
        "| B6 | **a spelling** — the extension is compared case-insensitively, "
        "so `.XHTML` passes where B.3 writes `.xhtml` | kept |",
        "\nM17 no longer claims x6-7-1-component-trees-in-the-package#1."),
    "another verb for the same statement": (
        "| B6 | **a spelling** — the extension is compared case-insensitively, "
        "so `.XHTML` passes where B.3 writes `.xhtml` | kept |",
        "\n\nM17 no longer covers x6-7-1-component-trees-in-the-package#1."),
    "the statement in the passive": (
        "| B6 | **a spelling** — the extension is compared case-insensitively, "
        "so `.XHTML` passes where B.3 writes `.xhtml` | kept |",
        "\n\nThe claim on x6-7-1-component-trees-in-the-package#1 was given up by M17."),
}


def _restates(text):
    """The gate's own reading, over a text rather than over the file."""
    return [" ".join(para.split())[:90]
            for para in PARAGRAPH.split(_without_the_cut_regions(text))
            if A_RULE_ID.search(para) and AN_OBLIGATION_ID.search(para)]


def test_the_control_is_caught():
    """Before asserting that the evasions are caught, that the gate catches
    anything: the same sentence in plain prose, away from every cut region."""
    text = (ROOT / "docs" / "divergences.md").read_text("utf-8")
    assert _restates(text) == []
    assert _restates(text + "\n\nM17 no longer claims x6-7-1-component-trees"
                            "-in-the-package#1.\n") != []


@pytest.mark.parametrize("what", sorted(GATE_EVASIONS), ids=sorted(GATE_EVASIONS))
def test_a_statement_about_a_claim_cannot_hide_from_the_gate(what):
    anchor, addition = GATE_EVASIONS[what]
    text = (ROOT / "docs" / "divergences.md").read_text("utf-8")
    assert anchor in text, "the fixture edit matched nothing: %s" % what
    assert _restates(text.replace(anchor, anchor + addition, 1)) != [], what


def test_a_withdrawal_that_went_elsewhere_says_where():
    """`WITHDRAWN_ELSEWHERE` exempts a leniency row from having to carry a
    refusal comment, on the grounds that the sentence went to another rule
    rather than becoming a gap. As a bare set of rule ids it asserted nothing:
    the grounds lived in a comment, and a comment is what the guard beside it
    exists to stop trusting -- the same shape as the row it was added to fix.

    So it names the sentence and the rule that took it, and both halves are
    read: the exempted rule must not claim the sentence, and the rule named
    must. If the sentence is withdrawn from that rule too, this fails and the
    row goes back to needing a refusal comment.
    """
    by_id = {rule.id: rule for rule in all_rules()}
    assert WITHDRAWN_ELSEWHERE, "an empty exemption is one nobody needs"
    for rule_id, (requirement, took_it) in sorted(WITHDRAWN_ELSEWHERE.items()):
        assert rule_id in by_id, rule_id
        assert took_it in by_id, took_it
        assert requirement not in (by_id[rule_id].covers or ()), (
            "%s is exempt because %s claims %s, but %s claims it too"
            % (rule_id, took_it, requirement, rule_id))
        assert requirement in (by_id[took_it].covers or ()), (
            "%s is exempt because %s was said to have taken %s, and %s does "
            "not claim it -- so the sentence is a gap, not a move"
            % (rule_id, took_it, requirement, took_it))


def test_a_claim_is_held_by_every_case_of_its_test_not_by_one():
    """The repair that only reached one of the two buckets.

    `tools/held_claims.py` was taught to check COUNTEREXAMPLES case by case
    and went on checking NAMED_CASES by function name, which counts a
    parametrised case list as held when any one row of it passed. Skipping
    twenty-six of appendix B's twenty-seven cases left the tool printing "42
    claims held" and exiting 0 with nine sentences standing on nothing.

    Asked of the tool with a record of its own rather than of the live one, so
    the property is checked and not the state of somebody's last run.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import held_claims

    assert NAMED_CASES, "no named case at all"

    a_name = "test_appendix_b_claims::" \
             "test_every_way_of_breaking_an_appendix_b_sentence_is_reported"
    collected = {a_name + "[one]", a_name + "[two]", a_name + "[three]"}
    keys = held_claims.keys_per_claim(gate=sys.modules[__name__], collected=collected)

    appendix = [wanted for requirement, wanted in keys.items()
                if any(k.startswith(a_name) for k in wanted)]
    assert appendix, "the appendix B claims stopped naming that test"
    for wanted in appendix:
        assert wanted == collected, (
            "a claim held by a parametrised test must want every case that "
            "ran under it: %s" % sorted(wanted))

    for requirement, wanted in keys.items():
        assert wanted, "%s is held by an empty set of cases" % requirement
