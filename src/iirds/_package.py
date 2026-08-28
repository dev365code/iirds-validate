"""Reading an iiRDS container."""
from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote

from rdflib import Graph, Namespace
from rdflib.namespace import RDF, RDFS

from . import _metadata as _meta

#: Where the metadata lives. metadata.rdf is the file iiRDS requires;
#: metadata.jsonld is the second serialisation it additionally allows.
METADATA_RDF = "META-INF/metadata.rdf"
METADATA_JSONLD = "META-INF/metadata.jsonld"

#: The base IRI this ecosystem's tools agree on for rdf:about="" — the same
#: convention the checker and its published SHACL shapes document.
PACKAGE_BASE = "urn:iirds:package:"

IIRDS = Namespace("http://iirds.tekom.de/iirds#")


def subclasses_of(graph: Graph, cls) -> frozenset:
    """`cls` plus every class the *package itself* declares beneath it.

    Section 7 lets a package subclass the standard's classes and requires
    consumers to treat instances as the parent. This closure walks only
    the data graph: the SDK bundles no ontology (that file is third-party
    material with its own licence apparatus), so its answer is always a
    subset of a fuller validator's — never a contradiction. Note the
    standard's 1.3 core declares no subclasses of any concrete class, so
    for Topic, Document, Rendition and friends this subset is in fact
    the whole answer.
    """
    return frozenset({cls} | set(graph.transitive_subjects(RDFS.subClassOf, cls)))


def instances_of(graph: Graph, cls) -> List:
    """Subjects typed `cls` or any package-declared subclass of it.

    First-seen graph order, deduplicated, deliberately unsorted: sorting
    twenty thousand topics nobody asked to sort is a cost, and callers
    that need stability can sort what they asked for.
    """
    out, seen = [], set()
    for c in subclasses_of(graph, cls):
        for s in graph.subjects(RDF.type, c):
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def source_of(graph: Graph, node) -> Optional[str]:
    """The container entry a node's iirds:source names, or None.

    The value is read as a URL, which is what §6.3 calls it twice in one
    normative sentence -- "MUST relate the rendition to the URL of the
    physical file. The URL MUST be relative to the root folder". So a name
    carrying a space arrives percent-encoded, and what follows an
    unencoded `#` or `?` is not part of it.

    The standard is not of one mind about this: Appendix A, also
    normative, calls the same value a "relative path of a file" with range
    rdfs:Literal, and a plain literal has no encoding layer. §5.1.3 lets a
    file name contain `%` and `#`, so a package naming a file `a%20b.xhtml`
    or `a#b.xhtml` is entitled to, and this reading cannot reach it. That
    cost is real and chosen; docs/divergences.md carries
    the evidence on both sides. What it buys is that a file named `a b.xhtml`
    is reachable, and that a `%2e%2e` escape is refused as the escape it
    is rather than passed on as an ordinary name.

    §5.1.3 also settles the cheap half: a colon and a backslash may not
    appear in a file name at all, so refusing a value that still holds a
    colon after decoding costs a conformant package nothing, and folding
    backslashes likewise.

    None means "no entry in this container": no source, an empty one, or
    one that names something outside it. A value that climbs out after
    normalising raises instead. That last difference is the layer, not the
    reading -- a reader refuses to resolve what escapes, while
    the checker answers None and reports it as a finding. The
    resolution itself is that project's, case for case.

    Deliberately *not* judged here: whether the entry exists. This
    function answers "what does the rendition name"; open() enforces
    existence, and the validator reports it.
    """
    for value in graph.objects(node, IIRDS["source"]):
        text = str(value)
        # Fragment and query cut by hand rather than through a URL parser:
        # a parser reads `//content/a` as an authority named `content` and
        # keeps only `a` -- a different file, silently. That leaves `//`
        # read as a path where the rest is read as a URL; the divergence is
        # deliberate and recorded.
        path = unquote(text.split("#", 1)[0].split("?", 1)[0])
        # Decode before folding: `%5c` is a backslash, and posixpath.normpath
        # leaves `..\..\` intact, so the oldest zip-slip spelling walks
        # straight out of anything that folds too early or not at all.
        path = path.replace("\\", "/")
        if ":" in path:
            return None                       # not a name a file may carry
        # lstrip takes a character set rather than a prefix, so a leading
        # dot would be eaten: ".config/a.xhtml" must not lose it.
        name = posixpath.normpath(path.lstrip("/"))
        if not path or name == ".":
            return None                       # an empty source names nothing
        if name == ".." or name.startswith("../"):
            raise IirdsError("iirds:source %r escapes the package" % text)
        return name
    return None


def label_of(graph: Graph, node) -> str:
    """rdfs:label, else iirds:title, else the node itself — the same
    order the validator prints, because two different names for one
    thing is how a reader stops trusting either."""
    for prop in (RDFS.label, IIRDS["title"]):
        for value in graph.objects(node, prop):
            return str(value)
    return str(node)


class IirdsError(Exception):
    """The file is not something this library can read as an iiRDS package."""


class Package:
    """An opened iiRDS container. Use as a context manager, like ZipFile.

    Reading is lazy: the ZIP directory is read on open, the metadata graph
    only when `.graph` is first touched.
    """

    def __init__(self, path):
        self.path = Path(path)
        try:
            self._zip = zipfile.ZipFile(self.path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise IirdsError("cannot open %s as a ZIP container: %s" % (self.path, exc)) from exc
        if METADATA_RDF not in self._zip.namelist():
            self._zip.close()
            raise IirdsError("%s has no %s, so it is not an iiRDS package"
                             % (self.path, METADATA_RDF))
        self._graph: Optional[Graph] = None
        self._graphs: dict = {}
        self._errors: List[str] = []
        self._loaded = False

    # -- files ---------------------------------------------------------------
    def names(self) -> List[str]:
        """Every entry in the container, in archive order."""
        return self._zip.namelist()

    def read(self, name: str) -> bytes:
        return self._zip.read(name)

    #: How much is pulled out of the decompressor at a time.
    _CHUNK = 1 << 20

    def _read_bounded(self, name: str, limit: int) -> bytes:
        """At most `limit + 1` bytes of `name`, read in chunks.

        One byte past the limit is enough to know there were more, and it
        costs that byte rather than the document. The caller reports what
        this raises: a member whose declared size is larger than its bytes
        makes the stream raise at the end of the data, and that is a broken
        archive, not an oversized document.
        """
        out = bytearray()
        with self._zip.open(name) as handle:
            while len(out) <= limit:
                chunk = handle.read(min(self._CHUNK, limit + 1 - len(out)))
                if not chunk:
                    break
                out += chunk
        return bytes(out)

    # -- metadata ------------------------------------------------------------
    def _load(self) -> None:
        """Parse the container's metadata, guarded, once.

        The size gate is on what is read, not on what is claimed. The
        uncompressed size in a ZIP's central directory is written by
        whoever built the archive, so a gate reading it is a gate the
        sender sets -- in either direction. One claiming a gigabyte over
        four hundred bytes made a conformant package unreadable here while
        the checker, which measures, read it and reported nothing. The
        read is bounded instead: one byte past the limit is enough to know
        there were more, and costs that byte rather than the document.
        """
        if self._loaded:
            return
        self._loaded = True
        for name in (METADATA_RDF, METADATA_JSONLD):
            if name not in self._zip.namelist():
                continue
            # The read is inside the contract too. `parse_errors` promises it
            # never raises, and decompressing the member happens before the
            # guarded parse ever sees it -- a byte flipped in transit, an
            # unsupported compression method, a bad CRC -- so the promise was
            # broken one layer below where it was repaired.
            try:
                raw = self._read_bounded(name, _meta.MAX_METADATA_BYTES)
            except Exception as exc:
                self._errors.append("%s: %s: %s" % (name, type(exc).__name__, exc))
                continue
            if len(raw) > _meta.MAX_METADATA_BYTES:
                self._errors.append(_meta._oversize(name, len(raw)))
                continue
            # Measured, then compared with the claim. A directory that says
            # more than the member holds makes the stream run on into whatever
            # follows it, so the bytes read are not the document; a directory
            # that says less means somebody else will read a longer one. Both
            # are the archive being wrong, and neither is a size to announce.
            declared = self._zip.getinfo(name).file_size
            if declared != len(raw):
                self._errors.append(
                    "%s: the archive says %d bytes and %d were read; its directory "
                    "does not describe its contents" % (name, declared, len(raw)))
                continue
            graph, error = _meta.parse_metadata(name, raw, base=PACKAGE_BASE)
            if error is not None:
                self._errors.append(error)
            else:
                self._graphs[name] = graph

    @property
    def graph(self) -> Graph:
        """The container's metadata as an rdflib Graph, parsed against the
        `urn:iirds:package:` base so rdf:about="" resolves the way the
        ecosystem's validators and shapes expect.

        Metadata that was refused (hostile) or unparsable raises IirdsError
        when no source could be read at all: a caller who asked for *the*
        graph of an unreadable package must not receive "empty" as the
        answer, because empty is also what a real, sparse package looks
        like."""
        if self._graph is None:
            self._load()
            if not self._graphs:
                raise IirdsError("; ".join(self._errors))
            self._graph = _meta.merge_sources(self._graphs)
        return self._graph

    @property
    def metadata_sources(self) -> List[str]:
        """The metadata documents that parsed, in the fixed
        (metadata.rdf, metadata.jsonld) order the merge also uses."""
        self._load()
        return [n for n in (METADATA_RDF, METADATA_JSONLD) if n in self._graphs]

    @property
    def metadata_graphs(self) -> dict:
        """Each parsed source as its own Graph, keyed by container path --
        for callers that need to know which document said what (the
        validator's cross-serialisation comparison is one)."""
        self._load()
        return dict(self._graphs)

    @property
    def parse_errors(self) -> List[str]:
        """Refusals and parse failures, one string per document, each
        leading with the file name. Reading this never raises; touching
        `graph` does when nothing parsed at all."""
        self._load()
        return list(self._errors)

    # -- queries -------------------------------------------------------------
    def instances_of(self, cls) -> List:
        return instances_of(self.graph, cls)

    def is_instance(self, node, cls) -> bool:
        return bool(set(self.graph.objects(node, RDF.type))
                    & subclasses_of(self.graph, cls))

    def label_of(self, node) -> str:
        return label_of(self.graph, node)

    def source_of(self, node) -> Optional[str]:
        return source_of(self.graph, node)

    def open(self, node):
        """A readable binary stream over the file `node`'s iirds:source
        names -- streaming, so a two-gigabyte PDF is read, not loaded.
        Raises when the node names nothing or names an absent entry.

        The stream borrows this Package's ZIP handle: consume it while the
        Package is open, not after close()."""
        name = self.source_of(node)
        if name is None:
            # Three silences answer None, and sending a reader to look for
            # a missing declaration when the declaration is there costs
            # them the search. Each one says what it actually met.
            declared = next(self.graph.objects(node, IIRDS["source"]), None)
            if declared is None:
                raise IirdsError("%s declares no iirds:source to open" % node)
            if not str(declared).strip():
                raise IirdsError("%s declares an empty iirds:source" % node)
            raise IirdsError("%s names %r, which is not an entry in this "
                             "container" % (node, str(declared)))
        if name not in self._zip.namelist():
            raise IirdsError("%s names %s, and the package has no such entry"
                             % (node, name))
        return self._zip.open(name)

    @property
    def version(self) -> Optional[str]:
        """The iiRDSVersion declared on the Package node (or a section-7
        subclass of it), stripped; None when no Package declares one. A
        version literal on some other subject is noise, not the
        declaration. Where two Package nodes disagree, the first in graph
        order wins — arbitrary, identical to the validator's reading, and
        the validator's M3 finding besides. No judgement about whether
        the value is a published version — that is validation."""
        for node in self.instances_of(IIRDS["Package"]):
            for value in self.graph.objects(node, IIRDS["iiRDSVersion"]):
                return str(value).strip()
        return None

    @property
    def variant(self) -> str:
        """"A", "H", or "unrestricted" — iirds:formatRestriction read off
        the Package node, absent or blank meaning unrestricted."""
        for node in self.instances_of(IIRDS["Package"]):
            for value in self.graph.objects(node, IIRDS["formatRestriction"]):
                text = str(value).strip()
                if text:
                    return text
        return "unrestricted"

    # -- lifecycle -----------------------------------------------------------
    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> Package:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        return "Package(%r)" % str(self.path)


def open_package(path) -> Package:
    """Open an .iirds container for reading."""
    return Package(path)
