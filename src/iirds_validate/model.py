"""Vocabulary, rule metadata and result types."""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Tuple

from iirds import METADATA_JSONLD, METADATA_RDF, PACKAGE_BASE  # noqa: F401  (re-exported)
from rdflib import Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD  # noqa: F401  (re-exported)

# --- iiRDS namespaces -------------------------------------------------------
IIRDS = Namespace("http://iirds.tekom.de/iirds#")
HOV = Namespace("http://iirds.tekom.de/iirds/domain/handover#")
MACH = Namespace("http://iirds.tekom.de/iirds/domain/machinery#")
SW = Namespace("http://iirds.tekom.de/iirds/domain/software#")
VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")

IIRDS_NAMESPACES = (str(IIRDS), str(HOV), str(MACH), str(SW))

VERSIONS: Tuple[str, ...] = ("1.0", "1.0.1", "1.1", "1.2", "1.3")
LATEST_VERSION = "1.3"
VARIANTS: Tuple[str, ...] = ("unrestricted", "A", "H")

# Where metadata lives inside the container. The two metadata paths and the
# parse base are the ecosystem's agreement, not this project's alone, so they
# are imported from the shared SDK above rather than declared a second time.
MIMETYPE_FILE = "mimetype"
MIMETYPE_VALUE = "application/iirds+zip"
META_DIR = "META-INF"


_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


#: PACKAGE_BASE (imported above) is deliberately a URN: URNs are not
#: hierarchical, so a relative rdf:about is left relative rather than being
#: silently joined into something that looks absolute.


def is_absolute_iri(node) -> bool:
    """An absolute IRI has a scheme. `urn:uuid:...` counts; a bare name does not."""
    return isinstance(node, URIRef) and bool(_SCHEME.match(str(node)))


def is_named(node) -> bool:
    """The resource was given an identifier of its own.

    Two ways it can fail. A blank node has no identifier at all. And
    `rdf:about=""` is a relative reference to the document itself, so it
    resolves to the base and comes back looking like a perfectly good IRI — a
    node that *is* the base was never named. Every "MUST have an IRI" rule
    turns on this, so getting it wrong silences sixty of them at once.

    A *relative* IRI does count as named. It identifies the resource; whether
    it should have been absolute is M5's question, and M5 is a RECOMMENDED.
    Conflating the two turned a recommendation into sixty MUSTs and failed
    packages the reference tool accepts.
    """
    return isinstance(node, URIRef) and str(node) not in ("", PACKAGE_BASE)


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    def __str__(self) -> str:
        return self.value


#: Specification keyword -> how loudly we complain.
PRIO_SEVERITY = {
    "MUST": Severity.ERROR,
    "MUST NOT": Severity.ERROR,
    "REQUIRED": Severity.ERROR,
    "SHALL": Severity.ERROR,
    "RECOMMENDED": Severity.WARNING,
    "SHOULD": Severity.WARNING,
    "MAY": Severity.INFO,
    "OPTIONAL": Severity.INFO,
}


@dataclass(frozen=True)
class Violation:
    """One concrete thing that is wrong, produced by a rule."""

    message: str
    subject: Optional[str] = None   # offending IRI, or path inside the container
    detail: Optional[str] = None    # extra context, e.g. the value we saw
    #: What to do about it, when this instance needs something more specific
    #: than the rule's standing advice. Most do not; the rule's `fix` covers
    #: the ordinary case and this overrides it where the remedy depends on
    #: what was actually found.
    fix: Optional[str] = None


@dataclass(frozen=True)
class Rule:
    id: str
    kind: str                       # container | schema | lint
    prio: str
    title: str
    versions: Tuple[str, ...]
    variants: Tuple[str, ...]       # empty tuple == applies to every variant
    spec: Optional[str]
    fn: Callable[..., Iterable[Violation]]
    #: One imperative sentence: what to change so this stops being reported.
    #:
    #: A validator that names a defect without naming the remedy has told you
    #: that something is wrong and left you to find the specification, which is
    #: most of the work and all of the expertise. Every rule carries this, and
    #: `tests/test_remediation.py` refuses a rule that does not.
    #:
    #: Not the requirement restated in the imperative. "Rendition must have
    #: exactly one iirds:format" -> "add an iirds:format" says nothing the
    #: message did not. Say where it goes, and what a correct value looks like.
    fix: Optional[str] = None
    #: Where this finding belongs in a report somebody has to act on.
    #:
    #: "cause" for a rule that explains other findings, "consequence" for one
    #: that only exists because something else went wrong, empty for the rest.
    #: Reports are ordered by it, because rule-id order buried R3 -- the finding
    #: that says the package is fine and merely misplaced -- fourth behind three
    #: telling the author to add files they already had.
    diagnosis: str = ""
    #: Ids from `docs/requirements.json`: which of the specification's 314
    #: absolute obligations this rule implements.
    #:
    #: The map from standard to rules, kept in the rules rather than in a
    #: document beside them, because a document beside them drifts. Empty on
    #: most rules today -- the enumeration exists and the mapping has barely
    #: started -- and the number that can honestly be published is the size of
    #: the union of these, which is why they live somewhere a test can count.
    covers: Tuple[str, ...] = ()
    #: True when a rule of ours implements a sentence the specification states
    #: as a MUST. Those have to run under `check`, whatever bucket they were
    #: written in — an advisory that the standard makes mandatory is not an
    #: advisory.
    conformance: bool = False

    @property
    def severity(self) -> Severity:
        return PRIO_SEVERITY.get(self.prio, Severity.WARNING)

    def applies_to(self, version: str, variant: str) -> bool:
        if self.versions and version not in self.versions:
            return False
        return not (self.variants and variant not in self.variants)


@dataclass(frozen=True)
class Finding:
    """A violation with its rule metadata resolved — what users actually see."""

    rule: Rule
    violation: Violation
    #: Severity the runner assigned for THIS run, where it differs from the
    #: rule's own. The Appendix B content rules are literal MUSTs, but which
    #: files they examine is this project's reading — so under iiRDS/A, whose
    #: whole point is restricting content to iiRDS XHTML5, they stay errors,
    #: and everywhere else they demote to warnings. The rule cannot know the
    #: profile; the runner can.
    demoted_to: Optional[Severity] = None

    @property
    def id(self) -> str:
        return self.rule.id

    @property
    def severity(self) -> Severity:
        return self.demoted_to or self.rule.severity

    #: Causes first, then error before warning before note, then consequences.
    #: Rule id last so the order is total and two runs cannot differ.
    ORDER = {"cause": 0, "": 1, "consequence": 2}
    SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}

    @property
    def reading_order(self):
        """Sort key for a person reading top to bottom.

        Total, down to the message: two findings of one rule must sort the
        same way on every run, or the determinism work quietly unravels one
        layer down — same findings, same first line, shuffled middle. The
        subject and detail are part of the key for exactly that reason, not
        for the reader.
        """
        rank = Finding.ORDER.get(self.rule.diagnosis, 1)
        return (rank,
                Finding.SEVERITY_ORDER[self.severity] if rank == 1 else 0,
                self.rule.id,
                self.violation.subject or "",
                self.violation.detail or "",
                self.violation.message)

    @property
    def fix(self) -> Optional[str]:
        """What to do about it: the violation's own advice, or the rule's."""
        return self.violation.fix or self.rule.fix

    @property
    def source(self) -> str:
        """Whose rule this is.

        `B*`, `L*` and `S4`-`S8` share an identifier namespace with the
        catalogue. If the catalogue ever mints a real `B1`, a stored report
        would become ambiguous and could not be repaired after the fact, so
        every finding says where its rule came from.
        """
        from .registry import CATALOG
        return "catalogue" if self.rule.id in CATALOG else "iirds-validate"

    def as_dict(self) -> dict:
        return {
            "rule": self.rule.id,
            "source": self.source,
            "kind": self.rule.kind,
            "severity": str(self.severity),
            "priority": self.rule.prio,
            "message": self.violation.message,
            "subject": self.violation.subject,
            "detail": self.violation.detail,
            "fix": self.fix,
            "diagnosis": self.rule.diagnosis or None,
            "title": self.rule.title,
            "spec": self.rule.spec,
        }


@dataclass
class Report:
    path: str
    version: Optional[str] = None            # as declared by the package, if it did
    effective_version: Optional[str] = None  # what the rules were actually run against
    variant: str = "unrestricted"
    findings: list = field(default_factory=list)
    checked: int = 0                 # rules actually executed
    skipped: int = 0                 # rules not applicable to this version/variant
    unimplemented: int = 0           # catalogued but not yet implemented here
    notes: list = field(default_factory=list)

    def count(self, sev: Severity) -> int:
        return sum(1 for f in self.findings if f.severity is sev)

    @property
    def ok(self) -> bool:
        return self.count(Severity.ERROR) == 0

    def as_dict(self) -> dict:
        return {
            "schemaVersion": 1,
            "package": self.path,
            "iirdsVersion": self.version,
            "validatedAgainst": self.effective_version,
            "variant": self.variant,
            "ok": self.ok,
            "summary": {
                "errors": self.count(Severity.ERROR),
                "warnings": self.count(Severity.WARNING),
                "info": self.count(Severity.INFO),
                "rulesChecked": self.checked,
                "rulesSkipped": self.skipped,
                "rulesNotImplemented": self.unimplemented,
            },
            "notes": self.notes,
            "findings": [f.as_dict() for f in self.findings],
        }
