"""Run the action's own shell the way GitHub runs it, and read what happens.

Reading `action.yml` cannot see what a shell does with it: `set -uo pipefail`
does not clear the `-e` that `shell: bash` already carries, so a non-zero
verdict written as a bare call ends the step before the line that publishes the
code. Running it can.

The interpreter here is a stub that exits a chosen code, so no package is
checked and nothing is slow. What is under test is the step's arithmetic: what
it publishes and what status it leaves, for each code the tool can return and
each mode the caller can ask for, and what it hands the tool. Whether the step
passes a real run through unchanged is the other file,
`tests/test_the_action_says_what_the_command_says.py`.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from action_parity import ACTION, GITHUB_BASH, read_action


def _check():
    return next(s for s in read_action(ACTION.read_text(encoding="utf-8")).steps if s.id == "check")


def _declared_env():
    """Every variable the step declares, empty.

    GitHub defines all of them -- an input nobody passed arrives as an empty
    string, not as an absent name -- and the step runs under `set -u`. A harness
    that sets only the interesting ones tests a shell nobody will ever run."""
    return dict.fromkeys(_check().env, "")


def _stub(tmp_path, body):
    stubs = tmp_path / "bin"
    stubs.mkdir(exist_ok=True)
    # Both names: the step asks for `python3` first and falls back to `python`.
    for name in ("python3", "python"):
        stub = stubs / name
        stub.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        stub.chmod(0o755)
    return stubs


def _run(tmp_path, *, stub, pyz="carried", paths="a.iirds", fail_on_finding="true",
         command="check", target="", extra="", want_sha="", path=None):
    """The `check` step, under GitHub's own bash invocation, with a stub
    interpreter. Returns (status, published outputs, what was printed)."""
    stubs = _stub(tmp_path, stub)
    if pyz == "carried":
        pyz = tmp_path / "iirds.pyz"
        pyz.write_text("not really a zipapp; the stub never reads it", encoding="utf-8")
    script = tmp_path / "step.sh"
    script.write_text(_check().run, encoding="utf-8")
    output = tmp_path / "GITHUB_OUTPUT"
    output.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update(_declared_env())
    env.update({
        "PATH": path if path is not None else "%s%s%s" % (stubs, os.pathsep, os.environ["PATH"]),
        "PYZ": str(pyz), "TARGET": str(target), "PATHS": paths, "COMMAND": command,
        "EXTRA": extra, "WANT_SHA": want_sha, "FAIL_ON_FINDING": fail_on_finding,
        "GITHUB_OUTPUT": str(output), "ARGV_FILE": str(tmp_path / "argv.txt"),
    })
    # From the directory the stub's names would be expanded in, so a pattern
    # that matched a file there would change what the tool is handed.
    done = subprocess.run([*GITHUB_BASH, str(script)], capture_output=True, text=True,
                          env=env, cwd=str(tmp_path))
    published = dict(line.split("=", 1) for line in
                     output.read_text(encoding="utf-8").splitlines() if "=" in line)
    return done.returncode, published, done.stdout + done.stderr


def _exits(code):
    return 'printf "stub ran: %%s\\n" "$*"\nexit %d\n' % code


#: What the stub was handed, one argument per line, and the PYTHONPATH it saw.
RECORDS = ': > "$ARGV_FILE"\nfor a in "$@"; do printf "%s\\n" "$a" >> "$ARGV_FILE"; done\n' \
          'printf "PYTHONPATH=%s\\n" "${PYTHONPATH:-}" >> "$ARGV_FILE"\nexit 0\n'


def _handed(tmp_path, **kwargs):
    _run(tmp_path, stub=RECORDS, **kwargs)
    seen = tmp_path / "argv.txt"
    return seen.read_text(encoding="utf-8").splitlines() if seen.exists() else []


@pytest.mark.parametrize("code", [0, 1, 2, 64])
def test_a_verdict_is_published_and_the_gate_fails_on_it(tmp_path, code):
    """Whatever the checker returns, the code is written down; and the step's own
    status is that code, because the default is a gate."""
    status, published, _ = _run(tmp_path, stub=_exits(code))
    assert published.get("exit-code") == str(code), "the code was not published for %d" % code
    assert status == code, "the gate returned %d for a checker that returned %d" % (status, code)


@pytest.mark.parametrize("code", [0, 1, 2, 64])
def test_asked_not_to_fail_it_succeeds_and_still_says_what_happened(tmp_path, code):
    status, published, log = _run(tmp_path, stub=_exits(code), fail_on_finding="false")
    assert published.get("exit-code") == str(code)
    assert status == 0, "fail-on-finding:false still failed the step with %d" % status
    assert "iirds returned %d; the step is not failing because fail-on-finding is false" % code in log


@pytest.mark.parametrize("code", [3, 70, 126, 127])
def test_a_checker_that_never_ran_is_not_reported_as_a_verdict(tmp_path, code):
    """127 is "no such program", not "your package has errors".

    In report mode this would be the worse of the two: the step succeeds, and a
    job gating on its status passes a run in which nothing was checked."""
    status, published, log = _run(tmp_path, stub=_exits(code), fail_on_finding="false")
    assert status == code, "a run where the checker never judged came back as %d" % status
    assert "exit-code" not in published, "a code the tool does not define was published as a verdict"
    assert "not a verdict" in log


def test_a_missing_checker_is_a_usage_error_before_python_is_asked(tmp_path):
    status, published, log = _run(tmp_path, stub=_exits(0), pyz=tmp_path / "nowhere.pyz")
    assert status == 64, "a missing checker came back as %d, not a usage error" % status
    assert published == {}, "a run that never happened published something"
    assert "stub ran" not in log


@pytest.mark.parametrize("command", ["check", "lint", "all"])
def test_the_verb_asked_for_is_the_verb_the_tool_is_handed(tmp_path, command):
    assert _handed(tmp_path, command=command)[1:2] == [command]


@pytest.mark.parametrize("command", ["", "Check", "diff", "check;id", "rules"])
def test_a_verb_that_does_not_judge_is_a_usage_error_before_python_is_asked(tmp_path, command):
    """`iirds lnit pkg.iirds` reads `lnit` as a path and answers 2 -- "could not
    run", about a package nobody named. The step refuses the word first."""
    status, published, log = _run(tmp_path, stub=_exits(0), command=command)
    assert status == 64, "command %r came back as %d" % (command, status)
    assert published == {} and "stub ran" not in log
    assert "command must be check, lint or all" in log


def test_a_path_with_a_space_in_it_can_be_named(tmp_path):
    """"Separated by spaces" cannot mean a directory name may not contain one.

    Written on one line, `paths` splits on spaces, which is what the input has
    always said. Written as a YAML block it is one package per line -- the only
    way to name `/my packages/a.iirds` at all."""
    handed = _handed(tmp_path, paths="/my packages/a.iirds\n/plain/b.iirds\n")
    assert handed[2:4] == ["/my packages/a.iirds", "/plain/b.iirds"]


def test_one_line_still_means_space_separated(tmp_path):
    assert _handed(tmp_path, paths="a.iirds b.iirds")[2:4] == ["a.iirds", "b.iirds"]


def test_a_package_named_like_a_pattern_is_not_expanded(tmp_path):
    """`a[1].iirds` is a file name somebody's build produced, not a glob, and
    `*.iirds` is not this action's to expand."""
    (tmp_path / "a1.iirds").write_text("", encoding="utf-8")
    assert _handed(tmp_path, paths="a[1].iirds *.iirds")[2:4] == ["a[1].iirds", "*.iirds"]


def test_args_come_before_the_paths_and_split_on_spaces(tmp_path):
    handed = _handed(tmp_path, extra="-f json -W", paths="a.iirds")
    assert handed[1:6] == ["check", "-f", "json", "-W", "a.iirds"]


def test_the_stub_really_is_what_ran(tmp_path):
    """The premise: if `python3` resolved to a real interpreter, every assertion
    above would be measuring something else."""
    _, _, log = _run(tmp_path, stub=_exits(1))
    assert "stub ran:" in log, log[-300:]


def test_a_runner_with_no_python_is_told_so(tmp_path):
    """macOS runners ship no bare `python`, and `python3` only through
    `actions/setup-python`. Without this the step reached `exit 127`."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    status, published, log = _run(tmp_path, stub=_exits(0), path=str(empty))
    assert status == 64, "no interpreter came back as %d" % status
    assert "no python on PATH" in log and published == {}


def _installed(tmp_path):
    target = tmp_path / "installed"
    (target / "iirds_validate").mkdir(parents=True)
    (target / "iirds_validate" / "__main__.py").write_text("", encoding="utf-8")
    return target


def test_the_default_door_runs_what_was_installed(tmp_path):
    """No `pyz:` means the released distribution, run out of the directory the
    install step left it in, and the caller's own environment untouched -- which
    is why it is `--target` and `PYTHONPATH` rather than a plain install."""
    target = _installed(tmp_path)
    handed = _handed(tmp_path, pyz="", target=target)
    assert handed[:3] == ["-m", "iirds_validate", "check"], handed
    assert "PYTHONPATH=%s" % target in handed, handed


@pytest.mark.parametrize("left", ["nothing", "an empty directory", "no checker in it"])
def test_nothing_installed_is_a_usage_error_not_a_verdict(tmp_path, left):
    """If the install step left no checker behind, `python -m iirds_validate`
    exits 1 -- the code that says a package has errors. The step looks first."""
    target = {"nothing": "", "an empty directory": tmp_path / "empty",
              "no checker in it": tmp_path / "other"}[left]
    if left != "nothing":
        target.mkdir()
    if left == "no checker in it":
        (target / "rdflib").mkdir()
    status, published, log = _run(tmp_path, stub=_exits(0), pyz="", target=target)
    assert status == 64, "came back as %d" % status
    assert "nothing was installed" in log and "stub ran" not in log and published == {}


def test_a_carried_file_can_be_held_to_a_hash(tmp_path):
    """A file carried into a closed network is checked by somebody, or by nobody."""
    status, published, log = _run(tmp_path, stub=_exits(0), want_sha="0" * 64)
    assert status == 64, "a file that is not what was asked for came back as %d" % status
    assert "hashes to" in log and "stub ran" not in log and published == {}


def test_the_hash_it_is_held_to_is_the_files(tmp_path):
    """And the comparison is a comparison: the right hash, written in capitals
    with a newline after it the way a copied checksum often is, passes."""
    import hashlib

    carried = tmp_path / "iirds.pyz"
    carried.write_bytes(b"the file you were promised")
    digest = hashlib.sha256(carried.read_bytes()).hexdigest().upper() + "\n"
    status, published, log = _run(tmp_path, stub=_exits(0), pyz=carried, want_sha=digest)
    assert status == 0 and published.get("exit-code") == "0", log[-300:]
