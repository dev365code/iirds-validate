"""The specification's normative statements, enumerated and kept honest.

For months the README asserted that iiRDS states "254 absolute requirements".
`grep -rn 254` returned one hit: that sentence. No script, no data, no way for
anyone to arrive at the number again -- the same species of unsourced claim
this project objects to in validators, one level up.

The number is now derived by `tools/extract_requirements.py`, and deriving it
showed it was wrong. Not the arithmetic: the scope.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import extract_requirements as extractor

ROOT = Path(__file__).resolve().parents[1]
INDEX = json.loads((ROOT / "docs" / "requirements.json").read_text("utf-8"))
REQUIREMENTS = INDEX["requirements"]


def test_the_index_is_for_the_release_the_tool_targets():
    assert INDEX["_release"] == extractor.RELEASE


def test_the_rfc2119_count_is_the_254_the_readme_used_to_quote():
    """It was right about what it counted. Keeping the figure visible means a
    change in the extractor that moves it cannot pass as a rounding."""
    marked = sum(INDEX["counts"].get(k, 0) for k in extractor.ABSOLUTE)
    assert marked == 254


def test_the_specification_also_states_obligations_with_no_keyword_at_all():
    """Sixty rows of the property tables read `0..1 iirds:dateOfEffect property
    - xsd:dateTimeStamp` and carry no RFC 2119 word. They are obligations: "at
    most one" is a MUST NOT have two, and M2.3 to M2.9, M21.2 to M21.6, M24.1
    to M24.4 and M95 exist to enforce exactly these.

    So a count of marked keywords understates the standard. The two sets are
    disjoint -- not one of the sixty rows contains a marker -- which is why
    taking either alone gives a wrong denominator.
    """
    assert INDEX["counts"]["0..1"] == 60
    assert INDEX["absolute"] == 314
    # and what the parse counts twice, derived rather than assumed: the
    # sentence that defines the RFC 2119 keywords, and appendix A's overview
    # restating each cardinality the class tables already give.
    reductions = INDEX["reductions"]
    assert len(reductions["keyword_definition"]) == 4
    assert len(reductions["restated_in_the_overview"]) == 30
    assert reductions["distinct"] == 280

    cardinality = [r for r in REQUIREMENTS if r["stated_as"] == "cardinality"]
    marked = [r for r in REQUIREMENTS if r["stated_as"] == "rfc2119"]
    assert len(cardinality) == 60
    assert all(r["keyword"] != "0..1" for r in marked)


def test_every_requirement_can_be_found_again_by_a_person():
    """An index whose entries cannot be located in the document is a list of
    sentences, not a map."""
    for requirement in REQUIREMENTS:
        assert requirement["section"] or requirement["subject_anchor"], requirement["id"]
        assert requirement["sentence"].strip(), requirement["id"]


def test_the_ids_are_unique_and_scoped_to_the_narrowest_anchor():
    """Appendix A repeats "IRI: REQUIRED" for every class, so a section-scoped
    id cannot tell sixty of them apart. Scoping to the <dfn> also means adding
    a class does not renumber every requirement after it."""
    ids = [r["id"] for r in REQUIREMENTS]
    assert len(set(ids)) == len(ids)

    appendix = [r for r in REQUIREMENTS if r["subject_anchor"]]
    assert len(appendix) >= 100
    assert all(r["id"].startswith(r["subject_anchor"]) for r in appendix)


def test_no_requirement_was_taken_from_a_note_or_an_example():
    """The specification puts those in <aside>. None is normative, and if that
    ever changes the count must not move without somebody noticing."""
    assert [r["id"] for r in REQUIREMENTS if r["in_aside"]] == []


def test_a_table_requirement_carries_the_row_it_came_from():
    """A cardinality table states its obligation across a row: the label in one
    cell, the word in the next. A cell alone reads "REQUIRED" and says nothing,
    and 129 of the 439 statements are cells."""
    cells = [r for r in REQUIREMENTS if r["block"] in ("td", "th")]
    assert len(cells) >= 120
    assert all(r["row_label"] or r["stated_as"] == "cardinality" for r in cells)
    assert all(r["subject"] for r in cells)


def spec_cache_or_skip():
    """The cached specification, or a skip -- unless this run was told it must
    have it.

    The specification is not redistributable, so `.spec-cache/` is ignored and
    CI has no copy: everything below can only run where somebody fetched one.
    Under `make` the absence is a failure, because `make check` is what claims
    to have checked the tree, and the checks it turns off here are the only
    ones that hold the published index to the document it was read from.
    """
    cache = ROOT / ".spec-cache" / ("%s.html" % extractor.RELEASE)
    if cache.exists():
        return cache
    if os.environ.get("IIRDS_REQUIRE_SPEC_CACHE"):
        raise AssertionError(
            "IIRDS_REQUIRE_SPEC_CACHE is set and %s is not here, so the index "
            "cannot be held to its source; run "
            "`python tools/extract_requirements.py --refresh`" % cache)
    pytest.skip("no cached specification; run --refresh")


def test_the_extractor_agrees_with_the_committed_index():
    """Re-derived from the cached specification, so a change to the parser that
    silently moves the count fails here rather than in a document.

    Every field, not the ids and the counts. Those were all this compared, and
    a sentence rewritten by hand in the committed index passed the whole suite
    -- which is exactly what the fingerprint test below says it exists to
    stop, and did not. The index is the enumeration the coverage figure is a
    fraction of and the thing every `covers=` claim points at, so a wrong
    sentence there misattributes an obligation rather than merely reading
    badly."""
    cache = spec_cache_or_skip()
    rebuilt = extractor.build(cache.read_text("utf-8"))
    assert rebuilt["counts"] == INDEX["counts"]
    assert rebuilt["absolute"] == INDEX["absolute"]
    assert rebuilt["requirements"] == REQUIREMENTS, next(
        (a["id"] for a, b in zip(rebuilt["requirements"], REQUIREMENTS) if a != b),
        "the two lists are different lengths")


def test_a_definition_scope_never_crosses_a_section():
    """The defect this index shipped with: the extractor carried the last
    <dfn> forward for ever, so a third of the statements — Party rules from
    §6.8, serialization rules from §6.12 — were filed under
    `dfn-iirds-zip-archive#N`, ids that look like spec anchors and point at
    the wrong definition. A heading now closes the scope, and this holds it
    closed: every requirement filed under a definition sits in the section
    where that definition was made.
    """
    section_of = {}
    for requirement in REQUIREMENTS:
        anchor = requirement["subject_anchor"]
        if not anchor:
            continue
        section_of.setdefault(anchor, requirement["section"])
        assert requirement["section"] == section_of[anchor], \
            "%s is scoped to %s but sits in %s" % (
                requirement["id"], anchor, requirement["section"])


def test_the_index_records_the_fingerprint_of_its_source():
    """Counts alone would let a hand-edited sentence pass the offline check."""
    assert len(INDEX["_source_sha256"]) == 64


def test_the_fingerprint_is_of_the_specification_on_disk():
    """The sentence above was the whole of this check: the digest was measured
    for length and compared with nothing. So the index could name a source it
    had not been built from, which is the one thing a fingerprint is for."""
    import hashlib

    cache = spec_cache_or_skip()
    got = hashlib.sha256(cache.read_text("utf-8").encode("utf-8")).hexdigest()
    assert got == INDEX["_source_sha256"], (
        "docs/requirements.json says it came from %s and the specification "
        "here hashes to %s" % (INDEX["_source_sha256"][:16], got[:16]))


# ---------------------------------------------------------------------------
# A sentence that is not a sentence
# ---------------------------------------------------------------------------

#: Where the specification's own text does not balance its parentheses, and
#: the quotation that says so. Section 5.1.3 closes a bracket it never opened:
#:
#:     Full path names (file names including the full directory path from the
#:     root) MUST NOT exceed 260 characters).
#:
#: The index is faithful there, so this is a list of one and it is a list
#: rather than a tolerance -- the next unbalanced sentence is a split that
#: went wrong until somebody writes down why it is not.
SPEC_DOES_NOT_BALANCE = {
    "x5-1-3-names-of-files-and-directories#3":
        "the specification writes '260 characters).' with a bracket it never opened",
}


def _flat(requirement) -> str:
    return " ".join(requirement["sentence"].split())


def test_no_sentence_is_a_fragment_of_one():
    """The index is the denominator of the published coverage figure *and* the
    text every `covers=` claim is judged against, so a sentence that is half a
    sentence cannot be judged at all: "does every package violating this
    sentence get reported" has no answer for "CSS, graphics, fonts) MUST be
    included in the iiRDS/A package."

    Unbalanced brackets are the signature. The splitter breaks on terminal
    punctuation followed by a capital, and an abbreviation inside a
    parenthesis -- `(e.g. CSS, ...)` -- looks exactly like the end of a
    sentence. Two rows arrived that way.
    """
    unbalanced = {r["id"]: _flat(r) for r in REQUIREMENTS
                  if _flat(r).count("(") != _flat(r).count(")")}
    unexplained = sorted(set(unbalanced) - set(SPEC_DOES_NOT_BALANCE))
    assert unexplained == [], (
        "a sentence whose brackets do not balance, and no note saying the "
        "specification's do not either: %s" % {k: unbalanced[k] for k in unexplained})
    stale = sorted(set(SPEC_DOES_NOT_BALANCE) - set(unbalanced))
    assert stale == [], "listed as unbalanced in the source and no longer is: %s" % stale


def test_no_sentence_begins_where_an_abbreviation_ended():
    """The general form, asked of the block rather than of the sentence.

    Unbalanced brackets catch the case where the split landed inside one. The
    other case leaves nothing behind to notice -- "A cryptographic hash
    function, e.g. SHA-256, MAY be used." splits into a half with no keyword,
    which is dropped, and "SHA-256, MAY be used.", which begins with a capital
    and reads like a sentence.

    But every row keeps the whole block it came from, so the question can be
    put to the data: does this sentence start immediately after an
    abbreviation in its own block? That is not a shape a sentence has; it is
    the fingerprint of the cut.
    """
    import re
    abbreviation = re.compile(
        r"(?:^|[\s(\[])(?:e\.g|i\.e|etc|cf|resp|vs|approx|Fig|No|Nos|ca)\.\s*$")
    cut = []
    for requirement in REQUIREMENTS:
        sentence, block = _flat(requirement), " ".join((requirement.get("context") or "").split())
        if not block or sentence == block:
            continue
        at = block.find(sentence)
        if at > 0 and abbreviation.search(block[:at]):
            cut.append(requirement["id"])
    assert sorted(cut) == [], sorted(cut)


#: The two the splitter had cut, with the whole sentence the specification
#: prints. Pinned verbatim rather than by shape: the repair is that these say
#: what the document says, and a shape test passes on a different mistake.
WHOLE_AGAIN = {
    "x8-2-1-2-graphics-formats#5":
        "All linked resources (e.g. CSS, graphics, fonts) MUST be included in "
        "the iiRDS/A package.",
    "x8-3-1-3-optional-checksums-for-packages#2":
        "A cryptographic hash function, e.g. SHA-256, MAY be used.",
}


@pytest.mark.parametrize("requirement_id,sentence", sorted(WHOLE_AGAIN.items()))
def test_the_two_that_were_cut_are_whole(requirement_id, sentence):
    found = [r for r in REQUIREMENTS if r["id"] == requirement_id]
    assert found, "%s is no longer in the index" % requirement_id
    assert _flat(found[0]) == sentence


def test_repairing_them_did_not_move_the_denominator():
    """Joining two halves back together adds no obligation and removes none:
    the half that carried the keyword was already counted, and the half that
    did not was never a row. If this moves, something other than a repair
    happened."""
    reduced = (set(INDEX["reductions"]["keyword_definition"])
               | set(INDEX["reductions"]["restated_in_the_overview"]))
    assert len([r for r in REQUIREMENTS
                if r["absolute"] and r["id"] not in reduced]) == 280
