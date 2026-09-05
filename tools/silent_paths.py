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
import hashlib
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


def enclosing(tree):
    """line number -> the function it is in, so a record can name a place
    rather than an offset."""
    where = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                where[line] = node.name
    return where


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


def key_for(where, lines, line, kinds):
    """What names a decision line in the record.

    Keyed by what the line is and which function it is in, not by its offset.
    A record keyed on line numbers goes stale the moment anything above it
    gains a line -- as this one did, pointing at a blank line, a docstring and
    a `def` -- and a stale record that only its own totals are compared against
    is a record nobody is reading.

    The ordinal is what makes that a key rather than a label. `function ::
    statement` alone collapses the four `continue` of one function into one
    entry, so twenty-six lines of the rule modules shared a name with another
    and the published count was of distinct sentences rather than of unmeasured
    decisions -- smallest exactly where a function has several unreached exits,
    which is where it matters. Counting occurrences within the *same function*
    keeps the property the text was chosen for: nothing above the function
    moves it, and nothing in a neighbouring function is counted with it.

    `where` maps line -> enclosing function name, as `enclosing()` builds it.
    """
    function = where.get(line, "<module>")
    text = " ".join(lines[line - 1].split())
    same = [n for n in sorted(kinds)
            if where.get(n, "<module>") == function
            and " ".join(lines[n - 1].split()) == text]
    if len(same) < 2:
        return "%s :: %s" % (function, text)
    return "%s :: %s [%d]" % (function, text, same.index(line) + 1)


def fingerprint():
    """What the rule modules are, right now, byte for byte."""
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(RULES.glob("*.py"))}


def measure(out_dir: Path, extra_args):
    """Run the suite under the tracer and return {file: {line: kind}} unreached.

    The tracer records line *numbers* and the source is read afterwards to say
    what is on them, so the two have to be the same source. A full run takes
    the better part of an hour, which is long enough to edit a rule module in,
    and one such edit shifted everything below it: thirteen `yield Violation`
    lines were reported as never reached in rules that `tools/rule_coverage.py`
    had recorded firing in the same run. Two instruments contradicting each
    other is how it was noticed; nothing in the tool objected.

    So the files are fingerprinted on both sides of the run and a change is a
    refusal, not a note. A measurement nobody can trust is worse than none,
    because this one gets written into a baseline and published.
    """
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
    before = fingerprint()
    result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    after = fingerprint()
    if before != after:
        moved = sorted(set(before) ^ set(after)) or sorted(
            name for name in before if before[name] != after[name])
        raise SystemExit(
            "the rule modules changed while the tracer was running (%s), so the "
            "line numbers it recorded belong to a source that is no longer here. "
            "Nothing is reported: re-run on a tree that stays still."
            % ", ".join(moved))
    tail = [line for line in result.stdout.splitlines() if "passed" in line or "failed" in line]
    print("  suite:", tail[-1] if tail else result.stdout.strip().splitlines()[-1:])
    if not seen_file.exists():
        raise SystemExit("the tracer wrote nothing:\n%s" % result.stdout[-2000:])
    seen = {k: set(v) for k, v in json.loads(seen_file.read_text("utf-8")).items()}

    unreached = {}
    for path in sorted(RULES.glob("*.py")):
        source = path.read_text("utf-8")
        kinds = executable_lines(path)
        where = enclosing(ast.parse(source))
        lines = source.splitlines()
        ran = seen.get(str(path.resolve()), set())
        missing = {}
        for line, kind in kinds.items():
            if line in ran:
                continue
            missing[key_for(where, lines, line, kinds)] = kind
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
        rows = [(key, kind) for key, kind in sorted(unreached[name].items())
                if kind in ("silent", "finding")]
        if rows:
            print("\n  %s" % name)
            for key, kind in rows:
                print("    %-8s %s" % (kind, key))

    # The fingerprint travels with the record. Refusing a source that changes
    # *during* the run was the first half; this is the other -- a baseline
    # written weeks ago describes a tree that has moved since, and `--check`
    # compared totals against it as though it had not. The run costs forty
    # minutes, so a stale baseline is expensive to find by running and free to
    # find from the file.
    record = {"tree": fingerprint(),
              "counts": counts,
              "unreached": {name: dict(sorted(missing.items()))
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
        if old.get("tree") != fingerprint():
            print("\n  the baseline describes different rule modules — rerun "
                  "--write-baseline")
            return 1
        was = {(name, key) for name, m in old["unreached"].items() for key in m}
        now = {(name, key) for name, m in unreached.items() for key in m}
        if old["counts"] != counts or was != now:
            for name, key in sorted(now - was):
                print("\n  newly unreached  %s  %s" % (name, key))
            for name, key in sorted(was - now):
                print("\n  now reached      %s  %s" % (name, key))
            if old["counts"] != counts:
                print("\n  baseline says %s, the suite says %s" % (old["counts"], counts))
            print("  baseline is stale — rerun --write-baseline")
            return 1
        print("\n  unreached lines unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
