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
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from gen_what_it_catches import OWN_RULE

    # The reader reads the label: without this, an empty result below could be
    # a pattern that stopped matching rather than a page with no such case.
    assert _own_labels("x " + OWN_RULE % "S10" + " y") == ["S10"]
    labelled = _own_labels(PAGE.read_text("utf-8"))
    # The page showed one such rule, L2, until every rule named its section or
    # said it had none: L2 now links to the section its finding is about, and
    # no case here is about a rule with nothing behind it. Pinned at none, on
    # purpose, so a case that brings the label back is a change made here as
    # well -- and the check below has something to read again.
    assert labelled == [], labelled

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
    from iirds_validate.registry import own_spec

    rules = {rule.id: rule for rule in all_rules()}
    text = PAGE.read_text("utf-8")
    # A link derived from the claims is a section, not the sentence, so a rule
    # holding one is asked the same question as a rule holding none.
    asked = [rule_id for rule_id, rule in rules.items()
             if rule.covers and own_spec(rule_id) is None and ("`%s`" % rule_id) in text]
    assert asked, "no rule on the page takes its link from its claims; this asks nothing"
    for rule_id, rule in rules.items():
        if rule_id in asked:
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
                 "It is unique among iiRDS validators.",
                 "Unlike plusmeta's rule, this one names both values.",
                 "Compared with e.g. the reference validator, this names both values."):
        assert aims(text), text
    for text in ("Rename one of them so the two differ by more than case.",
                 "Without one the element is anonymous, so no other statement can refer to it.",
                 "A rendition larger than this tool will read in one piece has to be split.",
                 "If it was exported from another tool, export as RDF/XML.",
                 "No other product variant may carry the same serial number.",
                 "Unlike the machinery domain, the software domain has no product type.",
                 "One passing through more links than a reader will follow."):
        assert aims(text) is None, text


def test_a_case_whose_words_would_not_reach_the_page_as_prose_is_refused():
    """The generator checks a case's heading and note before it builds
    anything. Deleting those calls left every other test green."""
    import pytest

    g = _generator()
    for heading, note, refusal in (
            ("Heading", "> A note that would render as a quote.", "starts with"),
            ("Heading", "    A note that would render as code.", "starts with"),
            ("Heading", "It reads both, as no other iiRDS validator does.", "comparison"),
            ("Unlike other validators, it reads both", "A plain note.", "comparison")):
        # Matched by what it says: with the check gone, the case still fails --
        # later, on a package that passes where it was to fail.
        with pytest.raises(g.Failed, match=refusal):
            g._case_block("probe", heading, "none", "C5", 1, note)


def test_what_a_case_prints_is_held_to_the_same_words(monkeypatch):
    """Every block of output on the page comes through `_verdict`, the cases'
    and the pair that is not flagged alike, and a remedy or a line the report
    prints reaches the page inside a block the prose check passes over."""
    import pytest

    g = _generator()
    said = ("probe.iirds\n  ERROR C5  a title\n    \u2192 Rename it. Unlike other\n"
            "    \u2192 validators, this names both.\n")
    monkeypatch.setattr(g, "_run", lambda args, env_extra=None: (1, said))
    with pytest.raises(g.Failed, match="compares this tool with another"):
        g._verdict("probe.iirds", exit_code=1, names="C5")
    assert g._entries(said.replace("\u2192", "->")) == [
        "probe.iirds", "ERROR C5  a title",
        "Rename it. Unlike other validators, this names both."]
