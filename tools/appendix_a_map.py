#!/usr/bin/env python3
"""Which appendix A rows a rule already checks, and which it only looks like it does.

Appendix A states, per class, that instances must have an IRI and how many of
each property they may carry. Eighty-four of the two hundred and eighty
obligations this project publishes a coverage figure against are rows of that
one table, and almost none of them were claimed — not because nothing checks
them, but because nobody had matched the rows to the rules. Fifty-three of the
fifty-six "IRI: REQUIRED" rows are checked by the generated table in
`src/iirds_validate/rules/schema_tables.py`, which was written from the same
appendix and never told which rows it was answering.

Matching them by hand is how a coverage figure stops meaning anything, so this
proposes the mapping and refuses four ways of getting it wrong:

  cardinality      `0..1 <property>` is "at most one" and a rule spelling
                   `_exactly_one` asks for one *and* at least one. A package
                   with none breaks the rule and not the row, so the rule
                   reports more than the sentence and the claim would be a
                   claim about a different sentence. Refused.
  edition          A row from the 1.3 appendix may not be claimed by a rule
                   that does not apply to 1.3.
  ambiguity        Two rules that both look right are a question for a person,
                   not a coin toss. Refused, and printed.
  double claim     A rule already claiming the row, or a row already claimed
                   by another rule, is left alone.

    python tools/appendix_a_map.py            # what it proposes and refuses
    python tools/appendix_a_map.py --check    # every proposal is already a claim

`--check` is the gate: once a proposal is accepted it must appear in `covers=`,
so the next person to touch the generated table cannot drop one silently.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iirds_validate.model import VERSIONS  # noqa: E402
from iirds_validate.registry import all_rules  # noqa: E402
from iirds_validate.rules.schema_tables import MUST_HAVE_IRI  # noqa: E402

INDEX = ROOT / "docs" / "requirements.json"

#: `rdfclasses_<domain>_<Class>#<n>` — the id carries the class the row is
#: about, which is what makes this matchable at all.
ROW = re.compile(r"^rdfclasses_(\w+?)_(\w+)#\d+$")

#: The appendix is the 1.3 document. A rule that does not apply to 1.3 cannot
#: be answering a row of it, whatever else it does.
EDITION = "1.3"


def rows(kind: str):
    """Appendix A rows of one kind, with the class each is about."""
    index = json.loads(INDEX.read_text("utf-8"))
    reduced = (set(index["reductions"]["keyword_definition"])
               | set(index["reductions"]["restated_in_the_overview"]))
    for row in index["requirements"]:
        if not row.get("absolute") or row["id"] in reduced:
            continue
        match = ROW.match(row["id"])
        if not match:
            continue
        sentence = " ".join(row["sentence"].split())
        if kind == "iri" and sentence != "IRI: REQUIRED":
            continue
        if kind == "cardinality" and not re.match(r"^\d+\.\.\d+n? ", sentence):
            continue
        yield row, match.group(2), sentence


def _applies_to(rule, edition: str) -> bool:
    return edition in (rule.versions or VERSIONS)


def _claims_already(rule, requirement: str) -> bool:
    return requirement in (rule.covers or ())


def propose():
    """(requirement, rule id) proposals, and (requirement, reason) refusals."""
    by_id = {rule.id: rule for rule in all_rules()}
    claimed = {c: rule.id for rule in all_rules() for c in (rule.covers or ())}
    checks_iri = {}
    for row in MUST_HAVE_IRI:
        checks_iri.setdefault(row[2], []).append(row[0])
    # R1 and R2 are the two written by hand for the same reason; they already
    # carry their rows, and are here so an ambiguity with them is seen.
    for rule in all_rules():
        for requirement in rule.covers or ():
            match = ROW.match(requirement)
            if match and requirement.endswith("#1"):
                checks_iri.setdefault(match.group(2), []).append(rule.id)

    proposals, refusals = [], []
    for row, class_name, _sentence in rows("iri"):
        candidates = sorted(set(checks_iri.get(class_name, [])))
        if not candidates:
            refusals.append((row["id"], "no rule checks that %s must be named" % class_name))
            continue
        if row["id"] in claimed:
            continue                    # already a claim; nothing to propose
        if len(candidates) > 1:
            refusals.append((row["id"], "two rules could be it: %s" % ", ".join(candidates)))
            continue
        rule = by_id.get(candidates[0])
        if rule is None:
            refusals.append((row["id"], "%s is not a registered rule" % candidates[0]))
            continue
        if not _applies_to(rule, EDITION):
            refusals.append((row["id"], "%s does not apply to %s" % (rule.id, EDITION)))
            continue
        if _claims_already(rule, row["id"]):
            continue
        proposals.append((row["id"], rule.id))

    for row, class_name, sentence in rows("cardinality"):
        if row["id"] in claimed:
            continue
        at_most = sentence.startswith("0..1")
        wrong = [rule.id for rule in all_rules()
                 if class_name.lower() in rule.id.lower()]
        # Nothing is proposed for these: a cardinality row needs the property
        # as well as the class, and the rules that answer them are written one
        # at a time. What is reported is the refusal, so the row is not
        # mistaken for one nobody has looked at.
        refusals.append((row["id"], "cardinality row (%s); needs a rule about that "
                                    "property, and `_exactly_one` is not it"
                         % ("at most one" if at_most else sentence.split()[0])))
        del wrong
    return proposals, refusals


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="fail if anything proposed is not already claimed")
    args = ap.parse_args()

    proposals, refusals = propose()
    iri_rows = list(rows("iri"))
    print("  appendix A, IRI rows: %d" % len(iri_rows))
    print("  proposals: %d" % len(proposals))
    print("  refusals:  %d" % len(refusals))
    for requirement, reason in refusals[:8]:
        print("    %-46s %s" % (requirement[:46], reason))
    if len(refusals) > 8:
        print("    ... and %d more" % (len(refusals) - 8))

    if args.check:
        if proposals:
            print("\n  %d appendix A rows are checked by a rule and claimed by nobody:"
                  % len(proposals))
            for requirement, rule_id in proposals[:10]:
                print("    %-46s %s" % (requirement[:46], rule_id))
            return 1
        print("\n  every row a rule checks is a row a rule claims")
    else:
        for requirement, rule_id in proposals:
            print("    %-46s -> %s" % (requirement[:46], rule_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
