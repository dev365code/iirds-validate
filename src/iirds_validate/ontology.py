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
from typing import Iterable, Set

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS

from . import resources
from .model import IIRDS_NAMESPACES, LATEST_VERSION

ONTOLOGIES = "ontologies"
#: iirds-skos.rdf restates core as SKOS concepts; loading both double-defines
#: every term, so it stays out unless explicitly requested.
DEFAULT_FILES = ("iirds-core.rdf", "iirds-machinery.rdf", "iirds-software.rdf", "iirds-handover.rdf")


#: Appendix A's per-class prose, which is where "IRI: required" lives.
DESCRIBED = URIRef("http://iirds.tekom.de/iirds#description")


class Ontology:
    def __init__(self, version: str = LATEST_VERSION, files: Iterable[str] = DEFAULT_FILES):
        self.version = version
        self.version_dir = version
        #: True when this version's ontology is not bundled and another was
        #: used instead. The caller reports it; validating a 1.0 package
        #: against the 1.3 class hierarchy without saying so is the same kind
        #: of silence this project exists to remove.
        self.substituted = None
        if not resources.exists(ONTOLOGIES, version):
            self.substituted = LATEST_VERSION
            self.version_dir = LATEST_VERSION
        self.graph = Graph()
        # Per-instance, not @functools.lru_cache on the method: that keys the
        # cache on `self` at class level, so every Ontology ever built — 2262
        # triples each — is retained for the life of the process.
        self._subclasses = {}
        self._subproperties = {}
        self._instances = {}
        self._defined = None
        for name in files:
            if resources.exists(ONTOLOGIES, self.version_dir, name):
                self.graph.parse(data=resources.read_bytes(ONTOLOGIES, self.version_dir, name),
                                 format="xml")

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

    def instances_of(self, cls: URIRef) -> frozenset:
        """Terms the ontology itself types as `cls`, or as a class beneath it.

        The narrow companion to `defined_terms`, for the rules that ask "is
        the thing this property points at the right *kind* of thing".
        `Context.is_instance` reads the package's graph and nothing else, so
        a package pointing `iirds:has-party-role` at `iirds:Author` -- the
        term the standard supplies for exactly that purpose -- has said
        nothing the package's own graph can confirm, and those rules
        exempted every term the ontology mentions instead.

        That whitelist is `frozenset(self.graph.subjects())`: 327 IRIs, every
        class and property and instance in the file. It let
        `iirds:has-content-lifecycle-status-value` point at `iirds:Topic`,
        and `iirds:has-party-role` point at `iirds:Manufacturer`'s
        neighbours, without a finding. This asks the question the rules
        meant: not "does the standard mention this name" but "does the
        standard say this name is one of these".
        """
        if cls not in self._instances:
            self._instances[cls] = frozenset(
                subject for below in self.subclasses_of(cls)
                for subject in self.graph.subjects(RDF.type, below)
                if isinstance(subject, URIRef))
        return self._instances[cls]

    def requires_an_iri(self, cls: URIRef) -> bool:
        """Does the standard say instances of this class must be named?

        Appendix A's row for a class is carried in the ontology as an
        iirds:description, and where it settles the question it says so in one
        of two words. Fifty of the generated rules' classes say "IRI:
        required"; ten say nothing about IRIs at all, and iirds:PlanningTime
        says "IRI: optional" -- which decides how far a rule about that class
        may reach, so it is read from the ontology rather than listed by hand.
        """
        for _s, _p, text in self.graph.triples((cls, DESCRIBED, None)):
            marker = str(text).find("IRI:")
            if marker >= 0:
                return "required" in str(text)[marker:].lower()
        return False

    def is_iirds_term(self, iri) -> bool:
        """A name under one of the standard's namespaces, exactly.

        A prefix test called `iirds#/Package` an iiRDS term and the bare
        vocabulary IRI one too: the first is a namespace one character off,
        which L14 reports as such rather than as unknown names, and the
        second names nothing. Whether the name is one the standard defines
        is `is_defined`; this answers only whose business the name is.
        """
        if not isinstance(iri, URIRef):
            return False
        text = str(iri)
        for namespace in IIRDS_NAMESPACES:
            if text.startswith(namespace):
                local = text[len(namespace):]
                return bool(local) and "/" not in local and "#" not in local
        return False

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
    if not resources.exists(ONTOLOGIES, "sha256sums.txt"):
        print("sha256sums.txt missing", file=sys.stderr)
        return 2
    recorded = {}
    for line in resources.read_text(ONTOLOGIES, "sha256sums.txt").splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            recorded[name.strip()] = digest

    # Both directions. Walking the manifest and hashing what it names cannot
    # see a file the manifest stopped naming, and deleting a line is easier
    # than forging a digest: with the `iirds-core.rdf` line removed this
    # printed four "ok" lines and exited 0 while a class added to tekom's file
    # was live in the class hierarchy.
    shipped = sorted(n for n in resources.listdir(ONTOLOGIES, LATEST_VERSION)
                     if n.endswith(".rdf"))
    unrecorded = [n for n in shipped if n not in recorded]
    if unrecorded:
        print("shipped but not in sha256sums.txt: %s" % ", ".join(unrecorded),
              file=sys.stderr)
        return 1

    bad = 0
    for name, digest in sorted(recorded.items()):
        present = resources.exists(ONTOLOGIES, LATEST_VERSION, name)
        actual = (hashlib.sha256(resources.read_bytes(ONTOLOGIES, LATEST_VERSION,
                                                      name)).hexdigest()
                  if present else "<missing>")
        status = "ok" if actual == digest else "FAILED"
        bad += status == "FAILED"
        print(f"{name:24} {status}")
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
