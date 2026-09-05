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

The record keeps what the run *collected* as well as what passed, because what
passed is not enough. A parametrised case list that ran one row and skipped
twenty-six leaves the function name in the passed set and nothing to say the
other rows were ever there: skipping twenty-six of appendix B's twenty-seven
cases left this printing "42 claims held" and exiting 0 with nine sentences
standing on nothing. Every row a claim's test collected has to be a row that
passed. The defence written here before -- that `make check` stops on the
first failure, so a partly-failing case list cannot reach this -- was true and
answered the wrong question: a skip is not a failure and stops nothing.
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


#: The test the COUNTEREXAMPLES table parametrises, and how it names a case.
#: Both are read from the gate module below rather than typed, except this
#: one string, which is the function's own name.
COUNTEREXAMPLE_TEST = ("test_covers_is_earned::"
                       "test_a_package_that_breaks_the_sentence_is_reported_by_a_rule_claiming_it")


def keys_per_claim(gate, collected):
    """claim -> the test keys that have to be in the record for it to be held.

    Two buckets, and the same demand of both: every case that ran under the
    name has to have passed. A COUNTEREXAMPLES claim names its rows in the
    table, so they are derived from it; a NAMED_CASES claim names a function,
    so its rows come from what the run collected under that name.

    Both were checked by the function name once, which counts a case list as
    held when one row of it passed. Repairing the first bucket and leaving the
    second was the same defect a second time, in the tool written to prevent
    it: thirty-nine of forty-two claims were still checked by name and fifteen
    of those name a parametrised test.
    """
    keys = {}
    for requirement, where in gate.NAMED_CASES.items():
        module, _, name = where.rpartition(":")
        bare = "%s::%s" % (module or "test_covers_is_earned", name)
        rows = {row for row in collected
                if row == bare or row.startswith(bare + "[")}
        keys[requirement] = rows or {bare}
    for requirement, cases in gate.COUNTEREXAMPLES.items():
        keys[requirement] = {
            "%s[%s:%s]" % (COUNTEREXAMPLE_TEST, requirement.rpartition("#")[2], kind)
            for _what, kind in cases}
    return keys


def claims_counted_and_checked():
    """(what the tool reports as held, what it actually looks at).

    Equal by construction now; a test asserts it, because they were not.
    """
    import test_covers_is_earned as gate

    counted = set(gate.NAMED_CASES) | set(gate.COUNTEREXAMPLES)
    return counted, set(keys_per_claim(gate, collected=()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.parse_args()

    if not PASSED_FILE.exists():
        print("  no record of what passed — run the suite first")
        return 1
    record = json.loads(PASSED_FILE.read_text("utf-8"))
    sys.path.insert(0, str(ROOT / "tests"))
    import conftest

    if record.get("tree") != conftest._tree_fingerprint():
        print("  the record was written against a different tree — run the suite again")
        return 1
    passed = set(record["passed"])
    collected = set(record["collected"])

    import test_covers_is_earned as gate

    keys = keys_per_claim(gate, collected)
    missing = []
    for requirement, wanted in sorted(keys.items()):
        if not wanted:
            missing.append((requirement, "no case at all"))
            continue
        absent = sorted(wanted - passed)
        if absent:
            missing.append((requirement, absent[0] if len(absent) == 1
                            else "%d of its %d cases" % (len(absent), len(wanted))))

    counted = len(keys)
    if missing:
        print("  %d of the %d claims called \"held by a package\" name a test that did "
              "not pass:" % (len(missing), counted))
        for requirement, key in missing:
            print("    %-52s %s" % (requirement, key))
        return 1
    print("  %d claims held, every case behind each of them passed" % counted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
