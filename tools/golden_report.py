#!/usr/bin/env python3
"""The whole report for one package, kept as a file a diff can be read from.

    python tools/golden_report.py            # write it
    python tools/golden_report.py --check    # it still says what the tool says

`tests/test_report_contract.py` pins the report's *shape*: which keys exist,
what type each one is, that `schemaVersion` moves when a meaning does. That
catches a renamed key. It does not catch a value quietly becoming a different
value -- a severity spelled differently, a rule dropping out of `rulesRun`, a
finding losing its `spec` -- because no test reads the whole document at once.

So the whole document is a file. A change to it is a line in a diff, which is
what makes "the report is an interface" reviewable rather than asserted: a
consumer reading this repository sees exactly what their parser would see move.

Two fields are replaced by a marker rather than pinned, because they are meant
to move and are held elsewhere:

* `judgedBy.toolVersion` -- every release moves it, and
  `tests/test_release_metadata.py` holds it against `pyproject.toml` and the
  changelog.
* `judgedBy.ruleSetDigest` -- it moves whenever any rule does, which is the
  point of it; `docs/rule-coverage.json` is where a rule's coming and going is
  reviewed.

Everything else is exact, `fixtures/bad.iirds` because it ships here, draws
findings, and is built by `tools/make_fixture_package.py` rather than kept as
bytes. The report is byte-identical between runs -- `tests/test_report_stability.py`
asks that of the whole corpus -- so a difference here is a change in what the
tool says, never noise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "docs" / "golden-report.json"
PACKAGE = "fixtures/bad.iirds"

#: Replaced rather than pinned, with the reason a reader needs. Each is a
#: fact about the tree that produced the report rather than about the report's
#: shape, and each moves on edits that change nothing a consumer parses -- a
#: golden that rewrites itself on every touch of `rules/` is a file nobody
#: reads the diff of, which is the one thing this file is for.
MOVING = {
    ("judgedBy", "toolVersion"):
        "<the release that ran it; tests/test_release_metadata.py>",
    ("judgedBy", "ruleSetDigest"):
        "<moves when any rule is added or removed; docs/rule-coverage.json>",
    ("judgedBy", "rulesSource", "digest"):
        "<the bytes of the rule modules; moves on any edit to them>",
}


def report() -> dict:
    """What `iirds check -f json` says about the fixture, from this tree."""
    if not (ROOT / PACKAGE).exists():
        subprocess.run([sys.executable, "tools/make_fixture_package.py", PACKAGE,
                        "--broken", "missing-format"], cwd=ROOT, check=True,
                       capture_output=True)
    import os

    # `src` on the path rather than an installed copy: this runs from a
    # checkout, and `make check` exports the same thing for the same reason.
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src")] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    done = subprocess.run([sys.executable, "-m", "iirds_validate", "check", PACKAGE,
                           "-f", "json"], cwd=ROOT, capture_output=True, text=True,
                          env=env)
    # 0 is a clean package and 1 is one with findings; anything else, and
    # whatever is on stdout is not a report. Said as a sentence, because a
    # gate that ends in a traceback is a gate whose failure nobody reads.
    if done.returncode not in (0, 1) or not done.stdout.strip():
        raise SystemExit("the checker gave no report for %s (exit %d): %s"
                         % (PACKAGE, done.returncode,
                            done.stderr.strip().splitlines()[-1] if done.stderr.strip()
                            else "nothing on stderr either"))
    try:
        document = json.loads(done.stdout)
    except ValueError as exc:
        raise SystemExit("the checker's output for %s is not JSON: %s"
                         % (PACKAGE, exc)) from exc
    for path, marker in MOVING.items():
        node = document
        for step in path[:-1]:
            node = node.get(step) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict) and path[-1] in node:
            node[path[-1]] = marker
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="the whole report for one package")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    fresh = json.dumps(report(), indent=1, sort_keys=True) + "\n"
    if not args.check:
        GOLDEN.write_text(fresh, encoding="utf-8")
        print("%s: written" % GOLDEN.relative_to(ROOT))
        return 0

    if not GOLDEN.exists():
        print("%s does not exist; run tools/golden_report.py"
              % GOLDEN.relative_to(ROOT), file=sys.stderr)
        return 1
    stored = GOLDEN.read_text(encoding="utf-8")
    if stored == fresh:
        print("the stored report is the one this tree produces")
        return 0

    import difflib
    diff = list(difflib.unified_diff(stored.splitlines(True), fresh.splitlines(True),
                                     fromfile="docs/golden-report.json",
                                     tofile="what this tree says", n=2))
    sys.stderr.writelines(diff[:60])
    if len(diff) > 60:
        print("... %d more lines" % (len(diff) - 60), file=sys.stderr)
    print("the report for %s is not what is stored. If the change is meant, "
          "`python tools/golden_report.py` writes it and the diff above is "
          "what a consumer's parser sees move." % PACKAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
