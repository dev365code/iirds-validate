"""What judged this report, and the four ways that question was answered wrong.

A stored report is read next quarter against a run of a later build. If the
report cannot say *which* rules answered, a rule that did not exist in the
first run is indistinguishable from a rule that changed its answer, and the
difference tells somebody they broke a package they never touched.

So `judgedBy` records the build, what was asked of it, and the rules that
answered. The whole value of that list is that it is exactly right, and this
file is mostly about the places it was not:

* a rule that raised was counted as having answered, next to the finding
  that exists to say it answered nothing;
* rules the runner reports itself produced findings while the list said they
  never ran;
* a fragment suspended four rules and the list called them clean.

The last section is about the digest, and half of it pins what the digest
*cannot* see. A limitation nobody wrote down becomes a promise the next
feature is built on.
"""
from __future__ import annotations

import dataclasses

import pytest

import iirds_validate
from conftest import MINIMAL_RDF
from iirds_validate import model, registry, runner
from iirds_validate.model import Rule, Severity, Violation


def report_of(make_package, kinds=None, metadata=None):
    if metadata is None:
        metadata = MINIMAL_RDF.replace("<iirds:title>A topic</iirds:title>", "")
    return runner.run(make_package(metadata=metadata), kinds or runner.ALL_KINDS)


def replace_rule(monkeypatch, rule_id, **changes):
    """One rule, changed, for the length of one test.

    `_registry` is module state every other test reads, so the replacement
    goes in through monkeypatch and comes back out; `Rule` is frozen, so
    `dataclasses.replace` is the only way to vary one and cannot damage the
    original.
    """
    registry._ensure_registered()
    original = registry._registry[rule_id]
    monkeypatch.setitem(registry._registry, rule_id,
                        dataclasses.replace(original, **changes))
    return original


# ---------------------------------------------------------------------------
# The list, and what "ran" is allowed to mean
# ---------------------------------------------------------------------------

def test_the_list_and_the_count_are_one_fact(make_package):
    """`rulesChecked` is `len(rulesRun)`, so the two cannot drift -- and the
    list carries no rule twice, which a count alone would hide."""
    document = report_of(make_package).as_dict()
    ran = document["judgedBy"]["rulesRun"]
    assert len(ran) == len(set(ran)), sorted({r for r in ran if ran.count(r) > 1})
    assert len(ran) == document["summary"]["rulesChecked"]


def test_a_rule_that_raised_is_not_listed_as_having_answered(make_package, monkeypatch):
    """`rules/system.py` on S3: "A rule that raised has checked nothing, and
    this finding exists so that its silence is not read as a pass." The count
    was incremented before the rule was called, so the report said it had
    checked it anyway -- and a difference across the release that fixed the
    crash would read the rule's findings as newly broken."""
    def boom(ctx):
        raise RuntimeError("mutation")

    replace_rule(monkeypatch, "M1", fn=boom)
    document = report_of(make_package).as_dict()
    ran = document["judgedBy"]["rulesRun"]
    assert "M1" not in ran
    assert "S3" in ran, "the rule that reports the crash did answer"
    assert any(f["rule"] == "S3" for f in document["findings"])


def test_a_rule_that_raised_takes_its_half_answer_with_it(make_package, monkeypatch):
    """A rule that yields and then raises leaves a list of findings that reads
    exactly like a complete one, and nothing in the report says it was cut
    short except an S3 several lines away. The verdict is withdrawn whole."""
    def one_then_boom(ctx):
        yield Violation("first", subject="urn:x")
        raise RuntimeError("mutation")

    replace_rule(monkeypatch, "M1", fn=one_then_boom)
    document = report_of(make_package).as_dict()
    assert not [f for f in document["findings"] if f["rule"] == "M1"]
    assert "M1" not in document["judgedBy"]["rulesRun"]
    assert document["notApplicable"]["raised"] == ["M1"]


def test_every_rule_considered_is_in_exactly_one_place(make_package, monkeypatch):
    """`ran` and the reasons in `notApplicable` partition what a run looked
    at. Without that, "did this rule run?" has a third answer -- silence --
    and silence is what a difference reads as "the rule was fine"."""
    def boom(ctx):
        raise RuntimeError("mutation")

    replace_rule(monkeypatch, "M1", fn=boom)
    document = report_of(make_package).as_dict()
    ran = document["judgedBy"]["rulesRun"]
    excused = [rid for ids in document["notApplicable"].values() for rid in ids]
    assert not (set(ran) & set(excused)), sorted(set(ran) & set(excused))
    assert len(excused) == len(set(excused))
    # `ALL_KINDS` names every kind there is, so this run considered the whole
    # registry and the partition can be stated exactly rather than as a
    # subset -- which is the difference between a gate and a restatement.
    considered = set(ran) | set(excused)
    assert considered == registry.implemented_ids(), (
        sorted(registry.implemented_ids() ^ considered))


def test_every_rule_that_produced_a_finding_is_named_as_having_answered(make_package):
    """The runner answers some questions itself -- an unreadable container,
    metadata that will not parse under `lint`, a rule that crashed -- and
    those findings carry a rule id that never went through the loop. A reader
    who finds a rule in `findings` and not in `rulesRun` cannot tell which of
    the two is lying."""
    for kinds in (runner.CONFORMANCE_KINDS, runner.LINT_KINDS, runner.ALL_KINDS):
        document = report_of(make_package, kinds, metadata="<not xml").as_dict()
        ran = set(document["judgedBy"]["rulesRun"])
        reported = {f["rule"] for f in document["findings"]}
        assert reported <= ran, (sorted(reported - ran), kinds)


def test_a_report_from_an_unreadable_path_says_what_answered(make_package):
    document = runner.run("/nonexistent/nowhere.iirds", runner.ALL_KINDS).as_dict()
    assert document["judgedBy"]["rulesRun"] == [f["rule"] for f in document["findings"]]
    assert document["judgedBy"]["ruleSetDigest"] is not None, (
        "the report most likely to be stored and re-run is the one that failed "
        "to open; it is also the one where the build cannot be inferred")


def test_a_suspended_rule_did_not_judge_the_fragment(tmp_path):
    """`--fragment` runs four rules and then deletes their findings, because a
    snippet cannot satisfy them. Reporting them as run-and-clean puts them in
    a difference against a whole package as rules that suddenly broke."""
    fragment = tmp_path / "metadata.rdf"
    fragment.write_text(MINIMAL_RDF, "utf-8")
    document = runner.run_fragment(fragment, runner.ALL_KINDS).as_dict()
    ran = set(document["judgedBy"]["rulesRun"])
    assert not (ran & runner.FRAGMENT_SUSPENDED), sorted(ran & runner.FRAGMENT_SUSPENDED)
    assert set(document["notApplicable"]["fragment"]) == set(runner.FRAGMENT_SUSPENDED)


def excused(document) -> dict:
    """rule id -> the reason this run gives for not answering it."""
    return {rule_id: reason
            for reason, ids in document["notApplicable"].items() for rule_id in ids}


def test_the_account_is_total_whatever_the_command_asked(make_package):
    """Every rule this build has is either answered or excused with a reason,
    for each of the three commands.

    Held for `all` since the envelope landed, and that was the only shape it
    held for: `check` left the fourteen lint rules in neither list and `lint`
    left two hundred and four. A rule in neither is a rule a later difference
    has to guess about -- and the guess it would make, "the two builds have
    different rules", is wrong in the most alarming direction available.
    """
    for kinds in (runner.CONFORMANCE_KINDS, runner.LINT_KINDS, runner.ALL_KINDS):
        document = report_of(make_package, kinds).as_dict()
        accounted = set(document["judgedBy"]["rulesRun"]) | set(excused(document))
        assert accounted == registry.implemented_ids(), (
            kinds, sorted(registry.implemented_ids() - accounted))


def test_a_container_that_could_not_be_opened_still_accounts_for_every_rule():
    """The report a reader is most likely to keep and re-run, and the one
    that used to name one rule and say nothing about the other two hundred."""
    document = runner.run("/nonexistent/nowhere.iirds", runner.ALL_KINDS).as_dict()
    accounted = set(document["judgedBy"]["rulesRun"]) | set(excused(document))
    assert accounted == registry.implemented_ids()
    assert set(document["notApplicable"]["unreadable"]), "the reason has to be named"


def test_a_rule_is_excused_once_and_for_one_reason(tmp_path):
    """`--fragment` withdraws four rules, and under `lint` two of them were
    never put in the first place. Filing them under `fragment` as well as
    `unasked` left the same rule in two lists, so the reason a difference
    prints for it depends on which key the parse happened to see last, and
    the summary counted them as suspended when nobody had asked them.
    """
    fragment = tmp_path / "metadata.rdf"
    fragment.write_text(MINIMAL_RDF, "utf-8")
    document = runner.run_fragment(fragment, runner.LINT_KINDS).as_dict()
    reasons = document["notApplicable"]
    twice = {rule_id: [r for r, ids in reasons.items() if rule_id in ids]
             for ids in reasons.values() for rule_id in ids}
    assert not [r for r, where in twice.items() if len(where) > 1], twice
    assert (document["summary"]["rulesChecked"] + document["summary"]["rulesSkipped"]
            + sum(len(reasons[r]) for r in model.NOT_IN_PLAY)
            == len(registry.implemented_ids()))


def test_the_runners_own_questions_are_in_play_whatever_the_container_did(tmp_path):
    """Under `lint` the runner asks three questions the rule loop does not,
    and a container that will not open means it never got to ask them. That
    is `unreadable`, not `unasked`: nobody stopped asking them, the container
    stopped being readable. A difference reading `unasked` would tell somebody
    they had typed a different command."""
    document = runner.run(tmp_path / "nowhere.iirds", runner.LINT_KINDS).as_dict()
    reasons = document["notApplicable"]
    for rule_id in runner.METADATA_ANSWERED:
        assert rule_id in reasons["unreadable"], (rule_id, reasons)


def test_a_clean_lint_run_names_the_rules_the_runner_answers_itself(make_package):
    """`lint` does not run the container rules, so the runner answers three
    of their questions itself -- did each metadata file parse. It recorded
    them only when the answer was no, which makes a clean answer
    unrepresentable and every failure an arrival rather than a change."""
    document = report_of(make_package, runner.LINT_KINDS,
                         metadata=MINIMAL_RDF).as_dict()
    ran = set(document["judgedBy"]["rulesRun"])
    assert set(runner.METADATA_ANSWERED) <= ran, sorted(set(runner.METADATA_ANSWERED) - ran)
    assert not [f for f in document["findings"] if f["rule"] in runner.METADATA_ANSWERED]


def test_breaking_the_metadata_moves_a_rule_inside_the_list(make_package):
    """The whole point of the one above. A rule that goes from clean to
    firing is a regression; a rule that goes from absent to firing is news,
    and a difference must not be able to confuse the two because the report
    could not say the rule had been clean."""
    clean = report_of(make_package, runner.LINT_KINDS, metadata=MINIMAL_RDF).as_dict()
    broken = report_of(make_package, runner.LINT_KINDS, metadata="<not xml").as_dict()
    fired = {f["rule"] for f in broken["findings"]} & set(runner.METADATA_ANSWERED)
    assert fired, "this fixture must make one of them fire"
    for rule_id in fired:
        assert rule_id in clean["judgedBy"]["rulesRun"], rule_id
        assert rule_id in broken["judgedBy"]["rulesRun"], rule_id
        assert rule_id not in {f["rule"] for f in clean["findings"]}


def test_the_rules_that_did_not_run_are_the_reason_they_did_not(make_package):
    """`rulesSkipped` is read off `notApplicable` rather than counted beside
    it -- the same argument as the list above, one field down."""
    document = report_of(make_package).as_dict()
    reasons = document["notApplicable"]
    # Two identities. What this command put to the package is checked plus
    # skipped; every rule the build has is that plus the ones nobody put.
    in_play = sum(len(ids) for reason, ids in reasons.items()
                  if reason not in model.NOT_IN_PLAY)
    assert document["summary"]["rulesSkipped"] == in_play
    assert (document["summary"]["rulesChecked"] + document["summary"]["rulesSkipped"]
            + sum(len(reasons[reason]) for reason in model.NOT_IN_PLAY)
            == len(registry.implemented_ids()))
    ran = set(document["judgedBy"]["rulesRun"])
    for reason, ids in reasons.items():
        assert not (ran & set(ids)), (reason, sorted(ran & set(ids)))


def test_every_rule_named_ran_is_a_rule_this_build_has(make_package):
    """`_emitted` falls back to building a Rule out of the catalogue when an
    id is not registered. Today nothing reaches that branch; if something did,
    `rulesRun` would name a rule the digest does not cover."""
    ran = set(report_of(make_package).as_dict()["judgedBy"]["rulesRun"])
    assert ran <= registry.implemented_ids(), sorted(ran - registry.implemented_ids())


# ---------------------------------------------------------------------------
# The envelope's other three fields
# ---------------------------------------------------------------------------

def test_the_tool_version_is_the_source_tree_that_ran(make_package):
    """Not `importlib.metadata.version(...)`, which answers about whichever
    copy was last installed on this machine, and not the alias distribution's
    -- a test pins those two equal, so importing the wrong one would be
    invisible for good."""
    assert (report_of(make_package).as_dict()["judgedBy"]["toolVersion"]
            == iirds_validate.__version__)


def test_the_kinds_say_which_command_was_asked(make_package):
    for kinds in (runner.CONFORMANCE_KINDS, runner.LINT_KINDS, runner.ALL_KINDS):
        document = report_of(make_package, kinds).as_dict()
        assert document["judgedBy"]["kinds"] == list(kinds)


def test_one_build_answers_with_one_digest_whatever_was_asked(make_package):
    """The digest identifies the build's rules, not the invocation. An
    implementation that hashed only the rules a command selected would pass
    every axis below while making a stored `check` report and a stored `lint`
    report from one release incomparable."""
    digests = {report_of(make_package, kinds).as_dict()["judgedBy"]["ruleSetDigest"]
               for kinds in (runner.CONFORMANCE_KINDS, runner.LINT_KINDS, runner.ALL_KINDS)}
    assert digests == {registry.rule_set_digest()}


#: Every argument of `run()` except the package itself, and where the report
#: writes down what it was given. A run's answer is a function of the package
#: and of these; an argument that is not written down is an axis on which two
#: reports can differ with nothing in either of them saying so, and a
#: difference between them then attributes the change to the package.
#:
#: `version` is recorded as its outcome rather than as the request:
#: `validatedAgainst` is the edition the rules actually ran against, which is
#: what a later reader needs. The profile is not here because it is not an
#: argument -- the package declares it, and the report carries it at the top
#: level as `variant`.
AXES = {
    "kinds": lambda doc: doc["judgedBy"]["kinds"],
    "version": lambda doc: doc["validatedAgainst"],
    "include_info": lambda doc: doc["judgedBy"]["includesInfo"],
}


def test_nothing_stands_in_front_of_the_runner():
    """The suite replaces `run`, `check` and `lint` to record what fired.

    A replacement that does not carry the function it stands for answers
    `(*args, **kwargs)` to anything that asks the runner about itself, and the
    gate below would then be reading the harness rather than the code. Held
    separately so the two failures have two names: that one going red must
    mean an argument is unrecorded, not that something got in the way.
    """
    import inspect

    for name in ("run", "check", "lint"):
        stands_there = getattr(runner, name)
        assert stands_there.__module__ == "iirds_validate.runner", (
            name, stands_there.__module__)
        assert stands_there.__qualname__ == name, (name, stands_there.__qualname__)
        assert inspect.unwrap(stands_there).__code__.co_filename.endswith("runner.py"), name


def test_every_argument_that_shapes_a_report_is_written_down_in_it(make_package):
    """The list above is the whole state space, and this is what holds it
    closed: add an argument to `run()` and this goes red until the report
    says what it was given."""
    import inspect

    arguments = [name for name in inspect.signature(inspect.unwrap(runner.run)).parameters
                 if name != "path"]
    assert set(arguments) == set(AXES), sorted(set(arguments) ^ set(AXES))

    document = report_of(make_package).as_dict()
    for name, read in AXES.items():
        assert read(document) is not None, name


def test_dropping_the_quiet_findings_is_recorded(make_package):
    """`include_info` throws away every INFO finding. A run that dropped them
    and a run that did not are two different questions, and comparing them
    reports every INFO rule as fixed."""
    package = make_package(metadata=MINIMAL_RDF.replace(
        "<iirds:title>A topic</iirds:title>", ""))
    for asked in (True, False):
        document = runner.run(package, runner.ALL_KINDS, include_info=asked).as_dict()
        assert document["judgedBy"]["includesInfo"] is asked


# ---------------------------------------------------------------------------
# The digest: what moves it
# ---------------------------------------------------------------------------

def a_rule(**changes) -> Rule:
    base = {"id": "X1", "kind": "schema", "prio": "MUST", "title": "a rule",
            "versions": ("1.3",), "variants": (), "spec": None, "fn": lambda ctx: ()}
    base.update(changes)
    return Rule(**base)


#: Two rules, by hand, and what they hash to. Every other test here is
#: relative -- "moves when X moves", "does not move when Y moves" -- and every
#: one of them stays green if the fields are reordered or one is dropped and
#: added back, which silently changes the digest of every report ever stored.
#: This is a pure function of a fixed input, so it never needs updating when
#: the rules change, and an algorithm change arrives as a diff somebody reads.
PINNED = [a_rule(), a_rule(id="B1", kind="lint", prio="SHOULD", variants=("A",))]
PINNED_DIGEST = "sha256:d8b50d8aa5c78825988c98f5fca45e8c9c35de284f20161df403e04896c92c54"


def test_the_digest_of_a_known_rule_set_is_this_string():
    assert registry.rule_set_digest(PINNED) == PINNED_DIGEST


@pytest.mark.parametrize("changes", [
    {"kind": "lint"},
    {"prio": "RECOMMENDED"},
    {"versions": ("1.0", "1.3")},
    {"variants": ("A",)},
    {"conformance": True},
])
def test_a_changed_identity_moves_the_digest(changes):
    """One axis at a time, so a failure names the axis."""
    assert registry.rule_set_digest([a_rule(**changes)]) != registry.rule_set_digest([a_rule()])


def test_a_rule_added_or_removed_moves_the_digest():
    one = registry.rule_set_digest([a_rule()])
    assert registry.rule_set_digest(PINNED) != one
    assert registry.rule_set_digest([]) != one


def test_the_digest_does_not_depend_on_the_order_the_rules_arrive_in():
    assert registry.rule_set_digest(PINNED) == registry.rule_set_digest(list(reversed(PINNED)))


def test_two_spellings_of_one_severity_are_one_digest():
    """MUST, MUST NOT, REQUIRED and SHALL all produce an error. Hashing the
    keyword would refuse to compare two reports over a difference no verdict
    can express, every time the catalogue is re-extracted."""
    assert a_rule(prio="REQUIRED").severity is Severity.ERROR
    assert (registry.rule_set_digest([a_rule(prio="REQUIRED")])
            == registry.rule_set_digest([a_rule(prio="MUST")]))


def test_an_id_the_catalogue_mints_is_not_the_same_rule(monkeypatch):
    """`B*`, `L*` and `S4`-`S8` share an identifier namespace with the
    catalogue; every finding carries a `source` for exactly this reason. A
    stored report cannot be repaired after the fact, so if the catalogue ever
    mints a real `B1` this digest must move and the comparison must stop
    rather than quietly treat two rules as one."""
    ours = a_rule(id="B1")
    assert "B1" not in registry.CATALOG
    before = registry.rule_set_digest([ours])
    monkeypatch.setitem(registry.CATALOG, "B1", {"kind": "lint", "prio": "MUST"})
    assert registry.rule_set_digest([ours]) != before


# ---------------------------------------------------------------------------
# The digest: what it cannot see
#
# Each of these is a fact, not a caveat. A difference view built on "the same
# digest means the same judgement" is built on a promise this string does not
# make, and prose in a docstring has never stopped anybody.
# ---------------------------------------------------------------------------

def test_a_rewritten_rule_body_leaves_the_digest_where_it_was():
    assert (registry.rule_set_digest([a_rule(fn=lambda ctx: ())])
            == registry.rule_set_digest([a_rule(fn=lambda ctx: iter(()))]))


def test_the_runners_own_policy_is_outside_the_digest(monkeypatch):
    """Which rules an unpacked container cannot answer, which a fragment
    suspends, and the run-time severity demotion are properties of the runner,
    not of any rule. The last one decides what severity a report prints for a
    rule whose identity never moved."""
    content_rule = a_rule(kind="content", prio="MUST")
    assert content_rule.severity is Severity.ERROR
    assert runner.severity_override(content_rule, "unrestricted") is Severity.WARNING
    assert runner.severity_override(content_rule, "A") is None

    before = registry.rule_set_digest()
    monkeypatch.setattr(runner, "ARCHIVE_ONLY", runner.ARCHIVE_ONLY + ("M1",))
    monkeypatch.setattr(runner, "FRAGMENT_SUSPENDED", frozenset())
    monkeypatch.setattr(runner, "severity_override", lambda rule, variant: None)
    assert registry.rule_set_digest() == before
