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

def _own_labels(text):
    """The rules the page calls this tool's own, found with the generator's own
    label. A pattern kept here would go on matching nothing once the label's
    wording changed, and the test below would pass for having found none."""
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from gen_what_it_catches import OWN_RULE

    before, _, after = OWN_RULE.partition("%s")
    return re.findall(re.escape(before) + r"([A-Z][A-Z0-9.]*[a-z]?)" + re.escape(after), text)


def test_a_rule_the_page_calls_its_own_claims_no_obligation():
    rules = {rule.id: rule for rule in all_rules()}
    labelled = _own_labels(PAGE.read_text("utf-8"))
    # The page shows one such rule today (L2). Finding none means the label
    # moved or the case went, and either way this test would be asserting
    # nothing; if the page is meant to show none, change this on purpose.
    assert labelled, "the page carries no own-rule label this test can read"

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


def _generator():
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    import gen_what_it_catches

    return gen_what_it_catches


def test_no_rule_compares_this_tool_with_another():
    """A rule's title and remedy reach the page inside captured output, which
    the check over the page's prose passes over. They are held here instead,
    for every rule and not only the ones a case shows."""
    aims = _generator().aims_at_a_tool
    said = sorted("%s %s: %s" % (rule.id, field, aims(getattr(rule, field)))
                  for rule in all_rules() for field in ("title", "fix", "diagnosis")
                  if aims(getattr(rule, field)))
    assert said == [], "\n".join(said)


def test_the_comparison_check_refuses_what_it_is_for():
    """The test above passes on every rule, which is also what it would do if
    the check matched nothing."""
    aims = _generator().aims_at_a_tool
    for text in ("Coverage is 172 of 280, as no other iiRDS tool does.",
                 "No other library reads it.",
                 "It finds more than twice as many defects as the reference implementation.",
                 "Unlike other validators, it reads the index.",
                 "It is unique among iiRDS validators."):
        assert aims(text), text
    for text in ("Rename one of them so the two differ by more than case.",
                 "Without one the element is anonymous, so no other statement can refer to it.",
                 "A rendition larger than this tool will read in one piece has to be split.",
                 "If it was exported from another tool, export as RDF/XML."):
        assert aims(text) is None, text
