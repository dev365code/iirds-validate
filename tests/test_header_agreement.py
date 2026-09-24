"""S10: every local file header describes the entry the central directory does.

`zipfile` reads the central directory, so that is the document this tool
judges. A consumer that reads the archive as a stream -- libarchive, Java's
stream reader, anything fed from a pipe -- reads the local header before
each entry's data instead, and `unzip` takes the checksum and the method
from it. Where the two records disagree, the two readers receive different
files, and until this rule nothing said so: a package could be blessed on
the seven bytes the directory described while a stream received seven
hundred.

Every fixture here is an ordinary package with one field of one record
changed. The archives real tools write -- stream writers with data
descriptors, ZIP64, differing extra fields, a prefixed archive -- are the
negatives, and stay silent.
"""
from __future__ import annotations

import sys
import zlib

import pytest

import ziplayout as Z
from conftest import build_package
from iirds_validate import runner

BODY = "<html xmlns=\"http://www.w3.org/1999/xhtml\"><body><p>spare</p></body></html>"
OTHER = "content/other.xhtml"
SPARE = "content/spare.xhtml"


def package(tmp_path, name="agree.iirds", **kwargs):
    """A conformant package with two entries nothing declares, so that a
    changed record is seen by this rule and by nothing that reads content."""
    return build_package(tmp_path, name, extra=((OTHER, BODY), (SPARE, BODY)), **kwargs)


def s10(report):
    assert "S3" not in {f.rule.id for f in report.findings}, "a rule raised"
    return [f for f in report.findings if f.rule.id == "S10"]


def patched(tmp_path, change, name="bent.iirds"):
    path = package(tmp_path, name)
    return Z.rewrite(path, change(path.read_bytes()))


# --- the archives real tools write stay silent ------------------------------

def test_a_plain_package_reports_nothing(tmp_path):
    assert s10(runner.check(package(tmp_path))) == []


def test_a_streamed_package_with_data_descriptors_reports_nothing(tmp_path):
    """Stream writers -- Java's, Commons Compress, libarchive, `ditto` --
    cannot seek back to write sizes into the local header, so they set bit
    3 and put crc and sizes in a descriptor after the data (4.3.9)."""
    path = package(tmp_path)
    data = Z.streamed(path)
    assert Z.u16(data, Z.local_header(data, OTHER) + 6) & 0x8
    assert s10(runner.check(Z.rewrite(path, data))) == []


@pytest.mark.parametrize("streamed", [False, True])
def test_a_zip64_package_reports_nothing(tmp_path, streamed):
    """ZIP64 puts 0xFFFFFFFF in the 32-bit size fields and the real sizes in
    an extra field (4.5.3); a stream writer leaves the local extra empty and
    writes an eight-byte descriptor instead."""
    path = package(tmp_path)
    if streamed:
        Z.rewrite(path, Z.streamed(path, force_zip64=True))
    else:
        import zipfile
        with zipfile.ZipFile(path, "a") as zf, \
                zf.open("content/big.xhtml", "w", force_zip64=True) as handle:
            handle.write(BODY.encode("utf-8"))
    assert s10(runner.check(path)) == []


def test_an_eight_byte_descriptor_without_a_local_zip64_extra_reports_nothing(tmp_path):
    """libarchive's `zip:zip64` form: bit 3, no zip64 extra in the local
    header, and a descriptor with eight-byte sizes."""
    path = package(tmp_path)
    data = Z.streamed(path)
    at = Z.descriptor_at(data, OTHER)
    assert data[at:at + 4] == Z.DESCRIPTOR
    crc, csize, usize = Z.u32(data, at + 4), Z.u32(data, at + 8), Z.u32(data, at + 12)
    wide = Z.DESCRIPTOR + Z.le(crc, 4) + Z.le(csize, 8) + Z.le(usize, 8)
    assert s10(runner.check(Z.rewrite(path, Z.splice(data, at, 16, wide)))) == []


def test_a_descriptor_without_its_signature_reports_nothing(tmp_path):
    """The descriptor's signature is optional (4.3.9.3)."""
    path = package(tmp_path)
    data = Z.streamed(path)
    at = Z.descriptor_at(data, OTHER)
    assert s10(runner.check(Z.rewrite(path, Z.splice(data, at, 4, b"")))) == []


def test_differing_extra_fields_are_not_a_disagreement(tmp_path):
    """Writers put different extra fields in the two records -- InfoZip's
    timestamps differ in length, CPython writes the zip64 record centrally
    only -- and none of it is the entry."""
    def change(data):
        local = Z.local_header(data, OTHER)
        assert Z.u16(data, local + 28) == 0
        extra = b"\x55\x58" + Z.le(4, 2) + b"\x01\x02\x03\x04"
        data = Z.splice(data, local + 30 + Z.u16(data, local + 26), 0, extra)
        return Z.bend(data, local + 28, Z.le(len(extra), 2))
    assert s10(runner.check(patched(tmp_path, change))) == []


def test_a_prefixed_archive_is_judged_at_the_adjusted_offsets(tmp_path):
    """A self-extracting stub or a stray header in front: `zipfile` measures
    the shift and corrects every offset it hands out, so the local headers
    are found where they are."""
    path = package(tmp_path)
    assert s10(runner.check(Z.rewrite(path, b"#!/bin/sh\nexit 0\n" + path.read_bytes()))) == []


# --- what a disagreement looks like -----------------------------------------

def test_the_directory_and_the_local_header_may_describe_two_documents(tmp_path):
    """The headline case. The directory says the entry is seven bytes with
    one crc; the local header says seven hundred with another. `zipfile`
    reads the seven and verifies them, C1 is silent, and a stream reader
    receives the seven hundred."""
    short = b"<p>a</p>"
    long = short + (BODY * 8).encode("utf-8")

    def change(data):
        local = Z.local_header(data, OTHER)
        start = Z.data_start(data, local)
        # stored, so that the data is the document: the directory keeps the
        # short reading and verifies -- the stream's document begins with it
        # -- while the local header describes the whole of it
        data = Z.bend(data, local + 8, Z.le(0, 2))
        data = Z.bend(data, Z.central_entry(data, OTHER) + 10, Z.le(0, 2))
        data = Z.splice(data, start, Z.u32(data, Z.central_entry(data, OTHER) + 20), long)
        central = Z.central_entry(data, OTHER)   # moved by the splice
        data = Z.bend(data, central + 16, Z.le(zlib.crc32(short), 4))
        data = Z.bend(data, central + 20, Z.le(len(short), 4) + Z.le(len(short), 4))
        data = Z.bend(data, local + 14, Z.le(zlib.crc32(long), 4))
        return Z.bend(data, local + 18, Z.le(len(long), 4) + Z.le(len(long), 4))

    path = patched(tmp_path, change)
    report = runner.check(path)
    findings = s10(report)
    assert [f.violation.subject for f in findings] == [OTHER]
    detail = findings[0].violation.detail
    assert "uncompressed size: directory %d, local header %d" % (len(short), len(long)) in detail
    assert "crc-32: directory %08x, local header %08x" % (zlib.crc32(short), zlib.crc32(long)) in detail
    assert "C1" not in {f.rule.id for f in report.findings}
    assert not report.ok


def test_a_local_name_that_disagrees_is_reported(tmp_path):
    def change(data):
        local = Z.local_header(data, OTHER)
        return Z.bend(data, local + 30, b"content/OTHER.xhtml")
    report = runner.check(patched(tmp_path, change))
    findings = s10(report)
    assert [f.violation.subject for f in findings] == [OTHER]
    assert "file name: directory content/other.xhtml, local header content/OTHER.xhtml" in findings[0].violation.detail


def test_a_local_compression_method_that_disagrees_is_reported(tmp_path):
    def change(data):
        return Z.bend(data, Z.local_header(data, OTHER) + 8, Z.le(0, 2))
    findings = s10(runner.check(patched(tmp_path, change)))
    assert [f.violation.subject for f in findings] == [OTHER]
    assert "compression method: directory 8 (deflated), local header 0 (stored)" in findings[0].violation.detail


def test_an_encryption_bit_set_only_in_the_local_header_is_reported(tmp_path):
    """S7 reads the directory; a stream reader asks for a password."""
    def change(data):
        local = Z.local_header(data, OTHER)
        return Z.bend(data, local + 6, Z.le(Z.u16(data, local + 6) | 0x1, 2))
    report = runner.check(patched(tmp_path, change))
    assert "S7" not in {f.rule.id for f in report.findings}
    findings = s10(report)
    assert "general purpose flag bit 0 (encryption): directory clear, local header set" in findings[0].violation.detail


WIDE = "content/café.xhtml"


def _unicode_path(name: str, spelled: bytes, version: int = 1) -> bytes:
    """An Info-ZIP Unicode Path extra field (0x7075): a version, the CRC-32
    of the name the record spells, and the name it gives instead."""
    body = bytes([version]) + Z.le(zlib.crc32(spelled), 4) + name.encode("utf-8")
    return Z.le(0x7075, 2) + Z.le(len(body), 2) + body


def _raw_field(tail: bytes) -> bytes:
    return Z.le(0x7075, 2) + Z.le(len(tail), 2) + tail


def _add_extra(data, record, extra, *, central):
    """`extra` appended to one record's extra field, with every length and
    offset the archive holds kept in step."""
    name_length = Z.u16(data, record + (28 if central else 26))
    extra_length_at = record + (30 if central else 28)
    at = record + (46 if central else 30) + name_length + Z.u16(data, extra_length_at)
    data = Z.bend(data, extra_length_at, Z.le(Z.u16(data, extra_length_at) + len(extra), 2))
    data = Z.splice(data, at, 0, extra)
    if central:
        end = data.rfind(Z.EOCD)
        data = Z.bend(data, end + 12, Z.le(Z.u32(data, end + 12) + len(extra), 4))
    return data


def _both(data, entry, extra):
    data = _add_extra(data, Z.central_entry(data, entry), extra, central=True)
    return _add_extra(data, Z.local_header(data, entry), extra, central=False)


def _respelled(data, entry, spelled):
    """`entry`'s name replaced by `spelled` in both records, bit 11 cleared."""
    old = entry.encode("utf-8")
    central = Z.central_entry(data, entry)
    data = Z.bend(data, central + 8, Z.le(Z.u16(data, central + 8) & ~0x800, 2))
    data = Z.bend(data, central + 28, Z.le(len(spelled), 2))
    data = Z.splice(data, central + 46, len(old), spelled)
    end = data.rfind(Z.EOCD)
    data = Z.bend(data, end + 12, Z.le(Z.u32(data, end + 12) + len(spelled) - len(old), 4))
    local = _local_spelling(data, old)
    data = Z.bend(data, local + 6, Z.le(Z.u16(data, local + 6) & ~0x800, 2))
    data = Z.bend(data, local + 26, Z.le(len(spelled), 2))
    return Z.splice(data, local + 30, len(old), spelled)


def _local_spelling(data, spelled):
    at = data.find(Z.LOCAL)
    while at != -1:
        if data[at + 30:at + 30 + Z.u16(data, at + 26)] == spelled:
            return at
        at = data.find(Z.LOCAL, at + 4)
    raise AssertionError("no local header spells %r" % spelled)


def _central_spelling(data, spelled):
    at = data.find(Z.CENTRAL)
    while at != -1:
        if data[at + 46:at + 46 + Z.u16(data, at + 28)] == spelled:
            return at
        at = data.find(Z.CENTRAL, at + 4)
    raise AssertionError("no directory record spells %r" % spelled)


def _s10_details(tmp_path, data, path):
    return [f.violation.detail for f in s10(runner.check(Z.rewrite(path, data)))]


def test_a_name_the_two_records_read_differently_is_reported(tmp_path):
    """Bit 11 says the name is UTF-8. Cleared in the local header alone, the
    same bytes read there as code page 437 and name another entry."""
    path = build_package(tmp_path, "wide.iirds", extra=((WIDE, BODY),))
    data = path.read_bytes()
    local = Z.local_header(data, WIDE)
    assert Z.u16(data, local + 6) & 0x800, "the writer did not flag the name as UTF-8"
    bent = Z.bend(data, local + 6, Z.le(Z.u16(data, local + 6) & ~0x800, 2))
    [detail] = _s10_details(tmp_path, bent, path)
    assert ("file name: directory content/café.xhtml, local header "
            "content/caf├⌐.xhtml") in detail


def test_a_name_spelled_in_two_encodings_is_reported(tmp_path):
    """UTF-8 under bit 11 in the directory, code page 437 without it in the
    local header: one name to zipfile, which reads it without a word, and two
    to libarchive, which takes the local header's 0x82 as the byte it is and
    cannot create the file on a UTF-8 system."""
    path = build_package(tmp_path, "spelled.iirds", extra=((WIDE, BODY),))
    data = path.read_bytes()
    local = Z.local_header(data, WIDE)
    utf8, cp437 = WIDE.encode("utf-8"), WIDE.encode("cp437")
    data = Z.bend(data, local + 6, Z.le(Z.u16(data, local + 6) & ~0x800, 2))
    data = Z.bend(data, local + 26, Z.le(len(cp437), 2))
    data = Z.splice(data, local + 30, len(utf8), cp437)
    report = runner.check(Z.rewrite(path, data))
    assert "C1" not in {f.rule.id for f in report.findings}
    [finding] = s10(report)
    assert ("file name: directory and local header both read content/café.xhtml, "
            "from different bytes") in finding.violation.detail


def test_the_name_encoding_flag_on_an_ascii_name_changes_nothing(tmp_path):
    """Code page 437 and UTF-8 read ASCII alike, so on such a name the flag
    changes nothing a reader does."""
    def change(data):
        local = Z.local_header(data, OTHER)
        return Z.bend(data, local + 6, Z.le(Z.u16(data, local + 6) | 0x800, 2))
    assert s10(runner.check(patched(tmp_path, change))) == []


RENAMED = ("a Unicode Path extra field naming the entry content/elsewhere.xhtml, "
           "where its bytes read content/other.xhtml")


def test_a_unicode_path_field_that_renames_the_entry_is_reported(tmp_path):
    """From Python 3.12 zipfile names the entry by the field, and the local
    header a streaming reader reads gives the name its bytes spell. Reported
    on every interpreter, whichever name this one judged the entry under."""
    path = package(tmp_path)
    data = path.read_bytes()
    field = _unicode_path("content/elsewhere.xhtml", OTHER.encode())
    data = _add_extra(data, Z.central_entry(data, OTHER), field, central=True)
    assert _s10_details(tmp_path, data, path) == ["the directory carries " + RENAMED]


def test_a_renaming_field_in_both_records_is_reported_in_both(tmp_path):
    """The records agree with each other and not with themselves: a reader
    that follows the field and one that does not receive two names -- zipfile
    on 3.12 and on 3.11 among them."""
    path = package(tmp_path)
    data = _both(path.read_bytes(), OTHER, _unicode_path("content/elsewhere.xhtml", OTHER.encode()))
    [detail] = _s10_details(tmp_path, data, path)
    assert detail == "the directory carries %s; the local header carries %s" % (RENAMED, RENAMED)


def test_a_field_that_repeats_the_name_is_no_fault(tmp_path):
    """What writers put there: the name again, in UTF-8."""
    path = package(tmp_path)
    data = _both(path.read_bytes(), OTHER, _unicode_path(OTHER, OTHER.encode()))
    assert _s10_details(tmp_path, data, path) == []


def test_a_field_is_held_to_the_name_whatever_its_crc(tmp_path):
    """Readers check the CRC-32 differently -- libarchive against the name
    it holds by then, converted to the system's form and renamed by any
    field before it -- so a field is held to the name whatever its CRC, and
    every field is read."""
    path = package(tmp_path)
    data = path.read_bytes()
    stale = _unicode_path("content/elsewhere.xhtml", b"content/renamed.xhtml")
    assert _s10_details(tmp_path, _add_extra(data, Z.central_entry(data, OTHER), stale,
                                             central=True), path) == [
        "the directory carries " + RENAMED]
    chained = _unicode_path(OTHER, OTHER.encode()) + _unicode_path(
        "content/elsewhere.xhtml", OTHER.encode())
    data = _add_extra(data, Z.local_header(data, OTHER), chained, central=False)
    assert _s10_details(tmp_path, data, path) == ["the local header carries " + RENAMED]


def test_a_field_of_another_version_is_held_to_the_name_as_well(tmp_path):
    """zipfile reads version 1 only, and libarchive does not ask."""
    path = package(tmp_path)
    data = path.read_bytes()
    field = _unicode_path("content/elsewhere.xhtml", OTHER.encode(), version=2)
    data = _add_extra(data, Z.local_header(data, OTHER), field, central=False)
    assert _s10_details(tmp_path, data, path) == ["the local header carries " + RENAMED]


def test_a_legacy_name_is_held_to_the_name_its_bytes_read(tmp_path):
    """The shape Info-ZIP writes: the name in a legacy encoding without bit
    11, the Unicode name in the field. Where code page 437 reads the bytes as
    that name, as it does 0x82, readers agree; where it does not, they do not."""
    for entry, legacy, silent in (("content/café.xhtml", "cp850", True),
                                  ("content/한글.xhtml", "cp949", False)):
        path = build_package(tmp_path, "legacy-%s.iirds" % legacy, extra=((entry, BODY),))
        spelled = entry.encode(legacy)
        data = _respelled(path.read_bytes(), entry, spelled)
        field = _unicode_path(entry, spelled)
        data = _add_extra(data, _central_spelling(data, spelled), field, central=True)
        data = _add_extra(data, _local_spelling(data, spelled), field, central=False)
        details = _s10_details(tmp_path, data, path)
        assert (details == []) is silent, (legacy, details)


def test_a_utf8_name_under_bit_11_passes(tmp_path):
    """What 7-Zip and Python's zipfile write for a name outside ASCII: UTF-8
    bytes, bit 11 set in both records, no field."""
    path = build_package(tmp_path, "sevenzip.iirds", extra=((WIDE, BODY),))
    data = path.read_bytes()
    assert Z.u16(data, Z.local_header(data, WIDE) + 6) & 0x800
    assert Z.u16(data, Z.central_entry(data, WIDE) + 8) & 0x800
    assert s10(runner.check(path)) == []


def test_an_info_zip_style_name_passes(tmp_path):
    """What Info-ZIP writes: a Latin name in code page 437 without bit 11,
    and a Unicode Path field in both records giving the same name in UTF-8.
    Every reader, following the field or not, sees one name."""
    path = build_package(tmp_path, "infozip.iirds", extra=((WIDE, BODY),))
    spelled = WIDE.encode("cp437")
    data = _respelled(path.read_bytes(), WIDE, spelled)
    field = _unicode_path(WIDE, spelled)
    data = _add_extra(data, _central_spelling(data, spelled), field, central=True)
    data = _add_extra(data, _local_spelling(data, spelled), field, central=False)
    assert _s10_details(tmp_path, data, path) == []


def test_a_name_in_another_code_page_says_what_the_writer_should_do(tmp_path):
    """The same shape from a writer whose code page is not 437: the field is
    right and the name is not what code page 437 reads, so readers disagree.
    The remedy is the writer's, and says so."""
    entry = "content/\ud55c\uae00.xhtml"
    path = build_package(tmp_path, "cp949.iirds", extra=((entry, BODY),))
    spelled = entry.encode("cp949")
    data = _respelled(path.read_bytes(), entry, spelled)
    field = _unicode_path(entry, spelled)
    data = _add_extra(data, _central_spelling(data, spelled), field, central=True)
    data = _add_extra(data, _local_spelling(data, spelled), field, central=False)
    [finding] = s10(runner.check(Z.rewrite(path, data)))
    assert "gives readers different names" in finding.violation.message
    assert "naming the entry %s, where its bytes read" % entry in finding.violation.detail
    assert "UTF-8 and bit 11 set" in finding.violation.fix


REFUSED = "one reader refuses and another passes by"


def _findings(tmp_path, data, path):
    return s10(runner.check(Z.rewrite(path, data)))


def test_a_local_field_libarchive_refuses_is_reported(tmp_path):
    """libarchive skips or refuses the entry for these, and zipfile never
    reads the local header's extra field; the same on every interpreter."""
    crc = Z.le(zlib.crc32(OTHER.encode()), 4)
    for number, (field, why) in enumerate((
            (_raw_field(b"\x01" + crc + b"\xff\xfe"), "that is not UTF-8"),
            (_raw_field(b"\x01" + crc), "that names nothing"),
            (Z.le(0x7075, 2) + Z.le(40, 2) + b"\x01" + crc, None))):
        path = package(tmp_path, name="broken-%d.iirds" % number)
        data = path.read_bytes()
        data = _add_extra(data, Z.local_header(data, OTHER), field, central=False)
        [finding] = _findings(tmp_path, data, path)
        assert REFUSED in finding.violation.message, why
        assert finding.violation.detail == (
            "the local header carries a Unicode Path extra field %s" % why if why else
            "the local header carries extra data that runs past its end")


def test_a_local_field_too_short_for_a_name_is_passed_by_everyone(tmp_path):
    path = package(tmp_path)
    data = path.read_bytes()
    data = _add_extra(data, Z.local_header(data, OTHER), _raw_field(b"\x01\x00"), central=False)
    assert _findings(tmp_path, data, path) == []


def test_every_faulty_field_in_a_record_is_named(tmp_path):
    path = package(tmp_path)
    data = path.read_bytes()
    crc = Z.le(zlib.crc32(OTHER.encode()), 4)
    fields = _raw_field(b"\x01" + crc + b"\xff\xfe") + _raw_field(b"\x01" + crc)
    data = _add_extra(data, Z.local_header(data, OTHER), fields, central=False)
    [finding] = _findings(tmp_path, data, path)
    assert finding.violation.detail.count("the local header carries") == 2


def test_a_unicode_path_field_after_another_extra_field_is_read(tmp_path):
    """Info-ZIP writes its timestamp field (0x5455) first."""
    path = package(tmp_path)
    data = path.read_bytes()
    timestamp = Z.le(0x5455, 2) + Z.le(5, 2) + b"\x01" + Z.le(0, 4)
    field = timestamp + _unicode_path("content/elsewhere.xhtml", OTHER.encode())
    data = _add_extra(data, Z.central_entry(data, OTHER), field, central=True)
    assert _s10_details(tmp_path, data, path) == ["the directory carries " + RENAMED]


def test_a_field_is_held_to_what_its_own_record_reads(tmp_path):
    """A local header with bit 11 set and its field naming the same UTF-8
    name agree, and a record's field is held to that record's name even
    where the two records' names differ."""
    path = build_package(tmp_path, "wide-field.iirds", extra=((WIDE, BODY),))
    data = path.read_bytes()
    data = _add_extra(data, Z.local_header(data, WIDE), _unicode_path(WIDE, WIDE.encode()),
                      central=False)
    assert _s10_details(tmp_path, data, path) == []
    upper = "content/OTHER.xhtml"
    path = package(tmp_path, name="two-names.iirds")
    data = path.read_bytes()
    local = Z.local_header(data, OTHER)
    data = Z.bend(data, local + 30, upper.encode())
    agreeing = _add_extra(data, local, _unicode_path(upper, upper.encode()), central=False)
    assert [f.violation.message for f in _findings(tmp_path, agreeing, path)] == [
        "local file header disagrees with the central directory"]
    renaming = _add_extra(data, local, _unicode_path("content/elsewhere.xhtml", upper.encode()),
                          central=False)
    assert len(_findings(tmp_path, renaming, path)) == 2


def test_a_field_is_compared_with_the_name_up_to_its_nul(tmp_path):
    """zipfile and libarchive both stop a name at a NUL."""
    path = package(tmp_path)
    spelled = OTHER.encode() + b"\x00junk"
    data = _respelled(path.read_bytes(), OTHER, spelled)
    local = _local_spelling(data, spelled)
    same = _unicode_path(OTHER, OTHER.encode())
    assert _s10_details(tmp_path, _add_extra(data, local, same, central=False), path) == []
    other = _unicode_path("content/elsewhere.xhtml", OTHER.encode())
    [detail] = _s10_details(tmp_path, _add_extra(data, local, other, central=False), path)
    assert detail == "the local header carries " + RENAMED


def test_names_composed_differently_are_one_name(tmp_path):
    """A field that spells the name decomposed, as macOS keeps names, names
    the same entry to every reader that composes names."""
    import unicodedata

    path = build_package(tmp_path, "nfd.iirds", extra=((WIDE, BODY),))
    data = path.read_bytes()
    decomposed = unicodedata.normalize("NFD", WIDE)
    data = _add_extra(data, Z.local_header(data, WIDE), _unicode_path(decomposed, WIDE.encode()),
                      central=False)
    assert _s10_details(tmp_path, data, path) == []


def test_local_extra_data_that_runs_past_its_end_is_reported(tmp_path):
    """libarchive refuses the entry for any kind of field, and zipfile never
    reads the local header's extra data."""
    path = package(tmp_path)
    data = path.read_bytes()
    overflow = Z.le(0x5455, 2) + Z.le(40, 2) + b"\x01" + Z.le(0, 4)
    data = _add_extra(data, Z.local_header(data, OTHER), overflow, central=False)
    [finding] = _findings(tmp_path, data, path)
    assert finding.violation.detail == "the local header carries extra data that runs past its end"


def test_a_field_after_one_readers_pass_by_is_still_read(tmp_path):
    """A local field too short to hold a name, or a directory field that
    names nothing, is passed by; the renaming field after it is not."""
    path = package(tmp_path)
    data = path.read_bytes()
    renaming = _unicode_path("content/elsewhere.xhtml", OTHER.encode())
    local = _add_extra(data, Z.local_header(data, OTHER), _raw_field(b"\x01\x00") + renaming,
                       central=False)
    assert _s10_details(tmp_path, local, path) == ["the local header carries " + RENAMED]
    if sys.version_info < (3, 12):
        # From 3.12 zipfile warns of an empty field, and this suite makes
        # warnings errors, so the archive would not open here.
        empty = _raw_field(b"\x01" + Z.le(zlib.crc32(OTHER.encode()), 4))
        central = _add_extra(data, Z.central_entry(data, OTHER), empty + renaming, central=True)
        assert _s10_details(tmp_path, central, path) == ["the directory carries " + RENAMED]


def test_a_directory_field_that_names_a_way_out_is_reported_by_s6(tmp_path):
    """zipfile gives the directory's field from 3.12; S6 reads it before."""
    path = build_package(tmp_path, "dir-out.iirds", extra=((OTHER, BODY),))
    data = path.read_bytes()
    data = _add_extra(data, Z.central_entry(data, OTHER), _unicode_path(ESCAPE, OTHER.encode()),
                      central=True)
    report = runner.check(Z.rewrite(path, data))
    assert ESCAPE in [f.violation.subject for f in report.findings if f.rule.id == "S6"]


def test_the_finding_is_filed_under_the_name_the_bytes_read(tmp_path):
    path = package(tmp_path)
    data = path.read_bytes()
    field = _unicode_path("content/elsewhere.xhtml", OTHER.encode())
    data = _add_extra(data, Z.central_entry(data, OTHER), field, central=True)
    assert [f.violation.subject for f in _findings(tmp_path, data, path)] == [OTHER]


def test_a_broken_field_in_the_directory_fails_on_every_interpreter(tmp_path):
    for number, tail in enumerate((b"\x01\x00", b"", b"\x01\x00\x00\x00")):
        path = package(tmp_path, name="short-%d.iirds" % number)
        data = path.read_bytes()
        data = _add_extra(data, Z.central_entry(data, OTHER), _raw_field(tail), central=True)
        report = runner.check(Z.rewrite(path, data))
        assert not report.ok
        if sys.version_info >= (3, 12):
            assert "S13" in {f.rule.id for f in report.findings}   # zipfile refuses it
        else:
            [finding] = s10(report)
            assert REFUSED in finding.violation.message
            assert finding.violation.detail == (
                "the directory carries a Unicode Path extra field too short to hold a name")


ESCAPE = "../escape.xhtml"


def test_a_name_that_escapes_under_its_bytes_is_reported_under_any_field(tmp_path):
    """Both records spell a name out of the root and carry a field giving a
    name inside it. From 3.12 zipfile gives the inside name, and S6 read only
    that one; a reader that does not follow the field extracts outside."""
    path = build_package(tmp_path, "out.iirds", extra=((ESCAPE, BODY),))
    data = _both(path.read_bytes(), ESCAPE, _unicode_path("content/inside.xhtml", ESCAPE.encode()))
    report = runner.check(Z.rewrite(path, data))
    assert ESCAPE in [f.violation.subject for f in report.findings if f.rule.id == "S6"]


def test_a_field_that_names_a_way_out_is_reported_before_3_12_too(tmp_path):
    path = build_package(tmp_path, "in.iirds", extra=((OTHER, BODY),))
    data = _both(path.read_bytes(), OTHER, _unicode_path(ESCAPE, OTHER.encode()))
    report = runner.check(Z.rewrite(path, data))
    assert ESCAPE in [f.violation.subject for f in report.findings if f.rule.id == "S6"]


def test_a_local_field_that_names_a_way_out_is_reported_by_s6(tmp_path):
    """libarchive takes the name from the local header's field."""
    path = build_package(tmp_path, "local-out.iirds", extra=((OTHER, BODY),))
    data = path.read_bytes()
    data = _add_extra(data, Z.local_header(data, OTHER), _unicode_path(ESCAPE, OTHER.encode()),
                      central=False)
    report = runner.check(Z.rewrite(path, data))
    assert ESCAPE in [f.violation.subject for f in report.findings if f.rule.id == "S6"]


def test_an_escaping_name_is_reported_once_per_entry(tmp_path):
    path = build_package(tmp_path, "once.iirds", extra=((ESCAPE, BODY),))
    report = runner.check(path)
    assert [f.violation.subject for f in report.findings if f.rule.id == "S6"] == [ESCAPE]


def test_a_name_is_read_up_to_its_nul_as_readers_read_it(tmp_path):
    """zipfile and libarchive both stop at a NUL, so what follows one
    escapes nothing."""
    path = build_package(tmp_path, "nul.iirds", extra=((OTHER, BODY),))
    data = _respelled(path.read_bytes(), OTHER, OTHER.encode() + b"\x00/../../x")
    report = runner.check(Z.rewrite(path, data))
    assert not [f for f in report.findings if f.rule.id == "S6"]


def test_a_data_descriptor_that_disagrees_is_reported(tmp_path):
    path = package(tmp_path)
    data = Z.streamed(path)
    at = Z.descriptor_at(data, OTHER)
    bent = Z.bend(data, at + 12, Z.le(Z.u32(data, at + 12) + 1, 4))
    findings = s10(runner.check(Z.rewrite(path, bent)))
    assert [f.violation.subject for f in findings] == [OTHER]
    assert "data descriptor" in findings[0].violation.detail


def test_a_bit_3_disagreement_is_reported(tmp_path):
    """Bit 3 set in the local header alone puts the sizes in a descriptor
    the entry does not have; set in the directory alone, the flag itself."""
    def local_only(data):
        local = Z.local_header(data, OTHER)
        return Z.bend(data, local + 6, Z.le(Z.u16(data, local + 6) | 0x8, 2))

    def central_only(data):
        central = Z.central_entry(data, OTHER)
        return Z.bend(data, central + 8, Z.le(Z.u16(data, central + 8) | 0x8, 2))

    detail = s10(runner.check(patched(tmp_path, local_only, "local.iirds")))[0].violation.detail
    assert "general purpose flag bit 3 (data descriptor): directory clear, local header set" in detail
    assert "no data descriptor" in detail
    detail = s10(runner.check(patched(tmp_path, central_only, "central.iirds")))[0].violation.detail
    assert "general purpose flag bit 3 (data descriptor): directory set, local header clear" in detail


@pytest.mark.parametrize("where", ["wrong signature", "past the end", "inside another entry's data",
                                   "another entry's header"])
def test_an_offset_that_holds_no_local_header_is_reported(tmp_path, where):
    def change(data):
        central = Z.central_entry(data, OTHER)
        local = Z.local_header(data, OTHER)
        if where == "wrong signature":
            return Z.bend(data, local, b"PK\x03\x05")
        if where == "past the end":
            return Z.bend(data, central + 42, Z.le(len(data) + 100, 4))
        if where == "inside another entry's data":
            return Z.bend(data, central + 42, Z.le(Z.data_start(data, Z.local_header(data, SPARE)) + 2, 4))
        return Z.bend(data, central + 42, Z.le(Z.local_header(data, SPARE), 4))

    findings = s10(runner.check(patched(tmp_path, change)))
    assert [f.violation.subject for f in findings] == [OTHER], where
    message = findings[0].violation.message
    if where == "another entry's header":
        assert "file name: directory content/other.xhtml, local header content/spare.xhtml" in findings[0].violation.detail
    else:
        assert message == "no local file header at the offset the central directory gives"


def test_an_entry_whose_data_runs_into_the_next_is_reported(tmp_path):
    """Both records agree on a compressed size that reaches into the next
    entry's header: a reader that trusts it hands out the neighbour's bytes
    as this entry's."""
    def change(data):
        local = Z.local_header(data, OTHER)
        central = Z.central_entry(data, OTHER)
        too_long = Z.u32(data, central + 20) + 40
        data = Z.bend(data, local + 18, Z.le(too_long, 4))
        return Z.bend(data, central + 20, Z.le(too_long, 4))
    findings = s10(runner.check(patched(tmp_path, change)))
    assert [f.violation.subject for f in findings] == [OTHER]
    assert findings[0].violation.message == (
        "entry data, as the central directory describes it, runs into the next entry")


def test_one_finding_per_entry_in_directory_order(tmp_path):
    def change(data):
        for name in (SPARE, OTHER):
            data = Z.bend(data, Z.local_header(data, name) + 8, Z.le(0, 2))
        return data
    findings = s10(runner.check(patched(tmp_path, change)))
    assert [f.violation.subject for f in findings] == [OTHER, SPARE]


def test_the_rule_stands_down_on_an_unpacked_container(tmp_path):
    import zipfile

    path = package(tmp_path)
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(path) as zf:
        zf.extractall(unpacked)
    report = runner.check(unpacked)
    assert s10(report) == []
    assert any("S10" in note for note in report.notes)


def test_reads_stay_bounded_on_a_hostile_name_length(tmp_path):
    """A local header claiming a 65535-byte name in a file that ends before
    it: no exception, one finding."""
    def change(data):
        local = Z.local_header(data, SPARE)
        return Z.bend(data, local + 26, Z.le(65535, 2))
    findings = s10(runner.check(patched(tmp_path, change)))
    assert [f.violation.subject for f in findings] == [SPARE]


def test_two_directory_records_sharing_one_local_header_are_one_name(tmp_path):
    """Two central records, the same name, the same offset -- and not S10's.

    This rule used to claim it, as "the central directory gives two entries the
    same local file header", and the finding named the same file as its subject
    and in its detail. That was not a slip in the wording: reaching that check
    means both records agreed with the local header they point at, agreement
    includes the name, and a header declares one name -- so "two entries"
    could only ever be one name listed twice, which is a fact about the
    directory rather than about any local header. S15 states it, with the
    record count and which one a reader resolves to.

    What this rule still says about a bent offset is one line up and is
    checked by `test_a_record_pointed_at_another_entrys_header_is_said_so`:
    move a record's offset and leave its name alone, and the name disagreement
    fires before an extent is ever recorded.
    """
    def change(data):
        other = Z.local_header(data, OTHER)
        central = Z.central_entry(data, SPARE)
        data = Z.bend(data, central + 46, OTHER.encode("ascii"))
        return Z.bend(data, central + 42, Z.le(other, 4))
    report = runner.check(patched(tmp_path, change))
    assert s10(report) == [], [(f.violation.subject, f.violation.detail) for f in s10(report)]
    said = [f for f in report.findings if f.rule.id == "S15"]
    assert [f.violation.subject for f in said] == [OTHER], \
        [f.violation.subject for f in said]
    assert "2 records" in said[0].violation.detail, said[0].violation.detail


def test_a_record_pointed_at_another_entrys_header_is_said_so(tmp_path):
    """The bent offset on its own, with the record's name left as it was.

    This is the shape the removed check was reaching for and never saw: one
    record describing an entry that is not where it says it is. The local
    header at the new offset declares a different name, so the two records of
    that entry disagree, which is exactly what this rule is about.
    """
    def change(data):
        other = Z.local_header(data, OTHER)
        return Z.bend(data, Z.central_entry(data, SPARE) + 42, Z.le(other, 4))
    findings = s10(runner.check(patched(tmp_path, change)))
    assert [f.violation.subject for f in findings] == [SPARE]
    assert findings[0].violation.detail == (
        "file name: directory %s, local header %s" % (SPARE, OTHER))


def test_an_offset_the_directory_cannot_express_yields_no_header(tmp_path):
    """A broken ZIP64 end record makes `zipfile` compute a negative
    correction, and every offset it hands out goes negative -- an InfoZip
    `-fd -fz` archive does this. A seek there raised, and the run reported
    the rule as having crashed; it is one more offset that holds no local
    file header."""
    from iirds_validate.package import Package

    with Package(package(tmp_path)) as pkg:
        pkg.infos[1].header_offset = -5
        headers = [header for _info, header, _descriptor in pkg.local_headers()]
    assert headers[1] is None and headers[0] is not None


def test_the_last_entrys_data_running_into_the_directory_is_reported(tmp_path):
    """The one branch of this rule no test had ever reached.

    Every other extent check compares one entry against the next; the last
    entry has no next, and is compared against the central directory instead.
    A tool that measured the check on the whole rule saw it exercised, because
    the rule fires elsewhere -- what was never exercised is this `yield`, and
    a branch nobody has run is a branch nobody knows the sign of. S8 was
    backwards for months in exactly that state.

    Both records are bent, not one: `_disagreements` compares the sizes and
    would report the mismatch and skip the extent, so a fixture that changed
    the directory alone would test the other branch and look like this one.
    """
    def change(data):
        name = max(_infos(data), key=lambda entry: entry[1])[0]
        grown = Z.le(Z.u32(data, Z.central_entry(data, name) + 20) + 4096, 4)
        data = Z.bend(data, Z.central_entry(data, name) + 20, grown)
        return Z.bend(data, Z.local_header(data, name) + 18, grown)

    findings = s10(runner.check(patched(tmp_path, change, "overrun.iirds")))
    assert findings, "the last entry's data now ends past the central directory"
    assert any("runs into the central directory" in f.violation.message for f in findings), \
        [f.violation.message for f in findings]


def _infos(data):
    """(name, header offset) for every entry, read from the central directory."""
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return [(info.filename, info.header_offset) for info in archive.infolist()]
