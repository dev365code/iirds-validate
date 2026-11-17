"""The tracer `tools/silent_paths.py` runs the suite under.

`docs/silent-paths.json` is the set of lines in the rule modules that the suite
never executed, so the tracer has one job: to see every line that ran there and
none that did not. Most tests here run a small suite under the plugin, the way
`measure()` runs the real one, against a module standing in for a rule module,
and read back what the plugin wrote; the last two hold the tool to the
environment it gives the suite.

The module is built from the shapes a rule is made of -- a decorated function,
an early `continue` and `break`, a loop's `else`, a generator, `try` with
`except` and `finally`, a class, a nested function, a generator expression, a
lambda, a module-level `if` -- because those are where two ways of tracing
could disagree about which line ran.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import silent_paths  # noqa: E402

SUBJECT = '''\
import functools

LIMIT = 3

if LIMIT > 2:
    MODE = "wide"
else:
    MODE = "narrow"


def decorated(function):
    @functools.wraps(function)
    def inner(*args):
        return function(*args)
    return inner


@decorated
def pick(values):
    for value in values:
        if value < 0:
            continue
        if value > LIMIT:
            break
        pass
    else:
        return None
    return value


def findings(values):
    for value in values:
        if value:
            yield value
    yield from ()


def guarded(value):
    try:
        if value is None:
            raise ValueError("none")
        return value
    except ValueError:
        return 0
    finally:
        pass


class Holder:
    size = 2

    def get(self):
        return self.size


def nested(values):
    def keep(value):
        return value % 2 == 0
    total = sum(value for value in values if keep(value))
    order = sorted(values, key=lambda value: -value)
    while order:
        order.pop()
    return total


def never_called():
    return "never"
'''

SUITE = '''\
import os
import sys

import subject


def test_drive():
    assert subject.pick([1, -1, 5]) == 5
    assert subject.pick([]) is None
    assert list(subject.findings([0, 1, 2])) == [1, 2]
    assert subject.guarded(None) == 0
    assert subject.guarded(4) == 4
    assert subject.Holder().get() == 2
    assert subject.nested([1, 2, 3, 4]) == 6
    with open(os.environ["TRACE_STATE_OUT"], "w") as handle:
        handle.write("untraced" if sys.gettrace() is None else "settrace")
'''

MONITORING = pytest.mark.skipif(not hasattr(sys, "monitoring"),
                                reason="sys.monitoring arrived in Python 3.12")


def run(tmp_path: Path, tracer: str | None = None, through_a_link: bool = False):
    """The lines of the stand-in module the plugin saw, and whether
    `sys.gettrace()` was set while the suite ran."""
    where = tmp_path / ((tracer or "default") + ("-linked" if through_a_link else ""))
    rules, suite, plugin = where / "rules", where / "suite", where / "plugin"
    for folder in (rules, suite, plugin):
        folder.mkdir(parents=True)
    (rules / "subject.py").write_text(SUBJECT, "utf-8")
    (suite / "test_drive.py").write_text(SUITE, "utf-8")
    (plugin / "silent_paths_plugin.py").write_text(silent_paths.PLUGIN, "utf-8")
    imported_from = rules
    if through_a_link:
        imported_from = where / "linked"
        try:
            imported_from.symlink_to(rules, target_is_directory=True)
        except OSError:
            pytest.skip("this platform will not make a symbolic link here")
    seen, state = where / "seen.json", where / "state.txt"
    # The child has this process's environment, less what would choose for
    # the test: Python on Windows can fail to start without SYSTEMROOT, and a
    # tracer or a pytest option set outside would answer in its place.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PYTEST_", "SILENT_PATHS_"))}
    env.update({
        "SILENT_PATHS_DIR": str(rules),
        "SILENT_PATHS_OUT": str(seen),
        "TRACE_STATE_OUT": str(state),
        "PYTHONPATH": "%s%s%s" % (imported_from, os.pathsep, plugin),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    if tracer:
        env["SILENT_PATHS_TRACER"] = tracer
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "silent_paths_plugin",
         "-p", "no:cacheprovider", "-p", "no:randomly", str(suite)],
        cwd=where, env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    recorded = json.loads(seen.read_text("utf-8"))
    return set(recorded.get(os.path.realpath(rules / "subject.py"), ())), \
        state.read_text("utf-8")


def line_of(text: str, nth: int = 1) -> int:
    """The line number of the nth line of SUBJECT that reads `text`."""
    found = [number for number, line in enumerate(SUBJECT.splitlines(), 1)
             if line.strip() == text]
    return found[nth - 1]


def test_the_tracer_sees_what_ran_and_not_what_did_not(tmp_path):
    lines, _ = run(tmp_path)
    for text in ('MODE = "wide"', "continue", "break", "return None",
                 "yield value", 'raise ValueError("none")', "return 0",
                 "return self.size", "return value % 2 == 0",
                 "order = sorted(values, key=lambda value: -value)",
                 "order.pop()"):
        assert line_of(text) in lines, text
    for text in ('MODE = "narrow"', 'return "never"'):
        assert line_of(text) not in lines, text


@MONITORING
def test_the_suite_runs_untraced_where_python_can_watch_lines_without_it(tmp_path):
    # sys.settrace calls the tracer on every function call in the process,
    # rule module or not; under it the suite ran several times as long as
    # without. sys.monitoring asks only for what it needs.
    _, state = run(tmp_path)
    assert state == "untraced"


@MONITORING
def test_both_tracers_see_the_same_lines(tmp_path):
    # sys.settrace wrote the records before this tracer did. The faster one
    # earns its place by seeing exactly what that one saw.
    old, state = run(tmp_path, tracer="settrace")
    assert state == "settrace"
    new, _ = run(tmp_path)
    assert new == old, (sorted(new - old), sorted(old - new))


def test_a_module_imported_through_a_link_is_recorded_under_its_real_path(tmp_path):
    # `measure()` reads the record back by each rule module's real path, so
    # every line is filed under that path, whichever path the import took.
    # Filed under the path it was imported by, a module reached through a
    # link would read back as never having run.
    direct, _ = run(tmp_path)
    linked, _ = run(tmp_path, through_a_link=True)
    assert linked and linked == direct, (sorted(direct - linked), sorted(linked - direct))


def test_the_tool_passes_a_choice_of_tracer_to_the_suite(monkeypatch, tmp_path):
    # `measure()` runs the suite with an environment of its own, so that the
    # caller's does not change what is recorded. A choice of tracer is
    # passed on: without it, `SILENT_PATHS_TRACER=settrace` would ask for
    # the older tracer and get the newer one.
    monkeypatch.setenv("SILENT_PATHS_TRACER", "settrace")
    env = silent_paths.child_env(tmp_path, tmp_path / "seen.json")
    assert env["SILENT_PATHS_TRACER"] == "settrace"
    monkeypatch.delenv("SILENT_PATHS_TRACER")
    assert "SILENT_PATHS_TRACER" not in silent_paths.child_env(tmp_path, tmp_path / "seen.json")


def test_the_suite_the_tool_runs_is_given_that_environment(monkeypatch, tmp_path):
    # The helper above is what `measure()` hands the suite, not a copy beside
    # the environment it actually builds. Nothing is traced here, so the tool
    # stops and says so; what it handed over is read on the way.
    monkeypatch.setenv("SILENT_PATHS_TRACER", "settrace")
    handed = {}

    class Ran:
        stdout = "1 passed"
        returncode = 0

    def run(cmd, **kwargs):
        handed.update(kwargs["env"])
        return Ran()

    monkeypatch.setattr(silent_paths.subprocess, "run", run)
    with pytest.raises(SystemExit, match="the tracer wrote nothing"):
        silent_paths.measure(tmp_path, [])
    assert handed == silent_paths.child_env(tmp_path, tmp_path / "seen.json")
    assert handed["SILENT_PATHS_TRACER"] == "settrace"
