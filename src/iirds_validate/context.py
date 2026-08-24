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
        classes = self._class_closure(cls) if include_subclasses else {cls}
        out, seen = [], set()
        for c in classes:
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
        for subject, predicate in sorted(self.graph.subject_predicates(node), key=str):
            if not isinstance(subject, BNode):
                return "%s %s" % (subject, str(predicate).split("#")[-1].split("/")[-1])
        digest = hashlib.sha256()
        for predicate, obj in sorted(self.graph.predicate_objects(node), key=str):
            digest.update(("%s %s\n" % (predicate, obj)).encode("utf-8"))
        return "_:%s" % digest.hexdigest()[:12]

    def label_of(self, node) -> str:
        for p in (RDFS.label, T.title):
            v = self.one(node, p)
            if v is not None:
                return str(v)
        return str(node)


def _detect(graph: Graph):
    """Read iirds:iiRDSVersion / iirds:formatRestriction off the package node."""
    declared, variant = None, None
    for pkg in graph.subjects(RDF.type, T.Package):
        v = graph.value(pkg, T.iiRDSVersion)
        if v is not None and declared is None:
            declared = str(v).strip()
        r = graph.value(pkg, T.formatRestriction)
        if r is not None and variant is None:
            variant = str(r).strip()
    return declared, (variant or "unrestricted")



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

        info = package.info(name)
        if info is not None and info.file_size > MAX_METADATA_BYTES:
            errors.append("%s: refused: %d bytes uncompressed, above the %d byte limit"
                          % (name, info.file_size, MAX_METADATA_BYTES))
            continue

        single, error = parse_metadata(name, package.read(name), base=PACKAGE_BASE)
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
