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


@rule("C12")
def c12_content_placement(ctx):
    for name in ctx.package.files:
        if name == MIMETYPE_FILE:
            continue
        head, _tail = posixpath.split(name)
        if head == "":
            yield Violation("content files must not sit in the root directory", subject=name)
        elif head == META_DIR and name not in (METADATA_RDF, METADATA_JSONLD):
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
