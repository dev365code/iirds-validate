"""Rendering a Report for humans and for machines."""
from __future__ import annotations

import json
import os
import sys
from typing import Optional, TextIO

from .model import Report, Severity

_COLOURS = {Severity.ERROR: "\033[31m", Severity.WARNING: "\033[33m", Severity.INFO: "\033[36m"}
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"

_MARK = {Severity.ERROR: "ERROR", Severity.WARNING: "WARN ", Severity.INFO: "INFO "}


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
    for finding in report.findings:
        sev = finding.severity
        mark = paint(_MARK[sev], _COLOURS[sev])
        print("  %s %-9s %s" % (mark, finding.rule.id, finding.violation.message), file=stream)
        if finding.violation.subject:
            print(paint("                      %s" % finding.violation.subject, _DIM), file=stream)
        if finding.violation.detail:
            print(paint("                      %s" % finding.violation.detail, _DIM), file=stream)
        if verbose and finding.rule.spec:
            print(paint("                      spec: %s" % finding.rule.spec, _DIM), file=stream)

    errors = report.count(Severity.ERROR)
    warnings = report.count(Severity.WARNING)
    infos = report.count(Severity.INFO)

    print(file=stream)
    verdict = paint("PASS", "\033[32m") if report.ok else paint("FAIL", "\033[31m")
    print("  %s  %d error(s), %d warning(s), %d note(s)" % (verdict, errors, warnings, infos),
          file=stream)
    tail = "  %d rules checked, %d not applicable to this version/variant" % (
        report.checked, report.skipped)
    if report.unimplemented:
        tail += ", %d catalogued but not yet implemented" % report.unimplemented
    print(paint(tail, _DIM), file=stream)


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
