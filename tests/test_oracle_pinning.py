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

import crossvalidate
from iirds_validate.registry import PROVENANCE

#: A full git object name. A branch or tag would reintroduce the defect while
#: looking like a fix -- `master` is a ref too.
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def test_the_catalogue_records_the_commit_it_came_from():
    assert COMMIT.match(PROVENANCE["_commit"]), PROVENANCE["_commit"]


def test_the_corpus_is_fetched_at_the_catalogue_s_commit():
    assert PROVENANCE["_commit"] == crossvalidate.REF


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
