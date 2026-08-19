"""Vocabulary, rule metadata and result types."""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Tuple

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

# Where metadata lives inside the container.
MIMETYPE_FILE = "mimetype"
MIMETYPE_VALUE = "application/iirds+zip"
META_DIR = "META-INF"
METADATA_RDF = "META-INF/metadata.rdf"
METADATA_JSONLD = "META-INF/metadata.jsonld"


_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


#: The base every metadata document is parsed against. Deliberately a URN:
#: URNs are not hierarchical, so a relative rdf:about is left relative rather
#: than being silently joined into something that looks absolute.
PACKAGE_BASE = "urn:iirds:package:"


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

    @property
    def id(self) -> str:
        return self.rule.id

    @property
    def severity(self) -> Severity:
        return self.rule.severity

    def as_dict(self) -> dict:
        return {
            "rule": self.rule.id,
            "kind": self.rule.kind,
            "severity": str(self.severity),
            "priority": self.rule.prio,
            "message": self.violation.message,
            "subject": self.violation.subject,
            "detail": self.violation.detail,
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
