"""The map from the standard to the rules, as far as it goes.

`docs/requirements.json` enumerates what iiRDS requires: 314 parsed absolute
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
import pathlib
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
    assert len(COVERED) == 25
    assert len(ABSOLUTE) == 314
    assert INDEX["reductions"]["distinct"] == 280, "the published denominator"


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


def test_a_sentence_no_single_container_can_decide_is_recorded_apart():
    """A second excuse list, kept separate because it excuses something else.
    NOT_ABOUT_THE_PACKAGE holds obligations addressed to reading applications:
    no artefact can satisfy or breach them. This one holds obligations that
    are squarely about the package and that a validator reading one container
    cannot decide, because deciding them means knowing something the container
    does not carry.

    Two lists rather than one, because merging them would let "hard to check"
    hide inside "not about the package", and that is the excuse this project
    said it would not make."""
    from iirds_validate.rules.requirements import NOT_ABOUT_THE_PACKAGE, NOT_DECIDABLE_ALONE

    assert set(NOT_ABOUT_THE_PACKAGE) & set(NOT_DECIDABLE_ALONE) == set()
    assert COVERED & set(NOT_DECIDABLE_ALONE) == set()
    for rid, reason in NOT_DECIDABLE_ALONE.items():
        assert rid in BY_ID, rid
        assert rid in ABSOLUTE, rid
        assert len(reason) > 40, rid


def test_the_undecidable_sentence_is_the_nested_package_one():
    """Named rather than counted, because a list whose only gate is its size
    can be filled with anything. This is the sentence: a nested package must
    not carry metadata about the outer one. Its antecedent follows from section 6.2 --
    a conformant child's own iirds:Package carries no is-part-of-package at
    all -- so the only evidence that this container is the nested one is the
    breach being looked for."""
    from iirds_validate.rules.requirements import NOT_DECIDABLE_ALONE

    assert sorted(NOT_DECIDABLE_ALONE) == ["x5-3-nested-iirds-packages#2"]


#: Chapter five obligations nothing checks, each with what it would take.
CHAPTER_FIVE_GAPS = {
    # "If metadata is provided in the JSON-LD 1.1 syntax, the META-INF
    # directory MUST contain the file metadata.jsonld." C16.2 claimed this and
    # does not check it: it asks whether an iiRDS/H package has the file and
    # whether the file parses, and the reader opens two fixed paths, so a
    # package carrying JSON-LD metadata at META-INF/metadata.json is read by
    # nothing and reported by nothing -- built and run, it passes clean. What
    # would close it is a rule about the other files in META-INF, and section
    # 5.1.1 recommends consumers ignore them, so the reading wants settling
    # before a rule is written.
    "x5-1-1-metadata-location-and-rdf-serializations#3",
}


def test_chapter_five_is_mapped_apart_from_its_gaps():
    """The first section taken end to end. 21 obligations: most have a rule,
    two are addressed to consumers, one cannot be decided by anything holding
    a single container, and the rest are named above.

    Pinned so a gap cannot be closed by accident or opened by one.
    """
    from iirds_validate.rules.requirements import NOT_ABOUT_THE_PACKAGE, NOT_DECIDABLE_ALONE

    chapter = [r for r in INDEX["requirements"]
               if r["absolute"] and r["section"].startswith("x5")]
    assert len(chapter) == 21

    gaps = sorted(r["id"] for r in chapter
                  if r["id"] not in COVERED and r["id"] not in NOT_ABOUT_THE_PACKAGE
                  and r["id"] not in NOT_DECIDABLE_ALONE)
    assert gaps == sorted(CHAPTER_FIVE_GAPS), \
        "the single-root requirement is R3, the outer-must-not-describe-the-child " \
        "prohibition is R6, one is recorded as undecidable, and the rest are named here"


def test_the_scope_document_publishes_the_coverage_it_has():
    """docs/scope.md leads with the coverage figure, and it is the number a
    reader is most likely to quote. It moved by hand when a rule last claimed
    a requirement and it had already drifted once -- the covers map said 20
    while the sentence still said 19."""
    import pathlib
    import re

    scope = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "scope.md").read_text("utf-8")
    found = re.search(r"\*\*Coverage of the standard is (\d+) of (\d+)\.\*\*", scope)
    assert found, "docs/scope.md no longer states coverage in the expected shape"
    assert int(found.group(1)) == len(COVERED), (
        "docs/scope.md says %s requirements are covered and the rules claim %d"
        % (found.group(1), len(COVERED)))
    # The distinct count, not the parse: the parse counts one obligation twice
    # in two derived ways, and the published denominator is the honest one.
    assert int(found.group(2)) == INDEX["reductions"]["distinct"], (
        "docs/scope.md says %s absolute requirements and the index has %d distinct"
        % (found.group(2), INDEX["reductions"]["distinct"]))


def test_the_scope_document_counts_the_excused_obligations_correctly():
    """The sentence shipped saying "Two obligations" and then listed two and
    one. A count written in words is not read by the gate that reads the
    coverage figure beside it, which is how it got out; this reads it."""
    import pathlib
    import re

    from iirds_validate.rules.requirements import NOT_ABOUT_THE_PACKAGE, NOT_DECIDABLE_ALONE

    words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}
    total = len(NOT_ABOUT_THE_PACKAGE) + len(NOT_DECIDABLE_ALONE)
    scope = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "scope.md").read_text("utf-8")

    m = re.search(r"^\s*(\w+) obligations sit outside the numerator", scope, re.M)
    assert m, "docs/scope.md no longer counts the excused obligations"
    assert m.group(1) == words[total], \
        "docs/scope.md says %s and the two lists hold %d" % (m.group(1), total)
    assert words[len(NOT_ABOUT_THE_PACKAGE)] + " are addressed to reading" in scope


def test_the_published_command_reports_both_excuse_lists():
    """docs/scope.md points a reader at tools/requirement_coverage.py and says
    both lists are there. The tool knew one of them: it went on printing the
    undecidable sentence as an unmapped gap while the documents beside it
    called the same id excused, so the two disagreed in public."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "tools/requirement_coverage.py",
         "--section", "x5-3-nested-iirds-packages"],
        cwd=str(pathlib.Path(__file__).resolve().parents[1]),
        capture_output=True, text=True, check=True).stdout

    assert "cannot be decided by anything holding one container" in out, out
    assert "x5-3-nested-iirds-packages#2" not in out, \
        "the excused sentence is still printed as an unmapped gap:\n%s" % out
