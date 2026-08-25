"""Every rule must say what to do about it.

A validator that names a defect and not the remedy has told the reader that
something is wrong and left them to find the specification, which is most of
the work and all of the expertise. That is fine for someone who already knows
iiRDS and useless for everyone else -- and everyone else is who this is for.

So the advice is part of a rule, not an optional extra, and it is checked the
way the ontology terms are checked: mechanically, so a rule cannot be added
without one.
"""
from __future__ import annotations

import re

import pytest

from iirds_validate import terms as T
from iirds_validate.model import HOV, IIRDS, MACH, SW
from iirds_validate.ontology import load
from iirds_validate.registry import CATALOG, all_rules

RULES = all_rules()

#: Restating the requirement in the imperative is not advice. "Rendition must
#: have exactly one iirds:format" -> "add an iirds:format" tells the reader
#: nothing the message did not already say.
LAZY_OPENINGS = ("must ", "should ", "do not forget")


@pytest.mark.parametrize("rule", RULES, ids=[r.id for r in RULES])
def test_every_rule_says_what_to_do(rule):
    assert rule.fix, "%s has no remediation text" % rule.id


@pytest.mark.parametrize("rule", RULES, ids=[r.id for r in RULES])
def test_the_advice_is_a_sentence_somebody_can_act_on(rule):
    fix = rule.fix or ""
    assert len(fix) >= 30, "%s: too short to be useful: %r" % (rule.id, fix)
    assert not fix.lower().startswith(LAZY_OPENINGS), \
        "%s: that is the requirement restated, not a remedy: %r" % (rule.id, fix)
    assert fix[0].isupper() or fix[0] in "`<", "%s: %r" % (rule.id, fix)
    assert fix.rstrip().endswith((".", "`")), "%s: %r" % (rule.id, fix)


def test_a_finding_carries_the_advice_through_to_the_report(make_package):
    """The whole point is that it reaches the person reading the output."""
    from conftest import MINIMAL_RDF
    from iirds_validate import runner

    broken = MINIMAL_RDF.replace(
        "        <iirds:format>application/xhtml+xml</iirds:format>\n", "")
    report = runner.check(make_package(metadata=broken))
    finding = next(f for f in report.findings if f.rule.id == "M11")

    assert finding.fix == finding.rule.fix
    assert report.as_dict()["findings"][0]["fix"] == finding.fix


def test_a_violation_may_override_its_rule(make_package):
    """Some remedies depend on what was actually found rather than on which
    rule fired, so a Violation can carry its own and it wins."""
    from iirds_validate.model import Finding, Rule, Violation

    rule = Rule(id="X", kind="lint", prio="MUST", title="t", versions=(), variants=(),
                spec=None, fn=lambda ctx: [], fix="The standing advice.")
    assert Finding(rule, Violation("m")).fix == "The standing advice."
    assert Finding(rule, Violation("m", fix="This one instead.")).fix == "This one instead."


# ---------------------------------------------------------------------------
# ...and the terms it names have to exist.
#
# `terms.py` is guarded: every term a rule *evaluates* is checked against the
# bundled ontology by tests/test_terms.py, which turns a guess into a failing
# test. The advice beside it was not guarded at all, because it is a string.
#
# So a rule could name a real defect, and then tell the reader to add a
# property the standard does not have. Three did, in two ways: a generator
# that spelled every class `iirds:` when six of them are `iirdsMch:`, and two
# sentences written from memory. The spec link printed two lines above the
# remedy carried the right spelling in both cases.
#
# The remedy is the only iiRDS claim this repository ships without a gate,
# and it ships twice -- `iirdsv rules -v` prints it and `sh:description`
# carries it into the shapes.
# ---------------------------------------------------------------------------

#: The prefixes the ontology files declare for themselves, so the advice
#: spells a term the way the specification does.
PREFIXES = {"iirds": IIRDS, "iirdsHov": HOV, "iirdsMch": MACH, "iirdsSft": SW}

_TERM = re.compile(r"\b(iirds|iirdsHov|iirdsMch|iirdsSft):([A-Za-z][A-Za-z0-9-]*)")

#: Terms the specification uses that the ontology files never declare. Taken
#: from the same list test_terms.py exempts, rather than a second one that
#: could drift away from it.
UNDECLARED = {str(T.TERMS[name]).split("#")[-1] for name in T.NOT_IN_ONTOLOGY}


def _named_terms(text):
    for prefix, local in _TERM.findall(text or ""):
        if local not in UNDECLARED:
            yield prefix, local, PREFIXES[prefix][local]


@pytest.mark.parametrize("rule", RULES, ids=[r.id for r in RULES])
def test_the_remedy_names_terms_that_exist(rule):
    for prefix, local, iri in _named_terms(rule.fix):
        assert load().is_defined(iri), (
            "%s: the remedy tells the reader to use %s:%s, which the bundled "
            "ontology does not define" % (rule.id, prefix, local))


@pytest.mark.parametrize("rule", RULES, ids=[r.id for r in RULES])
def test_our_own_titles_name_terms_that_exist(rule):
    """Titles this project wrote, not the ones it inherited.

    The catalogue's wording is reproduced verbatim so results stay diffable
    against the reference tool rule by rule, and several of its sentences name
    properties the ontology spells differently -- M16's `iirds:eventCode` is
    `iirds:has-event-code`. Correcting those would break the comparison this
    project promises, so they are recorded in docs/divergences.md instead of
    edited. What is checked here is the wording we chose ourselves.
    """
    if rule.title == CATALOG.get(rule.id, {}).get("en"):
        pytest.skip("catalogue wording, reproduced verbatim; see docs/divergences.md")
    for prefix, local, iri in _named_terms(rule.title):
        assert load().is_defined(iri), (
            "%s: the title names %s:%s, which the bundled ontology does not define"
            % (rule.id, prefix, local))
