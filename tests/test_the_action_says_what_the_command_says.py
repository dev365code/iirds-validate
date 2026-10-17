"""The action says what the command says, byte for byte.

The action is a door, and a door adds nothing to a verdict: what the step may
add to a run it adds to `$GITHUB_OUTPUT`, and what it prints and returns is the
command's. `tools/action_parity.py` asks that of every input it assembles --
each file of the vendored corpus as the bare metadata file it is, each package
the fixture builder makes, and the cases that are about the door rather than the
package -- by running the command directly and the action's `check` step under
GitHub's bash, and comparing stdout, stderr and the exit code as bytes.

Here the code both run is this tree's, the way the step runs a release it has
installed, and the inputs are the ones about the door -- every fixture, the door
cases and report mode -- on every platform the suite runs on. The whole set,
the corpus with it, is `make check`'s and CI's: `tools/action_parity.py` over
this tree, and in CI over an installed release and over the single file too.
"""
from __future__ import annotations

import json
from collections import Counter

import pytest

import action_parity
from action_parity import ROOT
from make_fixture_package import BREAKAGE


@pytest.fixture(scope="module")
def assembled(tmp_path_factory):
    work = tmp_path_factory.mktemp("action-parity")
    return work, action_parity.inputs(work)


@pytest.fixture(scope="module")
def outcome(assembled):
    work, cases = assembled
    return action_parity.compare([case for case in cases if case.kind != "corpus"],
                                 action_parity.Installed(ROOT / "src"), work)


def test_the_action_says_what_the_command_says(outcome):
    assert outcome.differences == [], "\n".join(outcome.differences[:12])


def test_the_inputs_are_the_whole_corpus_and_every_fixture(assembled):
    """A comparison over nothing agrees with itself. The corpus is the manifest's
    list rather than a walk of the directory, and every kind of package the
    builder knows is built -- so a file that went missing is a smaller number
    here, not a quieter pass."""
    work, cases = assembled
    manifest = json.loads((ROOT / "tests" / "corpus" / "plusmeta" / "MANIFEST.json")
                          .read_text(encoding="utf-8"))
    kinds = Counter(case.kind for case in cases)
    assert sorted(c.paths[0] for c in cases if c.kind == "corpus") == sorted(
        "corpus/" + name for name in manifest["files"])
    assert kinds["corpus"] == 132
    assert {c.label for c in cases if c.kind == "fixture"} == {"fixture/" + k for k in BREAKAGE}
    assert kinds["door"] >= 12 and kinds["report"] >= 4
    assert all((work / path).is_file() for c in cases if c.kind in ("corpus", "fixture")
               for path in c.paths)


def test_every_input_here_was_asked(outcome):
    assert outcome.asked["fixture"] == len(BREAKAGE)
    assert outcome.asked["door"] >= 12
    assert outcome.asked["report"] >= 4


def test_every_code_the_command_line_defines_was_compared(outcome):
    """The step treats each code it passes on the same way, and a code no input
    produced is a branch nobody compared."""
    from iirds_validate import cli

    defined = {cli.EXIT_OK, cli.EXIT_FINDINGS, cli.EXIT_ERROR, cli.EXIT_USAGE}
    assert set(outcome.codes) == defined, outcome.codes


#: A step changed the way a mistake would change it, and the cases that show it.
#: Each must come back as a difference; a comparison that cannot fail is the
#: thing this file would otherwise be. The anchors are the script as YAML hands
#: it over, from the margin, not as it is indented in `action.yml`.
MISTAKES = {
    "it prints a line of its own":
        ("\nrc=0\n", '\necho "checked by the action"\nrc=0\n', "fixture/none"),
    "it says something on stderr":
        ("\nrc=0\n", '\necho "note" >&2\nrc=0\n', "fixture/none"),
    "it swallows the checker's stderr":
        ('\n"$@" || rc=$?\n', '\n"$@" 2>/dev/null || rc=$?\n', "door/a path that names nothing"),
    "it flattens the code":
        ('\nexit "$rc"\n', "\nexit $(( rc != 0 ))\n", "door/a command line the checker refuses"),
    "it publishes a code that is not the checker's":
        ('\necho "exit-code=$rc" >> "$GITHUB_OUTPUT"\n',
         '\necho "exit-code=0" >> "$GITHUB_OUTPUT"\n', "fixture/missing-format"),
    "it drops the last path":
        ('\nset -- "$@" $PATHS\n', '\nset -- "$@" $PATHS\nset -- "${@:1:$(($#-1))}"\n',
         "door/two packages on one line"),
    "it says nothing in report mode":
        ('\n  echo "iirds returned $rc; the step is not failing because fail-on-finding is false"\n',
         "\n", "report/fixture/missing-format"),
}


@pytest.mark.parametrize("mistake", sorted(MISTAKES))
def test_a_step_that_changes_the_run_is_caught(tmp_path, mistake):
    original, changed, label = MISTAKES[mistake]
    step = action_parity.check_step()
    assert step.count(original) == 1, "the anchor for %r is not in the step once" % mistake
    cases = [case for case in action_parity.inputs(tmp_path) if case.label == label]
    assert len(cases) == 1, "no case is labelled %r" % label
    door = action_parity.Installed(ROOT / "src")
    honest = action_parity.compare(cases, door, tmp_path)
    assert honest.differences == [], honest.differences
    caught = action_parity.compare(cases, door, tmp_path, step=step.replace(original, changed))
    assert caught.differences, "%s, and the comparison saw no difference" % mistake


def test_the_codes_counted_are_the_codes_returned(tmp_path):
    """The counter the code assertion above reads is filled by the comparison
    itself, one per case -- not by the list of codes it was told to expect."""
    cases = [case for case in action_parity.inputs(tmp_path)
             if case.label in ("fixture/none", "fixture/missing-format")]
    seen = action_parity.compare(cases, action_parity.Installed(ROOT / "src"), tmp_path)
    assert seen.codes == Counter({0: 1, 1: 1}), seen.codes
