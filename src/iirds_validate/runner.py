"""Rule execution."""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from . import rules as _rules  # noqa: F401  — importing registers every rule
from .context import Context, load_context
from .model import Finding, Report, Rule, Severity, Violation
from .package import Package, PackageError
from .registry import CATALOG, all_rules

CONFORMANCE_KINDS = ("container", "schema")
LINT_KINDS = ("lint",)
ALL_KINDS = CONFORMANCE_KINDS + LINT_KINDS


def load(path, version: Optional[str] = None) -> Context:
    """Open a container and parse its metadata into a graph."""
    return load_context(Package(path), version=version)


def _synthetic(rule_id: str, kind: str, prio: str, title: str) -> Rule:
    return Rule(id=rule_id, kind=kind, prio=prio, title=title,
                versions=(), variants=(), spec=None, fn=lambda ctx: ())


def run(path, kinds: Sequence[str] = CONFORMANCE_KINDS, version: Optional[str] = None,
        include_info: bool = True) -> Report:
    report = Report(path=str(path))

    try:
        ctx = load(path, version=version)
    except PackageError as exc:
        report.findings.append(Finding(
            _synthetic("C1", "container", "MUST", "the container must be a readable ZIP archive"),
            Violation("cannot open container", subject=str(path), detail=str(exc))))
        report.checked = 1
        return report

    report.version = ctx.declared_version
    report.variant = ctx.variant

    if ctx.declared_version is None:
        report.notes.append(
            "no iirds:iiRDSVersion in the package; validated against %s. "
            "(Tools that filter rules by the declared version run zero rules here "
            "and report a clean package.)" % ctx.version)
    elif ctx.declared_version != ctx.version:
        report.notes.append("declared version %r is not a known iiRDS version; "
                            "validated against %s" % (ctx.declared_version, ctx.version))
    if ctx.sources:
        report.notes.append("metadata read from " + ", ".join(ctx.sources))
    if not ctx.sources:
        report.notes.append("no parsable metadata found; graph rules could not run")

    for rule in all_rules():
        if rule.kind not in kinds:
            continue
        if not rule.applies_to(ctx.version, ctx.variant):
            report.skipped += 1
            continue
        report.checked += 1
        try:
            for violation in rule.fn(ctx) or ():
                if rule.severity is Severity.INFO and not include_info:
                    continue
                report.findings.append(Finding(rule, violation))
        except Exception as exc:                      # a broken rule must not hide the rest
            report.findings.append(Finding(
                _synthetic("S3", "system", "MUST", "schema validation failed"),
                Violation("rule %s raised %s" % (rule.id, type(exc).__name__), detail=str(exc))))

    implemented = {r.id for r in all_rules()}
    report.unimplemented = sum(
        1 for rid, meta in CATALOG.items()
        if meta["kind"] in kinds and rid not in implemented
        and (not meta["versions"] or ctx.version in meta["versions"])
        and (not meta["variants"] or ctx.variant in meta["variants"]))

    report.findings.sort(key=lambda f: (f.severity is not Severity.ERROR,
                                        f.severity is not Severity.WARNING,
                                        f.rule.kind, f.rule.id, f.violation.subject or ""))
    return report


def check(path, version: Optional[str] = None) -> Report:
    """Conformance only: container structure plus the metadata graph."""
    return run(path, CONFORMANCE_KINDS, version=version)


def lint(path, version: Optional[str] = None) -> Report:
    """Interoperability only: can a consumer actually use this package?"""
    return run(path, LINT_KINDS, version=version)
