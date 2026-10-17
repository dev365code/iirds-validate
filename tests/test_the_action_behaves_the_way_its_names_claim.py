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


#: Before it runs a carried file the step asks the interpreter, with `-I -c`,
#: whether the file is the checker's single file. The stub says it is: the file
#: it stands in front of is not a real one, and what is under test here is what
#: happens after. Asking a real interpreter is a test of its own below.
ASKED = 'if [ "$1" = "-I" ] && [ "$2" = "-c" ]; then exit 0; fi\n'


def _stub(tmp_path, body):
    stubs = tmp_path / "bin"
    stubs.mkdir(exist_ok=True)
    # Both names: the step asks for `python3` first and falls back to `python`.
    for name in ("python3", "python"):
        stub = stubs / name
        stub.write_text("#!/bin/sh\n" + ASKED + body, encoding="utf-8")
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
    env = {k: v for k, v in os.environ.items()
           if k not in ("GITHUB_ENV", "GITHUB_PATH", "GITHUB_STATE", "GITHUB_STEP_SUMMARY")}
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


#: What the stub was handed, one argument per line, and two variables it saw.
RECORDS = ': > "$ARGV_FILE"\nfor a in "$@"; do printf "%s\\n" "$a" >> "$ARGV_FILE"; done\n' \
          'printf "PYTHONPATH=%s\\n" "${PYTHONPATH:-}" >> "$ARGV_FILE"\n' \
          'printf "PYTHONSAFEPATH=%s\\n" "${PYTHONSAFEPATH:-}" >> "$ARGV_FILE"\nexit 0\n'


def _handed(tmp_path, **kwargs):
    _run(tmp_path, stub=RECORDS, **kwargs)
    seen = tmp_path / "argv.txt"
    return seen.read_text(encoding="utf-8").splitlines() if seen.exists() else []


def _paths(handed):
    """The paths the tool was handed: everything after the `--`, before the two
    variables the stub writes last."""
    assert "--" in handed, handed
    return handed[handed.index("--") + 1:-2]


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
    assert _paths(handed) == ["/my packages/a.iirds", "/plain/b.iirds"]


def test_one_line_still_means_space_separated(tmp_path):
    assert _paths(_handed(tmp_path, paths="a.iirds b.iirds")) == ["a.iirds", "b.iirds"]


def test_a_package_named_like_a_pattern_is_not_expanded(tmp_path):
    """`a[1].iirds` is a file name somebody's build produced, not a glob, and
    `*.iirds` is not this action's to expand."""
    (tmp_path / "a1.iirds").write_text("", encoding="utf-8")
    assert _paths(_handed(tmp_path, paths="a[1].iirds *.iirds")) == ["a[1].iirds", "*.iirds"]


def test_a_path_that_begins_with_a_dash_is_a_path(tmp_path):
    """`paths: -h` was the help and a pass: an option where a path was meant. The
    `--` before the paths is what makes it a path the tool says is not there."""
    handed = _handed(tmp_path, paths="-h --fragment")
    assert _paths(handed) == ["-h", "--fragment"], handed


def test_args_come_before_the_paths_and_split_on_spaces(tmp_path):
    handed = _handed(tmp_path, extra="-f json -W", paths="a.iirds")
    assert handed[1:7] == ["check", "-f", "json", "-W", "--", "a.iirds"]


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
    # And the caller's working directory is not ahead of what was installed.
    assert "PYTHONSAFEPATH=1" in handed, handed


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


def _only_shasum(tmp_path):
    """A PATH on which `sha256sum` is not found and `shasum` is GNU's kind: the
    stub interpreter, the GNU-like `shasum`, and the two tools the step's
    comparison needs, linked in one by one -- not the system's directories,
    which on most machines hold a `sha256sum` and so never reach this branch."""
    import shutil

    tools = _gnu_hash_tools(tmp_path)
    (tools / "sha256sum").unlink()
    few = tmp_path / "few"
    few.mkdir(exist_ok=True)
    for name in ("tr", "cut"):
        (few / name).symlink_to(shutil.which(name))
    return os.pathsep.join([str(_stub(tmp_path, _exits(0))), str(tools), str(few)])


def _gnu_hash_tools(tmp_path):
    """`sha256sum` and `shasum` that answer the way GNU's manual says sha256sum
    does: handed a name with a backslash in it, the name is escaped and the line
    starts with a backslash; read from standard input, the line names `-`.
    Whatever this machine's own tools do, the step meets the strict one here."""
    import sys

    tools = tmp_path / "gnu"
    tools.mkdir(exist_ok=True)
    body = ('#!/bin/sh\nexec "%s" -c \'import hashlib, sys\n'
            'args = [a for a in sys.argv[1:] if not a.startswith("-") and a != "256"]\n'
            'if not args:\n    print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest() + "  -")\n'
            'else:\n    n = args[0]; h = hashlib.sha256(open(n, "rb").read()).hexdigest()\n'
            '    print(("\\\\" + h + "  " + n.replace("\\\\", "\\\\\\\\")) if "\\\\" in n else (h + "  " + n))\n'
            '\' "$@"\n' % sys.executable)
    for name in ("sha256sum", "shasum"):
        tool = tools / name
        tool.write_text(body, encoding="utf-8")
        tool.chmod(0o755)
    return tools


@pytest.mark.parametrize("tools", ["this machine's", "GNU's", pytest.param(
    "GNU's shasum alone", marks=pytest.mark.skipif(os.name == "nt", reason="links tools in by symlink"))])
@pytest.mark.parametrize("name", [
    "iirds.pyz",
    # Where a backslash can be part of a name. On Windows every path already has
    # one, which is how CI found that a hash tool handed the name escapes it.
    pytest.param("back\\slash.pyz", marks=pytest.mark.skipif(
        os.name == "nt", reason="a backslash is the separator here; every path has one")),
])
def test_the_hash_it_is_held_to_is_the_files(tmp_path, name, tools):
    """And the comparison is a comparison: the right hash, written in capitals
    with a newline after it the way a copied checksum often is, passes -- with
    this machine's hash tools, and with tools that escape a name the way GNU's
    do, which on this machine they may not."""
    import hashlib

    carried = tmp_path / name
    carried.write_bytes(bytes(range(256)))         # every byte, so no reading of it as text passes
    digest = hashlib.sha256(carried.read_bytes()).hexdigest().upper() + "\n"
    path = None
    if tools == "GNU's":
        path = os.pathsep.join([str(_stub(tmp_path, _exits(0))), str(_gnu_hash_tools(tmp_path)),
                                os.environ["PATH"]])
    elif tools == "GNU's shasum alone":
        path = _only_shasum(tmp_path)
    status, published, log = _run(tmp_path, stub=_exits(0), pyz=carried, want_sha=digest, path=path)
    assert status == 0 and published.get("exit-code") == "0", log[-300:]
    assert published.get("pyz") == str(carried), published


def test_the_shell_is_the_one_github_runs(tmp_path):
    """Every test here runs the step under `GITHUB_BASH`, and the step is written
    the way it is because that shell ends at the first failing command. So the
    constant has to mean that, or every test here measures another shell."""
    done = subprocess.run([*GITHUB_BASH, "-c", "false; echo after"], capture_output=True, text=True)
    assert done.returncode == 1 and "after" not in done.stdout, (done.returncode, done.stdout)
    done = subprocess.run([*GITHUB_BASH, "-c", "false | true; echo after"], capture_output=True, text=True)
    assert done.returncode == 1 and "after" not in done.stdout, "pipefail is not on"


@pytest.mark.parametrize("written", ["false", "False", "FALSE"])
def test_report_mode_is_asked_for_in_any_case(tmp_path, written):
    """`fail-on-finding: False` -- a capital is how a person writes a boolean in
    a hurry, and what GitHub hands over is the text as written when it is quoted."""
    status, published, log = _run(tmp_path, stub=_exits(1), fail_on_finding=written)
    assert status == 0 and published.get("exit-code") == "1", log[-300:]


def _real_python(tmp_path):
    """`python3` and `python` for the step to find, each the interpreter running
    this file -- a wrapper rather than a link, so it starts in its environment."""
    import sys

    shims = tmp_path / "real"
    shims.mkdir(exist_ok=True)
    for name in ("python3", "python"):
        shim = shims / name
        shim.write_text('#!/bin/sh\nexec "%s" "$@"\n' % sys.executable, encoding="utf-8")
        shim.chmod(0o755)
    return "%s%s%s" % (shims, os.pathsep, os.environ["PATH"])


def _zipapp(path, names):
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "import sys\nsys.exit(0)\n" if name == "__main__.py" else "")
    return path


@pytest.mark.parametrize("what", ["an empty file", "a page of HTML", "another zip application",
                                  "the package without a way to run it"])
def test_a_carried_file_that_is_not_the_checker_is_refused(tmp_path, what):
    """Handed an empty file, Python runs it and exits 0: a clean verdict on
    packages nothing looked at. Anything else it can open exits 1, "errors
    found". The step asks a real interpreter first whether the file is a zip
    application with the checker in it, and refuses it with 64 if not."""
    carried = tmp_path / "iirds.pyz"
    if what == "an empty file":
        carried.write_bytes(b"")
    elif what == "a page of HTML":
        carried.write_text("<!doctype html><title>404</title>", encoding="utf-8")
    elif what == "another zip application":
        _zipapp(carried, ["__main__.py"])
    else:
        _zipapp(carried, ["iirds_validate/__init__.py"])
    status, published, log = _run(tmp_path, stub=_exits(0), pyz=carried, path=_real_python(tmp_path))
    assert status == 64, "%s came back as %d" % (what, status)
    assert "is not the single file of this checker" in log and published == {}, log[-300:]


@pytest.mark.parametrize("workspace", [{}, {"types.py": "NAME = 1\n", "zipfile.py": "raise SystemExit(0)\n"}],
                         ids=["an empty workspace", "a workspace with modules of standard names"])
def test_the_checkers_own_layout_is_run(tmp_path, workspace):
    """And the question has an answer that is yes: a zip application with the
    checker's package in it is run, by the real interpreter -- and the answer is
    the file's, not the workspace's: a `types.py` there made the real file look
    like no checker, and a `zipfile.py` could have made an empty one look like
    one."""
    for name, text in workspace.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    carried = _zipapp(tmp_path / "iirds.pyz", ["__main__.py", "iirds_validate/__init__.py"])
    status, published, log = _run(tmp_path, stub=_exits(1), pyz=carried, path=_real_python(tmp_path))
    assert status == 0 and published.get("exit-code") == "0", log[-300:]
    assert published.get("pyz") == str(carried)
    if workspace:
        empty = tmp_path / "empty.pyz"
        empty.write_bytes(b"")
        status, published, log = _run(tmp_path, stub=_exits(1), pyz=empty, path=_real_python(tmp_path))
        assert status == 64 and published == {}, log[-300:]


def test_the_file_it_was_going_to_run_is_published_even_when_it_returns_no_verdict(tmp_path):
    """A caller can ask the file itself what version it is only if the step says
    which file it was. That is written before the run, so a run that ends in a
    code that is no verdict still says it."""
    status, published, log = _run(tmp_path, stub=_exits(3))
    assert status == 3 and "exit-code" not in published, log[-300:]
    assert published.get("pyz") == str(tmp_path / "iirds.pyz"), published


def _obtain(tmp_path, *, wanted="", ref="", pyproject='version = "9.8.7"\n'):
    """The `obtain` step, under GitHub's bash, with a `python` that records
    what pip was asked to install instead of installing it."""
    action = read_action(ACTION.read_text(encoding="utf-8"))
    step = next(s for s in action.steps if s.id == "obtain")
    here = tmp_path / "action"
    here.mkdir()
    if pyproject is not None:
        (here / "pyproject.toml").write_text('[project]\nname = "iirds"\n' + pyproject, encoding="utf-8")
    asked = tmp_path / "asked.txt"
    stubs = _stub(tmp_path, ': > "$ASKED"\nfor a in "$@"; do printf "%s\\n" "$a" >> "$ASKED"; done\n')
    script = tmp_path / "obtain.sh"
    script.write_text(step.run, encoding="utf-8")
    output = tmp_path / "GITHUB_OUTPUT"
    output.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update(dict.fromkeys(step.env, ""))
    env.update({"PATH": "%s%s%s" % (stubs, os.pathsep, os.environ["PATH"]),
                "WANTED": wanted, "ACTION_REF": ref, "ACTION_PATH": str(here),
                "RUNNER_TEMP": str(tmp_path / "temp"), "GITHUB_OUTPUT": str(output),
                "ASKED": str(asked)})
    done = subprocess.run([*GITHUB_BASH, str(script)], capture_output=True, text=True, env=env)
    published = dict(line.split("=", 1) for line in
                     output.read_text(encoding="utf-8").splitlines() if "=" in line)
    pip = asked.read_text(encoding="utf-8").splitlines() if asked.exists() else []
    return done.returncode, published, pip, done.stdout + done.stderr


@pytest.mark.parametrize("wanted,ref,pyproject,version", [
    ("1.0.0", "v2.0.0", 'version = "3.0.0"\n', "1.0.0"),     # what was asked for, first
    ("", "v2.0.0", 'version = "3.0.0"\n', "2.0.0"),          # else the release tag pinned
    ("", "v2", 'version = "3.0.0"\n', "3.0.0"),              # a short `v` ref is no tag here
    ("", "main", 'version = "3.0.0"\n', "3.0.0"),            # a branch: the tree's version
    ("", "", 'version = "3.0.0"\n', "3.0.0"),                # `./`
], ids=["version", "tag", "short-ref", "branch", "local"])
def test_the_install_step_installs_the_release_it_decided_on(tmp_path, wanted, ref, pyproject, version):
    """In the order the README gives: `version`, then the tag the action is used
    at, then the version the action's own tree is numbered for -- installed by
    name, into a directory named for it."""
    status, published, pip, log = _obtain(tmp_path, wanted=wanted, ref=ref, pyproject=pyproject)
    assert status == 0, log[-300:]
    assert published.get("version") == version, published
    assert pip[:3] == ["-m", "pip", "install"] and pip[-1] == "iirds==%s" % version, pip
    target = published.get("target", "")
    assert target.endswith("iirds-%s" % version) and pip[pip.index("--target") + 1] == target, pip


def test_an_install_step_that_cannot_tell_which_release_says_so(tmp_path):
    """No `version`, no release tag, and no `pyproject.toml` to read: 64 and the
    reason, rather than an error from `sed` and a guess."""
    status, published, pip, log = _obtain(tmp_path, ref="main", pyproject=None)
    assert status == 64, log[-300:]
    assert "cannot tell which version to run" in log and pip == [] and published == {}
