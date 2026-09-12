"""The corpus and the catalogue must come from the same upstream revision.

`extract_catalog.py` pins a commit, and its own docstring says why: regenerating
against a moved `master` would silently produce a different file. That reasoning
was never applied to `crossvalidate.py`, which fetched `master` -- so the rules
were pinned and the fixtures that validate them were not, and the two could
already be from different revisions of the same repository with nothing saying
so.

Every cross-validation number in the project rests on that pairing: the 64/66
in docs/divergences.md, the silence classification, the "0 unexplained" claim.
All of them were computed against a moving input.
"""
from __future__ import annotations

import re
import sys

import pytest

import crossvalidate
import extract_catalog
from iirds_validate.registry import PROVENANCE

#: A full git object name. A branch or tag would reintroduce the defect while
#: looking like a fix -- `master` is a ref too.
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def test_the_catalogue_records_the_commit_it_came_from():
    assert COMMIT.match(PROVENANCE["_commit"]), PROVENANCE["_commit"]


def test_the_corpus_is_fetched_at_the_catalogue_s_commit():
    assert PROVENANCE["_commit"] == crossvalidate.REF


def test_the_pin_in_the_script_is_the_commit_in_the_file():
    """Two records of one fact, and nothing compared them.

    `--ref` regenerates against another revision; committing that file without
    moving `DEFAULT_REF` leaves the script pinning one commit and the catalogue
    carrying another, and every sentence resting on provenance names whichever
    of the two its author happened to read.
    """
    assert PROVENANCE["_commit"] == extract_catalog.DEFAULT_REF


def test_asking_which_commit_it_came_from_fetches_nothing(monkeypatch, capsys):
    """The front page quotes this command, so it runs where the front page is
    gated -- in CI's lint job, which is not allowed the network. `--check`, the
    flag beside it, fetches three files; this one may not touch `fetch` at all.
    """
    def refuse(*args, **kwargs):
        raise AssertionError("--pin reached for the network")

    monkeypatch.setattr(extract_catalog, "fetch", refuse)
    monkeypatch.setattr(sys, "argv", ["extract_catalog.py", "--pin"])
    assert extract_catalog.main() == 0
    assert PROVENANCE["_commit"] in capsys.readouterr().out


def test_a_catalogue_from_another_commit_than_the_pin_is_a_failure(monkeypatch, capsys):
    """What `--pin` is for. The front page quotes its output as provenance, so
    it has to be the file's own answer and not the script's opinion of it."""
    monkeypatch.setattr(extract_catalog, "fetch",
                        lambda *a, **k: pytest.fail("--pin reached for the network"))
    monkeypatch.setattr(sys, "argv", ["extract_catalog.py", "--pin", "--ref", "0" * 40])
    assert extract_catalog.main() == 1
    assert "the pin says" in capsys.readouterr().err


def test_no_url_reaches_for_a_moving_ref():
    """The literal that caused this. Both the tree listing and the raw file
    URLs carried `master`, so pinning one of them would have fixed half of it.
    """
    for url in (crossvalidate.API, crossvalidate.RAW):
        assert PROVENANCE["_commit"] in url, url
        assert "/master/" not in url and "master?" not in url, url


def test_the_cache_is_partitioned_by_revision(tmp_path):
    """Fixtures were cached under their bare filename, so changing the ref
    would silently reuse files fetched from the previous one -- the same
    disease one layer down, and the one that would survive the fix above.
    """
    first = crossvalidate.cache_dir(tmp_path, "0" * 40)
    second = crossvalidate.cache_dir(tmp_path, "1" * 40)
    assert first != second
    assert first.is_relative_to(tmp_path) and second.is_relative_to(tmp_path)


#: Pairs where this project reports a finding on a fixture the catalogue marks
#: as passing, each with the argument for it. Empty is the honest state today
#: and was not the state before 2026-09-03: two `extra` pairs sat in
#: `docs/agreement.json` for months, both M15.10 against a passing handover
#: fixture, and both were this project's error -- the rule asked an
#: information object for a party section 8.3.2 hangs on its identity domain.
#:
#: The classifier saw it every run. Nothing failed, because the number was
#: recorded rather than answered. A finding on a fixture the reference passes
#: is either a defect the reference misses, which has to be argued in
#: docs/divergences.md, or a defect of ours; it is never a figure to carry.
ARGUED_EXTRA: dict = {}


def test_a_finding_on_a_passing_fixture_is_argued_or_it_is_a_bug():
    """The gate the two M15.10 pairs never met.

    Adding one means writing down why this project is right and the reference
    wrong, in the same commit, beside the rule id and the fixture it fires on.
    """
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    agreement = json.loads((root / "docs" / "agreement.json").read_text("utf-8"))
    extra = sorted(pair for pair, verdict in agreement.get("verdicts", {}).items()
                   if verdict == "extra")
    assert extra == sorted(ARGUED_EXTRA), (
        "these fire on fixtures the catalogue says pass and nothing argues for them: %s"
        % [p for p in extra if p not in ARGUED_EXTRA])
    for pair, reason in ARGUED_EXTRA.items():
        rule_id = pair.split("|", 1)[0]
        divergences = (root / "docs" / "divergences.md").read_text("utf-8")
        assert rule_id in divergences, (pair, "argued here but not in docs/divergences.md")
        assert len(reason) > 40, (pair, "the argument is the point")
