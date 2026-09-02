"""Container rules (C*) — the ZIP itself, before any RDF is looked at.

These are the cheap ones that catch the embarrassing mistakes: wrong extension,
missing mimetype, content dumped in the root. None of them need a graph, and
none of them are expressible in SHACL, which is why they live in Python.
"""
from __future__ import annotations

import posixpath
import re
import zipfile
from collections import Counter

from ..model import (
    META_DIR,
    METADATA_JSONLD,
    METADATA_RDF,
    MIMETYPE_FILE,
    MIMETYPE_VALUE,
    Violation,
)
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
    if not ctx.package.is_archive:
        return
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
    if not ctx.package.is_archive:
        return
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
       fix="Make the file contain exactly application/iirds+zip, ASCII, with no trailing newline and no byte order mark. Editors add both silently, so write it with a tool that does not.")
def c5_mimetype_content(ctx):
    if not ctx.package.has(MIMETYPE_FILE):
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
    if not ctx.package.is_archive:
        return
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
    if not any(n.startswith(META_DIR + "/") for n in ctx.package.names):
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
       covers=("x5-1-1-metadata-location-and-rdf-serializations#2",),
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
    # Decided where the graph is built, so that the graph rules and this rule
    # cannot disagree about whether the file was metadata: the context reads
    # the document element once and admits or withholds the graph on it.
    if ctx.not_rdfxml is not None:
        yield Violation("metadata.rdf is not an RDF/XML document",
                        subject=METADATA_RDF,
                        detail="document element is %s; RDF/XML starts with rdf:RDF or with "
                               "a single node element" % ctx.not_rdfxml)


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


@rule("C11.2",
       fix="Add index.html in the root of the archive. An iiRDS/H package is meant to be openable by a person with a browser and no iiRDS tooling at all, and that file is the way in.")
def c11_2_handover_content_list(ctx):
    if not ctx.package.has(CONTENT_LIST):
        yield Violation("an iiRDS/H package must contain a content list named index.html "
                        "in the root directory")
        return
    body = ctx.package.text(CONTENT_LIST)
    if "<html" not in body.lower():
        yield Violation("the content list index.html must be an HTML document",
                        subject=CONTENT_LIST)


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
       covers=("x5-1-1-metadata-location-and-rdf-serializations#2",),
       fix="Read the error reported alongside this: a syntax error means the markup is malformed and has to be corrected, while an encoding error means the bytes were damaged or cut short in transit and the file has to be sent again. Until it parses, no statement in it reaches a consumer.")
def c16_1_rdf_parses(ctx):
    for err in ctx.parse_errors:
        if err.startswith(METADATA_RDF):
            # "could not be read", not "invalid syntax": the reader refuses on
            # size and on entity declarations, and fails on an encoding the
            # bytes do not honour, none of which is a syntax error. The
            # detail carries which one it was. Deliberately not branching on
            # the error string to say more -- the seam contract is that it
            # leads with the file name and partitions on the first ": ", and
            # reading further into the SDK's wording would be a dependency
            # nothing pins.
            yield Violation("metadata.rdf could not be read as RDF 1.1 XML",
                            subject=METADATA_RDF, detail=err.split(": ", 1)[-1])


# The catalogue gates C16.2 to iiRDS/H because that is the profile where
# metadata.jsonld is *mandatory*. But the file is *permitted* in any 1.3
# package, and gating the whole rule meant a corrupt metadata.jsonld in an
# ordinary package was parsed, failed, and silently discarded. The rule runs
# everywhere; the mandatory-file branch checks the variant itself.
@rule("C16.2",
       covers=("x5-1-1-metadata-location-and-rdf-serializations#3",), variants=(),
       fix="Name the JSON-LD file META-INF/metadata.jsonld exactly. A consumer that supports JSON-LD looks for that path only, and one that does not will use metadata.rdf, which must still be present.")
def c16_2_jsonld(ctx):
    if ctx.variant == "H" and not ctx.package.has(METADATA_JSONLD):
        yield Violation("iiRDS/H packages must contain META-INF/metadata.jsonld")
    for err in ctx.parse_errors:
        if err.startswith(METADATA_JSONLD):
            # Same correction as C16.1 twenty lines up, for the same reason:
            # the reader refuses on size, on a context that names something to
            # fetch, and on an @import, none of which is a syntax error. A
            # refused document is perfectly valid JSON-LD 1.1. The detail says
            # which refusal it was; the message must stop contradicting it.
            yield Violation("metadata.jsonld could not be read as JSON-LD 1.1",
                            subject=METADATA_JSONLD, detail=err.split(": ", 1)[-1])
