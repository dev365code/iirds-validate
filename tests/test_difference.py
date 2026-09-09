"""Reading one report against another.

The command line answers "is this package conformant". It cannot answer "what
changed since the one I signed off", and that is the question a person
delivering a package actually has. Answering it needs two verdicts and a rule
for reading them together, and the rule is where the honesty is spent: a
difference that says "you broke this" about something the reader never touched
is worse than no difference at all, because it is offered by a tool whose whole
argument is that it says how to fix things.

So the vocabulary is split in two. When the two runs were judged on the same
basis -- same build, same rules, same command, same profile, same edition --
the difference speaks causally: a rule that was clean and now fires is a
regression. When any part of that basis moved, it speaks neutrally: the rule
started firing, and here is what else was different. The exit code is bound to
neither: it answers one question about the two documents, and that question
carries no cause at all.
"""
from __future__ import annotations

import copy
import json
import pathlib
import zipfile

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import difference as diff
from iirds_validate import runner

ROOT = pathlib.Path(__file__).resolve().parents[1]


def report_for(package, kinds=None):
    return runner.run(package, kinds or runner.ALL_KINDS).as_dict()


@pytest.fixture
def clean(make_package):
    return report_for(make_package(metadata=MINIMAL_RDF))


def without_title(metadata):
    """A warning, and a lint rule: L7."""
    return metadata.replace("<iirds:title>A topic</iirds:title>", "")


def two_formats(metadata):
    """An error, and the profile and the edition left where they were --
    which is what makes the causal register reachable at all."""
    return metadata.replace(
        "<iirds:format>application/xhtml+xml</iirds:format>",
        "<iirds:format>application/xhtml+xml</iirds:format>"
        "<iirds:format>text/html</iirds:format>")


# ---------------------------------------------------------------------------
# The classes
# ---------------------------------------------------------------------------

def test_a_package_compared_with_itself_has_nothing_to_say(clean):
    answer = diff.difference(clean, copy.deepcopy(clean))
    assert answer.comparable
    assert not answer.worse
    assert answer.as_dict()["regression"] == []
    assert answer.as_dict()["fixed"] == []
    assert answer.as_dict()["newlyChecked"] == []
    assert answer.as_dict()["noLongerChecked"] == []


def test_a_rule_that_was_clean_and_now_fires_is_a_regression(make_package, clean):
    broken = report_for(make_package(metadata=two_formats(MINIMAL_RDF)))
    answer = diff.difference(clean, broken)
    assert answer.comparable, answer.as_dict()["banners"]
    rules = [row["rule"] for row in answer.as_dict()["regression"]]
    assert rules, answer.as_dict()
    assert all(row["reason"] is None for row in answer.as_dict()["regression"])
    assert answer.worse


def test_the_same_change_read_backwards_is_fixed(make_package, clean):
    broken = report_for(make_package(metadata=two_formats(MINIMAL_RDF)))
    answer = diff.difference(broken, clean)
    assert [row["rule"] for row in answer.as_dict()["fixed"]]
    assert answer.as_dict()["regression"] == []
    assert not answer.worse


def test_a_rule_the_other_run_never_put_is_not_a_regression(make_package, clean):
    """`check` and `lint` are different questions. Every rule one asks and the
    other does not has to arrive as news, with the reason from the other
    document, and it must not set the exit code."""
    linted = report_for(make_package(metadata=without_title(MINIMAL_RDF)),
                        runner.LINT_KINDS)
    answer = diff.difference(clean, linted)
    document = answer.as_dict()
    assert not answer.comparable
    assert document["regression"] == [], document["regression"]
    assert document["noLongerChecked"], "the rules lint does not put"
    assert {row["reason"] for row in document["noLongerChecked"]} == {"unasked"}
    # And the other direction. `all` puts everything `lint` does, so the
    # arrival side is only reachable when the stored report is the narrower
    # run -- and a row with no reason is the sentence that lets a reader
    # assume the rule passed, whichever side it is on.
    other = diff.difference(linted, clean).as_dict()
    assert other["newlyChecked"], "the rules lint does not put"
    assert {row["reason"] for row in other["newlyChecked"]} == {"unasked"}
    assert other["regression"] == [], other["regression"]


def test_a_rule_that_moved_because_the_package_declares_another_edition(make_package):
    """The reason travels with the row. Without it a reader assumes the rule
    passed, which is the sentence the account exists to prevent."""
    before = report_for(make_package(metadata=MINIMAL_RDF))
    after = report_for(make_package(metadata=MINIMAL_RDF.replace("1.3", "1.0")))
    answer = diff.difference(before, after)
    document = answer.as_dict()
    moved = [row for row in document["noLongerChecked"] if row["reason"] == "version"]
    assert moved, document["noLongerChecked"]


# ---------------------------------------------------------------------------
# The two registers
# ---------------------------------------------------------------------------

def test_a_moved_basis_is_named_and_costs_the_causal_words(clean):
    """A build that changed only a rule's body has the same rule-set digest by
    design. `toolVersion` is the only field that can say the bodies differ, so
    a difference that does not read it reports a false regression with nothing
    above it."""
    later = copy.deepcopy(clean)
    later["judgedBy"]["toolVersion"] = "9.9.9"
    answer = diff.difference(clean, later)
    document = answer.as_dict()
    assert not answer.comparable
    assert any(banner["what"] == "toolVersion" for banner in document["banners"])
    assert all(banner["remedy"] for banner in document["banners"]), document["banners"]


def test_a_neutral_reading_still_answers_the_gate(make_package, clean):
    """The register decides the verb and not the number. A package that broke
    while its profile declaration went with it is the ordinary shape of this,
    and answering 0 there would be a quieter wrong answer than refusing."""
    broken = report_for(make_package(metadata=two_formats(MINIMAL_RDF)))
    broken["variant"] = "A"
    answer = diff.difference(clean, broken)
    assert not answer.comparable
    assert answer.worse, answer.as_dict()
    assert [row["rule"] for row in answer.as_dict()["startedFiring"]]


def test_a_directory_and_an_archive_are_not_the_same_basis(make_package, tmp_path, clean):
    """Seven rules a directory cannot answer would arrive as regressions
    otherwise, on a workflow as ordinary as building in a directory and
    releasing an archive."""
    package = make_package(metadata=MINIMAL_RDF)
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(unpacked)
    answer = diff.difference(report_for(unpacked), clean)
    assert not answer.comparable
    assert any(banner["what"] == "unpacked" for banner in answer.as_dict()["banners"])
    assert answer.as_dict()["regression"] == []


# ---------------------------------------------------------------------------
# The stored document is untrusted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wreck, why", [
    (lambda d: d.pop("schemaVersion"), "no version"),
    (lambda d: d.update(schemaVersion=1), "an older shape"),
    (lambda d: d.update(schemaVersion=True), "a boolean is not the integer 2"),
    (lambda d: d.pop("judgedBy"), "no envelope"),
    (lambda d: d.update(judgedBy={}), "an envelope with nothing in it"),
    (lambda d: d["judgedBy"].update(rulesRun="M1"), "a string where a list belongs"),
    (lambda d: d["judgedBy"].update(rulesRun=["M1", 5]), "a member that is not a name"),
    (lambda d: d.update(notApplicable={"version": "M16.1"}), "a string of reasons"),
    (lambda d: d.pop("notApplicable"), "no reasons at all"),
    (lambda d: d.update(suppressed={"M1": -3}), "a negative count"),
    (lambda d: d.update(suppressed={"M1": "12"}), "a count that is text"),
    (lambda d: d.update(findings=[{"rule": None}]), "a finding with no rule"),
    (lambda d: d.update(findings={}), "findings that are not a list"),
    (lambda d: d.update(variant=None), "no profile"),
    (lambda d: d.update(ok="yes"), "a verdict that is not a verdict"),
])
def test_a_document_that_cannot_be_trusted_is_refused(clean, wreck, why):
    """Every one of these reached a class and produced a difference a reader
    would have acted on. A refusal is a sentence, never a traceback."""
    broken = copy.deepcopy(clean)
    wreck(broken)
    with pytest.raises(diff.Refused) as refusal:
        diff.difference(broken, clean)
    assert str(refusal.value), why


def test_a_finding_from_a_rule_the_document_says_never_ran_is_refused(clean):
    """This build's own reports satisfy it. A stored one is somebody's file."""
    forged = copy.deepcopy(clean)
    forged["findings"] = [dict(forged["findings"][0], rule="ZZ9")] if forged["findings"] else [
        {"rule": "ZZ9", "kind": "lint", "severity": "error", "priority": "MUST",
         "message": "invented", "subject": None, "detail": None}]
    with pytest.raises(diff.Refused):
        diff.difference(forged, clean)


def test_the_same_rule_in_two_reason_lists_is_refused(clean):
    forged = copy.deepcopy(clean)
    some = forged["notApplicable"]["unasked"][:1] or forged["notApplicable"]["variant"][:1]
    assert some, "this fixture must excuse at least one rule"
    forged["notApplicable"]["version"] = list(forged["notApplicable"]["version"]) + some
    with pytest.raises(diff.Refused):
        diff.difference(forged, clean)


def test_duplicate_keys_do_not_pass_as_the_last_one(clean, tmp_path):
    """`json.loads` keeps the last silently, so a file a person reads one way
    parses another. That is a forgery that survives being looked at."""
    text = json.dumps(clean)
    doubled = text[:-1] + ', "ok": false}'
    with pytest.raises(diff.Refused):
        diff.difference(diff.parse(doubled), clean)


def test_a_number_that_is_not_a_number_is_refused(clean):
    """`json.loads` accepts NaN and Infinity by default and writes them back
    out, which stops the output being JSON."""
    text = json.dumps(clean).replace('"findingsNotListed": 0', '"findingsNotListed": NaN')
    with pytest.raises(diff.Refused):
        diff.parse(text)


def test_a_document_too_large_to_be_a_report_is_refused():
    with pytest.raises(diff.Refused):
        diff.parse("[]" * 10, limit=4)


def test_a_document_nested_past_reading_is_refused():
    """Counted rather than caught. `json` raises `RecursionError`, which is
    not a `ValueError`, so the obvious guard misses it -- and how deep is too
    deep moved between interpreters: this file was refused on 3.9 and read
    without complaint on 3.12, so the suite was green here and red in CI.
    A guard whose answer depends on which Python is installed is not a guard.
    """
    deep = diff.MAX_DOCUMENT_DEPTH + 1
    with pytest.raises(diff.Refused):
        diff.parse("[" * deep + "]" * deep)


def test_a_report_is_not_refused_for_being_a_report():
    """The discriminating half: a limit low enough to catch the attack has to
    stay above the shape a real report has."""
    document = json.dumps({"a": [{"b": [{"c": 1}]}]})
    diff._refuse_if_deep(document)
    assert '"' in document


# ---------------------------------------------------------------------------
# The difference is itself an interface
# ---------------------------------------------------------------------------

#: Every key of the difference document, and what a consumer does with it.
DOCUMENT = {
    "schemaVersion",     # this contract's own number
    "comparable",        # whether the two runs were judged on the same basis
    "worse",             # the one question the exit code answers
    "okStored", "okHere",
    "banners",           # every way the basis moved, each with what to do
    "regression", "fixed",              # the causal register
    "startedFiring", "stoppedFiring",   # the neutral one
    "stillFiring", "newlyChecked", "noLongerChecked",
}
ROW = {"rule", "reason", "stored", "here", "readByCount", "gone", "arrived"}
BANNER = {"what", "stored", "here", "remedy"}


def test_the_difference_document_carries_exactly_these_keys(make_package, clean):
    """A consumer's parser survives a new key and does not survive a renamed
    one, so growth is cheap and change is not -- the same argument the report
    makes, and the difference is as much of an interface: a build stores it,
    a dashboard parses it, an exit code gates a merge."""
    broken = report_for(make_package(metadata=two_formats(MINIMAL_RDF)))
    document = diff.difference(clean, broken).as_dict()
    assert set(document) == DOCUMENT
    assert document["schemaVersion"] == diff.SCHEMA_VERSION
    seen = [row for key in ("regression", "fixed", "startedFiring", "stoppedFiring",
                            "stillFiring", "newlyChecked", "noLongerChecked")
            for row in document[key]]
    assert seen, "this fixture must produce rows to pin them"
    for row in seen:
        assert set(row) == ROW, row


def test_every_row_and_banner_reaches_the_page(make_package, clean):
    """The report can afford a text that leaves out the envelope; a
    difference cannot afford a text that leaves out a reason, or the note that
    a rule was read by count, or a banner. Held as a property over both forms
    rather than against a golden file."""
    import io

    linted = report_for(make_package(metadata=without_title(MINIMAL_RDF)),
                        runner.LINT_KINDS)
    answer = diff.difference(clean, linted)
    document = answer.as_dict()
    rendered = io.StringIO()
    diff.render_text(answer, rendered)
    text = rendered.getvalue()

    assert document["banners"], "this fixture must move the basis"
    for banner in document["banners"]:
        assert banner["what"] in text, banner["what"]
        assert banner["remedy"] in text, banner["remedy"]
    for key, _heading in diff.HEADINGS:
        for row in document[key]:
            assert row["rule"] in text, (key, row["rule"])
            if row["reason"]:
                assert row["reason"] in text, row


def test_the_difference_is_the_same_document_whatever_the_hash_seed(tmp_path, make_package):
    """A union of two rule lists is a set, and iterating one is how the report
    itself came to depend on the seed a process starts with. "The same package
    twice gives an empty difference" cannot catch it: every ordering of an
    empty list is the same list."""
    import os
    import subprocess
    import sys

    good = make_package(metadata=MINIMAL_RDF)
    bad = make_package(metadata=two_formats(MINIMAL_RDF))
    # Two commands, so the difference carries hundreds of rows in several
    # classes. One row cannot be out of order with itself: a fixture that
    # produces a single row lets a set-iterated union pass.
    script = (
        "import io, json, sys;"
        "sys.path[:0] = [%r];"
        "from iirds_validate import difference, runner;"
        "a = runner.run(%r, runner.CONFORMANCE_KINDS).as_dict();"
        "b = runner.run(%r, runner.LINT_KINDS).as_dict();"
        "answer = difference.difference(a, b);"
        "out = io.StringIO();"
        "difference.render_text(answer, out);"
        "print(json.dumps(answer.as_dict(), sort_keys=True));"
        "print(out.getvalue())"
        % (str(ROOT / "src"), str(good), str(bad)))
    seen = set()
    for seed in ("0", "1", "2", "3", "4", "5", "6", "7"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, "-c", script], env=env,
                             capture_output=True, text=True, check=True).stdout
        assert '"noLongerChecked"' in out and out.count("      ") > 50, out[:400]
        seen.add(out)
    assert len(seen) == 1, "%d distinct differences across eight seeds" % len(seen)
