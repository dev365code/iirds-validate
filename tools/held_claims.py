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

One thing it does not distinguish: the record drops the parameters, so a
parametrised case counts as passed when any one of its parameters did. That is
safe only because `make check` stops on the first failure, and this runs after
a green suite -- there is no state where some parameters failed and this still
reports the claim as held. Written down because the guard is the sequencing,
not the check, and sequencing is easier to change by accident.
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


def _keys_per_claim(gate):
    """claim -> the test keys that have to be in the record for it to be held.

    Two buckets and they are checked differently, which is the whole of the
    repair. A NAMED_CASES claim names one test; a COUNTEREXAMPLES claim is a
    row of a table one parametrised test walks, so what has to have passed is
    every one of *its* parameters -- and the record keeps the parametrised
    ids for exactly this. Counting the second bucket and iterating only the
    first left three claims, the ones with the most cases behind them, held
    by nothing that anybody checked.
    """
    keys = {}
    for requirement, where in gate.NAMED_CASES.items():
        module, _, name = where.rpartition(":")
        keys[requirement] = {"%s::%s" % (module or "test_covers_is_earned", name)}
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
    return counted, set(_keys_per_claim(gate))


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

    keys = _keys_per_claim(gate)
    missing = []
    for requirement, wanted in sorted(keys.items()):
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
