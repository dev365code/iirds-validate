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
    #: Ours: the interoperability rules, the content rules, six system checks
    #: the catalogue has no rule for — that the declared version and profile
    #: exist, that no archive entry escapes the container, the two
    #: requirements section 5.2.2 states about the archive itself, and the
#: ceiling on what a run will decompress — and the R
    #: family, which implements specification requirements the catalogue
    #: enumerated no identifier for at all.
    ours = ({r.id for r in rules_of_kind("lint")}
            | {r.id for r in rules_of_kind("content")}
            | {"S4", "S5", "S6", "S7", "S8", "S9"}
            | {r.id for r in all_rules() if r.id.startswith("R")})
    assert uncatalogued == ours, \
        "uncatalogued ids are a typo unless they are ours: %s" % sorted(uncatalogued - ours)
    assert all(rid[0] in "LSBR" and rid[1:].isdigit() for rid in ours), sorted(ours)


def test_every_rule_kind_matches_the_catalogue():
    for rule in all_rules():
        if rule.id in CATALOG:
            assert rule.kind == CATALOG[rule.id]["kind"], rule.id


def test_every_rule_has_a_title_and_a_known_priority():
    for rule in all_rules():
        assert rule.title and rule.title != rule.id, rule.id
        assert rule.prio in ("MUST", "MUST NOT", "REQUIRED", "RECOMMENDED", "MAY"), rule.id


def test_coverage_matches_the_readme():
    """The README publishes these as headline numbers, and it took them from
    `coverage()`, which used to put the content rules and the extra system
    rules in the interoperability bucket. A tool whose pitch is rigour cannot
    miscount itself, and a reviewer comparing the table to `iirds rules`
    finds that in five minutes."""
    import pathlib
    import re

    readme = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text("utf-8")
    cov = coverage()

    for kind, label in (("container", r"container \(C\\\*\)"),
                        ("schema", r"schema \(M\\\*\)")):
        m = re.search(label + r"\s*\|\s*(\d+)\s*/\s*(\d+)", readme)
        assert m, "coverage row for %s not found in README" % kind
        assert (int(m.group(1)), int(m.group(2))) == (cov[kind]["implemented"], cov[kind]["total"])

    catalogued = sum(v["implemented"] for v in cov.values())
    ours = sum(v["ours"] for v in cov.values())
    assert "%d of %d catalogued rules" % (catalogued, len(CATALOG)) in readme, \
        "the README's headline count is stale"
    assert "plus %d of this project's own" % ours in readme, \
        "the README's count of this project's own rules is stale"

    # The "this project" column, and the same figure in the console block the
    # README presents as literal output. Reading only the catalogued fractions
    # let both drift: three rules were added, one sentence moved, and the
    # column went on summing to three less than the sentence beside it while
    # this test stayed green. A number a gate does not read is not pinned.
    for kind in ("container", "schema", "system", "content", "lint"):
        ours_here = cov[kind]["ours"]
        assert re.search(r"^%s\s.*\+%d of its own$" % (kind, ours_here), readme, re.M), \
            "the console block's '+N of its own' for %s is not %d" % (kind, ours_here)

    rows = re.findall(r"^\| \w+ \(\w\\\*\) \| ([^|]+) \| (\d+) \|$", readme, re.M)
    assert len(rows) == 5, "the kind table should have five rows, found %d" % len(rows)
    assert sum(int(n) for _cat, n in rows) == ours, \
        "the kind table's own-rule column sums to %d, not %d" % (
            sum(int(n) for _cat, n in rows), ours)


def test_every_finding_says_whose_rule_it_is():
    """B*, L* and S4-S8 share a namespace with the catalogue. A stored report
    has to survive the catalogue minting a real B1."""
    from iirds_validate.model import Finding, Violation
    catalogued = next(r for r in all_rules() if r.id in CATALOG)
    ours = next(r for r in all_rules() if r.id not in CATALOG)
    assert Finding(catalogued, Violation("x")).as_dict()["source"] == "catalogue"
    assert Finding(ours, Violation("x")).as_dict()["source"] == "iirds-validate"


def test_the_named_party_rules_do_not_quote_the_document_sentence():
    """The catalogue's spec links for four iiRDS/H rules carry a text
    fragment quoting "The following metadata is mandatory for each
    iirds:Document" — while the rules govern Package, InformationObject
    and IdentityDomain. A reader following the link lands on a sentence
    about the wrong class. The registry keeps
    the section anchor and drops the misleading quotation."""
    from iirds_validate.registry import all_rules

    for rule in all_rules():
        if rule.id in ("M15.7b", "M15.7d", "M15.9", "M15.10"):
            assert rule.spec and ":~:text=" not in rule.spec, rule.id


def test_the_readme_headline_figures_are_the_counts():
    """Every number this project publishes is supposed to be read by a test.
    Four were not: the rule count in the badge line, the shape count, "All N
    rules carry one imperative sentence", and how many of them have ever
    fired. Each moved by hand when the last rule landed and each would have
    rotted at the next one -- the same figures one file down, in
    shapes/README.md, were already read by a test, which is exactly what made
    the omission hard to see."""
    import json
    import pathlib

    from iirds_validate.registry import all_rules

    root = pathlib.Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text("utf-8")
    rules = len(all_rules())
    manifest = json.loads((root / "shapes" / "MANIFEST.json").read_text("utf-8"))
    shapes = len(manifest["core_emitted"]) + len(manifest["sparql_emitted"])
    coverage = json.loads((root / "docs" / "rule-coverage.json").read_text("utf-8"))

    own = rules - len(CATALOG)
    for phrase in ("**At a glance** — %d rules" % rules,
                   "%d SHACL shapes" % shapes,
                   "All %d rules carry one imperative" % rules,
                   "The %d rules this project invented" % own,
                   "%d of the %d have" % (coverage["exercised"], coverage["rules"])):
        assert phrase in readme, "README.md no longer says %r" % phrase
