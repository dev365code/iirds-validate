"""Container rules (C*) — the ZIP itself, before any RDF is looked at.

These are the cheap ones that catch the embarrassing mistakes: wrong extension,
missing mimetype, content dumped in the root. None of them need a graph, and
none of them are expressible in SHACL, which is why they live in Python.
"""
from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ElementTree
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
RDF_ROOT = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"


def _is_content_file(name: str) -> bool:
    return name.lower().endswith(CONTENT_SUFFIXES)


def _root_content_files(package, exempt=()):
    for name in package.files:
        if "/" in name or name in exempt:
            continue
        if _is_content_file(name):
            yield name


@rule("C1")
def c1_readable(ctx):
    broken = ctx.package.testzip()
    if broken:
        yield Violation("ZIP archive is corrupt", subject=broken)


@rule("C2")
def c2_not_empty(ctx):
    if not ctx.package.files:
        yield Violation("ZIP archive contains no files")


@rule("C3")
def c3_extension(ctx):
    if ctx.package.path.suffix.lower() != ".iirds":
        yield Violation("container file name must end in .iirds",
                        subject=ctx.package.path.name,
                        detail="found extension %r" % ctx.package.path.suffix)


@rule("C4")
def c4_mimetype_present(ctx):
    if not ctx.package.has(MIMETYPE_FILE):
        yield Violation("root directory must contain a file named 'mimetype'")


@rule("C5")
def c5_mimetype_content(ctx):
    if not ctx.package.has(MIMETYPE_FILE):
        return
    raw = ctx.package.read(MIMETYPE_FILE)
    if raw != MIMETYPE_VALUE.encode("ascii"):
        yield Violation(
            "mimetype must contain exactly %r with no line ending" % MIMETYPE_VALUE,
            subject=MIMETYPE_FILE, detail=repr(raw[:80]))


@rule("C6")
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


@rule("C7")
def c7_meta_inf(ctx):
    if not any(n.startswith(META_DIR + "/") for n in ctx.package.names):
        yield Violation("container must have a META-INF directory")


@rule("C8")
def c8_metadata_rdf(ctx):
    if not ctx.package.has(METADATA_RDF):
        yield Violation("META-INF must contain metadata.rdf")


@rule("C10")
def c10_forbidden_chars(ctx):
    for name in ctx.package.names:
        for segment in name.split("/"):
            bad = FORBIDDEN.findall(segment)
            if bad:
                yield Violation("file or directory name uses a forbidden character",
                                subject=name,
                                detail="forbidden: %r" % sorted({repr(b) for b in bad}))
                break


@rule("C9")
def c9_metadata_is_rdf(ctx):
    """C8 asks whether metadata.rdf is present; this asks whether it is RDF.

    Checked by namespace rather than by looking for the literal string
    "<rdf:RDF", so a document that binds the RDF namespace to a different
    prefix is not rejected for it.
    """
    if not ctx.package.has(METADATA_RDF) or any(
            e.startswith(METADATA_RDF) for e in ctx.parse_errors):
        return                      # C8 and C16.1 own those cases
    try:
        root = ElementTree.fromstring(ctx.package.read(METADATA_RDF))
    except ElementTree.ParseError:
        return
    if root.tag != RDF_ROOT:
        yield Violation("metadata.rdf must be an RDF document",
                        subject=METADATA_RDF, detail="root element is %s" % root.tag)


@rule("C11.1")
def c11_1_content_in_root(ctx):
    for name in _root_content_files(ctx.package):
        yield Violation("content files must be stored in subdirectories, not in the root",
                        subject=name)


@rule("C11.1H")
def c11_1h_content_in_root_handover(ctx):
    """Same rule for iiRDS/H, minus the one file the profile puts there itself."""
    for name in _root_content_files(ctx.package, exempt=(CONTENT_LIST,)):
        yield Violation("content files must be stored in subdirectories, not in the root",
                        subject=name)


@rule("C11.2")
def c11_2_handover_content_list(ctx):
    if not ctx.package.has(CONTENT_LIST):
        yield Violation("an iiRDS/H package must contain a content list named index.html "
                        "in the root directory")
        return
    body = ctx.package.text(CONTENT_LIST)
    if "<html" not in body.lower():
        yield Violation("the content list index.html must be an HTML document",
                        subject=CONTENT_LIST)


@rule("C12")
def c12_content_in_meta_inf(ctx):
    for name in ctx.package.files:
        head, _tail = posixpath.split(name)
        if head != META_DIR or name in (METADATA_RDF, METADATA_JSONLD):
            continue
        if _is_content_file(name):
            yield Violation("content files must not sit in META-INF", subject=name)


@rule("C13")
def c13_path_length(ctx):
    for name in ctx.package.names:
        if len(name) > MAX_PATH:
            yield Violation("full path exceeds %d characters" % MAX_PATH,
                            subject=name, detail="%d characters" % len(name))


@rule("C14")
def c14_name_length(ctx):
    for name in ctx.package.names:
        base = posixpath.basename(name.rstrip("/"))
        if len(base) > MAX_NAME:
            yield Violation("file name exceeds %d characters" % MAX_NAME,
                            subject=name, detail="%d characters" % len(base))


@rule("C15")
def c15_unique_names(ctx):
    for name, n in Counter(ctx.package.names).items():
        if n > 1:
            yield Violation("duplicate entry inside its parent directory",
                            subject=name, detail="appears %d times" % n)


@rule("C16.1")
def c16_1_rdf_parses(ctx):
    for err in ctx.parse_errors:
        if err.startswith(METADATA_RDF):
            yield Violation("metadata.rdf is not valid RDF 1.1 XML syntax",
                            subject=METADATA_RDF, detail=err.split(": ", 1)[-1])


# The catalogue gates C16.2 to iiRDS/H because that is the profile where
# metadata.jsonld is *mandatory*. But the file is *permitted* in any 1.3
# package, and gating the whole rule meant a corrupt metadata.jsonld in an
# ordinary package was parsed, failed, and silently discarded. The rule runs
# everywhere; the mandatory-file branch checks the variant itself.
@rule("C16.2", variants=())
def c16_2_jsonld(ctx):
    if ctx.variant == "H" and not ctx.package.has(METADATA_JSONLD):
        yield Violation("iiRDS/H packages must contain META-INF/metadata.jsonld")
    for err in ctx.parse_errors:
        if err.startswith(METADATA_JSONLD):
            yield Violation("metadata.jsonld is not valid JSON-LD 1.1",
                            subject=METADATA_JSONLD, detail=err.split(": ", 1)[-1])
