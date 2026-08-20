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

import pytest

from iirds_validate.registry import all_rules

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
