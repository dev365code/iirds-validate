"""The bundled iiRDS ontologies.

Loaded from disk, never from the network. The class hierarchy is read from the
ontology rather than hard-coded, so "is this an InformationUnit subclass?" stays
correct when the standard adds one.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import sys
from pathlib import Path
from typing import Iterable, Set

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS

from .model import IIRDS_NAMESPACES, LATEST_VERSION

DATA = Path(__file__).parent / "data" / "ontologies"
#: iirds-skos.rdf restates core as SKOS concepts; loading both double-defines
#: every term, so it stays out unless explicitly requested.
DEFAULT_FILES = ("iirds-core.rdf", "iirds-machinery.rdf", "iirds-software.rdf", "iirds-handover.rdf")


class Ontology:
    def __init__(self, version: str = LATEST_VERSION, files: Iterable[str] = DEFAULT_FILES):
        self.version = version
        self.dir = DATA / version
        #: True when this version's ontology is not bundled and another was
        #: used instead. The caller reports it; validating a 1.0 package
        #: against the 1.3 class hierarchy without saying so is the same kind
        #: of silence this project exists to remove.
        self.substituted = None
        if not self.dir.is_dir():
            self.substituted = LATEST_VERSION
            self.dir = DATA / LATEST_VERSION
        self.graph = Graph()
        # Per-instance, not @functools.lru_cache on the method: that keys the
        # cache on `self` at class level, so every Ontology ever built — 2262
        # triples each — is retained for the life of the process.
        self._subclasses = {}
        self._subproperties = {}
        self._defined = None
        for name in files:
            path = self.dir / name
            if path.exists():
                self.graph.parse(path.as_posix(), format="xml")

    # -- hierarchy ----------------------------------------------------------
    def subclasses_of(self, cls: URIRef) -> frozenset:
        """`cls` plus every class transitively below it."""
        if cls not in self._subclasses:
            self._subclasses[cls] = frozenset(
                {cls} | set(self.graph.transitive_subjects(RDFS.subClassOf, cls)))
        return self._subclasses[cls]

    def subproperties_of(self, prop: URIRef) -> frozenset:
        if prop not in self._subproperties:
            self._subproperties[prop] = frozenset(
                {prop} | set(self.graph.transitive_subjects(RDFS.subPropertyOf, prop)))
        return self._subproperties[prop]

    def defined_terms(self) -> frozenset:
        if self._defined is None:
            self._defined = frozenset(s for s in self.graph.subjects() if isinstance(s, URIRef))
        return self._defined

    def is_iirds_term(self, iri) -> bool:
        return isinstance(iri, URIRef) and str(iri).startswith(IIRDS_NAMESPACES)

    def is_defined(self, iri) -> bool:
        return iri in self.defined_terms()

    def classes(self) -> Set[URIRef]:
        return {s for s in self.graph.subjects(RDF.type, RDFS.Class) if isinstance(s, URIRef)}

    def properties(self) -> Set[URIRef]:
        return {s for s in self.graph.subjects(RDF.type, RDF.Property) if isinstance(s, URIRef)}


@functools.lru_cache(maxsize=4)
def load(version: str = LATEST_VERSION) -> Ontology:
    return Ontology(version)


def _verify() -> int:
    """Confirm the vendored files are byte-identical to what we shipped."""
    sums = DATA / "sha256sums.txt"
    if not sums.exists():
        print("sha256sums.txt missing", file=sys.stderr)
        return 2
    bad = 0
    for line in sums.read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        path = DATA / LATEST_VERSION / name.strip()
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "<missing>"
        status = "ok" if actual == digest else "FAILED"
        bad += status == "FAILED"
        print(f"{name.strip():24} {status}")
    if bad:
        print(f"\n{bad} vendored ontology file(s) modified — see data/ontologies/README.md", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="bundled iiRDS ontologies")
    ap.add_argument("--verify", action="store_true", help="check vendored files against sha256sums.txt")
    args = ap.parse_args()
    if args.verify:
        sys.exit(_verify())
    onto = load()
    print(f"iiRDS {onto.version}: {len(onto.classes())} classes, {len(onto.properties())} properties, "
          f"{len(onto.graph)} triples")
