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


def test_two_directory_entries_sharing_one_local_header_are_said_so(tmp_path):
    """Two central records, the same name, the same offset: a reader that
    trusts the directory hands out one file twice, and the second record's
    entry does not exist. Said as what it is rather than as data running
    into a neighbour."""
    def change(data):
        other = Z.local_header(data, OTHER)
        central = Z.central_entry(data, SPARE)
        data = Z.bend(data, central + 46, OTHER.encode("ascii"))
        return Z.bend(data, central + 42, Z.le(other, 4))
    findings = s10(runner.check(patched(tmp_path, change)))
    assert [f.violation.message for f in findings] == [
        "the central directory gives two entries the same local file header"]
    assert findings[0].violation.subject == OTHER


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
