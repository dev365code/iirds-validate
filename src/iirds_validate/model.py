"""Vocabulary, rule metadata and result types."""
from __future__ import annotations

import enum
import heapq
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Tuple

from rdflib import Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD  # noqa: F401  (re-exported)

from iirds import METADATA_JSONLD, METADATA_RDF, PACKAGE_BASE  # noqa: F401  (re-exported)

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


#: How many findings of one rule reach the listing. One rule can have as many
#: findings as the document has elements, and a metadata file repeating a
#: violation costs a few bytes per repetition and produces a finding per
#: repetition: 20,000 of them in a 51 KB archive made 17 MB of JSON and 143 MB
#: resident, linear all the way. Nobody reads the twenty-thousandth line and
#: nothing downstream needs it -- the count does, and the count is not bounded.
MAX_LISTED_PER_RULE = 100


class _Latest:
    """Orders a finding by how *late* it sorts, so a heap's root is the one to drop.

    A bounded listing has to keep the findings that sort first, not the ones
    that happened to arrive first: which arrive first is graph order, and graph
    order is a fact about this process. Inverting the comparison lets one heap
    hold the survivors and hand back the loser in log time.
    """

    __slots__ = ("key",)

    def __init__(self, finding):
        self.key = finding.reading_order

    def __lt__(self, other) -> bool:
        return self.key > other.key


@dataclass
class Report:
    path: str
    version: Optional[str] = None            # as declared by the package, if it did
    effective_version: Optional[str] = None  # what the rules were actually run against
    variant: str = "unrestricted"
    checked: int = 0                 # rules actually executed
    skipped: int = 0                 # rules not applicable to this version/variant
    unimplemented: int = 0           # catalogued but not yet implemented here
    notes: list = field(default_factory=list)
    #: rule id -> how many of its findings were counted but not listed.
    suppressed: dict = field(default_factory=dict)
    _kept: dict = field(default_factory=dict, repr=False)
    _unlisted_severity: dict = field(default_factory=dict, repr=False)
    _order: list = field(default_factory=lambda: [0], repr=False)
    _flat: Optional[list] = field(default=None, repr=False)

    @property
    def findings(self) -> list:
        """Every finding kept, in the order a person reads them.

        Derived rather than stored, because what is kept is decided per rule
        and the decision is revisited as findings arrive: a rule at its limit
        keeps the new finding and drops its own latest-sorting one. Ordering
        here rather than in the caller means a report cannot be read before it
        is ordered, which it could when the sort lived at one call site and
        the early return skipped it.
        """
        if self._flat is None:
            self._flat = sorted((finding for bucket in self._kept.values()
                                 for _, _, finding in bucket),
                                key=lambda f: f.reading_order)
        return self._flat

    def add(self, finding) -> None:
        """The one way a finding enters a report.

        A gateway rather than a bound at each caller, because the callers are
        four today and the next one is the one that forgets. What it bounds is
        the listing; `count` below reads the suppressed tally too, so the
        summary, `ok` and the exit code are computed over every finding
        whether or not it was kept.

        Which ones are kept is the whole difficulty. Keeping the first hundred
        to arrive keeps a hundred chosen by graph order -- and rdflib's store
        iterates in an order this process's hash seed and this parse's
        blank-node labels perturb, so the same package listed a different
        hundred every run. The hundred that sort first are the same hundred
        every run, and are also the hundred a reader would have wanted.
        """
        self._flat = None
        bucket = self._kept.setdefault(finding.rule.id, [])
        self._order[0] += 1
        entry = (_Latest(finding), self._order[0], finding)
        if len(bucket) < MAX_LISTED_PER_RULE:
            heapq.heappush(bucket, entry)
            return
        _latest, _seq, dropped = heapq.heappushpop(bucket, entry)
        self.suppressed[finding.rule.id] = self.suppressed.get(finding.rule.id, 0) + 1
        severity = dropped.severity
        self._unlisted_severity[severity] = self._unlisted_severity.get(severity, 0) + 1

    def drop(self, rule_ids) -> None:
        """Forget a rule entirely -- listing, tally and all.

        `--fragment` suspends the rules a snippet cannot satisfy, and a rule
        removed from the listing while its suppressed tally stayed behind
        would leave a summary counting findings the report does not contain.
        """
        rule_ids = set(rule_ids)
        for rule_id in rule_ids & set(self._kept):
            severity = self._kept[rule_id][0][2].severity
            if rule_id in self.suppressed:
                self._unlisted_severity[severity] = max(
                    0, self._unlisted_severity.get(severity, 0) - self.suppressed.pop(rule_id))
            del self._kept[rule_id]
        self._flat = None

    def total_for(self, rule_id: str) -> int:
        """How many findings that rule produced, listed or not."""
        return len(self._kept.get(rule_id, ())) + self.suppressed.get(rule_id, 0)

    def count(self, sev: Severity) -> int:
        return (sum(1 for f in self.findings if f.severity is sev)
                + self._unlisted_severity.get(sev, 0))

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
                "findingsNotListed": sum(self.suppressed.values()),
            },
            "notes": self.notes,
            #: What the listing left out, per rule and in total. A stored
            #: report has to be readable as a whole thing later, so it says
            #: this rather than leaving a reader to infer it from a summary
            #: that does not match the list beneath it.
            "suppressed": dict(self.suppressed),
            "findings": [f.as_dict() for f in self.findings],
        }
