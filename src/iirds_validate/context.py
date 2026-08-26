"""Everything a rule is handed: the container, the graph, and the ontology.

The whole point of this project lives in `build_graph`. iiRDS metadata is RDF,
and RDF says nothing about how it is written down. These are the same fact:

    <iirds:Document rdf:about="urn:d1"/>

    <rdf:Description rdf:about="urn:d1">
      <rdf:type rdf:resource="http://iirds.tekom.de/iirds#Document"/>
    </rdf:Description>

and so are these:

    <iirds:relates-to-event><iirds:Event rdf:about="urn:e1"/></iirds:relates-to-event>
    <iirds:relates-to-event rdf:resource="urn:e1"/>

A validator that walks the XML tree sees one form and misses the other, which is
how a package can be perfectly conformant and still unreadable to the tool that
is supposed to bless it. Parsing into a graph makes the distinction disappear
before any rule runs — and lets the same rules apply to metadata.jsonld.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Set

from iirds import MAX_METADATA_BYTES, merge_sources, parse_metadata, subclasses_of
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDF, RDFS

from . import ontology as ontology_mod
from . import terms as T
from .model import LATEST_VERSION, METADATA_JSONLD, METADATA_RDF, PACKAGE_BASE, VERSIONS
from .package import Package


@dataclass
class Context:
    package: Package
    graph: Graph
    ontology: ontology_mod.Ontology
    version: str
    variant: str
    declared_version: Optional[str] = None      # None when the package omits it
    requested_version: Optional[str] = None     # set when the caller overrode it
    parse_errors: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    #: One graph per metadata file, kept alongside the merged `graph` so a rule
    #: can ask whether the serialisations agree. Merging is right for every
    #: other rule and is exactly what hides a disagreement.
    per_source: dict = field(default_factory=dict)

    #: Per-class closure over ontology *and* package subclass declarations,
    #: filled lazily. Per-instance, same reasoning as Ontology's caches.
    _closure: dict = field(default_factory=dict, repr=False)

    # -- graph helpers ------------------------------------------------------
    def instances_of(self, cls: URIRef, include_subclasses: bool = True) -> List:
        """Subjects typed `cls`, or any class beneath it.

        "Beneath it" spans both hierarchies: the bundled ontology's, and any
        rdfs:subClassOf the package itself declares. Section 7 lets a package
        mint proprietary subclasses of iiRDS classes and requires consumers to
        process them as the parent -- so an instance typed only with the
        package's own subclass of iirds:Topic is a Topic to every rule here.
        (SHACL agrees by definition: targetClass follows the data graph's
        subClassOf. The differential gate caught this as a SHACL-only firing.)
        """
        # Sorted, like typed_as: the closure is a frozenset, and iterating one
        # orders the subjects by whichever class came out first. That reaches
        # the report through the order findings are generated in, and through
        # every rule that lists what it found.
        classes = self._class_closure(cls) if include_subclasses else {cls}
        out, seen = [], set()
        for c in sorted(classes, key=str):
            for s in self.graph.subjects(RDF.type, c):
                if s not in seen:
                    seen.add(s)
                    out.append(s)
        return out

    def _class_closure(self, cls: URIRef) -> frozenset:
        if cls not in self._closure:
            classes = set(self.ontology.subclasses_of(cls))
            for c in tuple(classes):
                classes.update(subclasses_of(self.graph, c))
            self._closure[cls] = frozenset(classes)
        return self._closure[cls]

    def typed_as(self, cls: URIRef) -> List:
        """Subjects typed `cls`, or any subclass the *package itself* declares.

        Between `instances_of`, which also walks the bundled ontology, and
        `typed_exactly`, which walks nothing. Section 7 lets a package subclass
        an iiRDS class and requires a consumer to process the instance as the
        parent, so a rule about a class has to see those; the ontology's own
        hierarchy is a different matter, because `iirds:iirdsDomainEntity` sits
        above nearly everything and pulling its descendants into one grouping
        class's rule would report every blank-node Rendition in a good package.

        `sh:targetClass` sees exactly this population -- the data graph's
        `rdfs:subClassOf` and nothing else -- which is what keeps the two
        encodings from disagreeing about who is in scope.
        """
        out, seen = [], set()
        for c in sorted(subclasses_of(self.graph, cls), key=str):
            for subject in self.graph.subjects(RDF.type, c):
                if subject not in seen:
                    seen.add(subject)
                    out.append(subject)
        return out

    def typed_exactly(self, cls: URIRef) -> List:
        """Subjects carrying `cls` itself as an rdf:type (no subclasses)."""
        return list(self.graph.subjects(RDF.type, cls))

    def is_instance(self, node, cls: URIRef) -> bool:
        """Is `node` an instance of `cls` under the same closure as
        `instances_of` — ontology hierarchy plus the package's own
        subclass declarations? Rules that ask about one node should ask
        this, not compare rdf:type values directly: exact typing is how
        section 7 gets forgotten one rule at a time."""
        return bool(set(self.values(node, RDF.type)) & self._class_closure(cls))

    def values(self, subject, prop: URIRef) -> List:
        return list(self.graph.objects(subject, prop))

    def one(self, subject, prop: URIRef):
        for o in self.graph.objects(subject, prop):
            return o
        return None

    def has(self, subject, prop: URIRef) -> bool:
        return (subject, prop, None) in self.graph

    def information_units(self) -> List:
        return self.instances_of(T.InformationUnit)

    def iirds_subjects(self) -> Set:
        """Every subject that carries at least one iiRDS type."""
        out = set()
        for s, o in self.graph.subject_objects(RDF.type):
            if self.ontology.is_iirds_term(o):
                out.add(s)
        return out

    def ref(self, node) -> str:
        """A name for a node that is the same on every run.

        rdflib mints a fresh identifier for every blank node on every parse, so
        a finding that reported `str(node)` gave `N8892b8d9…` one run and
        `N39e7e968…` the next. Two effects, both bad: a JSON report could not be
        diffed between runs, and the same package written as RDF/XML and as
        JSON-LD produced different findings — which is the one property this
        project claims above all others.

        A blank node is named by how you reach it instead: the nearest named
        subject and the property that points at it, which is also far more use
        to somebody reading the report than an opaque identifier. Where that
        fails, a hash of the statements about the node, which is stable because
        the statements are.
        """
        if not isinstance(node, BNode):
            return str(node)
        named = sorted((str(s), str(p)) for s, p in self.graph.subject_predicates(node)
                       if not isinstance(s, BNode))
        if named:
            subject, predicate = named[0]
            return "%s %s" % (subject, predicate.split("#")[-1].split("/")[-1])
        return "_:%s" % self._content_key(node)

    def _content_key(self, node, depth: int = 4, seen: frozenset = frozenset()) -> str:
        """A short name for a blank node, derived from what it says."""
        return said_by(self.graph, node, depth, seen)[:12]

    def label_of(self, node) -> str:
        """A human name for a node, or the most useful stand-in there is."""
        for p in (RDFS.label, T.title):
            v = self.one(node, p)
            if v is not None:
                return str(v)
        # ref, not str: an unlabelled blank node printed its minted identifier
        # here, and this one line feeds the detail of nine rules.
        return self.ref(node)


def _field(text: str) -> str:
    """One field, with its own length in front of it.

    A separator is not a boundary. Joining `predicate value` pairs with a
    newline let a value holding a newline and the text of a plausible
    neighbour spell the end of its own field, so two blank nodes saying
    different things answered to one name -- and a tie puts them back in
    graph order, which is the hash-seed order this exists to escape.
    """
    return "%d:%s" % (len(text), text)


def said_by(graph: Graph, node, depth: int = 4, seen: frozenset = frozenset()) -> str:
    """A name for a blank node derived from what it says, not from its id.

    The identifier rdflib gives a blank node is minted per parse -- that is
    what a blank node is -- so any name built from it changes between runs of
    the same file. This reads the statements instead, and renders a
    blank-node object as its own name rather than as its id, so nesting is
    covered: a Rendition under a Rendition was the shape that got past the
    first attempt, and a blank object left out of the digest altogether was
    the shape that got past the second.

    Bounded and cycle-safe on purpose. Beyond the depth, or back at a node
    already on the path, the child renders as a placeholder -- a collision
    there costs a reader a moment of ambiguity, while unbounded recursion
    costs them the run. The parts are sorted after rendering, so two graphs
    that say the same thing in a different order agree.
    """
    if depth <= 0 or node in seen:
        return "..."
    seen = seen | {node}
    parts = []
    for predicate, obj in graph.predicate_objects(node):
        rendered = ("_:" + said_by(graph, obj, depth - 1, seen)
                    if isinstance(obj, BNode) else str(obj))
        parts.append(_field(str(predicate)) + _field(rendered))
    parts.sort()
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()


def _node_key(graph: Graph, node):
    """A total order over package nodes that survives a new process.

    Named nodes sort by IRI. A blank node cannot: rdflib mints its label per
    parse, so sorting by it picks a different package tomorrow -- the same
    reason `Context.ref` exists. It sorts by what it says instead, after the
    named ones, under the same digest the report labels it with, so a node
    the report calls two things cannot be one thing to the ordering.
    """
    if isinstance(node, URIRef):
        return (0, str(node))
    return (1, said_by(graph, node))


def package_nodes(graph: Graph) -> List:
    """Every iirds:Package in the graph, in a fixed order.

    Closes over the subclasses the package declares, because §7 lets a
    package subclass an iiRDS class and requires a consumer to treat the
    instance as its parent. The ontology is deliberately not consulted:
    this runs before one is chosen, and tests/test_version_handling.py pins
    the premise that makes that complete -- the standard declares no
    subclass of iirds:Package.

    Ordered because graph order is not stable between processes. A parsed
    graph answers an indexed lookup in document order, but the merge that
    builds this graph fills a fresh one by iterating the parse, which is
    not ordered, so the order that reaches here changes with the hash seed.
    """
    out, seen = [], set()
    for cls in sorted(subclasses_of(graph, T.Package), key=str):
        for subject in graph.subjects(RDF.type, cls):
            if subject not in seen:
                seen.add(subject)
                out.append(subject)
    return sorted(out, key=lambda node: _node_key(graph, node))


def container_packages(graph: Graph) -> List:
    """The packages that represent this container, in a fixed order.

    A nested child is part of a *different* package. §6.2 draws the line with
    that word -- the container's own instance "MUST NOT be a member of
    another iiRDS package expressed by the property iirds:is-part-of-package"
    -- and the same sentence stands unchanged in 1.0. Reading the bare
    presence of the predicate as nesting let a package declared part of
    itself claim the exemption §6.3 grants to a child, and that exemption
    silences a MUST NOT: the same package drew M8 without the triple and
    nothing with it.

    The named parent has to be here, and has to be a package. §6.3.3 asks the
    child's package to "reference exactly one iirds:Package", and both of its
    MUSTs are scoped to one document -- "in the metadata.rdf file of the
    parent iiRDS container" -- where §6.2 requires the parent's own instance
    to exist. Example 16 prints both files and the child's own metadata.rdf
    carries no is-part-of-package at all, so a child delivered alone is not
    supposed to have the triple. Reading it more loosely meant an IRI nothing
    describes, a Topic, a literal or an anonymous blank node each bought the
    exemption -- and one of them beside a self-loop re-opened the bypass
    closed just before this. The population is the graph's own, not the
    ontology's, because SHACL's sh:class sees only the data graph and the two
    encodings have to be asking about the same nodes.

    M3 and M8 read it here -- one predicate, one place, so a package cannot
    be the container for one rule and a child for the next.

    Returns what it finds, including nothing: M3 has to be able to tell
    "no container package" from "one", and a fallback here would take that
    apart. Choosing what to do about an empty answer belongs to the caller.
    """
    packages = package_nodes(graph)
    present = set(packages)
    return [pkg for pkg in packages
            if not any(parent != pkg and parent in present
                       for parent in graph.objects(pkg, T.is_part_of_package))]


def _named_profiles(graph: Graph, pkg):
    """The formatRestriction values that name something, in a fixed order.

    A profile is a name, and a blank node names nothing -- its label is
    minted per parse, so letting one through put a different identifier in
    the report on every run and called it the package's profile. Skipped
    here; S5 still reports the value as one the standard does not publish.
    """
    return sorted(str(v).strip() for v in graph.objects(pkg, T.formatRestriction)
                  if not isinstance(v, BNode) and str(v).strip())


def _declared_rank(graph: Graph, pkg):
    """How new the version this package declares is, for choosing between
    packages that both claim to represent the container.

    Where several claim it M3 reports the pair, so no choice makes the package
    pass -- what the choice decides is whether the *other* defects in it are
    looked for. Taking whichever sorted first let a package declaring 1.0 win
    an alphabetical tie-break and stand every 1.1+ rule down, so a plain §6.3
    violation beside it went unreported. The newest answers, for the same
    reason two versions on one package resolve to the newer and a missing one
    falls back to the newest: nothing passes by silence.

    A package declaring nothing ranks as the newest rather than as the oldest,
    because that is already what "no declaration" means eight lines down.
    Ranking it lowest would let a declared 1.0 beat it and switch off rules
    that a missing version leaves on.

    Ranked by the version the run will be *judged against*, not by the string
    declared. `_version_key` sorts what it cannot read after every number,
    which is right inside one package -- a typo beside a real version wins
    and falls back to the newest, so the typo gets reported. Across packages
    it was wrong in a way that cost rules: a decoy declaring `banana` or an
    unpublished `9.9` outranked a real 1.3, and the profile comes off the
    same node, so the handover MUSTs stood down. Anything the run cannot use
    is the newest here too, which puts it level rather than on top.

    That leaves ties, and the tie is broken towards saying more: a package
    that names its profile is preferred over one that does not, because the
    named profile is the one that adds rules. Without it the tie fell back to
    IRI order -- the tie-break this exists to replace -- and a silent decoy
    beside a real iiRDS/H package took seventeen rules with it.
    """
    declared = sorted((str(v).strip() for v in graph.objects(pkg, T.iiRDSVersion)),
                      key=_version_key)
    newest = declared[-1] if declared else LATEST_VERSION
    effective = newest if newest in VERSIONS else LATEST_VERSION
    return (_version_key(effective), bool(_named_profiles(graph, pkg)))


def _detect(graph: Graph):
    """Read iirds:iiRDSVersion / iirds:formatRestriction off one package.

    One package: read with an accumulator each, a run could answer with a
    version off one package and a profile off another -- a pair no package
    in the container ever declared.

    Which one: the container's, not a nested child's. A child declares its
    own profile, and reading it as the container's turns the handover MUSTs
    on against a package that never claimed to be one. When nesting leaves
    no container at all, something still has to answer, because the
    alternative is to judge a 1.0 document against 1.3 while its own
    declaration sits three lines away. Then every package answers. Reaching
    that needs packages nested inside each other: a package part of itself is
    a container, and so is one whose named parent is not here, so both are
    answered before the fallback. There was a middle tier for the roots of
    what is present; under the reading above its predicate became the same
    one, so it could never contribute and it is gone.

    Where several candidates remain the first under the ordering answers.
    That is a fixed choice rather than a meaningful one, and in the fallback
    branches M3 is not reporting the ambiguity either -- it asks about
    container packages, and there are none. The report names the version and
    profile it used, which is where a reader sees which package won.

    Where one package declares several versions, M4 reports that and the
    newest answers. The lower one read as the kinder choice and is not: it
    switches rules off, so a package that breaks one of them can silence the
    finding by declaring an older version beside its own. Eight lines down,
    a missing version falls back to the newest for exactly that reason --
    nothing passes by silence -- and these two cannot be different rules.
    Profiles are not ordered, so where several are declared the first stands
    with nothing to prefer about it.
    """
    pool = container_packages(graph) or package_nodes(graph)
    if not pool:
        return None, "unrestricted"
    pool = sorted(pool, key=lambda node: _declared_rank(graph, node), reverse=True)
    pkg = pool[0]
    versions = sorted((str(v).strip() for v in graph.objects(pkg, T.iiRDSVersion)),
                      key=_version_key)
    variants = _named_profiles(graph, pkg)
    # `or "unrestricted"` rather than a default: an empty formatRestriction is
    # not a restriction, and S5 is silent about one in both encodings.
    return (versions[-1] if versions else None), (variants[0] if variants else "") or "unrestricted"


def _version_key(text: str):
    """A declared version as numbers where it is one, and after every number
    where it is not.

    Plain text order happens to be right for every version the standard has
    published -- tests/test_version_handling.py pins that -- but it is right
    by luck: a 1.10 would sort between 1.1 and 1.2. Anything unparseable
    sorts last so that a package declaring a real version beside a typo is
    judged against the typo, which falls back to the newest and reports it,
    rather than against the real one with the typo unmentioned.
    """
    parts = text.split(".")
    # isdecimal, not isdigit: `"\u00b2".isdigit()` is true and `int("\u00b2")` raises, so
    # the guard passed a value the conversion then refused -- and this runs
    # before any rule, outside the net where a rule that raises becomes a
    # finding, so one character ended the whole run.
    if text and all(part.isdecimal() for part in parts):
        return (0, tuple(int(part) for part in parts))
    return (1, text)



def build_graph(package: Package):
    """Parse every metadata serialisation in the container into one graph.

    The guards (entity declarations, oversize, remote @context, byte order
    marks), the parser and the isomorphic-once merge live in the iirds SDK:
    this project wrote them, moved them to the layer every tool shares, and
    imports them back, so the SDK's answer can never contradict this one.
    The one gate kept here is the pre-read size check -- it runs off the
    container's directory, refusing an oversized document without ever
    decompressing it, which only the container layer can do; the SDK's own
    length check backstops direct callers.
    """
    errors: List[str] = []
    sources: List[str] = []
    per_source = {}

    for name in (METADATA_RDF, METADATA_JSONLD):
        if not package.has(name):
            continue

        # Measured, not declared. The uncompressed size in a ZIP's central
        # directory is written by whoever built the archive, so a gate reading
        # it is a gate the sender sets -- in either direction: an entry
        # claiming a hundred bytes over a hundred megabytes of deflate passed
        # this and cost the hundred megabytes, and one claiming a gigabyte
        # over nothing was refused unread. `read_bounded` stops at the limit
        # whatever the entry claims, and the verdict is about what came back.
        try:
            raw, oversize = package.read_bounded(name, MAX_METADATA_BYTES)
            if oversize:
                errors.append("%s: refused: over the %d byte limit uncompressed"
                              % (name, MAX_METADATA_BYTES))
                continue
            single, error = parse_metadata(name, raw, base=PACKAGE_BASE)
        except Exception as exc:
            # The reader's contract is (graph, None) or (None, error), and a
            # rule that raises already becomes a finding rather than ending
            # the run. The reader earns the same treatment, because this
            # project declares a dependency floor rather than a pin: it will
            # be paired with readers it was never tested against, and no
            # package may end a run before a single rule has looked at it.
            # Observed on iirds 0.2.0, which raised UnicodeDecodeError out of
            # parse_metadata for metadata truncated mid code unit -- a
            # container under a kilobyte, and a traceback instead of a report.
            # The read is inside this, not only the parse: it was an argument
            # to the guarded call until a later change gave it a statement of
            # its own, and a wrong CRC or an unimplemented compression method
            # walked straight back out. Whatever fails between opening the
            # entry and having a graph is a finding.
            errors.append("%s: %s: %s" % (name, type(exc).__name__, exc))
            continue
        if error is not None:
            errors.append(error)
            continue
        per_source[name] = single
        sources.append(name)

    return merge_sources(per_source), errors, sources, per_source


def load_context(package: Package, version: Optional[str] = None) -> Context:
    graph, errors, sources, per_source = build_graph(package)
    declared, variant = _detect(graph)

    # plusmeta's tool filters its rules by the declared version string, so a
    # package that omits iirds:iiRDSVersion runs zero schema rules and reports
    # "no violations". Here a missing or unknown version falls back to the
    # newest one and is recorded as a note, so nothing passes by silence.
    effective = version or declared or LATEST_VERSION
    if effective not in VERSIONS:
        effective = LATEST_VERSION

    return Context(
        package=package,
        graph=graph,
        ontology=ontology_mod.load(effective if effective in VERSIONS else LATEST_VERSION),
        version=effective,
        variant=variant,
        declared_version=declared,
        requested_version=version,
        parse_errors=errors,
        sources=sources,
        per_source=per_source,
    )
