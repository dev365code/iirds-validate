"""Section 8.3.2 states its variant requirements twice, and only one was read.

    The following metadata is mandatory for each `iirds:Package`:
      · at least one `iirds:relates-to-product-variant` relating to an
        `iirds:ProductVariant`.
      · This `iirds:ProductVariant` MUST relate to an `iirds:Identity` with an
        `iirds:IdentityDomain`.
      · The `iirds:IdentityDomain` MUST have an `iirds:has-identity-type` of
        either `iirds:ObjectInstanceURI`, `iirds:ObjectTypeURI` or
        `iirds:SerialNumber`.
      · The `iirds:IdentityDomain` MUST relate to an `iirds:Party` with
        `iirds:has-party-role` `iirds:Manufacturer` and ...
      · (and the same three again for `iirds:ProductType`)

    The following metadata is mandatory for each `iirds:Document`:
      ... the same six bullets, word for word ...

M15.7a to M15.7d read the second list. Nothing read the first, and the shape
of that gap is the one this repository keeps finding: the conformant iiRDS/H
fixture in `tests/test_handover_rules_fire.py` has a Package that relates to
no product variant at all, and a test asserts it reports zero errors.

The two lists are not redundant. A package delivers documents about one
machine; each document may name a narrower variant. Section 8.3.2 asks both
questions, and asking only the second lets a package identify nothing.
"""
from __future__ import annotations

import pytest

from iirds_validate import runner

IIRDS = "http://iirds.tekom.de/iirds#"


PACKAGE_VARIANT = '    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n'


def _package_relates_to(variant: bool):
    """The conformant handover fixture, with the Package's own variant link
    present or absent. Everything else is what that fixture already is.

    The link is *in* the fixture now. It was not until these rules were
    written, and the fixture was asserted to report zero errors throughout --
    which is the finding, not a detail of the test.
    """
    from test_handover_rules_fire import HANDOVER

    assert PACKAGE_VARIANT in HANDOVER, "the fixture no longer names a variant on its Package"
    return HANDOVER if variant else HANDOVER.replace(PACKAGE_VARIANT, "", 1)


def ids(tmp_path, name, metadata):
    from test_handover_rules_fire import _package

    return {f.rule.id for f in runner.run(_package(tmp_path, name, metadata),
                                          runner.ALL_KINDS).findings}


def test_the_conformant_fixture_needs_the_packages_own_variant(tmp_path):
    """Take the link away and the fixture breaches the first bullet of the
    Package list -- which is the state it was in while being asserted clean."""
    assert "R13" in ids(tmp_path, "pkg_no_variant.iirds", _package_relates_to(False))
    assert "R13" not in ids(tmp_path, "pkg_variant.iirds", _package_relates_to(True))


#: (rule, what to remove from the conformant package, which bullet it is)
#:
#: The decomposition mirrors the Document side exactly -- R13 is M15.7a's
#: shape, R14 is M15.7b's, R15 is M15.7c's, R16 is M15.7d's -- because the two
#: lists are the same six sentences and a second decomposition of them is a
#: second thing to keep in step.
PACKAGE_BULLETS = [
    ("R13", '    <iirds:has-identity rdf:resource="urn:test:identity-instance"/>\n',
     "the variant carries no instance identity"),
    ("R15", '    <iirds:has-identity rdf:resource="urn:test:identity-type"/>\n',
     "the variant carries no ProductType identity"),
]


@pytest.mark.parametrize("rule_id,removal,what", PACKAGE_BULLETS,
                         ids=[r[0] for r in PACKAGE_BULLETS])
def test_each_package_bullet_is_reported(rule_id, removal, what, tmp_path):
    metadata = _package_relates_to(True)
    assert removal in metadata, removal
    broken = metadata.replace(removal, "", 1)
    got = ids(tmp_path, "%s_broken.iirds" % rule_id.lower(), broken)
    assert rule_id in got, (what, sorted(got))


def test_the_manufacturer_bullets_are_reported(tmp_path):
    """The two identical Manufacturer sentences, #3 and #6. One removal
    reaches both, because both identity domains name the same party -- each
    assertion is its own rule's."""
    metadata = _package_relates_to(True)
    line = '    <iirds:has-party-role rdf:resource="%sManufacturer"/>\n' % IIRDS
    assert line in metadata
    got = ids(tmp_path, "pkg_manufacturer.iirds", metadata.replace(line, "", 1))
    assert "R14" in got, sorted(got)
    assert "R16" in got, sorted(got)


def test_a_package_that_satisfies_the_list_is_clean(tmp_path):
    """The other half of every case above: none of the five fires on the
    package that carries what the list asks for."""
    got = ids(tmp_path, "pkg_clean.iirds", _package_relates_to(True))
    assert not ({"R13", "R14", "R15", "R16"} & got), sorted(got)
