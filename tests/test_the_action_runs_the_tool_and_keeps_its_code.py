"""The action is a door, not a second implementation.

One engine, several entrances: a terminal, an import, a single file, a local
page, and a workflow step. An entrance earns its place by passing the same
verdict through unchanged -- so what this file holds `action.yml` to is that it
runs the tool, hands the tool the caller's arguments without letting them become
commands, and returns the code the tool returned rather than a flattened success
or failure. What the step prints and returns, run, is
`tests/test_the_action_says_what_the_command_says.py`; this reads the file.

It reads the file with `tools/action_parity.py`'s reader, because pyyaml is not
a dependency of this project; the reader refuses a shape it does not know, and
CI holds it to a YAML parser on every push.
"""
from __future__ import annotations

import re

import pytest

from action_parity import ACTION, ROOT, read_action

WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def action():
    return read_action(ACTION.read_text(encoding="utf-8"))


def _step(action, name):
    return next(s for s in action.steps if s.id == name)


def test_the_file_is_written_the_way_its_reader_reads_it(action):
    """A tab or a trailing space is where a pattern and a YAML parser part ways
    -- a tab is not indentation to YAML at all -- so neither is allowed, and the
    reader has to find the two steps it expects, in order."""
    text = ACTION.read_text(encoding="utf-8")
    assert "\t" not in text, "a tab in action.yml"
    trailing = [n for n, line in enumerate(text.splitlines(), 1) if line != line.rstrip()]
    assert not trailing, "trailing whitespace on lines %s" % trailing
    assert [s.id for s in action.steps] == ["obtain", "check"]
    assert action.using == "composite"
    # YAML takes a literal block's indentation from its first line, so a script
    # read the way YAML reads it starts at the margin and no line of it is to
    # the left of that: the one property of the reading this file can ask
    # without a YAML parser.
    for step in action.steps:
        lines = [line for line in step.run.splitlines() if line.strip()]
        assert lines and not lines[0].startswith(" "), "%s is read with its indentation" % step.id
        assert step.run.endswith("\n") and not step.run.endswith("\n\n"), step.id


def test_the_action_uses_no_other_action(action):
    """Every step is a shell this file spells out. A `uses:` in here would run
    in other people's workflows at whatever its ref resolves to the day they run
    it -- the thing `tests/test_workflow_supply_chain.py` refuses in this
    repository's own workflows, done to somebody else's."""
    assert all(s.shell == "bash" and s.run for s in action.steps)
    assert not re.search(r"^\s*(-\s*)?uses:", ACTION.read_text(encoding="utf-8"), re.M)


def test_the_action_runs_the_checker_both_ways(action):
    body = _step(action, "check").run
    assert 'set -- "$PY" "$PYZ" "$COMMAND"' in body, "the single file you carried is never run"
    assert 'set -- "$PY" -m iirds_validate "$COMMAND"' in body, "the installed checker is never run"


def test_the_exit_code_reaches_the_job(action):
    """A step that returns success or failure loses the difference between "your
    package has errors" (1) and "your workflow is misspelt" (64). So the code is
    written to the step's outputs before the branch that can end the step, and
    the step's own status is that code unless the caller asked for a report."""
    body = _step(action, "check").run
    assert "exit-code=$rc" in body, "the code is not published as an output"
    assert re.search(r'exit "\$rc"', body), "the code is computed and then thrown away"
    assert action.outputs["exit-code"] == "${{ steps.check.outputs.exit-code }}"
    written, branched = body.index("exit-code=$rc"), body.index("fail-on-finding is false")
    assert written < branched, (
        "the code is written after the branch that can end the step, so the one "
        "case that needs it most -- a failure -- would not have it")


def test_the_gate_is_the_default(action):
    """An action that reports and stops nothing is decoration. Somebody who wants
    the reading asks for it; somebody who wants the gate types nothing."""
    assert action.inputs["fail-on-finding"].lower() == "true"


def test_no_expression_at_all_is_interpolated_into_a_shell_script(action):
    """`${{ inputs.paths }}` inside a `run:` makes a package name a place to put
    commands. Inputs travel as environment variables and are quoted where they
    are used, so a file called `; rm -rf ~` is a file, not a sentence -- and the
    rule is "no expressions", not "no inputs": `github.event.*` carries text
    strangers write."""
    offenders = [s.id for s in action.steps if "${{" in s.run]
    assert not offenders, "an expression is interpolated into the script of %s" % offenders


def test_only_the_install_step_can_reach_an_index(action):
    """The tool opens no socket for any input. The action may install the
    checker -- once, and only when it was not handed a file -- and nothing else
    here is allowed to make that promise smaller."""
    reaching = [s.id for s in action.steps if re.search(r"\bcurl\b|\bwget\b|pip install", s.run)]
    assert reaching == ["obtain"], "more than the install step reaches out: %s" % reaching
    assert _step(action, "obtain").if_ == "inputs.pyz == ''", (
        "the install runs even when the caller supplied the file, which is the one "
        "thing carrying your own copy is supposed to avoid")


def test_the_default_path_installs_the_release_by_its_name(action):
    """The index is what the release workflow publishes to by itself, so that is
    what the action leans on; `pyz:` remains for a runner that cannot reach an
    index at all."""
    install = _step(action, "obtain").run
    assert '"iirds==$version"' in install, "the install does not pin the version it resolved"
    assert "--only-binary :all:" in install, (
        "a source build on somebody else's runner is not this action's to ask for")
    assert "--target" in install, (
        "installing into the caller's environment changes a machine this action does not own")


def test_two_releases_in_one_job_do_not_share_a_directory(action):
    """`pip install --target` into a directory that already holds a release
    leaves that release there and says so in a warning -- so a second use of the
    action asking for another version would run the first. The directory is
    named for the version, and the check step runs what the install step left."""
    install = _step(action, "obtain").run
    assert re.search(r'target="\$\{RUNNER_TEMP:-/tmp\}/iirds-\$version"', install), install
    assert 'echo "target=$target" >> "$GITHUB_OUTPUT"' in install
    assert _step(action, "check").env.get("TARGET") == "${{ steps.obtain.outputs.target }}"


def test_the_verdicts_the_step_passes_on_are_the_codes_the_command_line_defines(action):
    """`cli.py` owns the exit codes, and two hand-written copies of one table
    drift. The step lets exactly those through as verdicts -- a code outside
    them means the checker did not run, and calling it a verdict would blame a
    package for it -- and the output's description names every one of them."""
    from iirds_validate import cli

    defined = {cli.EXIT_OK, cli.EXIT_FINDINGS, cli.EXIT_ERROR, cli.EXIT_USAGE}
    body = _step(action, "check").run
    passed = re.search(r"^\s*((?:\d+\|)*\d+)\)\s*;;\s*$", body, re.M)
    assert passed, "the step names no codes it passes on"
    assert {int(n) for n in passed.group(1).split("|")} == defined
    described = {int(n) for n in re.findall(r"\b(\d+)\b", action.output_descriptions["exit-code"])}
    assert defined <= described, "the output does not describe %s" % sorted(defined - described)


def test_the_verbs_it_offers_are_the_command_lines_verbs_that_judge(action):
    """`iirds <word>` reads a word that is not a verb as a path, so a misspelt
    `command:` would come back as 2, "could not run", about a package nobody
    named. The step therefore names the verbs it accepts and refuses the rest
    with 64 before Python is asked; and the verbs it names are verbs the parser
    has -- the three that judge a package."""
    from iirds_validate import cli

    body = _step(action, "check").run
    offered = re.search(r'case "\$COMMAND" in\s*\n\s*([a-z|]+)\)', body)
    assert offered, "the step does not say which verbs it accepts"
    verbs = set(offered.group(1).split("|"))
    assert verbs == {"check", "lint", "all"}
    assert verbs <= cli.subcommands()
    assert action.inputs["command"] == "check"


def test_every_input_is_described_where_a_user_would_look(action):
    """The front page is where somebody decides whether to use this, and an input
    that exists only in `action.yml` is an input nobody knows about. The section
    is found by its heading, and a heading that is gone fails rather than falling
    back to the whole page -- a gate with a fallback is a gate with an off switch."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    marker = "### In a workflow"
    assert marker in readme, "README has no %r section for the action" % marker
    section = readme.split(marker, 1)[1].split("\n## ", 1)[0]
    missing = [name for name in action.inputs if "`%s`" % name not in section]
    assert not missing, "the action's own section does not mention: %s" % missing
    missing = [name for name in action.outputs if "`%s`" % name not in section]
    assert not missing, "the action's own section does not mention the outputs: %s" % missing


def test_a_missing_checker_is_the_callers_mistake_and_says_so(action):
    """`pyz: dist/typo.pyz` must not come back as "could not run".

    CPython exits 2 when it cannot open the file it was given, and 2 is this
    tool's code for a package it could not read -- so a typo in the workflow
    would be reported as the supplier's package being unreadable. The step looks
    for the file and exits 64, the code for "you typed it wrong", first."""
    body = _step(action, "check").run
    guard = body.split('set -- "$PY" "$PYZ" "$COMMAND"')[0]
    assert '! -f "$PYZ"' in guard, "nothing checks that the checker is actually there"
    assert "exit 64" in guard, "a missing file does not come back as a usage error"


def test_a_carried_file_can_be_pinned_to_a_hash(action):
    """The default path is an index, and `pip` checks what an index serves. What
    is left unchecked is a file somebody carried in by hand, so the input that
    checks *that* stays."""
    assert "sha256" in action.inputs
    body = _step(action, "check").run
    assert "WANT_SHA" in body and ("sha256sum" in body or "shasum" in body), (
        "the hash input exists and nothing checks it")


def test_the_checker_is_allowed_to_fail_without_ending_the_step(action):
    """GitHub runs `shell: bash` as `bash --noprofile --norc -e -o pipefail`.

    A bare call that exits non-zero therefore ends the step where it stands, and
    every line after it -- the output, the branch, the message -- is never
    reached. `set -uo pipefail` does not turn the `-e` off."""
    body = _step(action, "check").run
    call = next(line for line in body.splitlines() if line.strip().startswith('"$@"'))
    assert call.rstrip().endswith("|| rc=$?"), (
        "the checker is called in a way errexit would end the step on: %r" % call)
    assert "rc=0" in body.split(call)[0], "rc is read before it is ever set"


def _job(name):
    """One job's block of ci.yml, by the two-space indent under `jobs:`."""
    text = WORKFLOW.read_text(encoding="utf-8").split("\njobs:\n", 1)[1]
    found = re.search(r"^  %s:\n(.*?)(?=^  [\w-]+:\n|\Z)" % re.escape(name), text, re.M | re.S)
    assert found, "ci.yml has no job %r" % name
    return found.group(1)


def _shells(block):
    """Every `run:` script in a job's block: a `run: |` block, or one line."""
    lines = block.split("\n")
    for at, line in enumerate(lines):
        head = re.match(r"^(\s*)(?:-\s*)?run:\s*(.*)$", line)
        if not head:
            continue
        if head.group(2) != "|":
            yield head.group(2)
            continue
        indent = len(head.group(1))
        body = []
        for later in lines[at + 1:]:
            if later.strip() and len(later) - len(later.lstrip()) <= indent:
                break
            body.append(later)
        yield "\n".join(body)


def test_the_repository_uses_its_own_action_every_way_it_can_be_used():
    """An action nobody runs is a README section. CI runs it on every push: with
    a file it built and nothing fetched, on a package that must fail, in report
    mode, against a release it installs -- and then holds every input to the
    command, through this tree, that release and the single file."""
    job = _job("the-action-this-repo-offers")
    assert job.count("uses: ./\n") >= 4, "the action is used fewer times than its paths"
    assert "pyz: dist/iirds.pyz" in job, "the carried-file path is never taken"
    assert "version: ${{ steps.newest.outputs.version }}" in job, "the install path is never taken"
    assert "continue-on-error: true" in job, "nothing checks that errors fail the step"
    assert 'fail-on-finding: "false"' in job, "report mode is never exercised"
    compared = "\n".join(_shells(job))
    for door in ("tools/action_parity.py --require-yaml\n",
                 'tools/action_parity.py --require-yaml --target "$RUNNER_TEMP/iirds-$WANT"',
                 "tools/action_parity.py --require-yaml --pyz dist/iirds.pyz"):
        assert door in compared, "CI does not compare the step with the command: %s" % door


def test_the_shortest_example_runs_on_a_runner_as_it_comes():
    """The README's example is `uses:` and `paths:`. Every other use here comes
    after `setup-python` and a build, so the line a reader copies would be the
    one nothing ran."""
    job = _job("the-action-on-a-runner-as-it-comes")
    assert "uses: ./\n" in job and "setup-python" not in job


def test_the_workflow_only_interpolates_things_it_wrote_itself():
    """The rule `action.yml` keeps, where this repository uses it: a step's own
    outcome and outputs are this workflow's, anything else -- `github.event.*`
    above all -- is somebody else's text and has no business in a shell."""
    allowed = re.compile(r"^steps\.[\w-]+\.(outcome|outputs\.[\w-]+)$")
    bad = []
    for name in ("the-action-this-repo-offers", "the-action-on-a-runner-as-it-comes"):
        for script in _shells(_job(name)):
            bad += [(name, e) for e in re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", script)
                    if not allowed.match(e)]
    assert not bad, "a shell in the action's jobs interpolates something else: %s" % bad
