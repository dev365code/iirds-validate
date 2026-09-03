#!/usr/bin/env python3
"""Every claim `docs/scope.md` calls "held by a package" is held by a test that ran.

`tests/test_covers_is_earned.py` names, for each such claim, the test that
stands behind it. What it could check was that the function existed:

    assert callable(getattr(where, name, None))

A function exists whether or not anybody runs it. Marking one
`@pytest.mark.skip` left the whole suite green, `docs/scope.md` went on
publishing the count, and the claim was held by nothing -- which is the state
that number exists to rule out. Its own comment said so: "a claim held by a
function nobody runs is a claim held by nothing."

So the check moved to where it can see the answer. `tests/conftest.py` records
every test that passed, and this compares that record against the named cases,
after the run, exactly as `tools/rule_coverage.py` compares what fired.

    python tools/held_claims.py --check      # after the suite has run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

PASSED_FILE = ROOT / ".passed-tests.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.parse_args()

    if not PASSED_FILE.exists():
        print("  no record of what passed — run the suite first")
        return 1
    passed = set(json.loads(PASSED_FILE.read_text("utf-8")))

    import test_covers_is_earned as gate

    missing = []
    for requirement, where in sorted(gate.NAMED_CASES.items()):
        module, _, name = where.rpartition(":")
        key = "%s::%s" % (module or "test_covers_is_earned", name)
        if key not in passed:
            missing.append((requirement, key))

    counted = len(gate.NAMED_CASES) + len(gate.COUNTEREXAMPLES)
    if missing:
        print("  %d of the %d claims called \"held by a package\" name a test that did "
              "not pass:" % (len(missing), counted))
        for requirement, key in missing:
            print("    %-52s %s" % (requirement, key))
        return 1
    print("  %d named cases, all of them passed; %d claims held in all"
          % (len(gate.NAMED_CASES), counted))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
