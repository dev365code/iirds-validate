"""Licence compliance, as tests rather than as good intentions.

The ontologies are third-party material under CC BY-ND 4.0. Redistributing them
is allowed, and Section 3(a)(1) says precisely what has to travel with them. A
notice that quietly loses one of those items during a refactor is the kind of
mistake nobody notices until it matters, so each one is asserted here.
"""
from __future__ import annotations

import hashlib
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTICE = (ROOT / "NOTICE").read_text("utf-8")
ONTOLOGIES = ROOT / "src/iirds_validate/data/ontologies"

#: CC BY-ND 4.0 Section 3(a)(1): what must be retained when Sharing.
REQUIRED_IN_NOTICE = {
    "(i) creator": ["tekom Deutschland e.V."],
    "(ii) copyright notice": ["© 2023 Gesellschaft für Technische Kommunikation"],
    "(iii) licence notice": ["Creative Commons Attribution-NoDerivatives 4.0"],
    "(iii) licence URI": ["https://creativecommons.org/licenses/by-nd/4.0/"],
    "(iv) warranty disclaimer": ["DISCLAIMER OF WARRANTIES"],
    "(v) licensed material URI": ["https://www.iirds.org/materials/version-13"],
    "modification status": ["NOT MODIFIED"],
    "no endorsement": ["not sponsored or endorsed"],
}


@pytest.mark.parametrize("requirement", sorted(REQUIRED_IN_NOTICE))
def test_notice_carries_every_attribution_element(requirement):
    for needle in REQUIRED_IN_NOTICE[requirement]:
        assert needle in NOTICE, "NOTICE no longer states %s (%r)" % (requirement, needle)


def test_notice_scopes_apache_away_from_the_third_party_material():
    """Section 2(a)(5) forbids imposing different terms on the licensed
    material. A bare "this project is Apache-2.0" would read as doing exactly
    that to files that are not ours to relicense."""
    assert "does NOT extend to the third-party material" in NOTICE


def test_the_ontologies_are_byte_for_byte_as_published():
    """The whole basis for bundling them is that they are unmodified. If that
    stops being true, the licence stops permitting redistribution."""
    sums = (ONTOLOGIES / "sha256sums.txt").read_text("utf-8")
    assert sums.strip(), "no checksums recorded"
    for line in sums.splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        blob = (ONTOLOGIES / "1.3" / name.strip()).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == digest, name.strip()


def test_each_ontology_keeps_its_own_copyright_header():
    """Retaining the notices that came with the material is not optional, and
    the notices came inside the files."""
    for path in sorted((ONTOLOGIES / "1.3").glob("*.rdf")):
        head = path.read_text("utf-8", errors="replace")[:2000]
        assert "tekom Deutschland e.V." in head, path.name
        assert "Attribution-NoDerivatives" in head, path.name


def test_no_converted_copy_of_an_ontology_is_committed():
    """CC BY-ND permits producing Adapted Material but not Sharing it. A
    checked-in Turtle or JSON-LD rendering of the ontology would be Sharing."""
    strays = [path for pattern in ("iirds-*.ttl", "iirds-*.jsonld", "iirds-*.nt")
              for path in ROOT.rglob(pattern)]
    assert not strays, [str(p.relative_to(ROOT)) for p in strays]


def test_the_readme_does_not_claim_endorsement():
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "Not affiliated with" in readme
    for forbidden in (r"\bofficial iiRDS validator\b", r"\bcertified\b(?! by)"):
        assert not re.search(forbidden, readme, re.I), forbidden
