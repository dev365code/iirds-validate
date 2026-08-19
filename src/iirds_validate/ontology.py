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
        if not self.dir.is_dir():
            self.dir = DATA / LATEST_VERSION
        self.graph = Graph()
        for name in files:
            path = self.dir / name
            if path.exists():
                self.graph.parse(path.as_posix(), format="xml")

    # -- hierarchy ----------------------------------------------------------
    @functools.lru_cache(maxsize=None)
    def subclasses_of(self, cls: URIRef) -> frozenset:
        """`cls` plus every class transitively below it."""
        return frozenset({cls} | set(self.graph.transitive_subjects(RDFS.subClassOf, cls)))

    @functools.lru_cache(maxsize=None)
    def subproperties_of(self, prop: URIRef) -> frozenset:
        return frozenset({prop} | set(self.graph.transitive_subjects(RDFS.subPropertyOf, prop)))

    @functools.lru_cache(maxsize=None)
    def defined_terms(self) -> frozenset:
        return frozenset(s for s in self.graph.subjects() if isinstance(s, URIRef))

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
