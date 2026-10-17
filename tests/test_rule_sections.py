"""Every rule names its section or says it has none.

`docs/capabilities.json` holds this as one of the conditions this project sets
itself for 1.0, and it did not hold: fifty-two rules carried no link to the
standard. Seventeen claimed obligations and gave no link to the sentences they
claim, and for the thirty-five that claim nothing, nothing in the rule or in
its report said whether there was a section to give.

The links are derived by `tools/rule_sections.py` wherever something says what
they are -- the rule's own claims, or the sentence its finding is about -- so
they move when the claims do. These tests hold the property, the derivation,
and the two places a reader meets it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from iirds_validate import cli
from iirds_validate.registry import all_rules

ROOT = Path(__file__).resolve().parents[1]
INDEX = json.loads((ROOT / "docs" / "requirements.json").read_text("utf-8"))
ROWS = {row["id"]: row for row in INDEX["requirements"]}


def _generator():
    sys.path.insert(0, str(ROOT / "tools"))
    import rule_sections
    return rule_sections


def test_every_rule_names_its_section_or_says_it_has_none():
    neither = [r.id for r in all_rules() if not r.spec and not getattr(r, "no_section", "")]
    assert neither == [], "names no section and says nothing about it: %s" % neither


def test_no_rule_both_names_a_section_and_says_it_has_none():
    both = [r.id for r in all_rules() if r.spec and getattr(r, "no_section", "")]
    assert both == [], both


def test_a_rule_that_claims_names_the_section_of_the_first_sentence_it_claims():
    """Derived, so it cannot drift from the claim: a rule given a new first
    claim names the new sentence's section without anybody editing a table."""
    from iirds_validate.registry import own_spec

    derived = [r for r in all_rules() if own_spec(r.id) is None and r.covers]
    # Seventeen claim obligations and had no link. One of them, M97.1, has a
    # catalogue row whose link is an empty string rather than none, and was
    # missing from this list until that was read as what it is.
    assert len(derived) == 17, sorted(r.id for r in derived)
    for r in derived:
        assert r.spec == "%s#%s" % (INDEX["_source"], ROWS[r.covers[0]]["section"]), r.id


def test_a_rule_with_its_own_link_keeps_it():
    """The catalogue's links carry a text fragment that lands on the sentence;
    a derived section link would be a worse answer to the same question."""
    from iirds_validate.registry import own_spec

    for r in all_rules():
        if own_spec(r.id):
            assert r.spec == own_spec(r.id), r.id


def test_the_table_is_what_the_generator_writes():
    from iirds_validate.sections import NO_SECTION, SECTIONS

    done = subprocess.run([sys.executable, str(ROOT / "tools" / "rule_sections.py"), "--check"],
                          cwd=ROOT, capture_output=True, text=True,
                          env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))
    assert done.returncode == 0, done.stdout + done.stderr
    # The line `make` prints is a count of the table it checked, not a figure.
    assert "%d rules name a section here, %d say they have none" % (
        len(SECTIONS), len(NO_SECTION)) in done.stdout, done.stdout


@pytest.mark.parametrize("edit,complaint", [
    (lambda t: t["NONE"].pop("S9"), "S9 carries no link, claims nothing"),
    (lambda t: t["NONE"].__setitem__("M1", "no reason"), "M1 is in NONE, but it"),
    (lambda t: t["SENTENCE"].__setitem__("L1", "x9-9-nothing#1"), "is not in the index"),
    (lambda t: t["NONE"].__setitem__("Z99", "no such rule"), "no rule has that id"),
    (lambda t: t["SECTION"].__setitem__("S9", "x5-2-iirds-zip-archive"), "S9 is in SECTION and in NONE"),
    (lambda t: t["SECTION"].__setitem__("L6", "not-a-section-of-anything"),
     "names not-a-section-of-anything, which is no section of the specification"),
    (lambda t: t["NONE"].__setitem__("S9", "   "), "S9 is in NONE with no reason"),
    (lambda t: t["SECTION"].__setitem__("L2", "x6-3-content-references-of-information-units"),
     "L2 is in SENTENCE and in SECTION"),
    (lambda t: t["NONE"].__setitem__("S9", "about the ZIP format beneath the standard"),
     "S9 is in NONE for a reason of neither kind"),
], ids=["a rule left out", "an entry nobody needs", "a sentence the index lacks",
        "an entry for no rule", "a rule in two tables", "an anchor the specification lacks",
        "a reason that says nothing", "a rule in two tables of sections",
        "a reason of a third kind"])
def test_the_generator_refuses_a_table_that_is_wrong(monkeypatch, edit, complaint):
    rule_sections = _generator()
    # The anchors a cached copy of the specification would give, so the anchor
    # case asks the same question with or without one.
    monkeypatch.setattr(rule_sections, "_cached_sections",
                        lambda data: {"x6-1-the-iirds-rdf-schema-and-identifiers"})
    tables = {name: dict(getattr(rule_sections, name)) for name in ("SENTENCE", "SECTION", "NONE")}
    edit(tables)
    for name, table in tables.items():
        monkeypatch.setattr(rule_sections, name, table)
    _sections, _none, problems, _unverified = rule_sections.derive()
    assert any(complaint in p for p in problems), problems


def test_every_section_named_by_anchor_is_one_the_specification_has():
    """The index knows every section that carries a keyword. An anchor outside
    it is checked against a cached copy of the specification, which CI does
    not have and `make` requires."""
    cache = ROOT / ".spec-cache" / ("%s.html" % INDEX["_release"])
    if not cache.exists():
        if os.environ.get("IIRDS_REQUIRE_SPEC_CACHE"):
            pytest.fail("IIRDS_REQUIRE_SPEC_CACHE is set and %s is not here" % cache)
        pytest.skip("no cached specification")
    from iirds_validate.sections import SECTIONS

    anchors = set(re.findall(r'<h[1-6][^>]*\bid="([^"]+)"', cache.read_text("utf-8")))
    named = {url.partition("#")[2] for url in SECTIONS.values()}
    assert named and not (named - anchors), sorted(named - anchors)


def test_the_rule_listing_says_when_there_is_none(capsys):
    assert cli.main(["rules", "S9"]) == 0
    out = capsys.readouterr().out
    assert "spec: none -- about this run" in out, out


def test_the_rule_listing_names_a_derived_section(capsys):
    assert cli.main(["rules", "R43"]) == 0
    out = capsys.readouterr().out
    assert "spec: %s#x8-2-1-2-graphics-formats" % INDEX["_source"] in out, out


def test_a_verbose_report_says_when_there_is_none(make_package):
    """The other place a reader meets a finding. A link prints under it as
    `spec:`; a rule with no section behind it says so on the same line."""
    import io

    from conftest import MINIMAL_RDF
    from iirds_validate import report, runner

    metadata = MINIMAL_RDF.replace(
        "<iirds:title>A topic</iirds:title>",
        "<iirds:title>A topic</iirds:title>\n"
        '    <iirds:relates-to-product-variant rdf:resource="urn:test:nowhere"/>', 1)
    assert metadata != MINIMAL_RDF
    result = runner.run(make_package(metadata=metadata), runner.ALL_KINDS)
    assert "L1" in {f.rule.id for f in result.findings}, sorted(f.rule.id for f in result.findings)
    out = io.StringIO()
    report.render_text(result, out, verbose=True)
    reason = {r.id: r for r in all_rules()}["L1"].no_section
    assert reason and ("spec: none -- %s" % reason) in out.getvalue(), out.getvalue()


def _stale_reason(text):
    at = text.index("NO_SECTION = {")
    return text[:at] + text[at:].replace("about this run: ", "about this run, stale: ", 1)


#: A table gone stale in each of its halves, written without naming any rule's
#: link: the first version moved one rule's current link, so a table changed
#: for good reason would have failed it for none, and a stale reason was not
#: asked at all.
STALE = {
    "a link": lambda text: text.replace(".html#", ".html#stale-", 1),
    "a reason": _stale_reason,
}


@pytest.mark.parametrize("half", sorted(STALE))
def test_the_check_fails_on_a_table_that_is_not_what_the_generator_writes(
        tmp_path, monkeypatch, capsys, half):
    """`--check` is the gate `make` and CI run, and nothing asked whether it can
    fail: with its comparison switched off every test above still passed."""
    rule_sections = _generator()
    committed = rule_sections.OUT.read_text("utf-8")
    stale = tmp_path / "sections.py"
    stale.write_text(STALE[half](committed), "utf-8")
    assert stale.read_text("utf-8") != committed
    monkeypatch.setattr(rule_sections, "OUT", stale)
    monkeypatch.setattr(sys, "argv", ["rule_sections.py", "--check"])
    assert rule_sections.main() == 1
    assert "does not match" in capsys.readouterr().err
    stale.write_text(committed, "utf-8")
    assert rule_sections.main() == 0


#: Ways the table can be there and not be a table: each stopped the generator
#: at the registry's import before it was asked as well as a missing file.
UNREADABLE = {
    "missing": None,
    "merge markers": "<<<<<<< HEAD\n",
    "empty": "",
    "without its names": "SECTIONS = {}\n",
}


@pytest.mark.parametrize("state", sorted(UNREADABLE))
def test_the_generator_rebuilds_a_table_it_cannot_read(tmp_path, state):
    """The registry imports the table the generator writes, so a table it could
    not import stopped the generator before it could write it."""
    import shutil

    for part in ("src", "docs/requirements.json", "tools/rule_sections.py"):
        source, target = ROOT / part, tmp_path / part
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(source, target)
    table = tmp_path / "src" / "iirds_validate" / "sections.py"
    if UNREADABLE[state] is None:
        table.unlink()
    else:
        committed = table.read_text("utf-8")
        table.write_text(UNREADABLE[state] + (committed if state == "merge markers" else ""), "utf-8")
    env = {k: v for k, v in os.environ.items() if k != "IIRDS_REQUIRE_SPEC_CACHE"}
    env.update(PYTHONPATH=str(tmp_path / "src"), PYTHONDONTWRITEBYTECODE="1")
    tool = [sys.executable, str(tmp_path / "tools" / "rule_sections.py")]
    checked = subprocess.run(tool + ["--check"], cwd=tmp_path, env=env,
                             capture_output=True, text=True)
    assert checked.returncode == 1, checked.stderr
    assert "is missing or is not a table the registry can import" in checked.stderr, checked.stderr
    written = subprocess.run(tool, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert written.returncode == 0, written.stdout + written.stderr
    assert table.read_text("utf-8") == (ROOT / "src" / "iirds_validate" / "sections.py").read_text("utf-8")


def test_the_json_rule_listing_carries_the_reason(capsys):
    assert cli.main(["rules", "S9", "R43", "--format", "json"]) == 0
    listed = {row["id"]: row for row in json.loads(capsys.readouterr().out)}
    reasons = {r.id: r.no_section for r in all_rules()}
    assert listed["S9"]["noSection"] == reasons["S9"] and listed["S9"]["spec"] is None
    assert listed["R43"]["noSection"] is None and listed["R43"]["spec"]


def _three(make_package, extra):
    """A topic carrying `extra` -- three of something, when the report is to group it."""
    from conftest import MINIMAL_RDF
    from iirds_validate import runner

    metadata = MINIMAL_RDF.replace("<iirds:title>A topic</iirds:title>",
                                   "<iirds:title>A topic</iirds:title>\n" + extra, 1)
    assert metadata != MINIMAL_RDF
    return runner.run(make_package(metadata=metadata), runner.ALL_KINDS)


#: A literal where a relation wants a resource: L16, which names the section
#: of the relations table, once per value.
LITERAL = "    <iirds:relates-to-product-variant>v%d</iirds:relates-to-product-variant>\n"


@pytest.mark.parametrize("times", [1, 3])
def test_a_verbose_report_names_the_section_under_a_finding(make_package, times):
    """The link is the line most rules print, and only the reason was asked: the
    link could go from under one finding, or a run of them, with every test here
    green. Once under one finding and once under a run."""
    import io

    from iirds_validate import report

    result = _three(make_package, "".join(LITERAL % n for n in range(times)))
    assert sum(f.rule.id == "L16" for f in result.findings) == times
    assert (times >= report.GROUP_FROM) == (times == 3)
    out = io.StringIO()
    report.render_text(result, out, verbose=True)
    spec = {r.id: r for r in all_rules()}["L16"].spec
    assert spec and out.getvalue().count("spec: %s" % spec) == 1, out.getvalue()


def test_a_verbose_report_says_it_for_a_run_of_findings_too(make_package):
    """Three findings of one rule print as a group, and the group printed
    neither the link nor the reason -- for any rule, before there were reasons."""
    import io

    from iirds_validate import report

    result = _three(make_package, "".join(
        '    <iirds:relates-to-product-variant rdf:resource="urn:test:nowhere%d"/>\n' % n
        for n in range(3)))
    assert sum(f.rule.id == "L1" for f in result.findings) >= report.GROUP_FROM
    out = io.StringIO()
    report.render_text(result, out, verbose=True)
    text = out.getvalue()
    reason = {r.id: r for r in all_rules()}["L1"].no_section
    assert text.count("spec: none -- %s" % reason) == 1, text
