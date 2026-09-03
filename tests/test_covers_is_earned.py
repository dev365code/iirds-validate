"""A `covers=` claim is earned by a package, not by a reading.

`docs/scope.md` publishes "coverage of the standard is N of 280". A reader
takes that to mean: for each of those N sentences, a package that breaks it
gets a finding. Until this file existed, nothing checked that. Claims were
added by reading a sentence and a rule side by side and judging them to be
about the same thing, and the only mechanical gate on them --
`test_a_rule_and_the_requirement_it_claims_are_about_the_same_thing` --
skips any requirement whose subject is not a qualified name, which is 78 of
the 80 claims. It asserted nothing about them and read like a gate over all.

Seven claims failed that criterion, and each failed it in silence:

  * three sentences of section 8.3.2 ask for a `vcard:Organization`, and the
    rules deliberately did not check the class, so a card typed
    `vcard:Individual` broke all three and the package passed;
  * one of those three was claimed by a rule that stays quiet in exactly the
    case its partner rule exists to report, and the partner did not claim it;
  * section 6.8.2's sentence names a class and a property, and the rule
    counted the property only -- while the identically shaped sentence one
    section later had two rules, one for each half;
  * section 6.7.2's obligation begins "If an external product ontology is
    ... used", and the rule triggers on an iiRDS-internal relation instead;
  * section 6.9.1 binds every node in a list level, and the rule exempts
    roots -- which `docs/divergences.md` said, in those words, before the
    claim was added over it.

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
    ],
    "x8-3-2-metadata-requirements#12": [
        ("a product variant's ProductType domain names a manufacturer whose "
         "vcard is typed vcard:Individual", "individual"),
        ("...whose vcard carries no vcard class at all", "untyped"),
        ("...whose vcard the package never describes", "undescribed"),
    ],
    "x8-3-2-metadata-requirements#13": [
        ("an information object's identity domain names a creator whose vcard "
         "is typed vcard:Individual", "individual"),
        ("...whose vcard carries no vcard class at all", "untyped"),
        ("...whose vcard the package never describes", "undescribed"),
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
    assert claimants, requirement
    report = runner.run(_package(tmp_path, "%s.iirds" % kind, _handover(kind)),
                        runner.ALL_KINDS)
    got = {f.rule.id for f in report.findings}
    assert claimants & got, (
        "%s: %s, and no rule claiming it fired (claimed by %s; fired: %s)"
        % (requirement, what, sorted(claimants), sorted(got)))


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

    wrong_type = fired(tmp_path, "lifecycle_wrong_type.iirds", metadata=toc("""
  <iirds:ContentLifeCycleStatus rdf:about="urn:test:status">
    <iirds:has-content-lifecycle-status-value rdf:resource="urn:test:notavalue"/>
  </iirds:ContentLifeCycleStatus>
  <iirds:Topic rdf:about="urn:test:notavalue">
    <iirds:title>not a status value</iirds:title>
  </iirds:Topic>"""))
    assert claimants & wrong_type, (
        "the property points at something that is not a status value",
        sorted(wrong_type))


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
    "b-3-conformance-criteria#2", "b-3-conformance-criteria#4",
    "b-3-conformance-criteria#5", "b-5-10-forms#1",
    "b-5-11-svg-mathml-and-iframes#1", "b-5-2-document-metadata#1",
    "b-5-7-scripting#1", "b-6-additional-semantic-tagging-of-content#5",
    "b-6-additional-semantic-tagging-of-content#6", "dfn-iirds-container#1",
    "dfn-iirds-package#1", "dfn-iirds-zip-archive#2",
    "dfn-iirds-zip-archive#3", "dfn-iirds-zip-archive#4",
    "dfn-iirds-zip-archive#5", "dfn-iirds-zip-archive#6",
    "rdfclasses_core_ClassificationType#1",
    "rdfclasses_handover_DocumentCategory#1",
    "x5-1-1-metadata-location-and-rdf-serializations#1",
    "x5-1-1-metadata-location-and-rdf-serializations#2",
    "x5-1-1-metadata-location-and-rdf-serializations#4",
    "x5-1-2-content-location#1", "x5-1-2-content-location#2",
    "x5-1-3-names-of-files-and-directories#2",
    "x5-1-3-names-of-files-and-directories#3", "x5-2-2-content-encoding#1",
    "x5-2-2-content-encoding#2", "x5-3-nested-iirds-packages#3",
    "x6-12-rdf-serialization#1", "x6-12-rdf-serialization#3",
    "x6-2-2-information-objects#2", "x6-2-information-units#1",
    "x6-2-information-units#2", "x6-2-information-units#3",
    "x6-2-information-units#4", "x6-2-information-units#5",
    "x6-2-information-units#7", "x6-3-1-reference-part-of-file-by-selector#1",
    "x6-3-1-reference-part-of-file-by-selector#2",
    "x6-3-3-metadata-of-nested-iirds-packages#2",
    "x6-3-3-metadata-of-nested-iirds-packages#4",
    "x6-3-content-references-of-information-units#2",
    "x6-3-content-references-of-information-units#3",
    "x6-3-content-references-of-information-units#4",
    "x6-3-content-references-of-information-units#5",
    "x6-7-3-packages-related-to-component-trees#5",
    "x6-8-1-complex-identity#2", "x6-8-1-complex-identity#3",
    "x6-8-3-parties-and-roles#3", "x6-8-4-external-classification#4",
    "x6-8-4-external-classification#7", "x6-9-1-directory-nodes#5",
    "x6-9-2-hierarchical-navigation#1", "x6-9-2-hierarchical-navigation#2",
    "x8-3-1-1-mandatory-content-list#1", "x8-3-1-1-mandatory-content-list#2",
    "x8-3-1-2-nesting-of-packages#2",
    "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#1",
    "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#4",
    "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#6",
    "x8-3-2-metadata-requirements#11", "x8-3-2-metadata-requirements#8",
))


def test_every_claim_is_either_held_by_a_package_or_named_as_unaudited():
    """No third category. A claim that is neither evidenced nor listed is a
    claim nobody decided about, which is how all seven arrived."""
    held = set(COUNTEREXAMPLES) | {
        "x6-8-2-content-lifecycle-status#2", "x6-8-3-parties-and-roles#2",
        "x7-1-iirds-extension-scenarios#5"}
    unexplained = sorted(set(CLAIMED) - held - UNAUDITED)
    assert unexplained == [], (
        "claimed with neither a counterexample nor a place in UNAUDITED: %s" % unexplained)
    stale = sorted(UNAUDITED - set(CLAIMED))
    assert stale == [], "listed as unaudited but no longer claimed: %s" % stale
    assert sorted(UNAUDITED & held) == [], "both audited and listed as unaudited"


def test_the_audited_share_is_what_the_scope_document_publishes():
    """Two numbers, and the second is the one a reader should weigh. Pinned
    together so raising the first without raising the second is an edit
    somebody had to make on purpose."""
    scope = (ROOT / "docs" / "scope.md").read_text("utf-8")
    assert len(CLAIMED) == 68, len(CLAIMED)
    assert len(UNAUDITED) == 62, len(UNAUDITED)
    assert "**Coverage of the standard is 68 of 280.**" in scope
    assert "6 of the 68 are held by a\n   package" in scope, \
        "docs/scope.md no longer states how many claims are evidenced"


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
REFUSALS_EXPECTED = 5     # M13.1, M13.2, M17, M18, M25


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
    found = sorted(refusals())
    assert len(found) == REFUSALS_EXPECTED, found
    for rule_id, requirement in found:
        rule = next((r for r in all_rules() if r.id == rule_id), None)
        assert rule is not None, "%s: no such rule" % rule_id
        assert requirement not in rule.covers, (
            "%s says it does not claim %s and claims it" % (rule_id, requirement))


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
