"""A remedy is printed under a finding and has to resolve that finding.

`tests/test_remediation.py` holds every remedy to naming terms that exist.
That is not enough. A rule that reports two different defects carries one
remedy unless it says otherwise, and where the two defects need different
actions the reader of the second one is told to do something that leaves the
finding exactly where it was — or something already done.

M24.5 was the first found: a child node carrying a structure type was told to
add the property to the root. These are the rest of that family. Each case
provokes the branch, reads the remedy off the finding, and then does what it
says, which is the only test that cannot be satisfied by rewording.

Rules whose one remedy genuinely serves every branch are not listed and do
not need to be: C6's two-pass recipe produces both properties, S6's "rewrite
the entry with a path inside the container" answers both escapes, and S10's
"rebuild the archive with one tool in one pass" answers all four. The defect
is a remedy that is *false* for a branch, not a remedy that is shared.
"""
from __future__ import annotations

import sys

import pytest

from conftest import MINIMAL_JSONLD, MINIMAL_RDF, build_package
from iirds_validate import runner

sys.path.insert(0, "tools")

HANDOVER_RDF = MINIMAL_RDF.replace(
    "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
    "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
    "    <iirds:formatRestriction>H</iirds:formatRestriction>")

ENTITY_XHTML = ('<!DOCTYPE html [<!ENTITY x "y">]>'
                '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>&x;</p></body></html>')
GOOD_XHTML = '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>x</p></body></html>'


def finding(tmp_path, name, rule_id, **kwargs):
    report = runner.run(build_package(tmp_path, name, **kwargs), runner.ALL_KINDS)
    hits = [f for f in report.findings if f.rule.id == rule_id]
    assert hits, "%s did not fire: %s" % (rule_id, sorted({f.rule.id for f in report.findings}))
    return hits[0], report


def test_c16_2_does_not_tell_a_reader_whose_file_is_named_right_to_name_it(tmp_path):
    """One branch is an iiRDS/H package with no metadata.jsonld; the other is
    a metadata.jsonld that does not parse. "Name the JSON-LD file
    META-INF/metadata.jsonld exactly" answers the first and is already true
    of the second."""
    missing, _ = finding(tmp_path, "c16_2_missing.iirds", "C16.2", metadata=HANDOVER_RDF)
    broken, _ = finding(tmp_path, "c16_2_broken.iirds", "C16.2",
                        metadata=MINIMAL_RDF, jsonld="{ not json")
    assert missing.fix != broken.fix
    assert "Name the JSON-LD file" in missing.fix
    assert "Name the JSON-LD file" not in broken.fix


def test_c11_2_does_not_tell_a_reader_whose_file_is_there_to_add_it(tmp_path):
    """One branch is a missing index.html; the other is one that is not an
    HTML document. "Add index.html in the root of the archive" is already
    done in the second."""
    missing, _ = finding(tmp_path, "c11_2_missing.iirds", "C11.2",
                         metadata=HANDOVER_RDF, jsonld=MINIMAL_JSONLD)
    unusable, _ = finding(tmp_path, "c11_2_unusable.iirds", "C11.2",
                          metadata=HANDOVER_RDF, jsonld=MINIMAL_JSONLD,
                          extra=(("index.html", "just some text, not html"),))
    assert missing.fix != unusable.fix
    assert unusable.fix.lower().startswith("write index.html")

    # and doing what it says clears it
    mended = build_package(tmp_path, "c11_2_mended.iirds", metadata=HANDOVER_RDF,
                           jsonld=MINIMAL_JSONLD,
                           extra=(("index.html", "<html><body><p>the units</p></body></html>"),))
    assert "C11.2" not in {f.rule.id for f in runner.run(mended, runner.ALL_KINDS).findings}


def test_b1_does_not_tell_a_reader_of_a_refused_file_to_fix_its_syntax(tmp_path):
    """A file that declares XML entities is refused before it is parsed --
    there is no syntax for a parser to reject, and opening it in one shows
    nothing wrong. The refusal is the finding, and the remedy has to name it.
    """
    refused, _ = finding(tmp_path, "b1_refused.iirds", "B1", content=(),
                         extra=(("content/topic1.xhtml", ENTITY_XHTML),))
    malformed, _ = finding(tmp_path, "b1_malformed.iirds", "B1", content=(),
                           extra=(("content/topic1.xhtml", "<html><p>unclosed"),))
    assert refused.fix != malformed.fix
    assert "fix the syntax" in malformed.fix
    assert "fix the syntax" not in refused.fix
    assert "entit" in refused.fix.lower()


def test_m15_7a_does_not_tell_a_reader_who_has_the_relation_to_add_it(tmp_path):
    """One branch is a Document relating to no product variant; the other is
    a Document whose variant carries no instance identity. "Add
    iirds:relates-to-product-variant on the Document" is already done in the
    second, where what is missing is on the variant."""
    from test_handover_rules_fire import HANDOVER, _package

    def m15_7a(name, metadata):
        report = runner.run(_package(tmp_path, name, metadata), runner.ALL_KINDS)
        hits = [f for f in report.findings if f.rule.id == "M15.7a"]
        assert hits, sorted({f.rule.id for f in report.findings})
        return hits[0]

    no_relation = m15_7a("m15_7a_none.iirds", HANDOVER.replace(
        '    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n', "", 1))
    no_identity = m15_7a("m15_7a_ident.iirds", HANDOVER.replace(
        '    <iirds:has-identity rdf:resource="urn:test:identity-instance"/>\n', "", 1))
    assert no_relation.fix != no_identity.fix
    assert no_relation.fix.startswith("Add iirds:relates-to-product-variant")
    assert not no_identity.fix.startswith("Add iirds:relates-to-product-variant")


@pytest.mark.parametrize("rule_id", ["C16.2", "C11.2", "B1", "M15.7a", "M24.5"])
def test_every_remedy_in_this_family_is_an_imperative(rule_id):
    """The house shape: a remedy opens with the action, so a reader who stops
    after five words has the answer."""
    from iirds_validate.registry import all_rules

    rule = next(r for r in all_rules() if r.id == rule_id)
    assert rule.fix, rule_id
    assert rule.fix[0].isupper() and not rule.fix.startswith("The "), rule.fix[:40]


# ---------------------------------------------------------------------------
# The five named-party MUSTs of section 8.3.2
#
# Each remedy is applied literally to the package that provoked it. A remedy
# that under-specifies -- "a Party with a role", where the rule wants one
# named role and a vcard naming an organisation -- leaves the finding, and a
# reader who follows it exactly is told nothing changed.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rule_id,removal,restore", [
    ("M15.8", '    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n', None),
    ("M15.9", None, None),
    ("M15.10", None, None),
    ("M15.7b", None, None),
    ("M15.7d", None, None),
])
def test_the_named_party_remedies_name_the_role_and_the_vcard(rule_id, removal, restore):
    """Every one of the five requires a *named* role and a vcard that names an
    organisation. A remedy that says "a Party with a role" is followed exactly
    and the finding stays."""
    from iirds_validate.registry import all_rules

    rule = next(r for r in all_rules() if r.id == rule_id)
    assert "has-party-role" in rule.fix, rule.fix
    assert "vcard:organization-name" in rule.fix, rule.fix
    assert "with a role." not in rule.fix, rule.fix


def test_m15_7b_remedy_is_about_the_party_not_the_identity_type():
    """Its finding is that no domain names a manufacturer. The remedy used to
    be M15.7c's -- "give the identity a domain that names one of
    ObjectInstanceURI, ObjectTypeURI or SerialNumber" -- which is a different
    rule's requirement and already satisfied wherever this one can fire."""
    from iirds_validate.registry import all_rules

    fix = next(r for r in all_rules() if r.id == "M15.7b").fix
    assert "Manufacturer" in fix
    assert "ObjectInstanceURI" not in fix


def test_following_m15_10s_remedy_clears_it_without_trading_it_for_others(tmp_path):
    """The branch with no identity at all: minting a bare iirds:Identity
    answers this rule and provokes M19.1, M19.2 and M35, so the remedy has to
    say what a complete identity carries."""
    from test_handover_rules_fire import HANDOVER, _package

    stripped = HANDOVER.replace(
        '    <iirds:has-identity rdf:resource="urn:test:identity-object"/>\n'
        "  </iirds:InformationObject>", "  </iirds:InformationObject>", 1)
    report = runner.run(_package(tmp_path, "m15_10_bare.iirds", stripped), runner.ALL_KINDS)
    hit = [f for f in report.findings if f.rule.id == "M15.10"]
    assert hit and "iirds:identifier" in hit[0].fix and "IRI" in hit[0].fix

    # the remedy, followed: the fixture's own identity chain is what it describes
    back = runner.run(_package(tmp_path, "m15_10_back.iirds", HANDOVER), runner.ALL_KINDS)
    errors = sorted({f.rule.id for f in back.findings if str(f.severity) == "error"})
    assert errors == [], errors
