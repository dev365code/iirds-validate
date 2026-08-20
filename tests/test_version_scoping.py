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
    "M96.1": (("1.2", "1.3"), "iirds:ExternalClassification arrives in 1.2"),
    "M96.2": (("1.2", "1.3"), "iirds:classificationIdentifier arrives in 1.2"),
    "M96.3": (("1.2", "1.3"), "iirds:classificationIdentifier arrives in 1.2"),
    "M97.1": (("1.2", "1.3"), "iirds:ClassificationDomain arrives in 1.2"),
    "M97.2": (("1.2", "1.3"), "iirds:ClassificationDomain arrives in 1.2"),
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


def test_every_handover_rule_is_1_3_only_and_they_are_all_m15():
    assert HANDOVER, "iiRDS/H rules must exist"
    assert all(r.startswith("M15.") for r in HANDOVER), sorted(HANDOVER)


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
    claim -- `iirdsv rules` says the rule applies where it cannot.

    Five rules were in that state, all naming the external classification
    vocabulary that arrives in 1.2 while the catalogue dated them from 1.0.
    """
    import json

    from version_inventory import terms_named_by

    data = json.loads((ROOT / "docs" / "version-terms.json").read_text("utf-8"))
    inventory = {k: set(v) for k, v in data["terms"].items()}

    problems = []
    for rule in all_rules():
        named = terms_named_by(rule)
        for version in rule.versions or ():
            if version in inventory:
                absent = [t for t in named if t not in inventory[version]]
                if absent:
                    problems.append((rule.id, version, sorted(absent)))
    assert problems == []


def test_the_versions_with_no_inventory_are_named_rather_than_ignored():
    """1.0 and 1.0.1 have no tagged ontology, so nothing is checked against
    them. "Not checked" and "checked and clean" must not look the same."""
    import json

    data = json.loads((ROOT / "docs" / "version-terms.json").read_text("utf-8"))
    assert data["_unavailable"] == ["1.0", "1.0.1"]
    assert set(data["terms"]) == {"1.1", "1.2", "1.3"}
