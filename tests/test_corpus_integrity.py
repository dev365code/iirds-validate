"""The vendored corpus must still be upstream's bytes.

It is the only external check this project has. The moment a fixture here
differs from what plusmeta published, every cross-validation number becomes a
statement about a file we edited -- which is worth nothing, and worth less than
nothing because it would still look like evidence.

So the hashes are checked by the test suite rather than by a tool somebody
remembers to run, on every platform the matrix covers. Windows matters
particularly: end-of-line conversion on checkout would break the bytes without
touching the repository, which is the confusing way for this to fail.
"""
from __future__ import annotations

import json

import pytest

import vendor_corpus
from iirds_validate.registry import PROVENANCE

MANIFEST = json.loads(vendor_corpus.MANIFEST.read_text("utf-8"))
FILES = sorted(vendor_corpus.FILES.glob("*.rdf"))


def test_the_corpus_is_present():
    assert len(FILES) == len(MANIFEST["files"]) > 100


def test_it_came_from_the_same_revision_as_the_rules():
    """A corpus from one revision and a catalogue from another is the defect
    this vendoring exists to close, so it is asserted rather than assumed."""
    assert MANIFEST["_commit"] == PROVENANCE["_commit"]


def test_nothing_is_present_that_the_manifest_does_not_record():
    assert {p.name for p in FILES} == set(MANIFEST["files"])


@pytest.mark.parametrize("path", FILES, ids=[p.name for p in FILES])
def test_every_fixture_matches_its_recorded_hash(path):
    data = path.read_bytes()
    recorded = MANIFEST["files"][path.name]
    assert vendor_corpus.digest(data) == recorded["sha256"]
    assert len(data) == recorded["bytes"]


@pytest.mark.parametrize("path", FILES, ids=[p.name for p in FILES])
def test_the_recorded_classification_is_reproducible(path):
    """The manifest says of each file whether it parses, is a fragment needing
    a namespace wrapper, is malformed, or is empty. That judgement decides what
    docs/divergences.md may claim about a rule with no usable fixture, so it is
    recomputed here rather than trusted.
    """
    assert vendor_corpus.classify(path.read_bytes()) == MANIFEST["files"][path.name]["parses"]


def test_the_defect_lists_agree_with_the_per_file_verdicts():
    for bucket in ("zero_byte", "needs_namespace_wrapper", "malformed_xml"):
        derived = sorted(name for name, meta in MANIFEST["files"].items()
                         if meta["parses"] == bucket)
        assert MANIFEST[bucket] == derived, bucket


def test_the_defective_fixtures_are_named_rather_than_repaired():
    """Repairing one would replace upstream's bytes with our reading of what
    upstream meant, and contaminate the only oracle here that is not ours. The
    lists are non-empty because upstream's corpus is genuinely defective; if
    they ever empty out, somebody has been tidying.
    """
    assert MANIFEST["zero_byte"], "upstream has two zero-byte fixtures"
    assert MANIFEST["malformed_xml"], "upstream has malformed fixtures"
    for name in MANIFEST["zero_byte"]:
        assert (vendor_corpus.FILES / name).stat().st_size == 0


def test_the_licence_travels_with_the_files():
    """MIT requires the copyright notice and permission notice to accompany
    every copy. This is a copy."""
    licence = (vendor_corpus.CORPUS / "LICENSE").read_text("utf-8")
    assert "plusmeta GmbH" in licence
    assert "Permission is hereby granted, free of charge" in licence
