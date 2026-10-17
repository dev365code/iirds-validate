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


def _carried(where):
    """The other door, without building the release file: a zip application in
    the checker's own layout whose `__main__.py` runs this tree's command line.
    What is compared is the step's handling of a carried file -- the check that
    it is one, the run, the `pyz` it publishes -- not the file's contents."""
    import zipfile

    path = where / "iirds.pyz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("__main__.py", "import sys\nsys.path.insert(0, %r)\n"
                         "from iirds_validate.cli import main\nsys.exit(main())\n" % str(ROOT / "src"))
        archive.writestr("iirds_validate/__init__.py", "")
    return action_parity.Carried(path)


@pytest.fixture(scope="module")
def outcome_carried(assembled):
    work, cases = assembled
    return action_parity.compare([case for case in cases if case.kind in ("door", "report")],
                                 _carried(work), work)


def test_the_action_says_what_the_command_says(outcome):
    assert outcome.differences == [], "\n".join(outcome.differences[:12])


def test_through_a_carried_file_too(outcome_carried):
    assert outcome_carried.differences == [], "\n".join(outcome_carried.differences[:12])
    assert outcome_carried.asked["door"] == len(DOOR)


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
    # Every file of the corpus as the bare metadata file it is: without
    # `--fragment` the comparison would be of a refusal, not of a reading.
    assert all(c.args == ["--fragment"] for c in cases if c.kind == "corpus")
    # The door cases by name, not by number: a count is satisfied by a case
    # swapped for an easier one.
    assert {c.label for c in cases if c.kind == "door"} == {"door/" + label for label in DOOR}
    assert {c.label for c in cases if c.kind == "report"} == {"report/" + label for label in REPORTED}
    assert all((work / path).is_file() for c in cases if c.kind in ("corpus", "fixture")
               for path in c.paths)
    # And the cases are the shape their names say: the name like a pattern has
    # a file beside it that the pattern would match, and the dash is a dash.
    by = {c.label: c for c in cases}
    assert (work / "patterned" / "a1.iirds").is_file()
    assert by["door/a name that looks like a pattern"].paths == ["patterned/a[1].iirds"]
    assert by["door/a path that begins with a dash"].paths[0].startswith("-")
    assert any(" " in p for p in by["door/two packages in block form"].paths)
    assert len(by["door/two packages in block form"].paths) == 2


#: The door cases, by name -- what the step does with what it is handed.
DOOR = {
    "a directory of packages", "two packages on one line", "a name with a space in it",
    "a name that looks like a pattern", "a path that names nothing",
    "a path that begins with a dash", "two packages in block form",
    "a command line the checker refuses", "the report as JSON", "the exit code only",
    "the spec links", "warnings fail the run", "interoperability", "both judgements",
}
#: The cases asked again in report mode.
REPORTED = {"fixture/none", "fixture/missing-format", "door/a path that names nothing",
            "door/a command line the checker refuses"}


def test_every_input_here_was_asked(outcome):
    assert outcome.asked["fixture"] == len(BREAKAGE)
    assert outcome.asked["door"] == len(DOOR)
    assert outcome.asked["report"] == len(REPORTED)


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
    "it adds a blank line at the end":
        ('\nexit "$rc"\n', '\necho\nexit "$rc"\n', "fixture/none"),
    "it writes to the job's environment":
        ('\n  export PYTHONPATH="$TARGET"\n',
         '\n  export PYTHONPATH="$TARGET"\n  echo "PYTHONPATH=$TARGET" >> "$GITHUB_ENV"\n', "fixture/none"),
    "it publishes a pyz it did not run":
        ('\necho "exit-code=$rc" >> "$GITHUB_OUTPUT"\necho "pyz=$PYZ" >> "$GITHUB_OUTPUT"\n',
         '\necho "exit-code=$rc" >> "$GITHUB_OUTPUT"\necho "pyz=" >> "$GITHUB_OUTPUT"\n',
         "carried/door/the exit code only"),
}


@pytest.mark.parametrize("mistake", sorted(MISTAKES))
def test_a_step_that_changes_the_run_is_caught(tmp_path, mistake):
    original, changed, label = MISTAKES[mistake]
    step = action_parity.check_step()
    assert step.count(original) == 1, "the anchor for %r is not in the step once" % mistake
    carried = label.startswith("carried/")
    label = label[len("carried/"):] if carried else label
    cases = [case for case in action_parity.inputs(tmp_path) if case.label == label]
    assert len(cases) == 1, "no case is labelled %r" % label
    door = _carried(tmp_path) if carried else action_parity.Installed(ROOT / "src")
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
