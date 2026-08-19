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

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from rdflib import Graph, URIRef
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
    parse_errors: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    #: One graph per metadata file, kept alongside the merged `graph` so a rule
    #: can ask whether the serialisations agree. Merging is right for every
    #: other rule and is exactly what hides a disagreement.
    per_source: dict = field(default_factory=dict)

    # -- graph helpers ------------------------------------------------------
    def instances_of(self, cls: URIRef, include_subclasses: bool = True) -> List:
        """Subjects typed `cls`, or any class beneath it."""
        classes = self.ontology.subclasses_of(cls) if include_subclasses else {cls}
        out, seen = [], set()
        for c in classes:
            for s in self.graph.subjects(RDF.type, c):
                if s not in seen:
                    seen.add(s)
                    out.append(s)
        return out

    def typed_exactly(self, cls: URIRef) -> List:
        """Subjects carrying `cls` itself as an rdf:type (no subclasses)."""
        return list(self.graph.subjects(RDF.type, cls))

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


#: An .iirds package arrives from a supplier, so its metadata is untrusted
#: input. Two cheap guards, applied before the parser sees anything.
MAX_METADATA_BYTES = 64 * 1024 * 1024
_ENTITY_DECL = re.compile(rb"<!ENTITY", re.IGNORECASE)


def build_graph(package: Package):
    """Parse every metadata serialisation in the container into one graph."""
    graph = Graph()
    errors: List[str] = []
    sources: List[str] = []
    per_source = {}

    for name, fmt in ((METADATA_RDF, "xml"), (METADATA_JSONLD, "json-ld")):
        if not package.has(name):
            continue

        info = package.info(name)
        if info is not None and info.file_size > MAX_METADATA_BYTES:
            errors.append("%s: refused: %d bytes uncompressed, above the %d byte limit"
                          % (name, info.file_size, MAX_METADATA_BYTES))
            continue

        raw = package.read(name)

        # Nested internal entities expand geometrically: a few hundred bytes of
        # declarations can occupy the parser indefinitely. iiRDS metadata has no
        # legitimate use for them, so refuse rather than try to bound the damage.
        if fmt == "xml" and _ENTITY_DECL.search(raw):
            errors.append("%s: refused: the document declares XML entities" % name)
            continue

        try:
            single = Graph()
            single.parse(data=raw, format=fmt, publicID=PACKAGE_BASE)
        except Exception as exc:
            errors.append("%s: %s: %s" % (name, type(exc).__name__, exc))
            continue
        per_source[name] = single
        graph += single
        sources.append(name)

    return graph, errors, sources, per_source


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
        parse_errors=errors,
        sources=sources,
        per_source=per_source,
    )
