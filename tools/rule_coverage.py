#!/usr/bin/env python3
"""Which rules the test suite has ever seen produce a finding.

A rule that fires nowhere in the suite has never been observed to work. It may
be correct and merely unexercised; it may be dead; it may be inverted. From
inside, those look identical, and the difference shows up in somebody's
package rather than here.

S8 is the worked example. It sat unexercised for months while being exactly
backwards -- it could only ever have fired on archives that were correct -- and
no test would have caught it, because no test made it fire at all. Line
coverage would not have helped either: the rule's body ran, and returned the
wrong answer.

    pytest                                   # conftest records what fired
    python tools/rule_coverage.py --check    # compare against the baseline
    python tools/rule_coverage.py --write-baseline

The baseline is not a target. It records which rules are currently unexercised
so that the number cannot grow quietly: adding a rule without a test that makes
it fire changes a committed file, and that shows up in review.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iirds_validate.registry import all_rules  # noqa: E402

OBSERVED = ROOT / ".rule-coverage.json"
BASELINE = ROOT / "docs" / "rule-coverage.json"


def _state():
    if not OBSERVED.exists():
        raise SystemExit("no observations; run pytest first")
    fired = set(json.loads(OBSERVED.read_text("utf-8")))
    rules = {r.id: r for r in all_rules()}
    return rules, sorted(set(rules) - fired), sorted(fired & set(rules))


def write_baseline() -> int:
    rules, never, fired = _state()
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps({
        "_generated_by": "tools/rule_coverage.py --write-baseline",
        "_note": ("Rules no test in the suite has been seen to make fire. Not a target: "
                  "the list should shrink, and it must not grow without somebody saying "
                  "why. A rule here is not known to be broken -- it is not known to work."),
        "rules": len(rules),
        "exercised": len(fired),
        "never_fires": never,
    }, indent=1) + "\n", "utf-8")
    print("%d of %d rules exercised; %d recorded as unexercised"
          % (len(fired), len(rules), len(never)))
    return 0


def check() -> int:
    if not BASELINE.exists():
        print("no baseline; run --write-baseline", file=sys.stderr)
        return 2
    recorded = set(json.loads(BASELINE.read_text("utf-8"))["never_fires"])
    rules, never, fired = _state()

    regressed = sorted(set(never) - recorded)      # used to fire, now does not
    newly_covered = sorted(recorded - set(never))  # good news, but update the file

    for rule_id in regressed:
        print("  %-9s no longer fires anywhere in the suite" % rule_id, file=sys.stderr)
    for rule_id in newly_covered:
        print("  %-9s now exercised — rerun --write-baseline" % rule_id)

    if regressed:
        print("\n%d rule(s) stopped being exercised. Either a test was removed, or a rule "
              "went dead." % len(regressed), file=sys.stderr)
        return 1
    if newly_covered:
        print("\nbaseline is stale: %d rule(s) are now exercised." % len(newly_covered),
              file=sys.stderr)
        return 1
    print("%d of %d rules exercised; the %d unexercised are the ones recorded"
          % (len(fired), len(rules), len(never)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", action="store_true", help="print the unexercised rules")
    args = ap.parse_args()

    if args.write_baseline:
        return write_baseline()
    if args.list:
        rules, never, _fired = _state()
        for rule_id in never:
            print("  %-9s %-10s %s" % (rule_id, rules[rule_id].kind, rules[rule_id].title[:70]))
        return 0
    return check()


if __name__ == "__main__":
    sys.exit(main())
