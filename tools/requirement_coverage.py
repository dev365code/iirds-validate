#!/usr/bin/env python3
"""How much of the specification the rules actually claim to cover.

The number this project has never been able to state. "157 of 157 catalogued
rules" measures agreement with plusmeta's enumeration of iiRDS, not with iiRDS,
and a reader has no way to tell the difference from the figure alone.

`docs/requirements.json` enumerates the standard independently. Rules declare
`covers=` against it. This prints the union, per section, so the gaps are a
work list rather than a percentage.

    python tools/requirement_coverage.py
    python tools/requirement_coverage.py --gaps      # only what nothing covers
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iirds_validate.registry import all_rules  # noqa: E402
from iirds_validate.rules.requirements import (  # noqa: E402
    NOT_ABOUT_THE_PACKAGE,
    NOT_DECIDABLE_ALONE,
)

INDEX = ROOT / "docs" / "requirements.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gaps", action="store_true", help="list only uncovered requirements")
    ap.add_argument("--section", help="restrict to one section anchor")
    args = ap.parse_args()

    requirements = [r for r in json.loads(INDEX.read_text("utf-8"))["requirements"]
                    if r["absolute"]]
    covered = defaultdict(list)
    for rule in all_rules():
        for rid in rule.covers:
            covered[rid].append(rule.id)

    by_section = defaultdict(lambda: [0, 0])
    for requirement in requirements:
        if args.section and requirement["section"] != args.section:
            continue
        bucket = by_section[(requirement["section"], requirement["section_title"])]
        bucket[1] += 1
        if requirement["id"] in covered:
            bucket[0] += 1

    total = sum(b[1] for b in by_section.values())
    done = sum(b[0] for b in by_section.values())
    elsewhere = sum(1 for r in requirements if r["id"] in NOT_ABOUT_THE_PACKAGE)
    undecidable = sum(1 for r in requirements if r["id"] in NOT_DECIDABLE_ALONE)

    if args.gaps or args.section:
        for requirement in requirements:
            if (requirement["id"] in covered
                    or requirement["id"] in NOT_ABOUT_THE_PACKAGE
                    or requirement["id"] in NOT_DECIDABLE_ALONE):
                continue
            if args.section and requirement["section"] != args.section:
                continue
            print("  %-46s %s" % (requirement["id"][:44], requirement["sentence"][:78]))
        print()

    for (anchor, title), (n, of) in sorted(by_section.items(), key=lambda kv: -kv[1][1]):
        if args.gaps and n == of:
            continue
        print("  %3d/%-4d %-34s %s" % (n, of, anchor[:32], title[:40]))

    print()
    print("  %d of %d absolute obligations are claimed by a rule" % (done, total))
    if elsewhere:
        print("  %d more %s addressed to consumers rather than to packages, so no "
              "validator can check them."
              % (elsewhere, "is" if elsewhere == 1 else "are"))
    if undecidable:
        print("  %d more %s about the package and cannot be decided by anything "
              "holding one container."
              % (undecidable, "is" if undecidable == 1 else "are"))
    print("  The rest are not known to be uncovered -- they are known not to be mapped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
