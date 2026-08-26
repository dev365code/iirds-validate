"""The map from the standard to the rules, as far as it goes.

`docs/requirements.json` enumerates what iiRDS requires: 314 absolute
obligations. Rules declare, in `covers=`, which of them they implement. The
size of the union is the only honest coverage figure this project can quote,
and today it is small -- the enumeration is finished and the mapping has barely
started.

The point of measuring it now, while it is embarrassing, is that a number which
starts honest can be watched. "157 of 157 catalogued rules" was never
embarrassing and was never coverage of the standard either.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from iirds_validate.registry import all_rules

ROOT = Path(__file__).resolve().parents[1]
INDEX = json.loads((ROOT / "docs" / "requirements.json").read_text("utf-8"))
BY_ID = {r["id"]: r for r in INDEX["requirements"]}
ABSOLUTE = {r["id"] for r in INDEX["requirements"] if r["absolute"]}

CLAIMED = {rule.id: set(rule.covers) for rule in all_rules() if rule.covers}
COVERED = {rid for ids in CLAIMED.values() for rid in ids}


def test_every_claimed_requirement_exists_in_the_index():
    """A rule citing a requirement id that is not in the index is claiming to
    implement something nobody can look up, which is worse than claiming
    nothing."""
    unknown = sorted(rid for rid in COVERED if rid not in BY_ID)
    assert unknown == [], unknown


def test_every_claimed_requirement_is_an_obligation():
    """Covering a MAY is not coverage. If a rule enforces a permission, that is
    a divergence and belongs in docs/divergences.md, not in a coverage count."""
    permissions = sorted(rid for rid in COVERED if rid not in ABSOLUTE)
    assert permissions == [], permissions


@pytest.mark.parametrize("rule_id", sorted(CLAIMED), ids=sorted(CLAIMED))
def test_a_rule_and_the_requirement_it_claims_are_about_the_same_thing(rule_id):
    """A weak check, and the only mechanical one available: where a requirement
    names a class or property, the rule claiming it should mention that name.

    Restricted to subjects that are qualified names on purpose. Appendix A's
    subjects are terms -- `iirds:Topic` -- and a rule about them says so. In
    chapter 5 the nearest definition is the whole artefact, "iiRDS container",
    which every rule there is about and none repeats: L9 is titled for the two
    metadata files rather than for the container holding them, and that is the
    better title. Applying the heuristic there would only teach people to
    rename rules to satisfy it.

    It cannot tell a correct mapping from a plausible one either -- that is the
    reading problem no single reader can solve. It catches a citation pasted
    from the wrong row.
    """
    rule = next(r for r in all_rules() if r.id == rule_id)
    for rid in sorted(CLAIMED[rule_id]):
        subject = BY_ID[rid].get("subject") or ""
        if ":" not in subject:
            continue
        assert subject.split(":")[-1].lower() in rule.title.lower(), \
            "%s claims %s, which is about %s" % (rule_id, rid, subject)


def test_the_coverage_figure_is_what_is_published():
    """Pinned so it cannot drift downward unnoticed, and so raising it is a
    deliberate edit rather than a side effect."""
    assert len(COVERED) == 20
    assert len(ABSOLUTE) == 314


def test_no_rule_claims_a_requirement_twice_over():
    """Two rules may legitimately cover one requirement -- M22.1 and M22.2 come
    from a single sentence. One rule claiming the same id twice is a typo."""
    for rule in all_rules():
        assert len(rule.covers) == len(set(rule.covers)), rule.id


@pytest.mark.parametrize("rule_id,iri,version", [
    ("R1", "http://iirds.tekom.de/iirds#ClassificationType", "1.3"),
    ("R2", "http://iirds.tekom.de/iirds/domain/handover#DocumentCategory", "1.3"),
], ids=["R1", "R2"])
def test_the_rules_found_by_the_index_fire_on_what_they_are_about(rule_id, iri, version,
                                                                  tmp_path):
    """Both directions, because a rule that fires on the defect and also on the
    correct form is not checking what it claims to.

    These two exist because Appendix A states `IRI: REQUIRED` for 56 classes
    and the catalogue had rules for 54. Nobody could see the gap while coverage
    was measured against the catalogue rather than against the standard.
    """
    from conftest import MINIMAL_RDF, build_package
    from iirds_validate import runner

    def ids(about):
        metadata = MINIMAL_RDF.replace("</rdf:RDF>", '''
  <rdf:Description%s>
    <rdf:type rdf:resource="%s"/>
    <rdfs:label xml:lang="en">Anonymous</rdfs:label>
  </rdf:Description>
</rdf:RDF>''' % (about, iri))
        package = build_package(tmp_path, "%s%d.iirds" % (rule_id, len(about)),
                                metadata=metadata)
        return {f.rule.id for f in runner.check(package, version=version).findings}

    assert rule_id in ids("")
    assert rule_id not in ids(' rdf:about="urn:test:named"')


def test_requirements_excused_as_not_about_the_package_are_real_and_absolute():
    """The excuse list is the one place a coverage figure can be quietly
    inflated, so every entry has to name a requirement that exists, is an
    obligation, and carries a reason."""
    from iirds_validate.rules.requirements import NOT_ABOUT_THE_PACKAGE

    for rid, reason in NOT_ABOUT_THE_PACKAGE.items():
        assert rid in BY_ID, rid
        assert rid in ABSOLUTE, rid
        assert len(reason) > 40, rid


def test_nothing_is_both_covered_and_excused():
    """If a rule checks it, it is about the package, and the excuse is wrong."""
    from iirds_validate.rules.requirements import NOT_ABOUT_THE_PACKAGE

    assert COVERED & set(NOT_ABOUT_THE_PACKAGE) == set()


def test_chapter_five_is_mapped_apart_from_its_three_gaps():
    """The first section taken end to end. 21 obligations: 16 have a rule, two
    are addressed to consumers, and the rest are things this validator does not
    check and could. The single-root requirement became R3; what remains are
    the two prohibitions on what a nested package may say about its
    neighbours.

    Pinned so the gaps cannot be closed by accident or reopened by one.
    """
    from iirds_validate.rules.requirements import NOT_ABOUT_THE_PACKAGE

    chapter = [r for r in INDEX["requirements"]
               if r["absolute"] and r["section"].startswith("x5")]
    assert len(chapter) == 21

    gaps = sorted(r["id"] for r in chapter
                  if r["id"] not in COVERED and r["id"] not in NOT_ABOUT_THE_PACKAGE)
    assert gaps == ["x5-3-nested-iirds-packages#2", "x5-3-nested-iirds-packages#3"], \
        "the single-root requirement is R3; the two nested-package prohibitions remain"
