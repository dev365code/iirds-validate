"""Guards on the registration path itself.

registry.rule() falls back to kind="lint" when an id is absent from the
catalogue, so a typo in @rule("M24.7") does not raise — it registers a
conformance rule that `check` will never run and `lint` will run against
packages it was not written for. Silent, and invisible in the coverage table.
"""
from __future__ import annotations

#: Ours, not plusmeta's. Derived rather than listed so adding one is a
#: one-line change and a *mistyped* one still fails the test below.
from iirds_validate.registry import (
    CATALOG,
    all_rules,
    coverage,
    implemented_ids,
    rules_of_kind,  # noqa: E402
)


def test_no_rule_id_is_missing_from_the_catalogue():
    """A typo registers as kind="lint" and is then never run by `check`."""
    uncatalogued = implemented_ids() - set(CATALOG)
    #: Ours: the interoperability rules, plus three system checks the
    #: catalogue has no rule for — that the declared version and profile
    #: actually exist, and that no archive entry escapes the container.
    ours = {r.id for r in rules_of_kind("lint")} | {"S4", "S5", "S6"}
    assert uncatalogued == ours, \
        "uncatalogued ids are a typo unless they are ours: %s" % sorted(uncatalogued - ours)
    assert all(rid[0] in "LS" and rid[1:].isdigit() for rid in ours), sorted(ours)


def test_every_rule_kind_matches_the_catalogue():
    for rule in all_rules():
        if rule.id in CATALOG:
            assert rule.kind == CATALOG[rule.id]["kind"], rule.id


def test_every_rule_has_a_title_and_a_known_priority():
    for rule in all_rules():
        assert rule.title and rule.title != rule.id, rule.id
        assert rule.prio in ("MUST", "MUST NOT", "REQUIRED", "RECOMMENDED", "MAY"), rule.id


def test_coverage_matches_the_readme():
    """The README publishes coverage as a headline number. Keep it true."""
    import pathlib
    import re

    readme = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text("utf-8")
    cov = coverage()
    for kind, label in (("container", r"container \(C\\\*\)"),
                        ("schema", r"schema \(M\\\*\)"),
                        ("system", r"system \(S\\\*\)")):
        m = re.search(label + r"\s*\|\s*(\d+)\s*/\s*(\d+)", readme)
        assert m, "coverage row for %s not found in README" % kind
        assert (int(m.group(1)), int(m.group(2))) == (cov[kind]["implemented"], cov[kind]["total"]), \
            "README says %s/%s for %s, actual is %s/%s" % (
                m.group(1), m.group(2), kind, cov[kind]["implemented"], cov[kind]["total"])
