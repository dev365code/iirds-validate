"""When the packages claiming the container disagree, say so rather than pick.

`_detect` elects one `iirds:Package` to answer for the container. Where several
claim it, the election is decided by `_declared_rank` -- newest edition first,
then whether a profile is named. Two things follow that no rule was saying.

**A and H are not ordered.** The rank asks whether a profile is named, not
which one, so two packages naming different profiles tie and the tie falls back
to the order the nodes come out of the graph -- which is the tie-break
`_declared_rank`'s own docstring says the profile term exists to replace. A
conformant iiRDS/H container beside one stray `iirds:Package` naming A is read
as iiRDS/A when the stray's IRI sorts first and as iiRDS/H when it sorts last.
There is no right answer to pick: the profiles are two values with no order
between them, and picking either is a coin toss the report prints as a fact.

**And `iirds lint` said nothing at all.** M3 reports several packages claiming
one container, but M3 is a schema rule and `LINT_KINDS` is `("lint", "system")`
-- so an interoperability run on that container returned `ok=True`, no
findings, and no note, having silently chosen one of the two. System is the one
kind every run includes, which is why this rule is one.
"""
from __future__ import annotations

import pytest

from conftest import build_package
from iirds_validate import runner

HEAD = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
%s</rdf:RDF>
"""


def package(iri, version=None, profile=None):
    body = ""
    if version:
        body += "    <iirds:iiRDSVersion>%s</iirds:iiRDSVersion>\n" % version
    if profile:
        body += "    <iirds:formatRestriction>%s</iirds:formatRestriction>\n" % profile
    return '  <iirds:Package rdf:about="%s">\n%s    <iirds:title>T</iirds:title>\n  </iirds:Package>\n' % (
        iri, body)


def report(tmp_path, body, run=runner.check, name="c.iirds"):
    return run(build_package(tmp_path, name, metadata=HEAD % body,
                             content=("content/topic1.xhtml",)))


def fired(tmp_path, body, **kw):
    return {f.rule.id for f in report(tmp_path, body, **kw).findings}


REAL_H = package("urn:zzz:real", "1.3", "H")


# ---------------------------------------------------------------------------
# The profiles disagree
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stray_iri,label", [("urn:aaa:stray", "sorting first"),
                                             ("urn:zzzz:stray", "sorting last")])
def test_two_packages_naming_different_profiles_are_reported(tmp_path, stray_iri, label):
    """Both orders, because only one of them changed the verdict -- and a rule
    that fires on the losing order only would be reporting the alphabet."""
    body = package(stray_iri, profile="A") + REAL_H
    assert "S11" in fired(tmp_path, body), label


def test_the_verdict_no_longer_depends_on_which_iri_sorts_first(tmp_path):
    """The point of the finding. The profile a run picks may still differ, and
    now the reader is told the pick was a pick."""
    first = fired(tmp_path, package("urn:aaa:stray", profile="A") + REAL_H)
    last = fired(tmp_path, REAL_H + package("urn:zzzz:stray", profile="A"))
    assert "S11" in first and "S11" in last


def test_one_package_naming_a_profile_is_not_reported(tmp_path):
    """The stray names none, so nothing about the profile is in doubt: the
    rank's own tie-break settles it, and that one is written down."""
    assert "S11" not in fired(tmp_path, package("urn:aaa:stray", "1.3") + REAL_H)


def test_a_single_package_is_not_reported(tmp_path):
    assert "S11" not in fired(tmp_path, REAL_H)


def test_two_packages_naming_the_same_profile_are_not_reported(tmp_path):
    """Two packages is M3's finding. This rule is about what the container is,
    and here they agree about that."""
    assert "S11" not in fired(tmp_path, package("urn:aaa:x", "1.3", "H") + REAL_H)


# ---------------------------------------------------------------------------
# The editions disagree
# ---------------------------------------------------------------------------

def test_two_packages_declaring_different_editions_are_not_reported(tmp_path):
    """Not an oversight -- a disagreement about the edition alone cannot lose a
    rule. The rank takes the newest, so the elected edition is the highest any
    of them declared and nothing an older one would have brought is missing.
    Reporting it would be reporting M3's finding in different words.
    """
    body = package("urn:aaa:x", "1.0") + package("urn:zzz:y", "1.3")
    assert "S11" not in fired(tmp_path, body)


def test_a_package_with_no_edition_beside_one_with_an_edition_is_reported(tmp_path):
    """An empty leftover element ranks as the newest, which is how it wins.
    Silently, until now."""
    body = '  <iirds:Package rdf:about="urn:aaa:leftover"/>\n' + package("urn:zzz:y", "1.0", "H")
    assert "S11" in fired(tmp_path, body)
    # And the harm is real, not notional: the handover rule that asks an
    # iiRDS/H package for its JSON-LD stops running.
    assert "C16.2" in fired(tmp_path, package("urn:zzz:y", "1.0", "H"))
    assert "C16.2" not in fired(tmp_path, body)


# ---------------------------------------------------------------------------
# Every run, not just the conformance one
# ---------------------------------------------------------------------------

def test_the_interoperability_run_stops_being_silent(tmp_path):
    """The reason this rule is `kind="system"`.

    `iirds lint` on this container returned ok=True with no findings and no
    note: M3 is a schema rule and a lint run does not include schema, so the
    one rule that had something to say was not asked.
    """
    body = package("urn:aaa:x", "1.3") + package("urn:zzz:y", "1.0", "H")
    lint = report(tmp_path, body, run=runner.lint)
    assert "S11" in {f.rule.id for f in lint.findings}
    assert not lint.ok


def test_the_conformance_run_reports_it_too(tmp_path):
    body = package("urn:aaa:x", "1.3") + package("urn:zzz:y", "1.0", "H")
    assert "S11" in fired(tmp_path, body)


def test_the_finding_names_what_was_chosen(tmp_path):
    """A reader has to be able to tell which reading the rest of the report
    used, or the finding says only that something is wrong somewhere."""
    body = package("urn:aaa:stray", profile="A") + REAL_H
    hits = [f for f in report(tmp_path, body).findings if f.rule.id == "S11"]
    assert len(hits) == 1
    text = (hits[0].violation.detail or "") + (hits[0].violation.message or "")
    assert "A" in text and "H" in text, text


def test_the_rule_is_a_system_rule(tmp_path):
    """Not decoration: `system` is the only kind every run includes, and the
    silence this closes was a lint run's."""
    from iirds_validate.registry import all_rules
    rule = {r.id: r for r in all_rules()}["S11"]
    assert rule.kind == "system", rule.kind
    assert rule.versions == () and rule.variants == ()
