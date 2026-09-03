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
from pathlib import Path

import pytest

from iirds_validate import terms as T
from iirds_validate.model import HOV, IIRDS, MACH, SW
from iirds_validate.ontology import load
from iirds_validate.registry import CATALOG, all_rules

ROOT = Path(__file__).resolve().parents[1]

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
# property the standard does not have. Eleven did, in two ways: a generator
# that spelled every class `iirds:` when six of them live in `iirdsMch:`, and
# five sentences written from memory. A hand search of the same text, run
# first, found eight of the eleven -- which is the argument for the gate. The spec link printed two lines above the
# remedy carried the right spelling in both cases.
#
# The remedy is the only iiRDS claim this repository ships without a gate,
# and it ships twice -- `iirds rules -v` prints it and `sh:description`
# carries it into the shapes.
# ---------------------------------------------------------------------------

#: The prefixes the ontology files declare for themselves, so the advice
#: spells a term the way the specification does.
PREFIXES = {"iirds": IIRDS, "iirdsHov": HOV, "iirdsMch": MACH, "iirdsSft": SW}

#: Greedy on purpose, past the characters an iiRDS name may contain. An
#: earlier form stopped at `.` and `_`, so `iirds:title.value` handed the
#: resolver `title` -- which exists -- and the invented name went out
#: unremarked. Trailing sentence punctuation is stripped below; anything
#: still holding a `.` or `_` is not a name this vocabulary can spell.
_TERM = re.compile(r"\b(iirds|iirdsHov|iirdsMch|iirdsSft):([A-Za-z][A-Za-z0-9._-]*)")

#: Terms the specification uses that the ontology files never declare. Taken
#: from the same list test_terms.py exempts, rather than a second one that
#: could drift away from it -- and held as full IRIs, because all three live
#: in the core namespace and a local name alone exempts `iirdsMch:iiRDSVersion`,
#: which names nothing at all.
UNDECLARED = {T.TERMS[name] for name in T.NOT_IN_ONTOLOGY}


def _named_terms(text):
    for prefix, local in _TERM.findall(text or ""):
        local = local.rstrip(".,;:)")
        iri = PREFIXES[prefix][local]
        if iri in UNDECLARED:
            continue
        yield prefix, local, iri


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


def _per_instance_remedies():
    """Every remedy a rule attaches to a single finding, with where it came from.

    `Finding.fix` is `violation.fix or rule.fix`, so a rule may override its
    standing remedy per finding -- and that override is a string the gate
    above never sees. The first rule to do it (L13, one remedy per position
    the name stood in) keeps its texts in a module-level dict of literals;
    this reads that dict through the module, so the texts pass the same
    check as every standing remedy. A form this cannot read is a failure,
    not a silence: the first per-instance remedy nobody checks is the one
    that names a term that does not exist.
    """
    import ast
    import importlib

    found, unreadable = [], []
    for path in sorted((ROOT / "src" / "iirds_validate" / "rules").glob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        module = None
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Violation"):
                continue
            for keyword in node.keywords:
                if keyword.arg != "fix":
                    continue
                value = keyword.value
                where = "%s:%d" % (path.name, node.lineno)
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.append((where, value.value))
                    continue
                root = value
                while isinstance(root, ast.Subscript):
                    root = root.value
                if isinstance(root, ast.Name):
                    module = module or importlib.import_module("iirds_validate.rules." + path.stem)
                    texts = getattr(module, root.id, None)
                    if isinstance(texts, dict) and all(isinstance(v, str) for v in texts.values()):
                        found.extend(("%s[%s]" % (where, key), text) for key, text in sorted(texts.items()))
                        continue
                    if isinstance(texts, str):
                        found.append((where, texts))
                        continue
                unreadable.append(where)
    return found, unreadable


PER_INSTANCE, UNREADABLE = _per_instance_remedies()


def test_every_per_instance_remedy_is_one_this_gate_can_read():
    assert not UNREADABLE, (
        "these findings carry a remedy in a form the gate cannot read: %s. Keep "
        "per-instance remedies as literals or in a module-level dict of literals, "
        "or the first per-instance remedy is the first one nobody checks." % UNREADABLE)


@pytest.mark.parametrize("where,text", PER_INSTANCE, ids=[w for w, _ in PER_INSTANCE])
def test_a_per_instance_remedy_names_terms_that_exist(where, text):
    for prefix, local, iri in _named_terms(text):
        assert load().is_defined(iri), (
            "%s: the remedy tells the reader to use %s:%s, which the bundled "
            "ontology does not define" % (where, prefix, local))


def test_the_term_reader_actually_reads_terms():
    """Both gates above are `for ... in _named_terms(text)` with the assertion
    inside. A reader that stopped matching anything would empty every loop and
    leave both of them green over 193 rules, so it is pinned here against a
    fixed string rather than only ever exercised through the corpus it is
    meant to police."""
    found = list(_named_terms("Give the iirds:Package an iirds:title."))
    assert [(prefix, name) for prefix, name, _ in found] == [
        ("iirds", "Package"), ("iirds", "title")]
    assert all(str(iri).startswith("http") for _, _, iri in found)
    assert list(_named_terms("no terms here at all")) == []
    assert list(_named_terms(None)) == []


def test_how_much_of_each_gate_is_actually_exercised():
    """Two loops that look alike and are not. Remedies name terms constantly,
    so that gate is dense. Titles mostly do not -- six of the hundred this
    project wrote itself -- so that one asserts something for six rules and
    nothing for the rest, and reads like a gate over all of them.

    Written down rather than left to be discovered, and counted so that a
    reader who removes the last term-naming title finds out here instead of
    keeping a gate that can no longer fail."""
    ours = [r for r in RULES if r.title != CATALOG.get(r.id, {}).get("en")]
    titled = [r for r in ours if list(_named_terms(r.title))]
    remedied = [r for r in RULES if list(_named_terms(r.fix))]
    terms_in_remedies = sum(len(list(_named_terms(r.fix))) for r in RULES)

    assert len(titled) == 6, sorted(r.id for r in titled)
    assert len(remedied) >= 120, len(remedied)
    assert terms_in_remedies >= 140, terms_in_remedies
