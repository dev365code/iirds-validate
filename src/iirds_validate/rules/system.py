"""System rules (S*) — the run itself failed, rather than the package.

These three were previously fabricated inside `runner.py`, which meant their
titles were written out twice and `iirds rules` reported system coverage as
0/3 for behaviour that already existed. Registering them puts their metadata
back in the catalogue with every other rule.

Two of them cannot be ordinary rules. S1 fires before there is anything to
validate, and S3 fires when another rule raises. Their bodies are empty and the
runner emits them; the registration exists so the rule is named and described
in one place.
"""
from __future__ import annotations

import posixpath
import unicodedata

from iirds import unreadable_method

from ..model import VARIANTS, VERSIONS, Violation
from ..package import MAX_LINK_HOPS, descriptor_readings
from ..registry import rule

#: Every kind of run, so a container that cannot be read is reported whether
#: the caller asked for conformance, interoperability, or both.
ALWAYS = ()


@rule("S1", versions=ALWAYS, variants=ALWAYS,
       fix="Check the path, and that the file is a readable ZIP. An .iirds container is an ordinary ZIP archive; `unzip -l` on it should list mimetype first.")
def s1_unreadable_container(ctx):
    """Emitted by `runner.run` when nothing could be read from the path.

    Absent, or not permitted, as distinct from C1: something was read and it is
    not a usable ZIP. Different problems for whoever is holding the package —
    one is a mistake in the command, the other arrived that way and the sender
    needs telling.

    There is no Context at that point, so there is nothing here to inspect;
    the function exists to give the finding a catalogued identity.
    """
    return ()


@rule("S2", versions=ALWAYS, variants=ALWAYS, diagnosis="consequence",
       fix="Fix the container problems reported alongside this. No graph rule can run until the metadata is found and read as RDF, so this is a consequence rather than a defect of its own.")
def s2_no_usable_metadata(ctx):
    """Nothing in META-INF was read as metadata, so no graph rule could have run.

    Without this, `iirds lint` on a package with unreadable metadata reports
    no findings and exits 0 — every L rule looked at an empty graph and found
    nothing to complain about. The reasons are the reader's own words: a
    parse failure, a refusal (size, entities, a remote context), or a
    document the RDF/XML grammar does not define.
    """
    if ctx.sources:
        return
    yield Violation("container validation failed: no usable metadata, so no graph rule could "
                    "check anything",
                    subject="META-INF",
                    detail="; ".join(ctx.parse_errors) or "no metadata file present")


@rule("S3", versions=ALWAYS, variants=ALWAYS, diagnosis="consequence",
       fix="Report this at https://github.com/dev365code/iirds-validate/issues, quoting the rule id and the exception named beside it. A rule that raised has checked nothing, and this finding exists so that its silence is not read as a pass; the other rules ran and what they report stands.")
def s3_rule_raised(ctx):
    """Emitted by `runner.run` when a rule raises.

    A rule that crashed is a rule that checked nothing, so it is reported
    rather than swallowed — and `tests/test_silent_pass.py` fails the suite if
    any fixture produces one.
    """
    return ()


@rule("S4", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="iirds:iiRDSVersion must name a published version of the standard",
       fix="Set iirds:iiRDSVersion to a version the standard has published: 1.0, 1.0.1, 1.1, 1.2 or 1.3. A version nobody published cannot be validated against, and rounding it up would silently check the wrong rules.")
def s4_declared_version_exists(ctx):
    """A package that says it is iiRDS 9.9 cannot be validated as anything.

    Nothing in the catalogue constrains the value — M4 only counts how many
    times the property appears — so a package could declare a version that
    does not exist, be quietly checked against the newest one, and pass. The
    fallback is the right behaviour; doing it in silence is not.
    """
    if ctx.declared_version is None or ctx.declared_version in VERSIONS:
        return
    yield Violation("declared iiRDS version is not one this standard has published",
                    subject=ctx.declared_version,
                    detail="published versions: %s" % ", ".join(VERSIONS))


@rule("S5", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="iirds:formatRestriction must name a published profile",
       fix="Set iirds:formatRestriction to a published profile, or remove the property to mean the unrestricted one. A value matching no profile would otherwise switch off both rule sets at once.")
def s5_declared_variant_exists(ctx):
    """An unrecognised profile silently switches off rules in both directions.

    Rules are filtered by variant, so a package declaring a profile that does
    not exist matches neither the unrestricted rules nor the handover ones: it
    skips both sets and reports clean. That is a one-line way to dodge
    validation entirely, and unlike the version case it produced no note at all.
    """
    if ctx.variant in VARIANTS:
        return
    yield Violation("declared iiRDS profile is not one this standard defines",
                    subject=ctx.variant,
                    detail="defined profiles: A, H, or no iirds:formatRestriction at all")


@rule("S6", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="every entry in the container must stay inside it",
       fix="Put a file inside the container in the entry's place, or take the entry out. A name containing .. or beginning with / escapes the extraction directory, so unpacking this archive would write outside it. In an unpacked container a link is read only while it stays inside: one that leads out, one written as an absolute path, one passing through more links than a system will follow, and one pointing at nothing are each not part of the package.")
def s6_entries_stay_inside_the_container(ctx):
    """An archive entry named `../../../etc/passwd` or `/tmp/x`.

    This validator never extracts anything, so it is not the one at risk — the
    consumer that unpacks the package is. Since the packages being checked
    arrive from suppliers, and since a build gate is the last thing that looks
    at them before something else does unpack them, it is worth failing on.

    An unpacked container is where this validator is the one at risk. A
    directory can hold a link, and a link to a file outside it had that file
    listed, read and judged as though it were in the package -- a private key
    linked as `mimetype` had its first bytes quoted in a finding. The unpacked
    form names such links instead of listing them (`package._walk`), and they
    are reported here, by name only: what they lead to is not read, and where
    it is is the checking machine's business, not the report's.

    A chain of links too long to follow is neither of those things, so it is
    reported as itself. Calling it an escape would say the package points
    somewhere it may well not.

    No catalogued rule covers it: the specification constrains name characters
    and path length but says nothing about escaping the root, because it
    assumes good faith.
    """
    # Every name an entry is read as, not only the one zipfile gives on this
    # interpreter: from Python 3.12 that is a Unicode Path field's where one
    # holds, and a name that escapes under the bytes alone was passed there.
    for name in readings(ctx.package):
        if name.startswith("/") or name.startswith("\\") or ":" in name.split("/")[0]:
            yield Violation("container entry is an absolute path",
                            subject=name)
            continue
        if any(part == ".." for part in name.replace("\\", "/").split("/")):
            yield Violation("container entry escapes the package root",
                            subject=name,
                            detail="resolves to %s" % posixpath.normpath(name))
    for name in ctx.package.outward_links:
        yield Violation("container entry is a link that leads out of the package",
                        subject=name,
                        detail="not read: what it leads to is not in the container")
    for name in ctx.package.chained_links:
        yield Violation("container entry is a chain of links too long to follow",
                        subject=name,
                        detail="not read: more than %d links deep" % MAX_LINK_HOPS)
    for name in ctx.package.absolute_links:
        yield Violation("container entry is a link to an absolute path",
                        subject=name,
                        detail="not read: a package names its own files relative to itself")
    for name in ctx.package.dangling_links:
        yield Violation("container entry is a link that leads nowhere",
                        subject=name,
                        detail="not read: the name it points at is not in the container")


#: Section 5.2.2 states two requirements about the archive itself that no
#: catalogued rule covers. They are cheap to check and both are the kind of
#: thing a consumer discovers only when unpacking fails.
ZIP64_ENTRY_LIMIT = 65536
ZIP64_SIZE_LIMIT = 4 * 1024 ** 3


#: The ZIP64 end-of-central-directory locator. Its presence is the archive
#: saying it used the extension, which is the only thing that settles it.
ZIP64_LOCATOR = b"PK\x06\x07"


def _has_zip64_record(path) -> bool:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 128 * 1024))
            return ZIP64_LOCATOR in handle.read()
    except OSError:                                    # pragma: no cover - defensive
        return False


@rule("S7",
       covers=("x5-2-2-content-encoding#2",), kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="the iiRDS ZIP archive must not be encrypted",
       fix="Rewrite the archive without encryption. A consumer holding only the package has no key, which is every consumer.")
def s7_archive_is_not_encrypted(ctx):
    """"The iiRDS ZIP archive MUST NOT be encrypted." (section 5.2.2)

    Bit 0 of the general purpose flag. An encrypted entry cannot be read by a
    consumer that has only the package, which is every consumer.
    """
    for info in ctx.package.infos:
        if info.flag_bits & 0x1:
            yield Violation("archive entry is encrypted", subject=info.filename)


@rule("S8",
       covers=("x5-2-2-content-encoding#1",), kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="large archives must use the ZIP64 extension",
       fix="Rebuild the archive with ZIP64 enabled. Past 65536 entries or 4 GB the ZIP32 offsets wrap and the archive is unreadable beyond the limit, however carefully it was assembled.")
def s8_zip64_where_required(ctx):
    """"The ZIP archive MUST use the ZIP64 extension if the file size is bigger
    than 4 GB or the package has more than 65536 file entries." (section 5.2.2)

    Without it the offsets wrap and the archive is unreadable past the limit —
    the classic way a large handover package arrives corrupt.
    """
    entries = len(ctx.package.infos)
    biggest = max((i.file_size for i in ctx.package.infos), default=0)
    if entries <= ZIP64_ENTRY_LIMIT and biggest <= ZIP64_SIZE_LIMIT:
        return

    # Ask the archive, not the entries. Inferring from per-entry offsets and
    # sizes says nothing about entry *count*: seventy thousand small files need
    # ZIP64 and never exceed 4 GB anywhere, so the earlier check could only
    # ever fire — it failed every large archive, which is precisely the kind
    # this tool exists for.
    if _has_zip64_record(ctx.package.path):
        return
    yield Violation("archive exceeds the ZIP32 limits but does not use ZIP64",
                    detail="%d entries, largest file %d bytes" % (entries, biggest))


#: Compression methods a reader is likely to meet, for the message.
_METHODS = {0: "stored", 8: "deflated", 12: "bzip2", 14: "lzma", 93: "zstd", 99: "aes"}


def _method(code: int) -> str:
    return "%d (%s)" % (code, _METHODS[code]) if code in _METHODS else str(code)


def _name_bytes(info) -> bytes:
    """The directory's name as bytes, under the encoding its own flag declares."""
    return info.orig_filename.encode("utf-8" if info.flag_bits & 0x800 else "cp437",
                                     errors="replace")


#: The Info-ZIP Unicode Path extra field (APPNOTE 4.6.9): a name in UTF-8
#: that a reader takes in place of the one the record spells.
_UNICODE_PATH = 0x7075


def _as_read(name: str) -> str:
    """A name as readers take it: zipfile and libarchive both stop at a NUL."""
    return name.split("\x00", 1)[0]


def _same_name(one: str, other: str) -> bool:
    """Two names a reader takes for one: equal once both are composed alike,
    as a filesystem that normalises names composes them."""
    return unicodedata.normalize("NFC", one) == unicodedata.normalize("NFC", other)


def _unicode_paths(extra: bytes, reads: str, *, central: bool):
    """The names a record's Unicode Path extra fields give, and which of its
    fields make readers disagree.

    APPNOTE 4.6.9 makes the field "the UTF-8 version of the contents of the
    File Name field", so a field is held to the name the record's bytes read
    -- up to a NUL, and composed alike -- whatever its version and CRC-32.
    Readers differ in how they check those: zipfile follows the directory's
    from Python 3.12, version 1 with the CRC-32 of the whole name; libarchive
    follows the local header's, of any version, against the name it holds by
    then, cut at a NUL, converted to the system's form, and renamed by any
    field before it. A field one reader might follow and that names the
    entry otherwise is two names for one entry.

    Broken fields are the ones a reader refuses where another passes them
    by: in the directory, one too short or not UTF-8, which zipfile refuses
    from 3.12; in the local header, one that is not UTF-8 or names nothing,
    and extra data of any kind that runs past its end, which libarchive
    refuses and zipfile never reads.

    `(names, renamed, broken)`: the names the fields give, and the two kinds
    of fault, as sentences.
    """
    names, renamed, broken, at = [], [], [], 0
    while at + 4 <= len(extra):
        tag = int.from_bytes(extra[at:at + 2], "little")
        size = int.from_bytes(extra[at + 2:at + 4], "little")
        body = extra[at + 4:at + 4 + size]
        at += 4 + size
        if len(body) < size:
            if not central:
                broken.append("extra data that runs past its end")
            break
        if tag != _UNICODE_PATH:
            continue
        if len(body) < 5:
            if central:
                broken.append("a Unicode Path extra field too short to hold a name")
            continue
        try:
            said = _as_read(body[5:].decode("utf-8"))
        except UnicodeDecodeError:
            broken.append("a Unicode Path extra field that is not UTF-8")
            continue
        if not said:
            if not central:
                broken.append("a Unicode Path extra field that names nothing")
            continue
        names.append(said)
        if not _same_name(said, reads):
            renamed.append("a Unicode Path extra field naming the entry %s, where its bytes "
                           "read %s" % (said, reads))
    return names, renamed, broken


def _local_reading(header) -> str:
    return _as_read(header.name.decode("utf-8" if header.flag_bits & 0x800 else "cp437",
                                       errors="replace"))


def readings(package):
    """Every name each entry is read as, in directory order.

    For an archive: the name zipfile gives on this interpreter, the one each
    record's bytes spell under its own bit 11, and the ones each record's
    Unicode Path fields give their readers -- zipfile the directory's from
    Python 3.12, libarchive the local header's. Names stop at a NUL, as both
    readers stop. An entry's names are each given once; an entry the
    directory lists twice is two entries here, as it was. An unpacked
    container's names are its paths.
    """
    if not package.infos:
        yield from package.names
        return
    for info, header, _descriptor in package.local_headers():
        names = [info.filename, _as_read(info.orig_filename)]
        names += _unicode_paths(info.extra, _as_read(info.orig_filename), central=True)[0]
        if header is not None:
            names.append(_local_reading(header))
            names += _unicode_paths(header.extra, _local_reading(header), central=False)[0]
        yield from dict.fromkeys(name for name in names if name)


#: What to do about an entry whose Unicode Path field renames it.
UNICODE_PATH_FIX = (
    "Repackage the archive with its names stored as UTF-8 and bit 11 set. A reader that "
    "follows the Unicode Path field sees one name for this entry and a reader that does "
    "not sees another; a writer that stores names in a local code page adds the field to "
    "carry the Unicode name, and with bit 11 the name itself is Unicode and needs no field.")

#: What to do about a Unicode Path field one reader refuses and another passes by.
BROKEN_PATH_FIX = (
    "Rebuild the archive without the field, or with it whole. zipfile refuses a broken "
    "Unicode Path field in the central directory from Python 3.12, and libarchive skips "
    "or refuses an entry whose local header carries one, while other readers pass it by.")


def _name_faults(info, header):
    """What each record's Unicode Path fields do to its name: `(renamed, broken)`."""
    renamed, broken = [], []
    for where, extra, reads, central in (
            ("directory", info.extra, _as_read(info.orig_filename), True),
            ("local header", header.extra, _local_reading(header), False)):
        _names, moved, bad = _unicode_paths(extra, reads, central=central)
        renamed += ["the %s carries %s" % (where, fault) for fault in moved]
        broken += ["the %s carries %s" % (where, fault) for fault in bad]
    return renamed, broken


def _disagreements(info, header, descriptor):
    """Every field on which the local header describes a different entry
    from the central directory's, in the order a reader meets them.

    The name is compared as each record reads it under its own bit 11, and as
    bytes: one set of bytes read under two flags is two names, and one name
    spelled in two encodings is two to a reader that does not read the flags
    as zipfile does. A record's Unicode Path fields are `_name_faults`'s.
    """
    local_name = header.name.decode("utf-8" if header.flag_bits & 0x800 else "cp437",
                                    errors="replace")
    spelled = _name_bytes(info)
    if local_name != info.orig_filename:
        yield "file name: directory %s, local header %s" % (info.orig_filename, local_name)
    elif header.name != spelled:
        # One name to zipfile, which reads each record under its own flag, and
        # two to a reader that takes bytes without the flag in its own
        # encoding: libarchive extracts code page 437's 0x82 as the byte it
        # is, where the directory's UTF-8 says e-acute.
        yield ("file name: directory and local header both read %s, from different bytes"
               % local_name)
    if header.compress_type != info.compress_type:
        yield "compression method: directory %s, local header %s" % (
            _method(info.compress_type), _method(header.compress_type))
    for bit, meaning in ((0x1, "bit 0 (encryption)"), (0x40, "bit 6 (strong encryption)"),
                         (0x8, "bit 3 (data descriptor)")):
        if (header.flag_bits ^ info.flag_bits) & bit:
            yield "general purpose flag %s: directory %s, local header %s" % (
                meaning, "set" if info.flag_bits & bit else "clear",
                "set" if header.flag_bits & bit else "clear")
    expected = (info.CRC, info.compress_size, info.file_size)
    if header.flag_bits & 0x8:
        # 4.4.4: with bit 3 the local fields are zero (or, from one writer,
        # the true sizes) and the descriptor after the data is the record
        if expected not in set(descriptor_readings(descriptor)):
            yield ("no data descriptor carrying the directory's crc-32 and sizes where "
                   "the directory's compressed size puts one")
    else:
        for label, ours, theirs, form in (
                ("crc-32", info.CRC, header.crc, "%08x"),
                ("compressed size", info.compress_size, header.compress_size, "%d"),
                ("uncompressed size", info.file_size, header.file_size, "%d")):
            if ours != theirs:
                yield ("%s: directory " + form + ", local header " + form) % (label, ours, theirs)


@rule("S14", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS, covers=(),
      diagnosis="cause",
      title="every entry must be compressed with a method a bounded read can be made of",
      fix="Rebuild the archive with deflate, or store the entry uncompressed; `iirds pack` "
          "writes deflate. Nothing is wrong with the file itself -- it was not opened, so "
          "nothing here has an opinion about its contents. The specification is silent about "
          "which method an entry uses, with one exception: `mimetype` must be stored, and "
          "where this names `mimetype` C6 reports that beside it and storing is the only "
          "remedy. What cannot be done is read it within a stated limit: "
          "the decompressors for these methods are not given the length the caller asked for, "
          "so the entry comes out whole or not at all, and a container from a stranger is the "
          "wrong place to find out how large whole is. Every consumer that applies the same "
          "guard will pass this entry over as well, so a delivery that relies on it is a "
          "delivery that arrives incomplete.")
def s14_entries_use_a_method_that_can_be_read(ctx):
    """Refused before opening, on the central directory's own record.

    This is this project's own decision and not a reading of the
    specification, which names a method only for `mimetype` (stored) and is
    silent about the rest; `docs/divergences.md` carries the argument. What
    forces it is measurable: every limit here bounds what a read returns, and
    for these methods the return is sliced out of a whole decompressed entry.
    A 189-byte archive declaring 64 MiB cost 71,530,984 bytes in one
    `read(65536)`, and lowering a ceiling does not touch that.

    Reported per entry rather than for the container: the rest of the package
    is judged normally, and naming the entry is what lets a sender fix it.
    """
    package = ctx.package
    for info in package.infos:
        why = unreadable_method(info)
        if why is not None:
            yield Violation("this entry was not read: its compression method cannot be "
                            "read within a stated limit",
                            subject=info.filename,
                            detail="compressed with %s; not decompressed, not parsed, and "
                                   "not checked for damage either -- answering that would "
                                   "mean decompressing it" % why)


@rule("S10", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS, covers=(),
      diagnosis="cause",
      title="every local file header must describe the entry the central directory describes",
      fix="Rebuild the archive with one tool in one pass and do not edit it afterwards; "
          "`iirds pack` writes both records from one source. Every entry is described twice, "
          "in a local file header before its data and in the central directory at the end. "
          "This run judged the entry the directory describes, as Python's zipfile does; a "
          "consumer that reads the local header -- libarchive, Java's stream reader, anything "
          "fed from a pipe, and unzip for the checksum and the method -- receives the entry the "
          "local header describes, and where the two disagree the two do not receive the same "
          "file.")
def s10_local_headers_agree_with_the_directory(ctx):
    """The archive's own index, checked against the archive.

    `zipfile` reads the central directory, so that is the document every
    other rule judges. A reader that takes the archive as a stream reads
    the local file header before each entry's data instead, and where the
    two records disagree the two readers receive different files -- a
    package blessed here on the seven bytes the directory described while a
    stream received seven hundred. Compared per entry: the name, as each
    record's bit 11 reads it and as its bytes spell it, the method, the
    flags that change what a reader does, and the crc and sizes -- from the
    local header, or from the data descriptor where the local header defers
    to one (bit 3). Extra fields and timestamps differ between writers and
    between the two records legitimately and are not compared; a Unicode
    Path field, which a reader takes the name from, is held to its own
    record's name. Then the entries' extents: data that runs into the next
    entry's header is handed out by a trusting reader as this entry's.

    One extent per entry a reader receives, which is one per name. A directory
    that lists a name twice is not this rule's business -- both records can
    describe the local header they point at perfectly, and S15 reports the
    duplication -- but it was reaching this rule as a flood of collisions
    between an entry and its own copy.
    """
    package = ctx.package
    resolved = {}
    for info, header, descriptor in package.local_headers():
        if header is None:
            yield Violation("no local file header at the offset the central directory gives",
                            subject=_as_read(info.orig_filename),
                            detail="offset %d" % info.header_offset)
            continue
        # Filed under the name the directory's bytes read: zipfile's own name
        # is a Unicode Path field's from 3.12, and the report is not to
        # depend on the interpreter any more than the verdict is.
        subject = _as_read(info.orig_filename)
        found = list(_disagreements(info, header, descriptor))
        if found:
            yield Violation("local file header disagrees with the central directory",
                            subject=subject, detail="; ".join(found))
        renamed, broken = _name_faults(info, header)
        if renamed:
            yield Violation("the entry's Unicode Path extra field gives readers different "
                            "names for it", subject=subject, detail="; ".join(renamed),
                            fix=UNICODE_PATH_FIX)
        if broken:
            yield Violation("the entry carries a Unicode Path extra field one reader refuses "
                            "and another passes by", subject=subject, detail="; ".join(broken),
                            fix=BROKEN_PATH_FIX)
        if found:
            continue
        # One extent per entry a reader receives, which is one per *name* and
        # not one per record: the directory may list a name many times, and
        # `zipfile` assigns into its name table as it walks, so the last
        # record carrying a name is the entry every read here resolves to.
        # Appending each record instead put fifty identical extents in the
        # list below, where the pairing compared each with its own copy and
        # reported forty-nine times that the directory "gives two entries the
        # same local file header" -- subject and detail naming one file, which
        # collides with nothing. S15 states that duplication once, as the fact
        # about the directory that it is.
        resolved[info.filename] = (info.header_offset,
                                   header.data_start + info.compress_size,
                                   _as_read(info.orig_filename))
    extents = sorted(resolved.values())
    # Nothing here for two extents at one offset, and there can be nothing: an
    # extent is only reached by a record that agreed with the local header it
    # points at, and that agreement includes the name -- so two records at one
    # offset both carry the one name that header declares, which is one entry
    # after the keying above. The branch that used to stand here said "the
    # central directory gives two entries the same local file header" and named
    # the same file as its subject and in its detail, on every archive that
    # could reach it, because the two entries were always one name. Bending a
    # record's offset without its name reports the name disagreement above
    # instead, three lines earlier. S15 reports the shape itself, once.
    for (_start, end, name), (following, _end, _other) in zip(extents, extents[1:]):
        if end > following:
            yield Violation("entry data, as the central directory describes it, runs into the "
                            "next entry", subject=name,
                            detail="data ends at %d, the next local header starts at %d"
                                   % (end, following))
    if extents and extents[-1][1] > package.directory_offset:
        yield Violation("entry data, as the central directory describes it, runs into the "
                        "central directory", subject=extents[-1][2],
                        detail="data ends at %d, the central directory starts at %d"
                               % (extents[-1][1], package.directory_offset))


@rule("S15", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS, covers=(),
      diagnosis="cause",
      title="the central directory must carry one record per entry name",
      fix="Rebuild the archive from the files you meant to ship; `iirds pack` writes one "
          "record per name. A ZIP's central directory is a list rather than a map, and "
          "nothing in the format stops two of its records from carrying one name -- so "
          "which bytes that name means is decided by whichever record the reader kept, "
          "and readers do not agree. This run kept the last, as Python's zipfile does. "
          "Editing the directory by hand is not the repair: the records a reader stops "
          "resolving to still have their data sitting in the archive, and the next tool "
          "to rewrite the index can find it again.")
def s15_one_record_per_name(ctx):
    """A name the directory carries twice is a name with two meanings.

    C15 reports the same archive and claims something else: that two entries
    may not share a name inside a directory, which is the specification's
    sentence and is about the package's namespace. This is about the archive.
    `zipfile` resolves a name by walking the central directory and assigning
    into its name table as it goes, so the last record carrying a name is the
    entry every read here reaches, and the records before it describe bytes
    nothing here opens. Where those records give different offsets they
    describe different bytes -- two whole entries, each with its own local file
    header and its own data, each consistent, and one name over both. Nothing
    is damaged and nothing disagrees with anything: S10 passes such an archive,
    because every record does describe the entry its own local header
    describes.

    Reported separately from C15 rather than folded into it because the two
    remedies differ. C15's is to rename or drop an entry; this one's is to
    distrust the index, which is a different thing to tell a sender and the
    only one that covers the case where the duplicate records point somewhere
    else.

    It is also what such an archive costs a pass that walks records instead of
    names. C1 opens every entry and reads it to the end to ask whether it comes
    back out again, and a name carried fifty times was read fifty times: from
    11,890 bytes on disk, one whole run decompressed 419,431,868 bytes in
    0.23 s, of which 419,430,400 was that one 8 MiB entry over and over.
    `Package.testzip` walks the name table now and the same run decompresses
    8,390,076, so the fifty records are reported here rather than read.
    """
    records = {}
    for info in ctx.package.infos:
        records.setdefault(info.filename, []).append(info.header_offset)
    for name, offsets in records.items():
        if len(offsets) < 2:
            continue
        # The last, because that is the one `zipfile` leaves in its name table
        # and therefore the one this whole run judged. Saying which record won
        # is the part a sender cannot work out from "duplicate".
        distinct = set(offsets)
        if len(distinct) == 1:
            detail = ("%d records, all at offset %d; a reader resolves the name to the last "
                      "of them, and every record before it describes an entry nothing will open"
                      % (len(offsets), offsets[-1]))
        else:
            detail = ("%d records, at %d different offsets; a reader resolves the name to the "
                      "last of them, at offset %d, so the records describe different bytes -- a "
                      "reader that kept another of them receives a different file under this name"
                      % (len(offsets), len(distinct), offsets[-1]))
        yield Violation("the central directory carries more than one record for this entry name",
                        subject=name, detail=detail)


@rule("S9", kind="system", prio="MUST", versions=(), variants=(),
      title="the run stopped decompressing content at its stated ceiling",
      spec="", covers=(), diagnosis="cause",
      fix="Nothing in the package is necessarily wrong: the run declined to "
          "decompress more than its ceiling, and the renditions past that point "
          "were not examined. Check the package on the command line with a "
          "larger IIRDS_CONTENT_BUDGET. A delivery this large can also be split, "
          "but not by nesting if this is an iiRDS/H handover package: R9 reports "
          "that as a MUST NOT, and a component tree is what the handover profile "
          "uses to say what is inside what.")
def s9_content_budget(ctx):
    """Per-entry limits bound each rendition and nothing bounded their sum,
    so an archive that compresses to nothing could make a run decompress as
    much as it declared: measured, forty one-megabyte renditions in a package
    of no size at all made the run read a hundred and sixty megabytes, the memo in
    `_bytes_of` not yet existing and each rendition being read four times.
    The ceiling is a number the report states, and the renditions past it are
    named as not examined rather than silently passed.

    That last sentence was not true when it was written. The ceiling refused
    each rendition after reading it, so "not examined" named forty files the
    run had decompressed in full: 49,510 bytes on disk drew 41,945,847 bytes
    of decompression against a two megabyte ceiling. What a rendition costs
    is not knowable without reading it, so one read crosses the ceiling;
    every one after it is now refused without a read, and what the content
    rules read is the ceiling plus one per-file limit."""
    hit = ctx.__dict__.get("content_budget")
    if hit is None:
        return
    read_so_far, limit, first = hit
    yield Violation("the run stopped decompressing content at its ceiling; renditions "
                    "from this one on were not examined",
                    subject=first,
                    detail="%d bytes decompressed against a budget of %d" % (read_so_far, limit))


@rule("S11", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS, covers=(),
      diagnosis="cause",
      title="the packages claiming this container must not disagree about what it is",
      fix="Keep one iirds:Package for the container and give the others iirds:is-part-of-package, "
          "or delete the leftover. Which edition and profile a run judges against is read off the "
          "package that claims the container, and where two claim it with different answers the "
          "run has to choose one: every rule the other answer would have brought is then not "
          "applied, and nothing else says so.")
def s11_container_packages_disagree(ctx):
    """`_detect` elects one package and prints its answers as the container's.

    Where several claim the container the election is decided by
    `_declared_rank` -- newest edition, then whether a profile is named. Two
    holes in that, and this reports the shape both come through rather than
    trying to pick better.

    **A and H have no order between them.** The rank asks whether a profile is
    named, not which one, so two packages naming different profiles tie and the
    tie falls back to the order the nodes leave the graph -- the tie-break that
    docstring says the profile term exists to replace. One stray package naming
    A beside a conformant iiRDS/H container moves twenty-four rules, in or out
    depending on how its IRI sorts. No rule can pick correctly here, because
    there is nothing to prefer: the container was described twice and the two
    descriptions are different documents' worth of rules.

    **And an edition can be won by saying nothing.** A package with no
    `iirds:iiRDSVersion` ranks as the newest, deliberately -- nothing should
    pass by declaring less -- so an empty leftover element outranks a package
    declaring 1.0 and takes its profile with it.

    M3 reports that several packages claim the container, which is the
    specification's sentence and this rule claims none of it. What it adds is
    which of them the run believed, and it is `kind="system"` because that is
    the only kind every run includes: M3 is a schema rule, and an
    interoperability run does not ask for those, so `iirds lint` on such a
    container returned no findings at all.
    """
    from ..context import _named_profiles, container_packages, package_nodes

    pool = container_packages(ctx.graph) or package_nodes(ctx.graph)
    if len(pool) < 2:
        return
    named = set()
    for node in pool:
        profiles = _named_profiles(ctx.graph, node)
        if profiles:
            named.add(profiles[0])
    # Only a dropped profile is a loss. A disagreement about the edition
    # cannot be one: the rank takes the newest, so the elected edition is the
    # highest any of them declared and no rule an older declaration would have
    # brought is missing. A profile the election did not choose is different --
    # every rule gated to it stands down, and the report names the winner as
    # though nobody had said otherwise.
    dropped = named - {ctx.variant}
    if not dropped:
        return
    yield Violation("a profile this container declares is not the one this run judged it as",
                    subject="%s %s" % (ctx.version or "no edition", ctx.variant),
                    detail="also declared: %s; this run judged the container as %s %s"
                           % (", ".join(sorted(dropped)), ctx.version or "no edition",
                              ctx.variant))


@rule("S12", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS, covers=(),
      diagnosis="cause",
      title="the run stopped looking for the package's own ontology at its ceiling",
      fix="Keep the package's own ontology under META-INF to the files that are one, and "
          "put signatures, manifests and anything else a consumer does not read as RDF "
          "somewhere else. Section 7 extensions are found by reading every file there and "
          "asking whether it attaches to iiRDS, so what is in that directory decides how "
          "much a run must read before it can say it looked.")
def s12_side_scan_stopped(ctx):
    """A scan that gave up and a scan that finished are the same silence.

    R18 finds a package's own ontology by reading every entry under META-INF
    that the standard does not name, parsing it as RDF, and keeping it only if
    it attaches something to iiRDS -- so the decision that a file is not its
    business is taken after the file has been read and parsed. Without a
    ceiling that is unbounded work bought with an archive's entry count, and
    the report it produces is empty, which is what a reader takes to mean the
    package was examined.

    Reported rather than raised, and `kind="system"` for the same reason S9 is:
    the subject is the run rather than the package, and every kind of run can
    be cut short this way.
    """
    cut = ctx.__dict__.get("side_scan_cut")
    if not cut:
        return
    _at_the_cut, limit, stopped_at = cut
    # What the reader needs is the ceiling and the file the scan stopped on,
    # not a byte count. Since the read is bounded by what is left of the
    # ceiling, the total at the cut is always the ceiling plus one, and
    # printing it read as a measurement of this package when it was a property
    # of the arithmetic. The file named here was not examined at all: it is
    # the one the ceiling ran out on, and R18 -- which decides whether a
    # META-INF file attaches anything to iiRDS -- cannot answer for a file
    # nobody parsed. That is what a ceiling costs, and saying so is the point
    # of this rule.
    yield Violation("the search for the package's own ontology stopped at its ceiling, "
                    "so this file and the rest of META-INF were not examined",
                    subject=stopped_at,
                    detail="the scan reads at most %d bytes and this file crossed it; "
                           "whether it attaches anything to iiRDS is unanswered" % limit)


@rule("S13", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      covers=("dfn-iirds-package#1",), diagnosis="cause",
      title="the container could not be opened at all",
      fix="Rebuild the archive. An iiRDS container is an ordinary ZIP: `unzip -l` on it "
          "should list mimetype first. Nothing else here has run, because there was "
          "nothing to run against.")
def s13_container_would_not_open(ctx):
    """Emitted by `runner.run` when something was read and it is not a container.

    Distinct from S1, which is a path nothing could be read from -- a mistake
    in the command rather than a package that arrived broken -- and from C1,
    which asks whether every entry of an archive that *did* open comes back
    out again.

    Its own body has nothing to inspect, like S1's: by the time a Context
    exists the container has opened. What it exists for is the identity, and
    the identity has to be `system` rather than `container`. The finding used
    to carry C1's, and `iirds lint` does not put the container rules -- so a
    clean lint report never mentioned it and a broken one did, which is not a
    rule going from clean to firing but a rule appearing out of nowhere. A
    difference between two such reports reads a package that stopped being a
    ZIP as a rule that has just been written.

    `system` is in every kind set, so this one is answered whichever question
    was asked: clean when the container opened, firing when it did not.
    """
    return ()


@rule("S16", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS, covers=(),
      diagnosis="consequence",
      title="a file the package lists as content must be one the container hands over and "
            "this run will parse",
      fix="Read the reason beside each name -- where the file is a rendition, B1 prints the same "
          "one against the same file. A damaged stream is rebuilt from the sources; a file the "
          "filesystem will not open is a permission on the unpacked copy; a rendition larger than "
          "this tool will read in one piece has to be split, because that ceiling is not a setting "
          "a run can be given; a document that declares XML entities is read once the declarations "
          "and every reference to them are gone -- a numeric character reference replaces one that "
          "stood for a single character, and otherwise what the entity stood for is written where "
          "the reference was. Deleting the declarations and keeping the references is not that "
          "remedy: it clears this error and leaves a document that still does not parse. Until the "
          "file parses nothing has examined it, so its rules are neither passed nor failed, and a "
          "consumer opening the package meets whatever this run met.")
def s16_content_not_examined(ctx):
    """A file the content rules never got a tree for is not a file that passed.

    Three things bring a name here, and what they have in common is that no
    content rule ever got a parsed document for the file: the container would
    not hand it over, it is larger on its own than `MAX_CONTENT_BYTES`, or it
    declares XML entities and is refused in its prolog. That last one is
    decided by a parser -- `_declares_entities` runs expat over the prolog and
    raises from the declaration handler -- so "not read" is the wrong word for
    it and "not parsed" is the right one.

    A document that is handed to a parser as a document and rejected by it --
    malformed, or declaring an encoding no codec has -- is B1's finding and
    the profile's business rather than this rule's. The difference is whose
    decision left it unparsed: the container's or this project's, against the
    document's own defect.

    The refusal is reported by B1 against the same file with the same reason
    -- for a rendition; `index.html` under iiRDS/H is read by the content
    rules and is not a rendition, so there B1 is silent and this is the only
    finding that names it. Either way B1 is a content rule, and content
    findings demote to warnings outside iiRDS/A: `runner.severity_override`
    gives the reason, that whether a given file is "iiRDS XHTML5 content" is
    this project's reading of the entry condition and an unrestricted package
    may carry what it likes. That this run never put the file to a parser is
    not a reading of anything, so the demotion must not carry it, and until
    this rule existed it did -- an unpacked package whose only fault was a
    rendition the filesystem would not open came back `ok`, exit 0. The
    archive form of the same package failed, and only by accident: C1's damage
    check opens every entry and holds the verdict there, and C1 is one of the
    rules an unpacked container suspends.

    Under iiRDS/A B1 already carries the same file at error, so there this
    repeats it, on purpose: the subject here is the run rather than the
    profile, and the one fact a profile cannot change should not appear and
    disappear with the profile.

    Six things stop a content rule getting a parsed document. One is the
    parser rejecting the document, which is B1's and demotes outside iiRDS/A
    as every content finding does. Of the other five, two have a rule of their
    own at the same severity and so stop short of here: the total a run will
    decompress is S9's subject, and a compression method no bounded read can
    be made of is S14's. Naming those files here as well would print two
    errors for one fault with one remedy between them. S12 is not among them
    at all: its ceiling bounds R18's own scan of `META-INF/`, which is a
    different reader and stops no content rule.

    Two of this rule's three arrived in 0.7.0 and did not before. 0.6.3 shipped
    this rule narrowed to what the container will not hand over, because
    widening it turns a legal package's pass into a failure and that release
    was a patch. Both are this project's own refusal rather than the
    container's:

    * a rendition larger on its own than `MAX_CONTENT_BYTES`, which is a
      number chosen here and not a setting a run can be given; and
    * a document that declares XML entities, which is read whole and then not
      parsed, on what it says rather than on anything the container did.

    Whose decision it was changes nothing a reader has to do, and the report
    said the same either way: B2 through B11 counted among the rules the run
    checked, and a file none of them had seen. `-W` is not the answer to that
    -- it promotes every warning at once, and this project reports warnings
    that are not failures on purpose, eleven of them from B10 across the
    Consortium's own samples.
    """
    for name, reason in sorted(ctx.__dict__.get("content_unexamined", {}).items()):
        yield Violation("this file was not parsed, so the rules that judge content "
                        "answered for the package without it",
                        subject=name, detail=reason)
