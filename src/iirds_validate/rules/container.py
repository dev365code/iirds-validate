"""Container rules (C*) — the ZIP itself, before any RDF is looked at.

These are the cheap ones that catch the embarrassing mistakes: wrong extension,
missing mimetype, content dumped in the root. None of them need a graph, and
none of them are expressible in SHACL, which is why they live in Python.
"""
from __future__ import annotations

import codecs
import io
import json
import posixpath
import re
import zipfile
from collections import Counter

from rdflib import Dataset, Graph, URIRef

from iirds import (
    MAX_METADATA_BYTES,
    NOT_COMPARED,
    NOT_RDFXML,
    parse_metadata,
    unreadable_method,
)

from .. import terms as T
from ..context import container_packages, package_nodes
from ..model import (
    META_DIR,
    METADATA_JSONLD,
    METADATA_RDF,
    MIMETYPE_FILE,
    MIMETYPE_VALUE,
    PACKAGE_BASE,
    Violation,
)
from ..package import entry_named, nested_containers
from ..registry import rule

#: Spec §5: all Unicode is allowed in names except  / , " * : < >  backslash,
#: DEL, the C0/C1 control ranges and the private use area.
FORBIDDEN = re.compile(
    "[/,\u201d\"*:<>\\\\]"      # / , \u201d " * : < > and backslash
    "|[\\x00-\\x1f\\x7f]"       # C0 controls and DEL
    "|[\\x80-\\x9f]"             # C1 controls
    "|[\\ue000-\\uf8ff]"         # private use area
)
MAX_PATH = 260
MAX_NAME = 255

#: What the specification means by "content": the file types a delivery is made
#: of. Taken from plusmeta's set so a package run through both tools produces
#: the same C11.1 / C12 findings — with one deliberate addition. Their pattern
#: matches .html and .htm but not .xhtml, and Appendix B of the specification
#: defines iiRDS XHTML5 as the content format; every content file in tekom's
#: own sample packages is .xhtml. Omitting it would mean the most common kind
#: of content file could sit in the root unnoticed.
CONTENT_SUFFIXES = (".pdf", ".jpg", ".jpeg", ".gif", ".png", ".html", ".htm",
                    ".xhtml", ".css", ".iirds", ".js")
CONTENT_LIST = "index.html"


def _is_content_file(name: str) -> bool:
    return name.lower().endswith(CONTENT_SUFFIXES)


def _root_content_files(package, exempt=()):
    for name in package.files:
        if "/" in name or name in exempt:
            continue
        if _is_content_file(name):
            yield name


@rule("C1",
       covers=("dfn-iirds-package#1",),
       fix="Rebuild the archive. A ZIP whose central directory is damaged cannot be read reliably by anything, so no other check here has run against it.")
def c1_readable(ctx):
    broken = ctx.package.testzip()
    if broken:
        yield Violation("ZIP archive is corrupt", subject=broken)


@rule("C2",
       fix="Add the package contents. An empty archive has no mimetype, no metadata and no content, so nothing about it can be assessed.")
def c2_not_empty(ctx):
    if not ctx.package.files:
        yield Violation("ZIP archive contains no files")


@rule("C3",
       covers=("dfn-iirds-zip-archive#2",),
       fix="Rename the file to end in .iirds. Consumers and file managers pick the handler by extension, and a .zip will be opened as a plain archive.")
def c3_extension(ctx):
    if ctx.package.path.suffix.lower() != ".iirds":
        yield Violation("container file name must end in .iirds",
                        subject=ctx.package.path.name,
                        detail="found extension %r" % ctx.package.path.suffix)


@rule("C4",
       covers=("dfn-iirds-zip-archive#3",),
       fix="Add a file named mimetype in the root of the archive. It is how a consumer recognises the container before unpacking it, and it must be the first entry.")
def c4_mimetype_present(ctx):
    if not ctx.package.has(MIMETYPE_FILE):
        yield Violation("root directory must contain a file named 'mimetype'")


@rule("C5",
       covers=("dfn-iirds-zip-archive#4",),
       fix="Make the file contain exactly application/iirds+zip, ASCII, with no trailing newline and no byte order mark. An editor can add either without showing it, so write the file with a tool that does not.")
def c5_mimetype_content(ctx):
    if not ctx.package.has(MIMETYPE_FILE):
        return
    info = ctx.package.info(MIMETYPE_FILE)
    if info is not None and unreadable_method(info) is not None:
        # Reading it raises, and an unhandled raise costs the whole rule: the
        # run reported "rule C5 raised" and told the reader to open an issue
        # about their own package. Nothing is lost by standing down here --
        # C6 requires this entry to be stored, so any method that stops this
        # read is already a C6 violation, and S14 names the entry besides.
        return
    raw = ctx.package.read(MIMETYPE_FILE)
    if raw != MIMETYPE_VALUE.encode("ascii"):
        yield Violation(
            "mimetype must contain exactly %r with no line ending" % MIMETYPE_VALUE,
            subject=MIMETYPE_FILE, detail=repr(raw[:80]))


@rule("C6",
       covers=("dfn-iirds-zip-archive#5", "dfn-iirds-zip-archive#6"),
       fix="Store the mimetype entry uncompressed. Most tools cannot express this: with the zip command it takes two passes, `zip -X0 out.iirds mimetype` then `zip -Xr out.iirds .` for the rest. `iirds pack` does it correctly.")
def c6_mimetype_stored_first(ctx):
    info = ctx.package.info(MIMETYPE_FILE)
    if info is None:
        return
    first = ctx.package.first_entry
    if first is None or first.filename != MIMETYPE_FILE:
        yield Violation("mimetype must be the first entry in the ZIP",
                        subject=MIMETYPE_FILE,
                        detail=("first entry is %r" % first.filename) if first else None)
    if info.compress_type != zipfile.ZIP_STORED:
        yield Violation("mimetype must be stored uncompressed ('Stored' mode)",
                        subject=MIMETYPE_FILE,
                        detail="compress_type=%s" % info.compress_type)


@rule("C7",
       covers=("x5-1-1-metadata-location-and-rdf-serializations#1",),
       fix="Create a META-INF directory in the root of the archive. It is where a consumer looks for metadata, and nowhere else is searched.")
def c7_meta_inf(ctx):
    # Names the container holds, readable or not: an entry S6 refuses to read
    # is still an entry, and saying the directory is missing because its one
    # file is a link out of the container describes the wrong defect.
    entries = (list(ctx.package.names) + list(ctx.package.outward_links)
               + list(ctx.package.chained_links) + list(ctx.package.dangling_links)
               + list(ctx.package.absolute_links))
    if not any(n.startswith(META_DIR + "/") for n in entries):
        yield Violation("container must have a META-INF directory")


@rule("C8",
       covers=("x5-1-1-metadata-location-and-rdf-serializations#2",),
       fix="Add META-INF/metadata.rdf. It carries everything a consumer knows about the package; without it the content files are a folder of documents with no structure or meaning.")
def c8_metadata_rdf(ctx):
    if not ctx.package.has(METADATA_RDF):
        yield Violation("META-INF must contain metadata.rdf")


@rule("C10",
       fix="Rename the entry without the reported characters. They are unusable or reserved on at least one of the platforms a package has to survive, so the archive would not extract intact everywhere.")
def c10_forbidden_chars(ctx):
    for name in ctx.package.names:
        for segment in name.split("/"):
            bad = FORBIDDEN.findall(segment)
            if bad:
                yield Violation("file or directory name uses a forbidden character",
                                subject=name,
                                detail="forbidden: %r" % sorted({repr(b) for b in bad}))
                break


@rule("C9",
       covers=("x5-1-1-metadata-location-and-rdf-serializations#2", "x6-12-rdf-serialization#1"),
       # The catalogue gives C8 and C9 identical wording, so without an
       # explicit title the two are indistinguishable in `iirds rules`. C8 is
       # presence; this is the file being RDF/XML at all.
       title="metadata.rdf must be an RDF/XML document (rdf:RDF, or a single node element)",
       fix="Start the document the way the RDF/XML grammar allows: an rdf:RDF element "
           "holding the node elements, or -- when there is only one top-level node "
           "element -- that element alone, with every namespace it uses declared on "
           "it. The file is well-formed XML but its document element is neither, so "
           "an RDF parser reads it as arbitrary classes and properties rather than as "
           "iiRDS metadata. If it was exported from another tool, export as RDF/XML "
           "rather than as plain XML.")
def c9_metadata_is_rdf(ctx):
    """C8 asks whether metadata.rdf is present; this asks whether it is RDF/XML.

    Judged by the grammar the obligation cites, not by the shape most files
    have: a document starts with rdf:RDF or with a single node element
    (§7.2.1, §2.6), and a node element is named by an absolute IRI outside
    the reserved names (§7.2.5). This rule used to demand rdf:RDF, and its
    remedy said no parser would read a rootless document -- while rdflib
    read one into exactly the graph its wrapped twin gives. Checked by
    namespace rather than by the literal string "<rdf:RDF", so a document
    that binds the RDF namespace to a different prefix is not rejected for it.
    """
    # Decided by the reader, so that the graph rules and this rule cannot
    # disagree about whether the file was metadata: the SDK judges the
    # document element on the bytes it parses and refuses the graph, and
    # this rule reports the refusal.
    for error in ctx.parse_errors:
        detail = rdfxml_refusal(error)
        if detail is not None:
            yield c9_violation(detail)


def rdfxml_refusal(error: str):
    """The reader's reason, when a parse error is its refusal of metadata.rdf
    as RDF/XML; None for every other error. The category is the SDK's
    exported constant, so this is the seam contract, not its wording."""
    name, _, rest = error.partition(": ")
    category, _, detail = rest.partition(": ")
    if name == METADATA_RDF and category == NOT_RDFXML:
        return detail
    return None


def c9_violation(detail: str) -> Violation:
    return Violation("metadata.rdf is not an RDF/XML document", subject=METADATA_RDF,
                     detail="%s; RDF/XML starts with rdf:RDF or with a single node element"
                            % detail)


def not_compared(error: str):
    """The reader's reason, when a parse error is the merge leaving a document
    out because it did not compare it with the one before; None for every
    other error. Routed on the SDK's exported category, as C9's is."""
    _name, _, rest = error.partition(": ")
    category, _, detail = rest.partition(": ")
    return detail if category == NOT_COMPARED else None


def not_compared_violation(name: str, detail: str) -> Violation:
    """The merge's refusal of a document it did not compare. The metadata is
    read in a fixed order, metadata.rdf first, so the document it names is
    metadata.jsonld and this is C16.2's to report."""
    return Violation("%s was not compared with metadata.rdf, so no rule read it"
                     % name.rsplit("/", 1)[-1], subject=name, detail=detail,
                     fix="Nothing in either file is necessarily wrong. Two serialisations of "
                         "one graph are compared in one pass wherever their blank nodes form "
                         "trees; a blank node that two blank nodes point at, or a cycle of "
                         "them, leaves a search whose cost grows faster than the files do, "
                         "and this reader makes it over at most 8 blank nodes. Give those "
                         "nodes IRIs, or write each anonymous node under one parent, and the "
                         "files are compared whatever their size. Until then this file's "
                         "statements reach no rule here, and a consumer that prefers it reads "
                         "them unchecked.")


@rule("C11.1",
       covers=("x5-1-2-content-location#1",),
       fix="Move the file under a directory rather than leaving it beside mimetype and META-INF. Only those two belong in the root; everything else has to live in a subdirectory.")
def c11_1_content_in_root(ctx):
    for name in _root_content_files(ctx.package):
        yield Violation("content files must be stored in subdirectories, not in the root",
                        subject=name)


@rule("C11.1H",
       fix="Move the file under a directory. In an iiRDS/H handover package only mimetype, META-INF and index.html belong in the root.")
def c11_1h_content_in_root_handover(ctx):
    """Same rule for iiRDS/H, minus the one file the profile puts there itself."""
    for name in _root_content_files(ctx.package, exempt=(CONTENT_LIST,)):
        yield Violation("content files must be stored in subdirectories, not in the root",
                        subject=name)


@rule("C11.2", covers=("x8-3-1-1-mandatory-content-list#1", "x8-3-1-1-mandatory-content-list#2",),
       fix="Add index.html in the root of the archive. An iiRDS/H package is meant to be openable by a person with a browser and no iiRDS tooling at all, and that file is the way in.")
def c11_2_handover_content_list(ctx):
    if not ctx.package.has(CONTENT_LIST):
        yield Violation("an iiRDS/H package must contain a content list named index.html "
                        "in the root directory")
        return
    info = ctx.package.info(CONTENT_LIST)
    if info is not None and unreadable_method(info) is not None:
        # Whether it is an HTML document cannot be asked of a file this run
        # will not open, and answering anyway is the defect this project keeps
        # finding in itself. Said rather than passed over in silence.
        yield Violation("the content list index.html was not read, so whether it is an "
                        "HTML document was not checked",
                        subject=CONTENT_LIST,
                        fix="Rebuild index.html with deflate, or store it uncompressed. The "
                            "file is present; its compression method is one this tool will "
                            "not decompress, which S14 reports beside this and explains. An "
                            "iiRDS/H package is meant to be openable by a person with a "
                            "browser, and a consumer applying the same guard will not open "
                            "this one either.")
        return
    body = ctx.package.text(CONTENT_LIST)
    if "<html" not in body.lower():
        # Its own remedy: the file is there, so "add it" is already done.
        yield Violation("the content list index.html must be an HTML document",
                        subject=CONTENT_LIST,
                        fix="Write index.html as an HTML document, beginning with an <html> "
                            "element. The file is present and a browser will not render it as "
                            "a page, which is the one thing it exists to do.")


@rule("C12",
       covers=("x5-1-2-content-location#2",),
       fix="Move the content file into a subdirectory. The root and META-INF are reserved, so a consumer scanning for content will not look there.")
def c12_content_in_meta_inf(ctx):
    for name in ctx.package.files:
        head, _tail = posixpath.split(name)
        if head != META_DIR or name in (METADATA_RDF, METADATA_JSONLD):
            continue
        if _is_content_file(name):
            yield Violation("content files must not sit in META-INF", subject=name)


@rule("C13",
       covers=("x5-1-3-names-of-files-and-directories#3",),
       fix="Shorten the path to 260 characters or fewer, counting from the container root. Longer ones fail to extract on Windows and on some archive tools, which turns a valid package into a partial one at the receiving end.")
def c13_path_length(ctx):
    for name in ctx.package.names:
        if len(name) > MAX_PATH:
            yield Violation("full path exceeds %d characters" % MAX_PATH,
                            subject=name, detail="%d characters" % len(name))


@rule("C14",
       fix="Shorten the file name to 255 characters or fewer. Longer names are rejected by common filesystems, so the entry would not survive extraction.")
def c14_name_length(ctx):
    for name in ctx.package.names:
        base = posixpath.basename(name.rstrip("/"))
        if len(base) > MAX_NAME:
            yield Violation("file name exceeds %d characters" % MAX_NAME,
                            subject=name, detail="%d characters" % len(base))


@rule("C15",
       covers=("x5-1-3-names-of-files-and-directories#2",),
       fix="Remove the repeated entry. The same path appears more than once in the archive, so which of them a consumer gets depends on which its unzip implementation keeps.")
def c15_unique_names(ctx):
    for name, n in Counter(ctx.package.names).items():
        if n > 1:
            yield Violation("duplicate entry inside its parent directory",
                            subject=name, detail="appears %d times" % n)


@rule("C16.1",
       covers=("x5-1-1-metadata-location-and-rdf-serializations#2", "x6-12-rdf-serialization#1"),
       fix="Read the error reported alongside this. A syntax error means the markup is malformed and has to be corrected. An encoding error is usually not damage: this reader decodes as UTF-8 whatever a document declares, and the message beside it names the declaration when the file carries one. Named as some other encoding, write the file as UTF-8 and make its declaration say UTF-8, or say nothing -- the bytes are intact and sending them again delivers the same file, and bytes already UTF-8 under another name need only the declaration changed; the same answer covers a declaration this reader will not use at all, a multi-byte codec or a name no codec has. Named as UTF-8 and reported as what these bytes are not, the file was saved in another encoding and the declaration left where it was; re-saving it as UTF-8 is the whole repair. Named not at all, UTF-8 is what XML assumes, so look at the file before asking for it again -- it was either written in another encoding or cut short in transit. A refusal reported as `refused:` is not about the markup either: over the size limit asks for smaller metadata, and declared XML entities are removed, this reader expanding none. And a refusal to read the entry at all -- reported here as it was raised -- means nothing has looked at the markup, so there is nothing in it to correct: S14 names an entry compressed with a method no bounded read can be made of, C1 names a damaged one in an archive, and in an unpacked container the usual cause is a mode bit on the file. Until it parses, no statement in it reaches a consumer.")
def c16_1_rdf_parses(ctx):
    for err in ctx.parse_errors:
        if err.startswith(METADATA_RDF) and rdfxml_refusal(err) is None:
            # "could not be read", not "invalid syntax": the reader refuses on
            # size and on entity declarations, and fails on an encoding the
            # bytes do not honour, none of which is a syntax error. The
            # detail carries which one it was. Deliberately not branching on
            # the error string to say more -- the seam contract is that it
            # leads with the file name and partitions on the first ": ", and
            # reading further into the SDK's wording would be a dependency
            # nothing pins. The one refusal C9 reports instead is recognised
            # by the category the SDK exports for it, which is pinned.
            yield Violation("metadata.rdf could not be read as RDF 1.1 XML",
                            subject=METADATA_RDF, detail=err.split(": ", 1)[-1])


#: The editions whose text names JSON-LD at all.
JSONLD_EDITIONS = ("1.3",)

#: Byte order marks a JSON document can open with, longest first: the UTF-32
#: marks begin with the UTF-16 ones.
_BOMS = ((codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
         (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"),
         (codecs.BOM_UTF8, "utf-8-sig"))


def _renditions(ctx):
    """The entries the metadata names as renditions."""
    return {entry_named(str(source))
            for rendition in ctx.graph.objects(None, T.has_rendition)
            for source in ctx.graph.objects(rendition, T.source)} - {None}


def _jsonld_metadata_elsewhere(ctx):
    """Every entry whose bytes are JSON-LD describing an iirds:Package, in a
    fixed order -- but metadata.jsonld, and the entries the metadata names as
    renditions. metadata.rdf is among them only when it did not read as
    RDF/XML.

    A rendition is content by the package's own statement: the content rules
    read it and pay for it, and reading it here as well decompressed every
    rendition twice, which tests/test_rendition_budget.py forbids. Everything
    else is read bounded the way a metadata file is, and like C1's damage
    check it pays nothing into the content budget: that ceiling is the
    content rules', and charging it here would move their findings.
    """
    found = []
    skip = _renditions(ctx) | {METADATA_JSONLD, MIMETYPE_FILE}
    if METADATA_RDF in ctx.per_source:
        skip.add(METADATA_RDF)
    for name in sorted(ctx.package.files):
        if name in skip:
            continue
        try:
            if _describes_a_package_in_jsonld(ctx, name):
                found.append(name)
        except Exception:                     # unreadable is not provided metadata
            continue
    return found


def _describes_a_package_in_jsonld(ctx, name: str) -> bool:
    head, more = ctx.package.read_bounded(name, 64)
    codec = next((codec for mark, codec in _BOMS if head.startswith(mark)), None)
    if codec is None and more and not head.strip():
        # JSON may open with any amount of whitespace.
        head = ctx.package.read_bounded(name, MAX_METADATA_BYTES)[0]
    if codec is None and head.lstrip()[:1] not in (b"{", b"["):
        return False
    raw, oversize = ctx.package.read_bounded(name, MAX_METADATA_BYTES)
    if oversize:
        return False
    # Before anything is parsed, which on a large document is slow: to type a
    # node iirds:Package a document spells "Package" somewhere, unless it
    # joins the name from a vocabulary or a declared prefix and a suffix, or
    # writes it in escapes. Bytes that do none of that are not asked further.
    if codec is None and not any(mark in raw for mark in (b"Package", b"@vocab", b"@prefix",
                                                         b"\\u")):
        return False
    document = json.loads(raw.decode(codec or "utf-8"))
    if not _has_a_meaningful_key(document):
        return False
    # Through the reader every metadata file goes through, which refuses a
    # document that would send it anywhere: whatever `_offline` left behind
    # is refused there rather than fetched.
    text = json.dumps(_offline(document)).encode("utf-8")
    as_named = name if name.endswith((".jsonld", ".json")) else name + ".jsonld"
    graph, _error = parse_metadata(as_named, text, base=PACKAGE_BASE)
    if graph is None:
        return False
    if package_nodes(graph):
        return True
    # The reader keeps the default graph; a named graph is read from the
    # document it has just accepted.
    dataset = Dataset()
    dataset.parse(data=text, format="json-ld", publicID=PACKAGE_BASE)
    statements = Graph()
    for subject, predicate, value, _graph in dataset.quads((None, None, None, None)):
        statements.add((subject, predicate, value))
    return bool(package_nodes(statements))


def _offline(node):
    """The document with every context it would fetch left out: an inline
    context stays, one named by a string -- a URL, or a path to another file
    -- goes, and so does @import. What a document defines in place is what it
    says to a reader that fetches nothing."""
    if isinstance(node, list):
        return [_offline(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key == "@import":
            continue
        if key == "@context":
            if isinstance(value, list):
                value = [item for item in value if not isinstance(item, str)]
            elif isinstance(value, str):
                continue
        out[key] = _offline(value)
    return out


def _has_a_meaningful_key(document) -> bool:
    stack = [document]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if any(key.startswith("@") or ":" in key for key in item):
                return True
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return False


# The catalogue gates C16.2 to iiRDS/H because that is the profile where
# metadata.jsonld is *mandatory*. But the file is *permitted* in any 1.3
# package, and gating the whole rule meant a corrupt metadata.jsonld in an
# ordinary package was parsed, failed, and silently discarded. The rule runs
# everywhere; the mandatory-file branch checks the variant itself.
@rule("C16.2", covers=("x6-12-rdf-serialization#3",
                        "x5-1-1-metadata-location-and-rdf-serializations#3"),
       variants=(),
       fix="Name the JSON-LD file META-INF/metadata.jsonld exactly. A consumer that supports JSON-LD looks for that path only, and one that does not will use metadata.rdf, which must still be present.")
def c16_2_jsonld(ctx):
    """Section 6.12: "iiRDS/H packages MUST contain iiRDS metadata in JSON-LD
    1.1 syntax." Three things, and the third went unasked for a while: the
    file is there, it reads, and it *contains iiRDS metadata*. An iiRDS/H
    package whose metadata.jsonld is a well-formed empty `@graph` satisfied
    the first two and printed PASS.

    The threshold is one statement mentioning a term of an iiRDS vocabulary,
    in any position, and it is deliberately the lowest one that can be
    defended. "Non-empty" is weaker than the sentence: a graph of Dublin Core
    is not iiRDS metadata. Anything stronger -- a typed instance, a Package
    node, the same graph as metadata.rdf -- starts checking a different
    sentence, and the last of those is section 5.1.1's, which is L9's. A file
    carrying some of the metadata carries iiRDS metadata; whether it carries
    *all* of it is the question L9 answers.

    Asked of `ctx.per_source`, not of the merged graph, because the merged
    graph is mostly metadata.rdf and would answer yes for a JSON-LD file that
    says nothing at all -- which is the whole defect.

    Section 5.1.1 says where the file goes, for every profile: "If metadata is
    provided in the JSON-LD 1.1 syntax, the META-INF directory MUST contain the
    file metadata.jsonld." The catalogue's sentence for this rule is that one,
    and the remedy above was written for it, but only the handover half was
    asked: a package outside iiRDS/H could carry its JSON-LD under any other
    name and nothing said so. The same section says why the name is the whole
    point: "It is RECOMMENDED for iiRDS Consumers to ignore any other files in
    the META-INF directory." A consumer following that reads JSON-LD metadata
    at that one path or not at all, so the recommendation is not a reason to
    leave other files alone here -- it is what a misnamed file costs. Other
    files are not forbidden, and a package that has metadata.jsonld is not
    told about a copy elsewhere.

    What counts as metadata provided in JSON-LD is read off the bytes, not the
    name -- a misnamed file is the case the sentence exists for, and so is
    metadata.rdf holding JSON-LD. "Metadata" is the package's: metadata.rdf
    contains "all metadata", and every metadata graph describes its package
    (M3), so a JSON-LD document describing an iirds:Package is that metadata,
    wherever it sits. A label table keyed by iiRDS names, structured data about
    a product, a side file describing an extension, or a file the metadata
    names as a rendition -- content by the package's own statement -- is not.
    The document is read the way a reader that fetches nothing reads it: a
    context named by a URL or a path, and @import, are left out, and what it
    defines in place is what it says; named graphs are read too. A
    metadata.jsonld that describes no package does not hold the metadata
    found elsewhere. Asked of 1.3 only, because 1.2 names one serialisation,
    RDF/XML, and the words JSON-LD and metadata.jsonld do not occur in it. An
    iiRDS/H package without the file is already told to add it, which answers
    both sentences, so it is told once.
    """
    if ctx.variant == "H" and not ctx.package.has(METADATA_JSONLD):
        yield Violation("iiRDS/H packages must contain META-INF/metadata.jsonld")
    elif ctx.variant == "H" and METADATA_JSONLD in ctx.per_source:
        graph = ctx.per_source[METADATA_JSONLD]
        if not any(ctx.ontology.is_iirds_term(term)
                   for triple in graph for term in triple):
            yield Violation("metadata.jsonld carries no iiRDS metadata",
                            subject=METADATA_JSONLD,
                            detail="%d statement(s), none mentioning an iiRDS term" % len(graph),
                            fix="Serialise the package's metadata into "
                                "META-INF/metadata.jsonld as well as META-INF/metadata.rdf. "
                                "An iiRDS/H consumer that prefers JSON-LD reads this file and "
                                "no other, so an empty one hands it a package with no metadata "
                                "at all.")
    elif ctx.version in JSONLD_EDITIONS and not package_nodes(
            ctx.per_source.get(METADATA_JSONLD, Graph())):
        where = ("does not describe the package" if ctx.package.has(METADATA_JSONLD)
                 else "is absent")
        for name in _jsonld_metadata_elsewhere(ctx):
            yield Violation("JSON-LD metadata is not in META-INF/metadata.jsonld",
                            subject=name,
                            detail="this file is JSON-LD describing an iirds:Package, and "
                                   "META-INF/metadata.jsonld %s" % where)
    for err in ctx.parse_errors:
        if err.startswith(METADATA_JSONLD) and not_compared(err) is not None:
            yield not_compared_violation(METADATA_JSONLD, not_compared(err))
        elif err.startswith(METADATA_JSONLD):
            # Same correction as C16.1 twenty lines up, for the same reason:
            # the reader refuses on size, on a context that names something to
            # fetch, and on an @import, none of which is a syntax error. A
            # refused document is perfectly valid JSON-LD 1.1. The detail says
            # which refusal it was; the message must stop contradicting it.
            # Its own remedy: this file is named exactly right and cannot be
            # read, so the rule's remedy about naming answers the other branch.
            yield Violation("metadata.jsonld could not be read as JSON-LD 1.1",
                            subject=METADATA_JSONLD, detail=err.split(": ", 1)[-1],
                            fix="Read the error reported alongside this and repair the file. A "
                                "refusal means the document asked the reader to fetch something "
                                "or was too large, not that its syntax is wrong; a parse error "
                                "means the JSON itself is malformed. Until it reads, the "
                                "statements in it reach no consumer that prefers JSON-LD.")


def _own_metadata(package, name: str):
    """What a nested container's own metadata.rdf says: the IRIs it gives its
    own package, and its graph -- or (None, None) where that cannot be read.

    The container is read whole, bounded as a metadata file is, because a ZIP
    names its entries at its end. Not charged to the content budget, for the
    reason `_jsonld_metadata_elsewhere` gives.
    """
    try:
        raw, oversize = package.read_bounded(name, MAX_METADATA_BYTES)
        if oversize:
            return None, None
        with zipfile.ZipFile(io.BytesIO(raw)) as inner:
            info = inner.getinfo(METADATA_RDF)
            if unreadable_method(info) is not None:
                return None, None
            with inner.open(info) as handle:
                data = handle.read(MAX_METADATA_BYTES + 1)
        if len(data) > MAX_METADATA_BYTES:
            return None, None
        graph, _error = parse_metadata(METADATA_RDF, data, base=PACKAGE_BASE)
    except Exception:                         # unreadable says no package
        return None, None
    if graph is None:
        return None, None
    own = {_iri(pkg) for pkg in container_packages(graph) if isinstance(pkg, URIRef)}
    return (own or None), graph


def _iri(node) -> str:
    """An IRI as compared here. No IRI holds a space, and the standard's own
    Example 16 opens the child's with one; that is not a different package."""
    return str(node).strip()


def _declared_for(graph, name: str, own):
    """The iirds:Package in `graph` that is the nested container `name`'s.

    First one declared as part of another package and carrying the IRI the
    child's own metadata gives its package; then one whose rendition names the
    archive; then any carrying that IRI -- a declaration part of no package,
    or this container's own package where the child was made from the same
    template and says it is this one.
    """
    if graph is None:
        return None
    packages = package_nodes(graph)
    own = own or set()
    containers = set(container_packages(graph))
    for pkg in packages:
        if pkg not in containers and _iri(pkg) in own:
            return pkg
    for pkg in packages:
        for rendition in graph.objects(pkg, T.has_rendition):
            if any(entry_named(str(source)) == name
                   for source in graph.objects(rendition, T.source)):
                return pkg
    for pkg in packages:
        if _iri(pkg) in own:
            return pkg
    return None


def _not_exactly_one(graph, node):
    """None where `node` names exactly one iirds:Package by
    iirds:is-part-of-package in `graph`; otherwise everything it names."""
    if graph is None or node is None:
        return []
    named = sorted(set(graph.objects(node, T.is_part_of_package)), key=str)
    if len(named) == 1 and named[0] in set(package_nodes(graph)):
        return None
    return named


_DECLARE_IT = ("Declare each nested package in its parent's metadata.rdf under the IRI the "
               "nested container's own metadata gives its package, and relate it by "
               "iirds:is-part-of-package to exactly one iirds:Package: the one that metadata "
               "describes as the container. A consumer reaches a nested package's content "
               "through that declaration, and a nested archive it cannot match to one is a "
               "package it does not know is there.")

#: In iiRDS/H the remedy is R9's: declaring the child would satisfy this rule
#: and break R9 twice over.
_R60_REMEDY = {
    "iiRDS/H": "This is an iiRDS/H package, which must not nest at all (R9): take the nested "
               "container out and model the hierarchy with a component tree, rather than "
               "declaring it here.",
    "other": _DECLARE_IT,
}


@rule("R60", kind="container", prio="MUST", versions=("1.3",), variants=(),
      title="a nested container is declared in the parent's metadata, part of exactly one package",
      spec="https://www.iirds.org/fileadmin/iiRDS_specification/"
           "20251103-1.3-release/index.html#metadata-of-nested-iirds-packages",
      covers=("x6-3-3-metadata-of-nested-iirds-packages#1",
              "x6-3-3-metadata-of-nested-iirds-packages#3"),
      fix=_DECLARE_IT)
def r60_nested_containers_are_declared(ctx):
    """Section 6.3.3, twice: "For each nested child iiRDS container, an
    iirds:Package MUST be present in the metadata of the parent iiRDS
    container", and "In the metadata.rdf file of the parent iiRDS container,
    the iirds:Package of the nested child iiRDS container MUST reference
    exactly one iirds:Package by iirds:is-part-of-package."

    Both ask which iirds:Package is a given child's, and the standard shows
    that rather than saying it: Example 16 prints the parent's metadata.rdf
    and the child's, and the nested package carries one IRI in both. So each
    child's own metadata is opened and its package's IRI looked for. Until 1.2
    the parent named the child's archive by iirds:has-rendition instead; 1.3
    recommends omitting that and does not forbid it, so a rendition naming the
    archive also says which package is the child's -- and is asked before an
    IRI the child shares with this container's own package, which is what a
    child made from the parent's template carries.

    Whose metadata is the parent's: the same section puts every nested
    container "side by side in the iiRDS ZIP archive of the highest level
    iiRDS package", so a grandchild sits beside its parent in this archive,
    and a child declared in a sibling's metadata.rdf is that sibling's child.
    Its declaration is held to the second sentence there.

    The second sentence names metadata.rdf, and is asked of it alone: a
    reference stated only in metadata.jsonld is not in that file, and a
    metadata.rdf that is not there or does not read describes no package. It
    counts every reference, because the property's range is iirds:Package:
    whatever a second reference names, the child's package references more
    than one.

    A child whose own package cannot be read off it -- metadata that does not
    parse, a package with no IRI, an archive past the metadata limit -- is
    still owed a package, and which declared one is its cannot be told. It is
    reported when no declared package is left that could be its and keep the
    second sentence: if a spare breaks that sentence, then either it is the
    child's and the second sentence is broken, or it is not and the first is.

    In iiRDS/H the finding carries R9's remedy, which is the one that fits.

    Version-gated to 1.3 for the reason R5, R6 and R8 are.
    """
    children = nested_containers(ctx.package)
    if not children:
        return
    rdf = ctx.per_source.get(METADATA_RDF)
    opened = {name: _own_metadata(ctx.package, name) for name in children}
    found = {name: _declared_for(ctx.graph, name, opened[name][0]) for name in children}
    by_sibling = {}
    for name, (own, graph) in opened.items():
        if graph is None:
            continue
        # What a sibling declares besides itself. Itself is the package this
        # metadata knew it by, or where it knew it by no IRI of its own, every
        # package its metadata leaves part of nothing.
        known = found[name]
        itself = ({_iri(known)} if known is not None and _iri(known) in (own or ())
                  else {_iri(p) for p in container_packages(graph)})
        for pkg in package_nodes(graph):
            if _iri(pkg) not in itself:
                by_sibling.setdefault(_iri(pkg), (name, graph, pkg))
    matched, unread = {}, []
    for name in children:
        own = opened[name][0]
        pkg = found[name]
        if pkg is not None:
            matched.setdefault(pkg, []).append(name)
            continue
        if own is None:
            unread.append(name)
            continue
        sibling = next((by_sibling[iri] for iri in sorted(own)
                        if iri in by_sibling and by_sibling[iri][0] != name), None)
        if sibling is not None:
            where, graph, node = sibling
            named = _not_exactly_one(graph, node)
            if named is not None:
                yield _more_or_less_than_one(ctx, node, named, [name],
                                             "declared in the metadata.rdf of %s" % where)
            continue
        yield Violation("the parent's metadata declares no iirds:Package for this "
                        "nested container",
                        subject=name, fix=_R60_REMEDY["iiRDS/H" if ctx.variant == "H" else "other"],
                        detail="its own metadata.rdf names its package %s, and no "
                               "iirds:Package here is that one or names this archive "
                               "as its rendition" % ", ".join(sorted(own)))
    containers = container_packages(ctx.graph)
    for pkg, names in matched.items():
        named = _not_exactly_one(rdf, _declared_for(rdf, names[0], opened[names[0]][0]))
        if named is None:
            continue
        said = []
        if rdf is None:
            said.append("there is no readable metadata.rdf")
        if containers == [pkg]:
            said.append("it is the package this metadata describes as the container itself")
        yield _more_or_less_than_one(ctx, pkg, named, names, "; ".join(said))
    if unread:
        spare = [p for p in package_nodes(ctx.graph)
                 if p not in matched and p not in containers
                 and _not_exactly_one(rdf, p if rdf is not None and (p, None, None) in rdf
                                      else None) is None]
        for name in unread[len(spare):]:
            yield Violation("the parent's metadata declares no iirds:Package for this "
                            "nested container",
                            subject=name, fix=_R60_REMEDY["iiRDS/H" if ctx.variant == "H" else "other"],
                            detail="its own metadata.rdf does not say which package it is, "
                                   "and no iirds:Package declared here that is part of "
                                   "exactly one package in metadata.rdf is left for it")


def _more_or_less_than_one(ctx, pkg, named, names, why):
    if not named:
        said = "none"
    elif len(named) == 1:
        said = "%s, which that metadata.rdf does not describe as an iirds:Package" % ctx.ref(named[0])
    else:
        said = "%d: %s" % (len(named), ", ".join(ctx.ref(p) for p in named))
    detail = "the package of the nested container %s" % ", ".join(names)
    if why:
        detail += "; " + why
    return Violation("in metadata.rdf a nested package must be part of exactly one "
                     "iirds:Package; this one is part of %s" % said,
                     subject=ctx.ref(pkg), detail=detail,
                     fix=_R60_REMEDY["iiRDS/H" if ctx.variant == "H" else "other"])
