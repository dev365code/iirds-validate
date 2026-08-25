"""Rule execution."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from . import rules as _rules  # noqa: F401  — importing registers every rule
from .context import Context, load_context
from .model import METADATA_RDF, Finding, Report, Rule, Severity, Violation
from .package import PackageError, UnreadablePath, open_package
from .registry import CATALOG, all_rules

#: "system" is in every set: a container that could not be read has to be
#: reported whichever question the caller asked.
CONFORMANCE_KINDS = ("container", "schema", "content", "system")
LINT_KINDS = ("lint", "system")
ALL_KINDS = ("container", "schema", "content", "lint", "system")


def load(path, version: Optional[str] = None) -> Context:
    """Open a container — archive or directory — and parse its metadata."""
    return load_context(open_package(path), version=version)


def _emitted(rule_id: str, kind: str = "system") -> Rule:
    """A registered rule the runner reports directly rather than executing.

    S1 fires before a Context exists and S3 fires when another rule raises, so
    neither can be evaluated in the normal loop. Their identity still comes
    from the registry, and from the catalogue behind it, rather than being
    written out a second time here.
    """
    registered = {r.id: r for r in all_rules()}.get(rule_id)
    if registered is not None:
        return registered
    meta = CATALOG.get(rule_id, {})
    return Rule(id=rule_id, kind=meta.get("kind", kind), prio=meta.get("prio", "MUST"),
                title=meta.get("en") or rule_id, versions=(), variants=(),
                spec=meta.get("spec"), fn=lambda ctx: ())


def _metadata_findings(ctx: Context, kinds: Sequence[str]):
    """Metadata that did not parse must fail the run whatever is being checked.

    The container rules already report this, but `lint` does not run them: the
    graph came out empty, every L rule found nothing, and the run went green on
    a package nobody could read. Notes do not affect the exit status, so the
    report said "no parsable metadata found" and passed anyway.
    """
    if "container" in kinds:
        return

    for error in ctx.parse_errors:
        name, _, detail = error.partition(": ")
        rule_id = "C16.1" if name == METADATA_RDF else "C16.2"
        yield Finding(_emitted(rule_id, "container"),
                      Violation("metadata could not be parsed", subject=name, detail=detail))




#: What a bare metadata file can never satisfy: a container around it
#: (L2 resolves sources against entries, S6 walks entry paths) and the
#: package-level declarations (M3, M4). Suspending them in fragment mode is
#: not leniency -- reporting "your snippet is not a whole package" five ways
#: buries the finding the snippet was brought here for.
FRAGMENT_SUSPENDED = frozenset(("M3", "M4", "L2", "S6"))


def run_fragment(path, kinds, version=None):
    """Validate a bare metadata file as if it were a package's metadata.

    The file is staged into a throwaway conformant container (mimetype
    first and stored -- the packer's usual guarantees), validated normally,
    and the rules a fragment cannot satisfy are suspended, with a note
    saying so. The report keeps the fragment's own path: the person reading
    it pointed at a file, not at our scratch directory.
    """
    import shutil
    import tempfile

    from iirds import pack

    from .model import METADATA_RDF

    source = Path(path)
    staging = Path(tempfile.mkdtemp(prefix="iirds-fragment-"))
    try:
        target = staging / "container" / METADATA_RDF
        target.parent.mkdir(parents=True)
        target.write_bytes(source.read_bytes())
        packed = pack(staging / "container", staging / "fragment.iirds")
        report = run(packed, kinds, version=version)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    report.path = str(source)
    suspended = sorted({f.rule.id for f in report.findings} & FRAGMENT_SUSPENDED)
    report.drop(FRAGMENT_SUSPENDED)
    report.notes.append(
        "fragment mode: validated inside a throwaway container; "
        "package-level rules suspended (%s)"
        % (", ".join(suspended) if suspended else "none fired"))
    return report


def run(path, kinds: Sequence[str] = CONFORMANCE_KINDS, version: Optional[str] = None,
        include_info: bool = True) -> Report:
    report = Report(path=str(path))

    try:
        package = open_package(path)
    except PackageError as exc:
        # S1 is "nothing could be read from that path"; C1 is "something was
        # read and it is not a usable ZIP". Both are catalogued, and emitting
        # C1 for both left S1 unable to fire at all while its own docstring
        # claimed this was where it came from.
        unreadable = isinstance(exc, UnreadablePath)
        report.add(Finding(
            _emitted("S1", "system") if unreadable else _emitted("C1", "container"),
            Violation("cannot read container" if unreadable else "cannot open container",
                      subject=str(path), detail=str(exc))))
        report.checked = 1
        return report

    with package:
        _run_against(package, report, kinds, version, include_info)
    # Ordered for a reader rather than for the registry: what caused the rest
    # first, what only follows from it last. Rule-id order put the finding that
    # explains a report behind three that mislead.
    # (ordering moved into Report.findings, so no path can read an unordered one)
    return report


def _run_against(package, report: Report, kinds, version, include_info) -> None:
    ctx = load_context(package, version=version)
    report.version = ctx.declared_version
    report.effective_version = ctx.version
    report.variant = ctx.variant

    # Three different situations used to share one message, which is how a
    # package declaring 1.3 came to be told that 1.3 is not a known version.
    if ctx.requested_version and ctx.requested_version != ctx.declared_version:
        report.notes.append(
            "validated against %s because it was asked for; the package declares %s"
            % (ctx.version, ctx.declared_version or "no version"))
    elif ctx.declared_version is None:
        report.notes.append(
            "no iirds:iiRDSVersion in the package; validated against %s. "
            "(Tools that filter rules by the declared version run zero rules here "
            "and report a clean package.)" % ctx.version)
    elif ctx.declared_version != ctx.version:
        report.notes.append("declared version %r is not one this standard has published; "
                            "validated against %s instead" % (ctx.declared_version, ctx.version))
    if not package.is_archive:
        report.notes.append(
            "validated as an unpacked container; the five requirements about the ZIP "
            "archive itself (C1, C3, C6, S7, S8) cannot be assessed until it is packed")
    if ctx.ontology.substituted:
        report.notes.append(
            "no ontology bundled for iiRDS %s; class hierarchy taken from %s, so rules that "
            "depend on subclassing may differ from that version"
            % (ctx.version, ctx.ontology.substituted))
    if ctx.sources:
        report.notes.append("metadata read from " + ", ".join(ctx.sources))
    if not ctx.sources:
        report.notes.append("no parsable metadata found; graph rules could not run")

    conformance_run = "schema" in kinds
    for rule in all_rules():
        if rule.kind not in kinds and not (conformance_run and rule.conformance):
            continue
        if not rule.applies_to(ctx.version, ctx.variant):
            report.skipped += 1
            continue
        report.checked += 1
        try:
            for violation in rule.fn(ctx) or ():
                if rule.severity is Severity.INFO and not include_info:
                    continue
                report.add(Finding(rule, violation,
                                   demoted_to=severity_override(rule, ctx.variant)))
        except Exception as exc:                      # a broken rule must not hide the rest
            report.add(Finding(
                _emitted("S3"),
                Violation("rule %s raised %s" % (rule.id, type(exc).__name__), detail=str(exc))))

    for finding in _metadata_findings(ctx, kinds):
        report.add(finding)

    implemented = {r.id for r in all_rules()}
    report.unimplemented = sum(
        1 for rid, meta in CATALOG.items()
        if meta["kind"] in kinds and rid not in implemented
        and (not meta["versions"] or ctx.version in meta["versions"])
        and (not meta["variants"] or ctx.variant in meta["variants"]))

    # No sort here. The one ordering is reading_order, applied once in run();
    # a second, partial sort at this point used to shadow it and made the
    # output look stably ordered when the stability was an accident.


def severity_override(rule, variant: str):
    """The one place run-time severity policy lives.

    Content findings demote to warnings outside iiRDS/A: the B rules quote
    MUSTs, but the decision that a given file is "iiRDS XHTML5 content" — the
    entry condition — is this project's reading, and an unrestricted package
    may carry any content it likes. Under A the profile itself makes the
    restriction, so the errors stand. docs/divergences.md carries the
    reasoning.

    Extracted from the collection loop so the policy has a name: the SHACL
    shapes mirror rule severities and their README points here for the one
    divergence between a rule's own severity and what a run reports.
    """
    if rule.kind == "content" and variant != "A" and rule.severity is Severity.ERROR:
        return Severity.WARNING
    return None

def check(path, version: Optional[str] = None) -> Report:
    """Conformance only: container structure plus the metadata graph."""
    return run(path, CONFORMANCE_KINDS, version=version)


def lint(path, version: Optional[str] = None) -> Report:
    """Interoperability only: can a consumer actually use this package?"""
    return run(path, LINT_KINDS, version=version)
