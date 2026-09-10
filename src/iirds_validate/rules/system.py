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
    for name in ctx.package.names:
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


def _disagreements(info, header, descriptor):
    """Every field on which the local header describes a different entry
    from the central directory's, in the order a reader meets them."""
    if header.name != _name_bytes(info):
        local_name = header.name.decode("utf-8" if header.flag_bits & 0x800 else "cp437",
                                        errors="replace")
        yield "file name: directory %s, local header %s" % (info.orig_filename, local_name)
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
    stream received seven hundred. Compared per entry: the name, the
    method, the flags that change what a reader does, and the crc and
    sizes -- from the local header, or from the data descriptor where the
    local header defers to one (bit 3). Extra fields and timestamps differ
    between writers and between the two records legitimately and are not
    compared. Then the entries' extents: data that runs into the next
    entry's header is handed out by a trusting reader as this entry's.
    """
    package = ctx.package
    extents = []
    for info, header, descriptor in package.local_headers():
        if header is None:
            yield Violation("no local file header at the offset the central directory gives",
                            subject=info.filename, detail="offset %d" % info.header_offset)
            continue
        found = list(_disagreements(info, header, descriptor))
        if found:
            yield Violation("local file header disagrees with the central directory",
                            subject=info.filename, detail="; ".join(found))
            continue
        extents.append((info.header_offset, header.data_start + info.compress_size, info.filename))
    extents.sort()
    for (start, end, name), (following, _end, other) in zip(extents, extents[1:]):
        if following == start:
            yield Violation("the central directory gives two entries the same local file header",
                            subject=other, detail="offset %d, also the header of %s"
                                                  % (start, name))
        elif end > following:
            yield Violation("entry data, as the central directory describes it, runs into the "
                            "next entry", subject=name,
                            detail="data ends at %d, the next local header starts at %d"
                                   % (end, following))
    if extents and extents[-1][1] > package.directory_offset:
        yield Violation("entry data, as the central directory describes it, runs into the "
                        "central directory", subject=extents[-1][2],
                        detail="data ends at %d, the central directory starts at %d"
                               % (extents[-1][1], package.directory_offset))


@rule("S9", kind="system", prio="MUST", versions=(), variants=(),
      title="the run stopped decompressing content at its stated ceiling",
      spec="", covers=(), diagnosis="cause",
      fix="Nothing in the package is necessarily wrong: the run declined to "
          "decompress more than its ceiling, and the renditions past that point "
          "were not examined. Check the package on the command line with a "
          "larger IIRDS_CONTENT_BUDGET, or split a delivery this large into "
          "nested packages, which is what nesting is for.")
def s9_content_budget(ctx):
    """Per-entry limits bound each rendition and nothing bounded their sum,
    so an archive that compresses to nothing could make a run decompress as
    much as it declared: measured, forty one-megabyte renditions in a package
    of no size at all made the run read a hundred and sixty. The ceiling is a
    number the report states, and the renditions past it are named as not
    examined rather than silently passed."""
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
    # The live total rather than the figure recorded when the ceiling was
    # passed. They are the same number when the scan stops there, and that is
    # the point: a version that recorded the overrun and went on reading
    # reports a larger one, and the test that reads this finding is what says
    # the ceiling stops the loop rather than annotating it. Written the other
    # way first, and a mutation that kept reading passed every test here.
    read = ctx.__dict__.get("side_bytes_read", _at_the_cut)
    yield Violation("the search for the package's own ontology stopped at its ceiling, "
                    "so the rest of META-INF was not examined",
                    subject=stopped_at,
                    detail="%d bytes read of a %d byte ceiling" % (read, limit))


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
