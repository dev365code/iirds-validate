"""Rule execution."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from rdflib import URIRef

from . import rules as _rules  # noqa: F401  — importing registers every rule
from .context import Context, load_context
from .model import METADATA_RDF, Finding, Report, Rule, Severity, Violation
from .package import PackageError, UnreadablePath, open_package
from .registry import CATALOG, all_rules, rule_set_digest
from .rules.container import c9_violation, rdfxml_refusal

#: "system" is in every set: a container that could not be read has to be
#: reported whichever question the caller asked.
CONFORMANCE_KINDS = ("container", "schema", "content", "system")
LINT_KINDS = ("lint", "system")
ALL_KINDS = ("container", "schema", "content", "lint", "system")


#: The requirements whose subject is the ZIP archive itself. None can be
#: answered by a directory, so the runner is what says they were not assessed
#: -- in the report, not only in prose.
#:
#: Each of them used to open with `if not ctx.package.is_archive: return`, and
#: was counted as checked before it ran. R3 is the one that shows why this has
#: to be a list rather than a guard per rule: it carries the same guard, is
#: about the archive's own layout, and was left out when the other six moved
#: here -- so an unpacked container went on reporting it among the rules it had
#: checked. The unreached-line count is what found it.
ARCHIVE_ONLY = ("C1", "C3", "C6", "R3", "S7", "S8", "S10")


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


#: The questions the runner answers itself when the container rules were not
#: asked for: did each metadata file parse, and was the RDF/XML refused. Named
#: once and read twice -- by the emitter below and by the accounting, which
#: must not list them as unasked when the runner is about to ask them.
METADATA_ANSWERED = ("C9", "C16.1", "C16.2")


def _selected(rule, kinds: Sequence[str]) -> bool:
    """Whether the rule loop runs that rule.

    A conformance run also takes the two lint rules that are marked as
    conformance, so "the rules of the selected kinds" is not the set and a
    second copy of this expression would be wrong in a way nothing catches.
    """
    return rule.kind in kinds or ("schema" in kinds and rule.conformance)


def _put(rule, kinds: Sequence[str]) -> bool:
    """Whether this command puts that rule's question at all.

    Wider than `_selected`, and the difference is `METADATA_ANSWERED`: on a
    run that does not take the container rules, the runner asks those three
    itself. A container that would not open means it never got that far --
    which is `unreadable`, not `unasked`. Nobody stopped asking them; the
    container stopped being readable, and a reader told otherwise would think
    they had typed a different command.
    """
    return _selected(rule, kinds) or (rule.id in METADATA_ANSWERED
                                      and "container" not in kinds)


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
        refusal = rdfxml_refusal(error)
        if refusal is not None:
            yield Finding(_emitted("C9", "container"), c9_violation(refusal))
            continue
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
    report.drop(FRAGMENT_SUSPENDED, "fragment")
    report.notes.append(
        "fragment mode: validated inside a throwaway container; "
        "package-level rules suspended (%s)"
        % (", ".join(suspended) if suspended else "none fired"))
    return report


def run(path, kinds: Sequence[str] = CONFORMANCE_KINDS, version: Optional[str] = None,
        include_info: bool = True) -> Report:
    report = Report(path=str(path), kinds=tuple(kinds), rule_set=rule_set_digest(),
                    includes_info=include_info)

    try:
        package = open_package(path)
    except PackageError as exc:
        # S1 is "nothing could be read from that path"; C1 is "something was
        # read and it is not a usable ZIP". Both are catalogued, and emitting
        # C1 for both left S1 unable to fire at all while its own docstring
        # claimed this was where it came from.
        unreadable = isinstance(exc, UnreadablePath)
        finding = Finding(
            _emitted("S1", "system") if unreadable else _emitted("S13", "system"),
            Violation("cannot read container" if unreadable else "cannot open container",
                      subject=str(path), detail=str(exc)))
        report.add(finding)
        # Read off the finding rather than written out again: the id is
        # already decided one line above, and a second copy of it is a second
        # thing to keep in step.
        report.answered(finding.rule.id)
        # Nothing else was put to this container, and saying so is the point:
        # a rule missing from both lists is one a later reader has to guess
        # about. The report a person is most likely to keep and re-run named
        # one rule and was silent about the other two hundred.
        for rule in all_rules():
            if rule.id in report.ran:
                continue
            reason = "unreadable" if _put(rule, kinds) else "unasked"
            report.not_applicable[reason].append(rule.id)
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
    # A namespace spelled `iirds/` for `iirds#`, or a document that is not
    # about iiRDS at all, used to be reported as "declares no iirds:Package"
    # and a proprietary class per type: three true findings, none of them
    # the place to look. Said once, and before every other note -- the
    # version note came first and said "no iirds:iiRDSVersion", true and the
    # wrong layer again, when the version was there under the misspelling.
    iris = {term for triple in ctx.graph for term in triple if isinstance(term, URIRef)}
    if iris and not any(ctx.ontology.is_iirds_term(term) for term in iris):
        report.notes.append(
            "no iiRDS name appears in the metadata (%d IRIs, none under an iiRDS namespace); "
            "the findings below describe the absence of iiRDS rather than a defect in it "
            "-- check the namespace, which is http://iirds.tekom.de/iirds# for the core "
            "vocabulary" % len(iris))
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
            "validated as an unpacked container; the %d requirements about the ZIP "
            "archive itself (%s) cannot be assessed until it is packed"
            % (len(ARCHIVE_ONLY), ", ".join(ARCHIVE_ONLY)))
    if ctx.ontology.substituted:
        report.notes.append(
            "no ontology bundled for iiRDS %s; class hierarchy taken from %s, so rules that "
            "depend on subclassing may differ from that version"
            % (ctx.version, ctx.ontology.substituted))
    if ctx.sources:
        report.notes.append("metadata read from " + ", ".join(ctx.sources))
    if not ctx.sources:
        report.notes.append("no usable metadata found; the graph rules had nothing to check")

    # Before the loop, so that the three questions the runner answers itself
    # are already recorded when the loop decides what was never asked.
    if "container" not in kinds:
        for rule_id in METADATA_ANSWERED:
            report.answered(rule_id)
    for finding in _metadata_findings(ctx, kinds):
        report.add(finding)

    for rule in all_rules():
        if not _selected(rule, kinds):
            if rule.id not in report.ran:
                report.not_applicable["unasked"].append(rule.id)
            continue
        if not rule.applies_to(ctx.version, ctx.variant):
            reason = "version" if rule.versions and ctx.version not in rule.versions else "variant"
            report.not_applicable[reason].append(rule.id)
            continue
        # These stand down at their own first line when the container is not an
        # archive, and the count was incremented before they ran -- so an
        # unpacked directory reported them among the rules it had checked and
        # came back clean. "Not assessed" was a sentence in `notes` and nothing
        # a consumer of the report could read.
        if rule.id in ARCHIVE_ONLY and not package.is_archive:
            report.not_applicable["unpacked"].append(rule.id)
            continue
        try:
            for violation in rule.fn(ctx) or ():
                if rule.severity is Severity.INFO and not include_info:
                    continue
                report.add(Finding(rule, violation,
                                   demoted_to=severity_override(rule, ctx.variant)))
        except Exception as exc:                      # a broken rule must not hide the rest
            # S3's own words: "A rule that raised has checked nothing, and this
            # finding exists so that its silence is not read as a pass." The
            # count was incremented before the rule was called, so the report
            # said it had checked it anyway. Whatever it managed to yield
            # first goes with it -- a partial list of a rule's findings reads
            # exactly like a complete one.
            crash = Finding(
                _emitted("S3"),
                Violation("rule %s raised %s" % (rule.id, type(exc).__name__), detail=str(exc)))
            report.drop((rule.id,), "raised")
            report.add(crash)
            report.answered(crash.rule.id)
            continue
        report.answered(rule.id)


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
