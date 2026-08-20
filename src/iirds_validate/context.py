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
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

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


#: An .iirds package arrives from a supplier, so its metadata is untrusted
#: input. Two cheap guards, applied before the parser sees anything.
MAX_METADATA_BYTES = 64 * 1024 * 1024
_ENTITY_DECL = re.compile(rb"<!ENTITY", re.IGNORECASE)
_HAS_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


#: rdflib decodes a bytes payload as UTF-8 unconditionally, so a document that
#: declares — and marks with a byte order mark — any other encoding fails to
#: parse at all. XML says the BOM decides, so it is honoured here and the
#: payload handed on as UTF-8.
_BOMS = ((b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
         (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"),
         (b"\xef\xbb\xbf", "utf-8-sig"))


def _decode_by_bom(raw: bytes) -> bytes:
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            text = raw.decode(encoding)
            # The declaration would now contradict the bytes.
            text = re.sub(r'(<\?xml[^>]*?)\s+encoding\s*=\s*(["\'])[^"\']*\2',
                          r"\1", text, count=1)
            return text.encode("utf-8")
    return raw


def _remote_contexts(node, found=None):
    """Every `@context` in the document that names a location to go and fetch.

    JSON-LD lets a context be a URL, and the parser will dereference it. In a
    package that arrived from a supplier that is two separate problems: it
    breaks the promise that validation touches no network, and it lets the
    sender choose a host for a machine inside the plant to connect to.

    Contexts nest, and a context can be an array mixing inline objects with
    URLs, so the whole document is walked rather than just the top level.
    """
    found = [] if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "@context":
                for candidate in (value if isinstance(value, list) else [value]):
                    if isinstance(candidate, str) and _HAS_SCHEME.match(candidate):
                        found.append(candidate)
                    else:
                        _remote_contexts(candidate, found)
            else:
                _remote_contexts(value, found)
    elif isinstance(node, list):
        for item in node:
            _remote_contexts(item, found)
    return found


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

        raw = _decode_by_bom(package.read(name))

        # Nested internal entities expand geometrically: a few hundred bytes of
        # declarations can occupy the parser indefinitely. iiRDS metadata has no
        # legitimate use for them, so refuse rather than try to bound the damage.
        if fmt == "xml" and _ENTITY_DECL.search(raw):
            errors.append("%s: refused: the document declares XML entities" % name)
            continue

        if fmt == "json-ld":
            try:
                document = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                errors.append("%s: %s: %s" % (name, type(exc).__name__, exc))
                continue
            remote = _remote_contexts(document)
            if remote:
                errors.append("%s: refused: @context must be inline, not fetched from %s"
                              % (name, ", ".join(sorted(set(remote))[:3])))
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
        requested_version=version,
        parse_errors=errors,
        sources=sources,
        per_source=per_source,
    )
