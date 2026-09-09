"""One report read against another.

The command line answers "is this package conformant". The question a person
delivering one actually has is "what changed since the report I signed off",
and no single run can answer it. Two verdicts and a rule for reading them
together can -- and the rule is where the honesty is spent.

The failure to design against is this: a report stored by one build compared
with a run of a later one, whose new rules fire, so the difference says the
package broke something it never touched. That is wrong in the expensive
direction, delivered by a tool whose argument is that it says how to fix
things. Everything below is shaped by not doing it.

**Two registers.** When both runs were judged on the same basis -- same build,
same rules, same command, same profile, same edition, same treatment of the
quiet findings, both packed or both not -- the difference speaks causally: a
rule that was clean and now fires is a regression. When any part of that basis
moved, it speaks neutrally: the rule started firing, and here is what else was
different.

**The exit code is bound to neither.** An earlier draft tied it to the
register, and that made the tool worse than refusing: `variant` is read out of
the package's own metadata and falls back when the metadata stops parsing, so
the worst breakage there is moves the basis, and answering neutrally there
would answer 0. What the number answers instead is a question about two
documents that carries no cause at all -- does this run have errors the stored
report does not.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional, Tuple

#: This document's own contract, moved when its shape or the meaning of a
#: field changes -- the same rule the report follows and for the same reason.
SCHEMA_VERSION = 1

#: The report shape this build reads. A version 1 report listed three rules
#: only when they failed, so a clean answer from them cannot be told from a
#: rule that did not exist; comparing across that says a package broke
#: something it never touched.
READS_REPORT_VERSION = 2

#: Measured: a report of a package that floods every rule is about half a
#: megabyte, and the analytic ceiling of one is around fifteen. Twice that,
#: checked before the parse, because `json.load` materialises the whole
#: document while a container is read a chunk at a time -- the command line's
#: "no limit at all" belongs to the second and not to the first.
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024

#: Everything outside the package that decides what a run says. Two reports
#: that disagree on any of it were not asked the same question.
BASIS = ("ruleSetDigest", "toolVersion", "kinds", "includesInfo",
         "variant", "validatedAgainst", "unpacked", "fragment")

REMEDY = {
    "toolVersion": "store a fresh baseline with this build before the next comparison",
    "ruleSetDigest": "the two runs did not have the same rules; store a fresh baseline",
    "kinds": "run the command the stored report was made with",
    "includesInfo": "one of the runs discarded its INFO findings; run both the same way",
    "variant": "the package declares a different profile, or none because its metadata "
               "stopped parsing; check the declaration before reading anything below",
    "validatedAgainst": "the edition the rules ran against moved, and a rule that reads it "
                        "can answer differently while staying in the list",
    "unpacked": "one side was an unpacked directory; the rules about the archive itself "
                "cannot be answered by one",
    "fragment": "one side was a fragment; the rules a snippet cannot satisfy were suspended",
    "package": "the two reports name different files",
    "iirdsVersion": "the package declares a different edition than it did",
}


class Refused(Exception):
    """The comparison was not attempted, and this says why."""


def _refuse(sentence: str):
    raise Refused(sentence)


def parse(text, limit: int = MAX_DOCUMENT_BYTES) -> dict:
    """A stored report, read from bytes this tool did not write.

    Every guard here is a measured way past `json.loads`: duplicate keys, of
    which the last silently wins, so a file a person reads one way parses
    another; `NaN` and `Infinity`, which it accepts by default and writes back
    out, stopping the result being JSON; and a nesting depth that raises
    `RecursionError` -- not a `ValueError`, so the obvious guard misses it and
    the tool exits with a traceback where it meant to print a sentence.
    """
    size = len(text) if isinstance(text, bytes) else len(text.encode("utf-8"))
    if size > limit:
        _refuse("that file is %d bytes; a report of the largest package this tool can "
                "read is far smaller, and this one is not read" % size)

    def no_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                _refuse("that file names %r twice in one object; the two values disagree "
                        "and nothing can say which was meant" % key)
            seen[key] = value
        return seen

    def not_a_number(token):
        _refuse("that file carries %s, which is not a number JSON has" % token)

    try:
        return json.loads(text, object_pairs_hook=no_duplicates, parse_constant=not_a_number)
    except Refused:
        raise
    except RecursionError:
        _refuse("that file is nested deeper than a report ever is")
    except ValueError as exc:
        _refuse("that file is not JSON: %s" % exc)


def _text(value, where):
    if not isinstance(value, str):
        _refuse("%s must be text and is %s" % (where, type(value).__name__))


def _names(value, where):
    if not isinstance(value, list) or any(not isinstance(name, str) for name in value):
        _refuse("%s must be a list of rule names" % where)


def _checked(document, which: str) -> dict:
    """One side, validated. Raises `Refused` with a sentence, never a shape."""
    if not isinstance(document, dict):
        _refuse("%s is not a report: a report is an object, and this is %s. A run of "
                "several packages writes an array; name one of them."
                % (which, type(document).__name__))
    version = document.get("schemaVersion")
    if isinstance(version, bool) or not isinstance(version, int):
        _refuse("%s does not say which report shape it is" % which)
    if version != READS_REPORT_VERSION:
        if version < READS_REPORT_VERSION:
            _refuse("%s was written by a build that recorded three rules only when they "
                    "failed, so a clean answer from them cannot be told from a rule that "
                    "did not exist. Validate the package again to get a current report."
                    % which)
        _refuse("%s is report shape %d, which this build does not read" % (which, version))

    envelope = document.get("judgedBy")
    if not isinstance(envelope, dict):
        _refuse("%s does not say what judged it" % which)
    for key in ("toolVersion", "ruleSetDigest", "kinds", "rulesRun", "includesInfo"):
        if key not in envelope:
            _refuse("%s was judged by a build that did not record %s" % (which, key))
    _text(envelope["toolVersion"], "%s: toolVersion" % which)
    _text(envelope["ruleSetDigest"], "%s: ruleSetDigest" % which)
    _names(envelope["kinds"], "%s: kinds" % which)
    _names(envelope["rulesRun"], "%s: rulesRun" % which)
    if not isinstance(envelope["includesInfo"], bool):
        _refuse("%s: includesInfo must say yes or no" % which)

    reasons = document.get("notApplicable")
    if not isinstance(reasons, dict):
        _refuse("%s does not say why the rules it did not answer went unanswered" % which)
    for reason, ids in reasons.items():
        _names(ids, "%s: notApplicable[%r]" % (which, reason))

    suppressed = document.get("suppressed")
    if not isinstance(suppressed, dict):
        _refuse("%s: suppressed must be a count per rule" % which)
    for rule_id, count in suppressed.items():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            _refuse("%s: suppressed[%r] is not a count" % (which, rule_id))

    findings = document.get("findings")
    if not isinstance(findings, list):
        _refuse("%s: findings must be a list" % which)
    for finding in findings:
        if not isinstance(finding, dict) or not isinstance(finding.get("rule"), str):
            _refuse("%s carries a finding that does not say which rule made it" % which)

    _text(document.get("variant"), "%s: variant" % which)
    if not isinstance(document.get("ok"), bool):
        _refuse("%s does not carry a verdict" % which)
    if document.get("validatedAgainst") is not None:
        _text(document["validatedAgainst"], "%s: validatedAgainst" % which)

    ran = set(envelope["rulesRun"])
    excused = {}
    for reason, ids in reasons.items():
        for rule_id in ids:
            if rule_id in excused:
                _refuse("%s excuses %s twice, for %s and for %s, so the reason it gives "
                        "depends on the order the file was read"
                        % (which, rule_id, excused[rule_id], reason))
            if rule_id in ran:
                _refuse("%s says %s both answered and did not" % (which, rule_id))
            excused[rule_id] = reason
    for finding in findings:
        if finding["rule"] not in ran:
            _refuse("%s carries a finding from %s and says that rule never answered"
                    % (which, finding["rule"]))
    return {"ran": ran, "excused": excused, "envelope": envelope, "document": document,
            "findings": findings, "suppressed": suppressed, "reasons": reasons}


def _basis_of(side) -> dict:
    envelope, document, reasons = side["envelope"], side["document"], side["reasons"]
    return {
        "ruleSetDigest": envelope["ruleSetDigest"],
        "toolVersion": envelope["toolVersion"],
        "kinds": list(envelope["kinds"]),
        "includesInfo": envelope["includesInfo"],
        "variant": document["variant"],
        "validatedAgainst": document.get("validatedAgainst"),
        "unpacked": bool(reasons.get("unpacked")),
        "fragment": bool(reasons.get("fragment")),
    }


def _listed(side, rule_id) -> list:
    return [f for f in side["findings"] if f["rule"] == rule_id]


def _totals(side, rule_id) -> Tuple[int, int, int]:
    """(findings listed, of those how many are errors, how many were not listed)."""
    listed = _listed(side, rule_id)
    errors = sum(1 for f in listed if f.get("severity") == "error")
    return len(listed), errors, side["suppressed"].get(rule_id, 0)


def _fires(side, rule_id) -> bool:
    listed, _errors, unlisted = _totals(side, rule_id)
    return bool(listed or unlisted)


def _subjects(side, rule_id) -> set:
    """What each of a rule's findings is about, as a comparable tuple.

    `None` is kept rather than folded into the empty string. A finding with no
    subject and a finding whose subject is empty are two different things --
    "this rule is about the package" against "this rule is about a name that
    turned out to be blank" -- and collapsing them would put two rows on one
    line with nothing saying so. No rule writes an empty subject today; the
    cost of not relying on that is one sort key.
    """
    return {(f.get("subject"), f.get("message"), f.get("detail"), f.get("severity"))
            for f in _listed(side, rule_id)}


def _orderable(subject) -> tuple:
    """A total order over tuples that may hold `None`, which does not compare
    with `str`. Missing sorts before present, and the order is the same in
    every process -- iterating the set instead is how the report itself came
    to depend on the hash seed."""
    return tuple((part is None, part or "") for part in subject)


@dataclass(frozen=True)
class Row:
    rule: str
    reason: Optional[str] = None
    stored: Optional[tuple] = None
    here: Optional[tuple] = None
    read_by_count: bool = False
    gone: tuple = ()
    arrived: tuple = ()

    def as_dict(self) -> dict:
        return {"rule": self.rule, "reason": self.reason,
                "stored": list(self.stored) if self.stored else None,
                "here": list(self.here) if self.here else None,
                "readByCount": self.read_by_count,
                "gone": [list(s) for s in self.gone],
                "arrived": [list(s) for s in self.arrived]}


@dataclass(frozen=True)
class Difference:
    comparable: bool
    worse: bool
    ok_stored: bool
    ok_here: bool
    banners: tuple = ()
    rows: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "comparable": self.comparable,
            "worse": self.worse,
            "okStored": self.ok_stored,
            "okHere": self.ok_here,
            "banners": [dict(b) for b in self.banners],
            "regression": [r.as_dict() for r in self.rows.get("regression", ())],
            "fixed": [r.as_dict() for r in self.rows.get("fixed", ())],
            "startedFiring": [r.as_dict() for r in self.rows.get("startedFiring", ())],
            "stoppedFiring": [r.as_dict() for r in self.rows.get("stoppedFiring", ())],
            "stillFiring": [r.as_dict() for r in self.rows.get("stillFiring", ())],
            "newlyChecked": [r.as_dict() for r in self.rows.get("newlyChecked", ())],
            "noLongerChecked": [r.as_dict() for r in self.rows.get("noLongerChecked", ())],
        }


def difference(stored, here) -> Difference:
    """Read the stored report against this run. Raises `Refused`."""
    left, right = _checked(stored, "the stored report"), _checked(here, "this run")
    basis_left, basis_right = _basis_of(left), _basis_of(right)

    banners = []
    for what in BASIS:
        if basis_left[what] != basis_right[what]:
            banners.append({"what": what, "stored": basis_left[what],
                            "here": basis_right[what], "remedy": REMEDY[what]})
    for what in ("package", "iirdsVersion"):
        if left["document"].get(what) != right["document"].get(what):
            banners.append({"what": what, "stored": left["document"].get(what),
                            "here": right["document"].get(what), "remedy": REMEDY[what]})
    comparable = not any(b["what"] in BASIS for b in banners)

    rows = {name: [] for name in ("regression", "fixed", "startedFiring", "stoppedFiring",
                                  "stillFiring", "newlyChecked", "noLongerChecked")}
    worse = False
    for rule_id in sorted(left["ran"] | right["ran"]):
        in_left, in_right = rule_id in left["ran"], rule_id in right["ran"]
        stored_totals = _totals(left, rule_id) if in_left else None
        here_totals = _totals(right, rule_id) if in_right else None
        if in_right and not in_left:
            rows["newlyChecked"].append(
                Row(rule_id, left["excused"].get(rule_id), None, here_totals))
            continue
        if in_left and not in_right:
            rows["noLongerChecked"].append(
                Row(rule_id, right["excused"].get(rule_id), stored_totals, None))
            continue
        fired_then, fires_now = _fires(left, rule_id), _fires(right, rule_id)
        if fires_now and (here_totals[1] > stored_totals[1]
                          or (here_totals[1] and here_totals[2] > stored_totals[2])):
            worse = True
        if not fired_then and not fires_now:
            continue
        capped = bool(stored_totals[2] or here_totals[2])
        gone = arrived = ()
        if not capped:
            before_subjects, after_subjects = _subjects(left, rule_id), _subjects(right, rule_id)
            gone = tuple(sorted(before_subjects - after_subjects, key=_orderable))
            arrived = tuple(sorted(after_subjects - before_subjects, key=_orderable))
        row = Row(rule_id, None, stored_totals, here_totals, capped, gone, arrived)
        if not fired_then and fires_now:
            rows["regression" if comparable else "startedFiring"].append(row)
        elif fired_then and not fires_now:
            rows["fixed" if comparable else "stoppedFiring"].append(row)
        elif gone or arrived or stored_totals != here_totals:
            rows["stillFiring"].append(row)
    return Difference(comparable, worse, left["document"]["ok"], right["document"]["ok"],
                      tuple(banners), {k: tuple(v) for k, v in rows.items()})


#: What each class is called where a person reads it, and the order they are
#: read in: what got worse first, what a reader must decide about next, what
#: is only news last.
HEADINGS = (
    ("regression", "clean in the stored report, firing in this run"),
    ("startedFiring", "not firing in the stored report, firing in this run"),
    ("stillFiring", "firing in both, and not the same findings"),
    ("newlyChecked", "this run answered; the stored report did not"),
    ("noLongerChecked", "the stored report answered; this run did not"),
    ("stoppedFiring", "firing in the stored report, not firing in this run"),
    ("fixed", "firing in the stored report, clean in this run"),
)


def _said(subject) -> str:
    """A finding's identity, for a person. `None` is not "None": it is the
    absence of a subject, and the two are different findings."""
    return " · ".join("—" if part is None else str(part) for part in subject)


def render_text(answer: Difference, stream=None) -> None:
    """The difference, for a person.

    Every row and every banner in the document appears here, and a test holds
    that as a property rather than against a golden file. The report can
    afford two encodings that differ -- its text deliberately leaves out the
    envelope -- because both are renderings of one verdict a reader can
    re-run. A difference cannot: a text that drops a reason, or the note that
    a rule was read by count, or a banner, says something the machine form
    does not, and there would be nothing to catch it.

    No word here carries a clock. Neither document has a time of its own, so
    "the stored report" and "this run" are what they are called; `before` and
    `after` would assert an order the data does not have.
    """
    import sys

    out = sys.stdout if stream is None else stream
    document = answer.as_dict()
    for banner in document["banners"]:
        out.write("  ! %s: stored %r, here %r\n      %s\n"
                  % (banner["what"], banner["stored"], banner["here"], banner["remedy"]))
    if not answer.comparable:
        out.write("  ! the two runs were not judged on the same basis, so nothing below "
                  "is attributed to the package\n")
    out.write("\n  stored verdict %s, this run %s\n\n"
              % ("PASS" if answer.ok_stored else "FAIL",
                 "PASS" if answer.ok_here else "FAIL"))
    for key, heading in HEADINGS:
        rows = document[key]
        if not rows:
            continue
        out.write("  %s (%d) -- %s\n" % (key, len(rows), heading))
        for row in rows:
            out.write("      %s" % row["rule"])
            if row["reason"]:
                out.write("  reason: %s" % row["reason"])
            if row["readByCount"]:
                out.write("  read by count: a listing was cut short")
            if row["stored"] or row["here"]:
                out.write("  stored %s, here %s" % (row["stored"], row["here"]))
            out.write("\n")
            for subject in row["gone"]:
                out.write("        gone: %s\n" % _said(subject))
            for subject in row["arrived"]:
                out.write("        here: %s\n" % _said(subject))
        out.write("\n")
    out.write("  %s\n" % ("this run has errors the stored report does not"
                          if answer.worse else
                          "no rule has errors here that the stored report did not"))
