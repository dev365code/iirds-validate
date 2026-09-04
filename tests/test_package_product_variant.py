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


# ---------------------------------------------------------------------------
# The other half of the same six sentences.
#
# Section 8.3.2 states them twice, word for word, once for iirds:Package and
# once for iirds:Document, and the rules were parameterised so one builder
# answers both. The readings did not drift; the claims did. R13 covered #1 and
# #2 while M15.7a, which is the same builder called with iirds:Document,
# covered #8 alone -- so #7, the same sentence as #1 about the other class,
# was claimed by nobody and reported by M15.7a all along.
#
# Held here rather than asserted in the covers table, because "the rule
# reports it" is a thing to show a package, not a thing to write down.
# ---------------------------------------------------------------------------

def test_a_variant_identity_without_a_domain_is_reported_for_both_classes(tmp_path):
    """§8.3.2 #1/#7 and #4/#10: "This iirds:ProductVariant MUST relate to an
    iirds:Identity with an iirds:IdentityDomain."

    One package, four rules: the two that read the Package's variant and the
    two that read the Document's. Every identity in the fixture loses its
    domain, which is the one way this sentence breaks.
    """
    import re

    from test_handover_rules_fire import HANDOVER

    broken = re.sub(r"\s*<iirds:has-identity-domain[^/]*/>", "", HANDOVER)
    assert broken != HANDOVER, "the fixture no longer relates an identity to a domain"
    got = ids(tmp_path, "no_domain.iirds", broken)

    assert {"R13", "R15"} <= got, ("the Package half", sorted(got))
    assert {"M15.7a", "M15.7c"} <= got, ("the Document half", sorted(got))

    clean = ids(tmp_path, "no_domain_clean.iirds", HANDOVER)
    assert not ({"R13", "R15", "M15.7a", "M15.7c"} & clean), sorted(clean)


def test_the_advice_is_about_the_class_the_finding_is_about(tmp_path):
    """The messages were parameterised when these rules were split by class;
    one remedy was not. R13's finding is about the Package and told the reader
    about "the product variant this document names", then sent them to M15.7b
    -- the Document-half rule, whose Package-half counterpart is R14.

    It is the only remedy in the registry that names another rule, and the one
    it named was wrong. So the check is on the pair: a Package-half rule may
    not say "document", and may not send the reader to a Document-half rule.
    """
    import re

    from test_handover_rules_fire import HANDOVER

    broken = re.sub(r"\s*<iirds:has-identity-domain[^/]*/>", "", HANDOVER)
    assert broken != HANDOVER, "the fixture edit matched nothing"

    from test_handover_rules_fire import _package

    report = runner.run(_package(tmp_path, "advice.iirds", broken), runner.ALL_KINDS)
    halves = {"R13": "package", "R14": "package", "R15": "package", "R16": "package",
              "M15.7a": "document", "M15.7b": "document",
              "M15.7c": "document", "M15.7d": "document"}
    other_half = {"package": [r for r in halves if halves[r] == "document"],
                  "document": [r for r in halves if halves[r] == "package"]}

    seen = 0
    for finding in report.findings:
        half = halves.get(finding.rule.id)
        if half is None:
            continue
        seen += 1
        wrong_word = "document" if half == "package" else "package"
        assert wrong_word not in finding.fix.lower(), (
            "%s is about the %s and its remedy says %r: %s"
            % (finding.rule.id, half, wrong_word, finding.fix))
        for other in other_half[half]:
            assert other not in finding.fix, (
                "%s sends the reader to %s, which is the other half"
                % (finding.rule.id, other))
    assert seen >= 4, "the fixture stopped provoking these rules"
