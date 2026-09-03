#!/usr/bin/env python3
"""Lines in the rules that decide "no finding" and no test has ever run.

`tools/rule_coverage.py` asks whether a rule has ever been seen to fire. That
catches a rule that is dead or inverted, and its own docstring says what it
cannot catch: "the rule's body ran, and returned the wrong answer". There is a
third state between those two, and it is where the expensive defects live --
the rule fires, in the suite and in the field, and one *branch inside it* has
never executed. That branch is almost always an exemption, and an exemption
that no test reaches is a place where a package passes for a reason nobody has
checked.

What this does not catch, stated first, because the tool was nearly documented
with the opposite claim. The defect that prompted it was an exemption reading
"any term the ontology defines", where the rule meant "any term the ontology
says is one of these". That line *executed* in the suite, hundreds of times,
by way of the very clause that was wrong -- every correct referent took it.
Line coverage is blind to a decision that is taken for a good reason and is
also wrong for inputs nobody tried. Finding that needed the branches
enumerated and a package written for each, which is what
`tests/test_shapes_parity.py` now does for that family, and it is a different
and more expensive discipline than this.

What this catches is the cheaper class beside it: a decision line that no test
has executed *at all*. Nothing can be said about such a line -- not that it is
right, not that it is wrong, not even that it runs. It runs the suite under a
line tracer scoped to the rule modules and reports what never executed, ranked
by what the line does:

  silent   a line that ends the rule's consideration of a subject without a
           finding -- `continue`, `return`, `pass`, or the test that guards
           one. A package takes this path and is told nothing.
  finding  a `yield Violation` never reached: the rule has a case it has never
           reported. Either dead or untested.
  other    everything else.

    python tools/silent_paths.py                # measure and report
    python tools/silent_paths.py --check        # compare against the baseline
    python tools/silent_paths.py --write-baseline

The baseline is not a target, for the same reason `rule_coverage.py` says: it
records what is currently unreached so the number cannot grow quietly.

Tracing is `sys.settrace`, not a dependency. `coverage.py` would do this better
and this repository ships and tests offline with one runtime dependency; a
tool that only maintainers run is not worth a second one.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "src" / "iirds_validate" / "rules"
BASELINE = ROOT / "docs" / "silent-paths.json"

#: The tracer runs inside pytest, so it is written to a file the child process
#: imports through PYTHONSTARTUP-like injection: a conftest plugin would put
#: tracing in every developer's run. A `-p` plugin module is the narrow way.
PLUGIN = '''
import sys, json, os

# The decision is memoised by `co_filename`. It was not, and the tracer called
# os.path.realpath on every function call in the process -- a syscall per call,
# across pytest and rdflib -- which turned a five-minute suite into two and a
# half hours before it was killed. A trace function runs in the hottest loop
# there is; it may not touch the filesystem.
_WANT = os.path.realpath(os.environ["SILENT_PATHS_DIR"]) + os.sep
_seen = {}
_known = {}


def _trace(frame, event, arg):
    if event != "call":
        return None
    filename = frame.f_code.co_filename
    key = _known.get(filename, 0)
    if key == 0:
        try:
            real = os.path.realpath(filename)
        except OSError:
            real = None
        key = real if real and real.startswith(_WANT) else None
        _known[filename] = key
    if key is None:
        return None
    lines = _seen.setdefault(key, set())

    def _line(frame, event, arg):
        if event == "line":
            lines.add(frame.f_lineno)
        return _line
    lines.add(frame.f_lineno)
    return _line


def pytest_configure(config):
    sys.settrace(_trace)
    threading = sys.modules.get("threading")
    if threading is not None:
        threading.settrace(_trace)


def pytest_unconfigure(config):
    sys.settrace(None)
    with open(os.environ["SILENT_PATHS_OUT"], "w") as handle:
        json.dump({k: sorted(v) for k, v in _seen.items()}, handle)
'''


def executable_lines(path: Path):
    """Line numbers of statements, and what kind each is.

    Docstrings, decorators and the module's own table literals are not
    branches: a rule module is mostly data, and reporting every unexecuted
    line of a `fix=` string would bury the four lines that matter.
    """
    tree = ast.parse(path.read_text("utf-8"))
    kinds = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Continue, ast.Pass, ast.Return)):
            kinds[node.lineno] = "silent"
        elif isinstance(node, (ast.Yield, ast.YieldFrom)):
            kinds.setdefault(node.lineno, "finding")
        elif isinstance(node, (ast.If, ast.For, ast.While)):
            kinds.setdefault(node.lineno, "branch")
        elif isinstance(node, ast.stmt) and not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                       ast.Import, ast.ImportFrom, ast.Expr, ast.Assign,
                       ast.AnnAssign, ast.AugAssign)):
            kinds.setdefault(node.lineno, "other")
    return kinds


def measure(out_dir: Path, extra_args):
    """Run the suite under the tracer and return {file: {line: kind}} unreached."""
    plugin_dir = out_dir
    (plugin_dir / "silent_paths_plugin.py").write_text(PLUGIN, "utf-8")
    seen_file = plugin_dir / "seen.json"
    env = {
        "SILENT_PATHS_DIR": str(RULES),
        "SILENT_PATHS_OUT": str(seen_file),
        "PYTHONPATH": "%s:%s" % (ROOT / "src", plugin_dir),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(Path.home()),
    }
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "silent_paths_plugin",
           "-p", "no:cacheprovider", *extra_args]
    result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    tail = [line for line in result.stdout.splitlines() if "passed" in line or "failed" in line]
    print("  suite:", tail[-1] if tail else result.stdout.strip().splitlines()[-1:])
    if not seen_file.exists():
        raise SystemExit("the tracer wrote nothing:\n%s" % result.stdout[-2000:])
    seen = {k: set(v) for k, v in json.loads(seen_file.read_text("utf-8")).items()}

    unreached = {}
    for path in sorted(RULES.glob("*.py")):
        kinds = executable_lines(path)
        ran = seen.get(str(path.resolve()), set())
        missing = {line: kind for line, kind in kinds.items() if line not in ran}
        if missing:
            unreached[path.name] = missing
    return unreached


def summarise(unreached):
    counts = {"silent": 0, "finding": 0, "branch": 0, "other": 0}
    for missing in unreached.values():
        for kind in missing.values():
            counts[kind] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="compare against the baseline")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--tests", nargs="*", default=["tests"],
                    help="what to run under the tracer (default: the whole suite)")
    args = ap.parse_args()

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        unreached = measure(Path(tmp), args.tests)

    counts = summarise(unreached)
    print("\n  unreached lines in the rule modules: "
          "%(silent)d silent, %(finding)d finding, %(branch)d branch, %(other)d other"
          % counts)
    for name in sorted(unreached):
        rows = [(line, kind) for line, kind in sorted(unreached[name].items())
                if kind in ("silent", "finding")]
        if rows:
            print("\n  %s" % name)
            for line, kind in rows:
                print("    %-8s %s:%d" % (kind, name, line))

    record = {"counts": counts,
              "unreached": {name: {str(k): v for k, v in sorted(missing.items())}
                            for name, missing in sorted(unreached.items())}}
    if args.write_baseline:
        BASELINE.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", "utf-8")
        print("\n  baseline written")
        return 0
    if args.check:
        if not BASELINE.exists():
            print("\n  no baseline yet — run --write-baseline")
            return 1
        old = json.loads(BASELINE.read_text("utf-8"))
        if old["counts"] != counts:
            print("\n  baseline says %s, the suite says %s" % (old["counts"], counts))
            print("  baseline is stale — rerun --write-baseline")
            return 1
        print("\n  unreached lines unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
