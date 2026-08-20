"""The Consortium's own sample packages, pinned finding for finding.

iiRDS Sample Content (2019-10-31): two complete .iirds packages published by
tekom alongside the standard, behind free registration at iirds.org. They are
the only full packages in existence that the standard's own authors built --
which makes them the strongest false-positive oracle this project can run, and
the first real iiRDS 1.0 material it has ever seen.

Every error below survived adversarial verification against the specification
text of the exact edition the packages declare (1.0, 2018-04-18):

  sample 1, M22.1 -- a Party carrying only a vcard, no has-party-role.
    1.0: "An iirds:Party MUST have a related iirds:Role that is assigned by
    the property iirds:has-party-role". A real defect in the official sample.
  sample 2, M18 -- relates-to-product-variant pointing only at an external
    vocabulary, no iirds:ProductVariant declared. 1.0 and 1.3, verbatim:
    "they MUST be present in the metadata.rdf of the iiRDS package".
  sample 1, L10 -- the package types mch:EnvironmentalProtectionInstruction
    directly as iirds:InformationSubject; tekom's own 1.3 machinery vocabulary
    types that term as an instance of iirds:Safety. The warning's advice is
    the vocabulary's own current position.

The packages are registration-gated, so they are not vendored; set
IIRDS_SAMPLE_CONTENT to the directory holding them and this file stops
skipping. Pinned as golden so a rule change that alters the verdict on the
standard's own packages cannot pass unremarked.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import pytest

from iirds_validate import runner

DIRECTORY = os.environ.get("IIRDS_SAMPLE_CONTENT", "")
pytestmark = pytest.mark.skipif(
    not (DIRECTORY and Path(DIRECTORY).is_dir()),
    reason="official sample content not present; set IIRDS_SAMPLE_CONTENT")


def _by_severity(report):
    out = {}
    for finding in report.findings:
        out.setdefault(str(finding.severity), Counter())[finding.rule.id] += 1
    return out


def test_sample_1_the_reviewer_party_has_no_role():
    report = runner.run(Path(DIRECTORY) / "iirds-sample-1.iirds", runner.ALL_KINDS)
    assert report.version == "1.0" and report.variant == "A"
    assert not report.ok
    assert _by_severity(report) == {"error": Counter({"M22.1": 1}),
                                    "warning": Counter({"L10": 1})}


def test_sample_2_relates_to_variants_it_never_declares():
    report = runner.run(Path(DIRECTORY) / "iirds-sample-2.iirds", runner.ALL_KINDS)
    assert report.version == "1.0" and report.variant == "A"
    assert not report.ok
    assert _by_severity(report) == {"error": Counter({"M18": 1}),
                                    "warning": Counter({"L1": 1}),
                                    "info": Counter({"L8": 5})}


def test_the_version_gating_ran_against_real_1_0_material():
    """The first genuine 1.0 packages this project has seen. Rules scoped away
    from 1.0 must actually stand down on them."""
    report = runner.run(Path(DIRECTORY) / "iirds-sample-1.iirds", runner.ALL_KINDS)
    assert report.effective_version == "1.0"
    assert report.skipped > 0
