#!/usr/bin/env python3
"""Run this repository's action the way GitHub runs it, and hold it to the command.

    python tools/action_parity.py                   # over this tree's code
    python tools/action_parity.py --target DIR      # over what `pip install --target DIR` left
    python tools/action_parity.py --pyz iirds.pyz   # over a single file somebody carried

`action.yml` is a door, not a second implementation. What its `check` step may
add to a run is a code in `$GITHUB_OUTPUT`; what it may change is nothing. So
every input assembled here is checked twice -- once by the command, run directly
from the install being asked about, and once by the action's own step, run with
the flags GitHub runs `shell: bash` with -- and stdout, stderr and the exit code
are compared as bytes, and the code the step publishes has to be the code the
command returned. The command is the one the step runs, `iirds <verb> <args> --
<paths>`: the `--` keeps a path that begins with a dash a path, and changes
nothing for any other.

The inputs: every file the vendored corpus's manifest lists, as the bare
metadata file it is (`--fragment`); every package `tools/make_fixture_package.py`
knows how to build; and the cases that are about the door rather than the
package -- a path that names nothing, a command line the checker refuses, a
directory, a name with a space in it, one that looks like a pattern and one that
begins with a dash, two paths on one line, each verb, and the report options.
Then a few again in report mode (`fail-on-finding: false`), where the step
succeeds, publishes the code, and adds one line that says so -- that line, and
nothing else.

Both runs share one environment, with the hash seed fixed: what is compared is
the door, under the conditions the command had. Whether the engine answers the
same under every seed is a question about the engine, asked elsewhere.

`action.yml` is read with a pattern, because pyyaml is not a dependency of this
project, and the reader refuses a shape it does not know. Where pyyaml is
installed the reading is also compared with pyyaml's, and `--require-yaml` makes
its absence a failure; CI asks for that.

Exit 0 when every run agrees, 1 when any does not, and 2 when the comparison
cannot be made: no bash, no action, or an action this reader cannot read.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "action.yml"
CORPUS = ROOT / "tests" / "corpus" / "plusmeta"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_fixture_package import BREAKAGE, build_package  # noqa: E402

#: The invocation GitHub prints in its own logs for `shell: bash`. Recorded
#: rather than guessed: the `-e` is why the step is written the way it is.
GITHUB_BASH = [shutil.which("bash") or "/bin/bash", "--noprofile", "--norc", "-e", "-o", "pipefail"]

#: The one line the step adds in report mode, and the only one it may.
REPORTED = "iirds returned %d; the step is not failing because fail-on-finding is false\n"


class Unreadable(Exception):
    """`action.yml` has a shape this reader does not know."""


Step = namedtuple("Step", "id if_ shell env run keys")

#: The keys a step may have here. Anything else is something GitHub would act on
#: and this comparison would not: `working-directory:` moves the step,
#: `continue-on-error:` turns the gate off, and both would pass unseen.
STEP_KEYS = {"id", "name", "if", "shell", "env", "run"}
Action = namedtuple("Action", "using inputs outputs output_descriptions steps")


def _block(lines, start, indent):
    """A literal block scalar (`key: |`), YAML's way: the lines indented at least
    `indent`, with that much taken off; blank lines kept inside it and dropped at
    its end, and one line break at the end ("clip")."""
    body, at = [], start
    while at < len(lines):
        line = lines[at]
        if line.strip() and len(line) - len(line.lstrip(" ")) < indent:
            break
        body.append(line[indent:] if line.strip() else "")
        at += 1
    while body and not body[-1]:
        body.pop()
    if not body:
        raise Unreadable("an empty block at line %d" % start)
    return "\n".join(body) + "\n", at


def _folded(lines, start, indent):
    """A folded block (`key: >`): lines joined with spaces, which is all the
    descriptions here need."""
    words, at = [], start
    while at < len(lines) and (not lines[at].strip()
                               or len(lines[at]) - len(lines[at].lstrip(" ")) >= indent):
        words.append(lines[at].strip())
        at += 1
    return " ".join(w for w in words if w), at


def _scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _mapping(lines, start, indent):
    """`key: value` lines at exactly `indent`, until the indentation drops."""
    found, at = {}, start
    while at < len(lines):
        line = lines[at]
        if not line.strip() or line.lstrip().startswith("#"):
            at += 1
            continue
        depth = len(line) - len(line.lstrip(" "))
        if depth < indent:
            break
        if depth > indent:
            raise Unreadable("line %d is deeper than a %d-space mapping" % (at + 1, indent))
        key, sep, value = line.strip().partition(": ")
        if not sep:
            raise Unreadable("line %d is not `key: value`" % (at + 1))
        found[key] = _scalar(value)
        at += 1
    return found, at


def _section(lines, name):
    """The line after a top-level `name:`."""
    try:
        return lines.index("%s:" % name) + 1
    except ValueError:
        raise Unreadable("no top-level %r" % name) from None


def _entries(lines, start):
    """`inputs:` and `outputs:`: two-space names, each with four-space keys, and
    a description that may be folded."""
    entries, at = {}, start
    while at < len(lines) and (not lines[at].strip() or lines[at].startswith("  ")):
        line = lines[at]
        if not line.strip() or line.lstrip().startswith("#"):
            at += 1
            continue
        if line.startswith("   ") or not line.rstrip().endswith(":"):
            raise Unreadable("line %d is not an entry name" % (at + 1))
        name, keys, at = line.strip()[:-1], {}, at + 1
        while at < len(lines) and (not lines[at].strip() or lines[at].startswith("    ")):
            if not lines[at].strip() or lines[at].lstrip().startswith("#"):
                at += 1
                continue
            key, _, value = lines[at].strip().partition(":")
            value = value.strip()
            if value == ">":
                keys[key], at = _folded(lines, at + 1, 6)
            else:
                keys[key], at = _scalar(value), at + 1
        entries[name] = keys
    return entries


def read_action(text: str) -> Action:
    """The parts of `action.yml` the comparison needs, read the way it is written."""
    lines = text.splitlines()
    inputs = {name: keys.get("default", "") for name, keys in _entries(lines, _section(lines, "inputs")).items()}
    outs = _entries(lines, _section(lines, "outputs"))
    at = _section(lines, "runs")
    using = None
    steps = []
    while at < len(lines) and (not lines[at].strip() or lines[at].startswith("  ")):
        line = lines[at]
        if line.startswith("  using: "):
            using = _scalar(line.split(":", 1)[1])
        elif line == "  steps:":
            at += 1
            break
        at += 1
    while at < len(lines):
        line = lines[at]
        if not line.strip() or line.lstrip().startswith("#"):
            at += 1
            continue
        if not line.startswith("    - "):
            raise Unreadable("line %d does not start a step" % (at + 1))
        lines[at] = "      " + line[len("    - "):]          # the dash is the step's first key's indent
        keys, env, run = {}, {}, None
        while at < len(lines) and (lines[at].startswith("      ") or not lines[at].strip()
                                   or lines[at].lstrip().startswith("#")):
            here = lines[at]
            if not here.strip() or (here.lstrip().startswith("#") and not here.startswith("       ")):
                at += 1
                continue
            if here.startswith("       "):
                raise Unreadable("line %d is deeper than a step's keys" % (at + 1))
            key, colon, value = here.strip().partition(":")
            if not colon or (value and not value.startswith(" ")):
                # `shell:bash` is one plain scalar to YAML, not a key and its value.
                raise Unreadable("line %d is not `key: value`" % (at + 1))
            value = value.strip()
            if key not in STEP_KEYS:
                raise Unreadable("line %d gives a step `%s:`, which this comparison does not model"
                                 % (at + 1, key))
            if key in keys or (key == "env" and env) or (key == "run" and run is not None):
                raise Unreadable("line %d gives a step `%s:` twice" % (at + 1, key))
            if key == "env" and not value:
                env, at = _mapping(lines, at + 1, 8)
            elif key == "run" and value == "|":
                run, at = _block(lines, at + 1, 8)
            else:
                keys[key], at = _scalar(value), at + 1
        if "id" not in keys or run is None:
            raise Unreadable("a step without an id or a `run: |` block")
        present = frozenset(keys) | {"run"} | ({"env"} if env else set())
        steps.append(Step(keys["id"], keys.get("if"), keys.get("shell"), env, run, present))
    return Action(using, inputs, {name: keys.get("value", "") for name, keys in outs.items()},
                  {name: keys.get("description", "") for name, keys in outs.items()}, steps)


#: What the comparison takes for granted about the steps, and so refuses to run
#: without: it plays the install step as run exactly when no `pyz` is given, and
#: the check step as always run, in bash.
OBTAIN_IF = "inputs.pyz == ''"


def modelled(action) -> None:
    """Refuse an action whose steps GitHub would run differently from the way
    this plays them -- a condition on the check step would let GitHub skip it
    while the comparison ran it and called the result the command's."""
    if [s.id for s in action.steps] != ["obtain", "check"]:
        raise Unreadable("the steps are %s, not obtain then check" % [s.id for s in action.steps])
    for step in action.steps:
        if step.shell != "bash":
            raise Unreadable("%s runs in %r, and the comparison runs bash" % (step.id, step.shell))
    obtain, check = action.steps
    if obtain.if_ != OBTAIN_IF:
        raise Unreadable("obtain runs if %r; the comparison plays it as %r" % (obtain.if_, OBTAIN_IF))
    if check.if_ is not None:
        raise Unreadable("check runs only if %r, and the comparison would run it regardless"
                         % check.if_)


def agrees_with_yaml(text: str):
    """Where pyyaml is installed: the places this reader and it read differently.
    None when it is not installed."""
    try:
        import yaml
    except ImportError:
        return None
    theirs = yaml.safe_load(text)
    mine = read_action(text)
    said = []
    if theirs["runs"]["using"] != mine.using:
        said.append("using")
    def given(value):
        """What GitHub hands a step for a default: text, and a YAML boolean as
        the word it is written as."""
        return ("true" if value else "false") if isinstance(value, bool) else str(value)

    for name, keys in theirs["inputs"].items():
        if given(keys.get("default", "")) != mine.inputs.get(name):
            said.append("inputs.%s.default" % name)
    if set(theirs["inputs"]) != set(mine.inputs):
        said.append("the inputs")
    for name, keys in theirs["outputs"].items():
        if keys.get("value") != mine.outputs.get(name):
            said.append("outputs.%s.value" % name)
        if " ".join(str(keys.get("description", "")).split()) != mine.output_descriptions.get(name):
            said.append("outputs.%s.description" % name)
    steps = theirs["runs"]["steps"]
    if [s.get("id") for s in steps] != [s.id for s in mine.steps]:
        said.append("the steps")
    for step, read in zip(steps, mine.steps):
        if set(step) != set(read.keys):
            said.append("%s.keys %s vs %s" % (read.id, sorted(step), sorted(read.keys)))
        for key, value in (("if", read.if_), ("shell", read.shell), ("run", read.run)):
            if step.get(key) != value:
                said.append("%s.%s" % (read.id, key))
        if {k: str(v) for k, v in (step.get("env") or {}).items()} != read.env:
            said.append("%s.env" % read.id)
    return said


def check_step(text: str = None) -> str:
    action = read_action(ACTION.read_text(encoding="utf-8") if text is None else text)
    return next(s.run for s in action.steps if s.id == "check")


Case = namedtuple("Case", "kind label command args paths report")


def inputs(work: Path) -> list:
    """Everything the command and the step are both asked about, built under
    `work` and named relative to it."""
    fixtures = work / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    for kind, breakage in sorted(BREAKAGE.items()):
        build_package(fixtures, "%s.iirds" % kind, **breakage)
    corpus = work / "corpus"
    corpus.mkdir(exist_ok=True)
    listed = json.loads((CORPUS / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
    for name in listed:
        shutil.copyfile(CORPUS / "files" / name, corpus / name)

    cases = [Case("corpus", "corpus/" + name, "check", ["--fragment"], ["corpus/" + name], False)
             for name in sorted(listed)]
    cases += [Case("fixture", "fixture/" + kind, "check", [], ["fixtures/%s.iirds" % kind], False)
              for kind in sorted(BREAKAGE)]

    (work / "with space").mkdir(exist_ok=True)
    shutil.copyfile(fixtures / "missing-format.iirds", work / "with space" / "a package.iirds")
    patterned = work / "patterned"
    patterned.mkdir(exist_ok=True)
    shutil.copyfile(fixtures / "missing-format.iirds", patterned / "a[1].iirds")
    shutil.copyfile(fixtures / "none.iirds", patterned / "a1.iirds")   # what `a[1]` would match

    bad, good = "fixtures/missing-format.iirds", "fixtures/none.iirds"
    door = [
        ("a directory of packages", "check", [], ["fixtures"]),
        ("two packages on one line", "check", [], [good, bad]),
        ("a name with a space in it", "check", [], ["with space/a package.iirds"]),
        ("a name that looks like a pattern", "check", [], ["patterned/a[1].iirds"]),
        ("a path that names nothing", "check", [], ["no/such/package.iirds"]),
        ("a path that begins with a dash", "check", [], ["-h"]),
        ("two packages in block form", "check", [], ["with space/a package.iirds", good]),
        ("a command line the checker refuses", "check", ["--iirds-version", "9.9"], [good]),
        ("the report as JSON", "check", ["-f", "json"], [bad]),
        ("the exit code only", "check", ["-q"], [bad]),
        ("the spec links", "check", ["-v"], [bad]),
        ("warnings fail the run", "all", ["-W"], ["fixtures"]),
        ("interoperability", "lint", [], ["fixtures"]),
        ("both judgements", "all", [], ["fixtures"]),
    ]
    cases += [Case("door", "door/" + label, command, args, paths, False)
              for label, command, args, paths in door]
    again = ("fixture/none", "fixture/missing-format", "door/a path that names nothing",
             "door/a command line the checker refuses")
    cases += [case._replace(kind="report", label="report/" + case.label, report=True)
              for case in cases if case.label in again]
    return cases


class Installed:
    """What the default door runs: a directory `pip install --target` filled."""

    def __init__(self, target: Path):
        self.target = Path(target).resolve()
        self.pyz = ""

    def argv(self):
        return [sys.executable, "-m", "iirds_validate"]

    def env(self):
        return {"PYTHONPATH": str(self.target)}

    def __str__(self):
        return "installed in %s" % self.target


class Carried:
    """What the other door runs: a single file somebody brought."""

    def __init__(self, pyz: Path):
        self.pyz = str(Path(pyz).resolve())
        self.target = ""

    def argv(self):
        return [sys.executable, self.pyz]

    def env(self):
        return {}

    def __str__(self):
        return "the single file %s" % self.pyz


Outcome = namedtuple("Outcome", "differences codes asked runs")
Run = namedtuple("Run", "stdout stderr code published")

EXPRESSION = re.compile(r"^\$\{\{\s*([\w.-]+)\s*\}\}$")


def _step_env(action, case: Case, door) -> dict:
    """The step's `env:`, with every expression in it evaluated the way GitHub
    would for this case. An expression this does not know is a refusal: the
    comparison would otherwise run a step GitHub never would."""
    given = {"paths": ("\n".join(case.paths) + "\n") if any(" " in p for p in case.paths)
             else " ".join(case.paths),
             "command": case.command, "args": " ".join(case.args),
             "pyz": door.pyz, "fail-on-finding": "false" if case.report else "true"}
    step = next(s for s in action.steps if s.id == "check")
    env = {}
    for key, value in step.env.items():
        match = EXPRESSION.match(value)
        if not match:
            raise Unreadable("%s is %r, which is not one expression" % (key, value))
        what = match.group(1)
        if what.startswith("inputs."):
            name = what[len("inputs."):]
            if name not in action.inputs:
                raise Unreadable("%s names an input the action does not have: %s" % (key, name))
            env[key] = given.get(name, action.inputs[name])
        elif what == "steps.obtain.outputs.target":
            env[key] = str(door.target)
        else:
            raise Unreadable("%s is %s, which this comparison does not know how to give" % (key, what))
    return env


def _shims(work: Path) -> Path:
    """`python3` and `python` for the step to find, each this interpreter.

    A wrapper rather than a link: an interpreter finds its environment from the
    path it was started by, and a link elsewhere starts it outside the one the
    command runs in."""
    shims = work / "bin"
    shims.mkdir(exist_ok=True)
    for name in ("python3", "python"):
        shim = shims / name
        shim.write_text('#!/bin/sh\nexec "%s" "$@"\n' % sys.executable, encoding="utf-8")
        shim.chmod(0o755)
    return shims


#: The files a step can write to change the job it runs in. Each case gets
#: empty ones of its own, and they have to be empty after: what the step may
#: change is nothing, and in CI these would otherwise be the comparing job's.
JOB_FILES = ("GITHUB_ENV", "GITHUB_PATH", "GITHUB_STATE", "GITHUB_STEP_SUMMARY")


def _base_env() -> dict:
    """The environment both runs start from. No `PYTHONPATH`: each side gets the
    one its door gives it -- the command from the door, the step from its own
    `export` -- so a step that lost that line runs nothing, here as on a runner,
    instead of finding the same code through a path the test run happened to
    have. And no file of the job's: those are given per case."""
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    for name in ("PYTHONPATH", "GITHUB_OUTPUT", *JOB_FILES):
        env.pop(name, None)
    return env


def _published(path: Path) -> dict:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def _where(mine: bytes, theirs: bytes) -> str:
    at = next((n for n, (a, b) in enumerate(zip(mine, theirs)) if a != b), min(len(mine), len(theirs)))
    return ("%d bytes from the step, %d from the command, first different at byte %d: "
            "step %r, command %r" % (len(mine), len(theirs), at,
                                     mine[max(0, at - 30):at + 50], theirs[max(0, at - 30):at + 50]))


def _one(index, case, door, action, script, shims, work):
    env = _base_env()
    env.update(door.env())
    direct = subprocess.run([*door.argv(), case.command, *case.args, "--", *case.paths],
                            cwd=work, env=env, capture_output=True, timeout=600)
    command = Run(direct.stdout, direct.stderr, direct.returncode, None)

    output = work / "outputs" / ("%04d" % index)
    output.write_text("", encoding="utf-8")
    job_files = {name: work / "outputs" / ("%04d.%s" % (index, name)) for name in JOB_FILES}
    for path in job_files.values():
        path.write_text("", encoding="utf-8")
    env = _base_env()
    env.update(dict.fromkeys(next(s for s in action.steps if s.id == "check").env, ""))
    env.update(_step_env(action, case, door))
    env.update({"PATH": str(shims) + os.pathsep + env.get("PATH", ""), "GITHUB_OUTPUT": str(output)})
    env.update({name: str(path) for name, path in job_files.items()})
    ran = subprocess.run([*GITHUB_BASH, str(script)], cwd=work, env=env, capture_output=True, timeout=600)
    step = Run(ran.stdout, ran.stderr, ran.returncode, _published(output))
    wrote = [name for name, path in job_files.items() if path.read_bytes()]

    said = []
    expected_out = command.stdout
    expected_code = command.code
    if case.report:
        expected_out += (REPORTED % command.code).encode("utf-8")
        expected_code = 0
    if step.stdout != expected_out:
        said.append("stdout: " + _where(step.stdout, expected_out))
    if step.stderr != command.stderr:
        said.append("stderr: " + _where(step.stderr, command.stderr))
    if step.code != expected_code:
        said.append("exit code: the step %d, %s" % (
            step.code, "report mode expects 0" if case.report else "the command %d" % command.code))
    if step.published.get("exit-code") != str(command.code):
        said.append("published exit-code %r, the command returned %d"
                    % (step.published.get("exit-code"), command.code))
    if step.published.get("pyz", "") != door.pyz:
        said.append("published pyz %r, the step ran %r" % (step.published.get("pyz"), door.pyz))
    if wrote:
        said.append("the step wrote to %s, which changes the job it runs in" % ", ".join(wrote))
    return case, command.code, ["%s: %s" % (case.label, s) for s in said]


def compare(cases, door, work: Path, step: str = None, workers: int = None) -> Outcome:
    """Run every case both ways and say where they part."""
    work = Path(work)
    text = ACTION.read_text(encoding="utf-8")
    action = read_action(text)
    modelled(action)
    # Every case's environment, evaluated here, where a refusal stops the
    # comparison before anything runs rather than inside a worker after all of it.
    for case in cases:
        _step_env(action, case, door)
    script = work / ("step-%d.sh" % os.getpid())
    script.write_text(check_step(text) if step is None else step, encoding="utf-8")
    (work / "outputs").mkdir(exist_ok=True)
    shims = _shims(work)
    differences, codes, asked = [], Counter(), Counter()
    workers = workers or min(8, os.cpu_count() or 2)
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        done = pool.map(lambda pair: _one(pair[0], pair[1], door, action, script, shims, work),
                        enumerate(cases))
        for case, code, said in done:
            asked[case.kind] += 1
            codes[code] += 1
            differences += said
    return Outcome(differences, codes, asked, len(cases))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--target", type=Path, help="a directory `pip install --target` filled")
    where.add_argument("--pyz", type=Path, help="a single file to run")
    parser.add_argument("--require-yaml", action="store_true",
                        help="fail when pyyaml is not installed to check this reader against")
    args = parser.parse_args(argv)

    if not shutil.which("bash"):
        print("cannot compare: no bash here, and the step is a bash script", file=sys.stderr)
        return 2
    if not ACTION.is_file():
        print("cannot compare: there is no %s" % ACTION.relative_to(ROOT), file=sys.stderr)
        return 2
    text = ACTION.read_text(encoding="utf-8")
    try:
        modelled(read_action(text))
        disagreeing = agrees_with_yaml(text)
    except Unreadable as refusal:
        print("cannot compare: action.yml is not in a shape this reads: %s" % refusal, file=sys.stderr)
        return 2
    except Exception as failure:          # pyyaml's own refusal of the file
        print("cannot compare: action.yml does not parse: %s" % failure, file=sys.stderr)
        return 2
    if disagreeing is None and args.require_yaml:
        print("cannot compare: --require-yaml, and pyyaml is not installed", file=sys.stderr)
        return 2
    if disagreeing:
        print("cannot compare: this reader and pyyaml read %s differently" % ", ".join(disagreeing),
              file=sys.stderr)
        return 2

    if args.pyz:
        if not args.pyz.is_file():
            print("cannot compare: no single file at %s" % args.pyz, file=sys.stderr)
            return 2
        door = Carried(args.pyz)
    else:
        target = args.target or ROOT / "src"
        if not (target / "iirds_validate" / "__main__.py").is_file():
            print("cannot compare: nothing installed in %s" % target, file=sys.stderr)
            return 2
        door = Installed(target)

    with tempfile.TemporaryDirectory(prefix="action-parity-") as tmp:
        work = Path(tmp)
        try:
            outcome = compare(inputs(work), door, work)
        except Unreadable as refusal:
            print("cannot compare: %s" % refusal, file=sys.stderr)
            return 2
    for line in outcome.differences:
        print(line)
    asked = outcome.asked
    print("%s: %d corpus files, %d fixtures, %d door cases and %d in report mode -- "
          "codes %s; %s" % (
              door, asked["corpus"], asked["fixture"], asked["door"], asked["report"],
              ", ".join("%d x%d" % (c, n) for c, n in sorted(outcome.codes.items())),
              "%d differences" % len(outcome.differences) if outcome.differences
              else "the step said what the command said, byte for byte, every time"))
    return 1 if outcome.differences else 0


if __name__ == "__main__":
    sys.exit(main())
