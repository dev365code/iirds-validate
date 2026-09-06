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
proposes the mapping and refuses three ways of getting it wrong:

  cardinality      `0..1 <property>` is "at most one" and a rule spelling
                   `_exactly_one` asks for one *and* at least one. A package
                   with none breaks the rule and not the row, so the rule
                   reports more than the sentence and the claim would be a
                   claim about a different sentence. Refused.
  edition          A row from the 1.3 appendix may not be claimed by a rule
                   that does not apply to 1.3.
  double claim     A rule already claiming the row, or a row already claimed
                   by another rule, is left alone.

**Which rules answer a row is measured, not looked up.** This read the
generated table and the rows other rules already claimed, and drew two wrong
conclusions from that. It refused `rdfclasses_core_InformationUnit#1` saying
"no rule checks that InformationUnit must be named" — M2.1 does, and has all
along; it is written by hand rather than generated, so the table the tool read
did not mention it. And it refused three rows as ambiguous, "two rules could be
it", where the two are one check under two catalogue ids: M20.1 and M48 have
the same title, word for word, and report the same node.

So the candidates for a row are the rules that report an instance of the class
with no IRI and stay quiet on one with an IRI — which is the covering criterion
itself, applied. Ambiguity is no longer a refusal: several rules may claim one
id, the criterion says so, and choosing between two identical checks by hand
was the coin toss the refusal existed to avoid.

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


#: The namespace each `rdfclasses_<domain>_` prefix names.
NAMESPACE = {
    "core": "http://iirds.tekom.de/iirds#",
    "handover": "http://iirds.tekom.de/iirds/domain/handover#",
    "machinery": "http://iirds.tekom.de/iirds/domain/machinery#",
    "software": "http://iirds.tekom.de/iirds/domain/software#",
}


def _reported(class_iri: str, named: bool):
    """Which rules report one instance of the class, with or without an IRI.

    A package rather than a table. The tables say where a rule was written --
    generated or by hand -- which is not what a claim is about.
    """
    import tempfile

    from iirds_validate import runner
    from make_fixture_package import MINIMAL_RDF, build_package

    subject = ('rdf:about="urn:test:named"' if named else 'rdf:nodeID="anonymous"')
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", (
        '  <rdf:Description %s>\n    <rdf:type rdf:resource="%s"/>\n'
        "  </rdf:Description>\n</rdf:RDF>") % (subject, class_iri))
    package = build_package(tempfile.mkdtemp(), "probe.iirds", metadata=metadata)
    return {f.rule.id for f in runner.check(package).findings}


def _answers_the_row(class_iri: str):
    """The rules that report an unnamed instance and not a named one.

    The covering criterion, applied: every package breaking "instances of this
    class MUST have an IRI" is one of these, and a rule firing on the named
    instance too would be reporting something else.
    """
    return _reported(class_iri, named=False) - _reported(class_iri, named=True)


def propose():
    """(requirement, rule id) proposals, and (requirement, reason) refusals."""
    by_id = {rule.id: rule for rule in all_rules()}
    claimed = {c: rule.id for rule in all_rules() for c in (rule.covers or ())}

    proposals, refusals = [], []
    for row, class_name, _sentence in rows("iri"):
        domain = ROW.match(row["id"]).group(1)
        if domain not in NAMESPACE:
            refusals.append((row["id"], "%s is not a domain this tool knows" % domain))
            continue
        candidates = sorted(_answers_the_row(NAMESPACE[domain] + class_name))
        if not candidates:
            refusals.append((row["id"], "no rule reports an unnamed %s" % class_name))
            continue
        if row["id"] in claimed:
            continue                    # already a claim; nothing to propose
        # Several claimants are allowed and sometimes right: M20.1 and M48 are
        # one check under two catalogue ids, and picking one would say the
        # other does not answer a row it reports.
        for candidate in candidates:
            rule = by_id.get(candidate)
            if rule is None:
                refusals.append((row["id"], "%s is not a registered rule" % candidate))
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
