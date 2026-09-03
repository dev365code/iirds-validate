"""Why four rules do not apply to every version, checked rather than inherited.

Every `versions` array in the catalogue came from the reference tool and none
had ever been checked against anything. Nineteen rules are scoped to less than
all versions: fifteen are the iiRDS/H profile, which arrived with 1.3 and could
not apply earlier. The other four are the interesting ones, and one of them
turns a rule off in the two most recent releases of the standard.

Pinned here because the failure mode is silent in both directions. A scoping
that is too narrow switches a MUST off for the versions people actually ship;
one that is too broad claims a rule applies where its vocabulary did not exist.
Neither produces a finding, a traceback, or any other sign.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.registry import all_rules
from iirds_validate.resources import read_text, version_terms

ROOT = Path(__file__).resolve().parents[1]
ALL_VERSIONS = ("1.0", "1.0.1", "1.1", "1.2", "1.3")
RULES = {r.id: r for r in all_rules()}

#: Every rule scoped to less than all versions, with the reason. A rule
#: appearing here without one, or disappearing from it, fails the test below.
SCOPED = {
    "M8":    (("1.1", "1.2", "1.3"),
              "the prohibition on the enclosing package carrying a rendition "
              "arrives in 1.1"),
    "M24.4": (("1.1", "1.2", "1.3"),
              "the cardinality on iirds:relates-to-information-unit arrives in 1.1"),
    "M16.1": (("1.0", "1.0.1", "1.1"),
              "relaxed from MUST to MAY: 1.3 reads 'Instances of the iirds:Event class "
              "MAY have the following properties'"),
    "M16.2": (("1.0", "1.0.1", "1.1"), "relaxed from MUST to MAY with M16.1"),
    "M49":   (("1.1", "1.2", "1.3"), "iirds:IdentityType arrives in 1.1 with the identity-type system"),
    "M76":   (("1.1", "1.2", "1.3"), "mch:ProtectiveEquipment arrives in 1.1"),
    "R5":    (("1.3",),
              "section 6.3.3 exists in the cached 1.3 and not in the cached 1.0; "
              "1.1 and 1.2 are not on hand, so 1.3 is the only edition this can "
              "claim the sentence for"),
    "R6":    (("1.3",),
              "section 5.3 has no nesting chapter in the cached 1.0 either, so the "
              "same edition limit as R5 and for the same reason"),
    "R8":    (("1.3",),
              "section 6.3.3 again, the sentence that puts the nested containers in "
              "the archive; the cached 1.0 has no nesting chapter"),
    "R9":    (("1.3",),
              "sections 8.3.1.2 and 6.7.3 are the handover profile's, and the string "
              "iiRDS/H does not occur in the cached 1.0 at all"),
    "M96.1": (("1.2", "1.3"), "iirds:ExternalClassification arrives in 1.2"),
    "M96.2": (("1.2", "1.3"), "iirds:classificationIdentifier arrives in 1.2"),
    "M96.3": (("1.2", "1.3"), "iirds:classificationIdentifier arrives in 1.2"),
    "M97.1": (("1.2", "1.3"), "iirds:ClassificationDomain arrives in 1.2"),
    "M97.2": (("1.2", "1.3"), "iirds:ClassificationDomain arrives in 1.2"),
    "R1":    (("1.2", "1.3"), "iirds:ClassificationType arrives in 1.2 with the rest of "
                              "the external classification vocabulary"),
    "R2":    (("1.3",), "iirdsHov:DocumentCategory is part of iiRDS/H, which arrives in 1.3"),
    "R4":    (("1.3",), "the vcard a party points at is an iiRDS/H requirement, and the "
                        "profile arrives in 1.3"),
}

#: iiRDS/H arrived with 1.3, so its rules cannot apply to anything earlier.
HANDOVER = {r.id for r in all_rules() if tuple(r.versions) == ("1.3",)}


def test_the_only_version_scoped_rules_are_the_ones_accounted_for():
    """A new scoping appearing without a reason is the thing this catches. It
    would otherwise be invisible: a rule that stops running on the versions
    people ship produces nothing at all."""
    scoped = {r.id for r in all_rules()
              if r.versions and tuple(r.versions) != ALL_VERSIONS}
    assert scoped == set(SCOPED) | HANDOVER


def test_every_1_3_only_rule_belongs_to_the_handover_profile():
    """iiRDS/H arrived with 1.3, so its rules cannot apply earlier. R2 is here
    for the same reason without an M15 identifier: it implements a
    specification requirement the catalogue has no id for, and R4 for the same
    reason again -- it owns the softening the five named-party MUSTs share."""
    assert HANDOVER, "iiRDS/H rules must exist"
    # By the profile the rule declares, not by the shape of its id. R13 to
    # R16 are section 8.3.2's Package list and carry variants=("H",); reading
    # the id would have made "belongs to the handover profile" mean "is
    # called M15-something", which is a different sentence.
    by_id = {rule.id: rule for rule in all_rules()}
    outside = sorted(r for r in HANDOVER
                     if "H" not in by_id[r].variants and r not in SCOPED)
    assert outside == [], outside


@pytest.mark.parametrize("rule_id", sorted(SCOPED), ids=sorted(SCOPED))
def test_the_scoping_is_what_was_verified(rule_id):
    assert tuple(RULES[rule_id].versions) == SCOPED[rule_id][0]


def _event_package(tmp_path, version):
    metadata = MINIMAL_RDF.replace(
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
        "<iirds:iiRDSVersion>%s</iirds:iiRDSVersion>" % version).replace("</rdf:RDF>", '''
  <iirds:Event rdf:about="urn:test:e1">
    <rdfs:label xml:lang="en">Overheat</rdfs:label>
  </iirds:Event>
</rdf:RDF>''')
    return build_package(tmp_path, "ev%s.iirds" % version.replace(".", "_"), metadata=metadata)


def test_an_event_with_no_code_is_a_defect_in_1_1_and_not_in_1_3(tmp_path):
    """The same package, two declared versions, two correct answers.

    This is the one scoping that switches a rule off for current releases, so
    it is asserted from both ends rather than trusted. iiRDS 1.0 to 1.1 said
    instances of iirds:Event MUST carry a code and a type; 1.3 says MAY. The
    reference tool's own spec link for these two rules points at the 1.3
    document, where the sentence reads MAY -- so a reader following it sees
    this validator apparently contradicting the standard. It does not; the
    link is to a later edition of a sentence that changed.
    """
    old = {f.rule.id for f in runner.check(_event_package(tmp_path, "1.1")).findings}
    assert {"M16.1", "M16.2"} <= old

    current = {f.rule.id for f in runner.check(_event_package(tmp_path, "1.3")).findings}
    assert not {"M16.1", "M16.2"} & current


def test_a_handover_rule_does_not_reach_back_into_earlier_versions(tmp_path):
    """iiRDS/H did not exist before 1.3, so a 1.2 package declaring the profile
    must not be measured against requirements the standard had not written."""
    metadata = MINIMAL_RDF.replace(
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
        "<iirds:iiRDSVersion>1.2</iirds:iiRDSVersion>"
        "<iirds:formatRestriction>H</iirds:formatRestriction>")
    report = runner.check(build_package(tmp_path, "h12.iirds", metadata=metadata))
    assert not {f.rule.id for f in report.findings} & HANDOVER


def test_no_rule_claims_a_version_whose_vocabulary_it_predates():
    """The check `tools/version_inventory.py` performs, run in the suite.

    A rule declaring itself applicable to a version in which its own class or
    property did not exist is wrong in a way that produces nothing at all: it
    runs, matches nothing, reports a clean package. What it corrupts is the
    claim -- `iirds rules` says the rule applies where it cannot.

    Five rules were in that state, all naming the external classification
    vocabulary that arrives in 1.2 while the catalogue dated them from 1.0.
    """
    from version_inventory import terms_named_by

    inventory = version_terms()

    problems = []
    for rule in all_rules():
        named = terms_named_by(rule)
        for version in rule.versions or ():
            if version in inventory:
                absent = [t for t in named if t not in inventory[version]]
                if absent:
                    problems.append((rule.id, version, sorted(absent)))
    assert problems == []


def test_every_published_edition_has_an_inventory():
    """This began with 1.0 and 1.0.1 in an "unavailable" list, because the
    GitHub tags carry only 1.1 and 1.2. The Consortium's own site publishes
    every edition's schema files, so the list is now empty — and the check
    still refuses to conflate "not checked" with "checked and clean" if an
    edition ever appears faster than its schemas do."""
    import json

    data = json.loads(read_text("version-terms.json"))
    assert data["_unavailable"] == []
    assert set(data["terms"]) == {"1.0", "1.0.1", "1.1", "1.2", "1.3"}
