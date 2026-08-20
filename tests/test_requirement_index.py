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


def test_the_extractor_agrees_with_the_committed_index():
    """Re-derived from the cached specification, so a change to the parser that
    silently moves the count fails here rather than in a document."""
    cache = ROOT / ".spec-cache" / ("%s.html" % extractor.RELEASE)
    if not cache.exists():
        pytest.skip("no cached specification; run --refresh")
    rebuilt = extractor.build(cache.read_text("utf-8"))
    assert rebuilt["counts"] == INDEX["counts"]
    assert rebuilt["absolute"] == INDEX["absolute"]
    assert [r["id"] for r in rebuilt["requirements"]] == [r["id"] for r in REQUIREMENTS]
