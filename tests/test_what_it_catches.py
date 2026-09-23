"""What the examples page says about where each rule comes from.

The page tells a reader, for every case, whether the rule is enforcing a
sentence of the standard or is this tool's own judgement. That is a claim
about the rule, so it is checked against the rule.

The first version of the page decided it by whether the rule carries a
`spec` link, and a link is not the same thing as a claim. `S13` carries no
link and does claim an obligation -- "An iiRDS package MUST implement an
iiRDS ZIP archive", through `covers` -- and counts toward the coverage figure
the front page publishes, while the page called it "this tool's own rule, no
specification reference". Fifteen rules are in that position.
"""
from __future__ import annotations

import re
from pathlib import Path

from iirds_validate.registry import all_rules

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "what-it-catches.md"

#: The label the page gives a rule it says the standard does not stand behind.
OWN = re.compile(r"\*\*This tool's own rule\*\* \(`([A-Z0-9.]+[a-z]?)`\)")


def test_a_rule_the_page_calls_its_own_claims_no_obligation():
    rules = {rule.id: rule for rule in all_rules()}
    labelled = OWN.findall(PAGE.read_text("utf-8"))

    wrong = sorted(rule_id for rule_id in labelled
                   if rules[rule_id].spec or rules[rule_id].covers)
    assert wrong == [], (
        "the page calls these rules this tool's own, and each claims an "
        "obligation of the standard: %s" % ", ".join(
            "%s (%s)" % (rule_id, ", ".join(rules[rule_id].covers) or rules[rule_id].spec)
            for rule_id in wrong))


def test_the_page_says_which_rules_claim_an_obligation_without_a_link():
    """The other half: a rule that claims an obligation and carries no link is
    not left looking like either of the two cases that do exist. The page
    names the requirement it claims, so a reader can find it."""
    rules = {rule.id: rule for rule in all_rules()}
    text = PAGE.read_text("utf-8")
    for rule_id, rule in rules.items():
        if rule.covers and not rule.spec and ("`%s`" % rule_id) in text:
            for claimed in rule.covers:
                assert claimed in text, (
                    "%s appears on the page, claims %s, and the page does not say so"
                    % (rule_id, claimed))
