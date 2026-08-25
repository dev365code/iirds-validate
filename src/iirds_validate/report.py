"""Rendering a Report for humans and for machines."""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Optional, TextIO

from .model import Report, Severity

_COLOURS = {Severity.ERROR: "\033[31m", Severity.WARNING: "\033[33m", Severity.INFO: "\033[36m"}
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"

_MARK = {Severity.ERROR: "ERROR", Severity.WARNING: "WARN ", Severity.INFO: "INFO "}


def _wrap(text: str, width: int):
    """Fold to `width`, because a remedy that runs off the terminal is not one.

    Deliberately not textwrap: this keeps the dependency surface at zero and
    the behaviour obvious, and the strings involved are one sentence long.
    """
    words, line, out = text.split(), "", []
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = "%s %s" % (line, word) if line else word
    if line:
        out.append(line)
    return out


#: Past this many findings of one rule, the report stops repeating itself:
#: the remedy is printed once and the subjects are listed, natural-sorted so
#: file2 comes before file10. Every finding kept is in --format json, and the
#: listing is bounded per rule -- `summary.findingsNotListed` says by how many.
GROUP_FROM = 3
GROUP_SHOWN = 5

_NATURAL = re.compile(r"(\d+)")


def _natural(text: str):
    return [int(part) if part.isdigit() else part for part in _NATURAL.split(text or "")]


def _use_colour(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def render_text(report: Report, stream: Optional[TextIO] = None, verbose: bool = False) -> None:
    # Resolved here rather than as a default argument: a default is evaluated
    # once at import, so `stream=sys.stdout` would capture the interpreter's
    # original stdout and keep writing there no matter what a caller redirected.
    stream = sys.stdout if stream is None else stream
    colour = _use_colour(stream)

    def paint(text: str, code: str) -> str:
        return "%s%s%s" % (code, text, _RESET) if colour else text

    head = os.path.basename(str(report.path).rstrip("/\\")) or str(report.path)
    version = report.version or "not declared"
    variant = "" if report.variant == "unrestricted" else "  variant %s" % report.variant
    print(paint(head, _BOLD) + paint("   iiRDS %s%s" % (version, variant), _DIM), file=stream)

    for note in report.notes:
        print(paint("  note: " + note, _DIM), file=stream)

    if report.findings:
        print(file=stream)

    def show(finding):
        sev = finding.severity
        mark = paint(_MARK[sev], _COLOURS[sev])
        print("  %s %-9s %s" % (mark, finding.rule.id, finding.violation.message), file=stream)
        if finding.violation.subject:
            print(paint("                      %s" % finding.violation.subject, _DIM), file=stream)
        if finding.violation.detail:
            print(paint("                      %s" % finding.violation.detail, _DIM), file=stream)
        # Shown by default, not behind -v. A report you cannot act on is a
        # report that has told you only that you are in trouble.
        if finding.fix:
            for line in _wrap(finding.fix, 74):
                print(paint("                    → %s" % line, _DIM), file=stream)
        if verbose and finding.rule.spec:
            print(paint("                      spec: %s" % finding.rule.spec, _DIM), file=stream)

    # One rule, forty findings used to mean the same remedy paragraph forty
    # times — 246 lines for "forty files are missing", and nothing saying so.
    # Findings arrive grouped by rule (the reading order sorts them so), and a
    # run of GROUP_FROM or more collapses: the shared message once, the
    # subjects natural-sorted, the remedy once.
    index = 0
    findings = report.findings
    while index < len(findings):
        run = index
        while run < len(findings) and findings[run].rule.id == findings[index].rule.id:
            run += 1
        group = findings[index:run]
        index = run

        if len(group) < GROUP_FROM:
            for finding in group:
                show(finding)
            continue
        _show_group(group, report.total_for(group[0].rule.id), paint, stream)

    errors = report.count(Severity.ERROR)
    warnings = report.count(Severity.WARNING)
    infos = report.count(Severity.INFO)

    print(file=stream)
    verdict = paint("PASS", "\033[32m") if report.ok else paint("FAIL", "\033[31m")
    print("  %s  %d error(s), %d warning(s), %d informational" % (verdict, errors, warnings, infos),
          file=stream)
    tail = "  %d rule%s checked, %d not applicable to this version/variant" % (
        report.checked, "" if report.checked == 1 else "s", report.skipped)
    if report.unimplemented:
        tail += ", %d catalogued but not yet implemented" % report.unimplemented
    print(paint(tail, _DIM), file=stream)


def _show_group(group, total, paint, stream) -> None:
    """A run of one rule, told once: headline with the count, the first few
    subjects natural-sorted, the remedy a single time.

    `total` rather than `len(group)`, because the listing is bounded per rule
    and the group holds only what was kept. A headline reading the length of
    the list would say a hundred where there were twenty thousand -- and it
    is the one number in the line a reader acts on.
    """
    first = group[0]
    mark = paint(_MARK[first.severity], _COLOURS[first.severity])
    messages = {finding.violation.message for finding in group}
    headline = first.violation.message if len(messages) == 1 else first.rule.title
    print("  %s %-9s %s   ×%d" % (mark, first.rule.id, headline, total), file=stream)

    ordered = sorted(group, key=lambda g: _natural(g.violation.subject or ""))
    for finding in ordered[:GROUP_SHOWN]:
        line = finding.violation.subject or finding.violation.message
        if finding.violation.detail:
            line += "  (%s)" % finding.violation.detail
        print(paint("                      %s" % line[:100], _DIM), file=stream)
    if total > GROUP_SHOWN:
        if total > len(group):
            note = ("… and %d more; listed to %d per rule, counted in full above"
                    % (total - GROUP_SHOWN, len(group)))
        else:
            note = "… and %d more; every one is in --format json" % (total - GROUP_SHOWN)
        print(paint("                      %s" % note, _DIM), file=stream)
    if first.fix:
        for line in _wrap(first.fix, 74):
            print(paint("                    → %s" % line, _DIM), file=stream)

def render_json(report: Report, stream: Optional[TextIO] = None) -> None:
    stream = sys.stdout if stream is None else stream
    json.dump(report.as_dict(), stream, ensure_ascii=False, indent=2)
    stream.write("\n")


def render(report: Report, fmt: str = "text", stream: Optional[TextIO] = None,
           verbose: bool = False) -> None:
    if fmt == "json":
        render_json(report, stream)
    else:
        render_text(report, stream, verbose=verbose)
