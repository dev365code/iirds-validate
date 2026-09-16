"""One name, several records in the central directory.

A ZIP's central directory is a list, not a map. Nothing in the format stops
two records from carrying the same entry name, and `zipfile` builds its name
table by walking that list and assigning as it goes -- so a name resolves to
the *last* record carrying it, and every record before it describes bytes
nothing here will ever open. Where those records give different header
offsets they describe different bytes: two complete entries, each with its own
local file header and its own data, delivered under one name to whichever
reader picks differently.

Two things follow, and this file pins both.

**A pass that walks records reads the same entry over and over.** C1 asks
whether every entry comes back out again, which means opening each one and
reading it to the end. Walking `infolist()` -- one item per record -- read one
8 MiB entry fifty times from an archive of 11,890 bytes: 419,430,400 bytes
decompressed in 0.23 s. Walking the name table reads it once, 8,390,076 bytes
for the whole run, and the ratio is the point rather than either number: the
work an archive can buy with a duplicated record is unbounded in the record
count, which costs 46 bytes plus the name.

**And the duplication is a finding, not a silence.** C15 already reports the
same archive, as a defect in the package's namespace -- the specification's
sentence about it -- and that is a different claim from this one: S15 says
what the archive does to a reader, which is that the name means whichever
record the reader kept. The two coexist deliberately.

The recipe below is the whole trick: build an ordinary container, then copy one
central-directory record and adjust the end-of-central-directory record's
counts. Every copy is byte-identical, so the archive stays perfectly
self-consistent -- each record agrees with the one local file header it points
at, and S10 has nothing to say about it. That is what makes this a rule of its
own rather than a case of S10.
"""
from __future__ import annotations

import collections
import struct
import zipfile
from pathlib import Path

from conftest import build_package
from iirds_validate import runner

#: Big enough that reading one entry fifty times is unmistakable in the
#: numbers, small enough that a machine running this suite survives it.
BOMB_BYTES = 8 * 1024 * 1024

#: How many records carry the one name. Fifty is arbitrary; what it has to be
#: is large enough that "once per name" and "once per record" cannot be
#: confused for each other by a margin of measurement.
COPIES = 50

BOMB = "extra/bomb.bin"

_CENTRAL = b"PK\x01\x02"
_EOCD = b"PK\x05\x06"


def _records(raw: bytes, offset: int, count: int):
    """The central directory as (name, bytes) pairs, in the order it lists them."""
    out = []
    at = offset
    for _ in range(count):
        assert raw[at:at + 4] == _CENTRAL, "not a central-directory record at %d" % at
        name_len, extra_len, comment_len = struct.unpack("<HHH", raw[at + 28:at + 34])
        size = 46 + name_len + extra_len + comment_len
        out.append((raw[at + 46:at + 46 + name_len].decode("utf-8", "replace"), raw[at:at + size]))
        at += size
    return out


def _rewrite_directory(raw: bytes, offset: int, blobs) -> bytes:
    """The archive with its central directory replaced by `blobs`.

    The entry data is untouched -- only the index over it changes -- which is
    what a tool editing an archive in place does and what a hostile one does
    deliberately.
    """
    directory = b"".join(blobs)
    end = _EOCD + struct.pack("<HHHHIIH", 0, 0, len(blobs), len(blobs),
                              len(directory), offset, 0)
    return raw[:offset] + directory + end


def _open_directory(path: Path):
    """(bytes, where the directory starts, its records) for an archive on disk."""
    raw = Path(path).read_bytes()
    at = raw.rindex(_EOCD)
    _disk, _cd_disk, _here, total, _size, offset, _comment = struct.unpack(
        "<HHHHIIH", raw[at + 4:at + 22])
    return raw, offset, _records(raw, offset, total)


def one_name_many_records(tmp_path, copies=COPIES, name="duplicated.iirds"):
    """A conformant container, with one entry's record copied `copies` times.

    Every copy points at the one local file header the original does, so the
    archive is not damaged in any other way: it opens, every entry reads, and
    the only thing wrong with it is that the directory says one name `copies`
    times.
    """
    base = build_package(tmp_path, "base-for-%s" % name, extra=((BOMB, b"a" * BOMB_BYTES),))
    raw, offset, records = _open_directory(base)
    blobs = []
    for entry_name, blob in records:
        blobs.append(blob)
        if entry_name == BOMB:
            blobs.extend([blob] * (copies - 1))
    path = Path(tmp_path) / name
    path.write_bytes(_rewrite_directory(raw, offset, blobs))
    return path


def two_entries_one_name(tmp_path, name="collided.iirds"):
    """Two whole entries, of different sizes, under one name.

    Both records are renamed, in the directory and in the local file header
    alike, so each record still agrees with the header it points at and S10
    passes the archive. What a reader receives under `extra/one.bin` is then
    decided entirely by which record it kept.
    """
    first, second = "extra/one.bin", "extra/two.bin"
    assert len(first) == len(second), "the rename is in place, so the names must be one length"
    base = build_package(tmp_path, "base-for-%s" % name,
                         extra=((first, b"a" * 4096), (second, b"b" * 65536)))
    raw = bytearray(Path(base).read_bytes())
    # Every occurrence of the second name, in its local file header and in its
    # central-directory record, becomes the first name. Same length, so no
    # offset in the archive moves.
    raw = bytearray(bytes(raw).replace(second.encode(), first.encode()))
    path = Path(tmp_path) / name
    path.write_bytes(bytes(raw))
    return path


def decompressed_by(run):
    """(what `run()` returned, bytes decompressed while it ran, per entry name).

    Counted where the decompression is handed over rather than where it is
    asked for: `ZipExtFile.read` returns what came out of the decompressor,
    and a rule that asks for a bounded slice of an entry is charged the slice
    it got. A test that counted calls instead would pass a version that read
    the same entry fifty times in one call each.
    """
    seen: collections.Counter = collections.Counter()
    original = zipfile.ZipExtFile.read

    def counted(self, n=-1):
        out = original(self, n)
        seen[self.name] += len(out)
        return out

    zipfile.ZipExtFile.read = counted
    try:
        result = run()
    finally:
        zipfile.ZipExtFile.read = original
    return result, sum(seen.values()), seen


def ids(report):
    return sorted({f.rule.id for f in report.findings})


def test_zipfile_resolves_a_duplicated_name_to_the_last_record(tmp_path):
    """The premise every claim in this file rests on, asserted rather than
    assumed.

    `zipfile` assigns into `NameToInfo` as it walks the directory, so the last
    record carrying a name is the one `open()` and `read()` reach. If a future
    CPython kept the first instead, the rules below would be describing the
    wrong record and nothing else here would notice.
    """
    package = one_name_many_records(tmp_path, copies=3)
    with zipfile.ZipFile(package) as archive:
        records = [i for i in archive.infolist() if i.filename == BOMB]
        assert len(records) == 3, [i.filename for i in archive.infolist()]
        assert len(archive.NameToInfo) == len({i.filename for i in archive.infolist()})
        assert archive.getinfo(BOMB) is records[-1], "the name no longer resolves to the last"


def test_the_damage_check_reads_each_name_once_not_each_record(tmp_path):
    """C1 opens every entry and reads it to the end. Once per name.

    Measured on this archive, 11,890 bytes on disk, one entry declaring 8 MiB
    and fifty records naming it. Walking `infolist()` -- once per record --
    the whole run decompressed 419,431,868 bytes in 0.23 s, of which
    419,430,400 was that one entry, fifty times over. Walking the name table
    the same run decompresses 8,390,076, of which 8,388,608 is the entry,
    once. The assertion is the *shape* of that -- about one entry's worth, not
    fifty -- because the ratio is what an archive controls and the absolute
    figure is what this machine happens to do with it.

    Two entries' worth of room, not one: the metadata, the mimetype and the
    one content file are read by the rules as well, and a later rule that
    reads the bomb once for a reason of its own should not turn this red.
    What it may not do is read it again per record.
    """
    package = one_name_many_records(tmp_path)
    report, total, per_name = decompressed_by(lambda: runner.run(package, runner.ALL_KINDS))

    assert total <= 2 * BOMB_BYTES, (
        "a %d byte archive with %d records for one %d byte entry made the run decompress "
        "%d bytes: %r" % (Path(package).stat().st_size, COPIES, BOMB_BYTES, total,
                          dict(per_name)))
    assert per_name[BOMB] <= 2 * BOMB_BYTES, (
        "the duplicated entry alone was decompressed %d times" % (per_name[BOMB] // BOMB_BYTES))
    # The entry was read -- this is not passing by reading nothing.
    assert per_name[BOMB] >= BOMB_BYTES
    assert "C1" not in ids(report), "the archive is not damaged; C1 must not fire on it"


def test_a_name_the_directory_carries_more_than_once_is_reported(tmp_path):
    """The archive-level fact, which is not C15's.

    C15 reports the same archive for the same reason the specification gives:
    two entries cannot share a name inside a directory. This says what the
    archive does to a reader -- that the name resolves to one record and the
    others describe bytes nobody opens -- and it has to say how many and
    which, because "duplicate" alone does not tell a sender whether they
    shipped one stray record or fifty.
    """
    report = runner.run(one_name_many_records(tmp_path), runner.ALL_KINDS)
    said = [f for f in report.findings if f.rule.id == "S15"]

    assert said, "nothing reported the duplicated records; findings were %s" % ids(report)
    assert [f.violation.subject for f in said] == [BOMB], \
        "the finding names %s, not the entry" % [f.violation.subject for f in said]
    detail = said[0].violation.detail
    assert str(COPIES) in detail, "the detail does not say how many records: %r" % detail
    assert "last" in detail, "the detail does not say which record a reader resolves to: %r" % detail


def test_records_at_one_offset_and_records_at_several_read_differently(tmp_path):
    """Fifty copies of one record and two records for two whole entries are
    not the same defect, and a detail that reads the same for both is a detail
    that has not been written.

    Copies of one record waste a reader's time. Records at different offsets
    hand two readers different files under one name, which is the case worth
    the sender's attention, so the finding has to distinguish them.
    """
    copies = runner.run(one_name_many_records(tmp_path), runner.ALL_KINDS)
    collided = runner.run(two_entries_one_name(tmp_path), runner.ALL_KINDS)

    one = next(f for f in copies.findings if f.rule.id == "S15").violation.detail
    several = next(f for f in collided.findings if f.rule.id == "S15").violation.detail
    assert one != several
    assert "different bytes" in several, \
        "the records describe different bytes and the detail does not say so: %r" % several
    assert "different bytes" not in one, \
        "these records all describe the same bytes: %r" % one


def test_the_collided_archive_is_otherwise_sound(tmp_path):
    """The negative that makes the rule mean something.

    Both records agree with the local file header they point at, both entries
    are whole, and the archive opens and reads. If S10 fired here the finding
    above would be redundant -- the archive would already be reported as
    self-contradictory -- and this rule would be a second name for S10.
    """
    report = runner.run(two_entries_one_name(tmp_path), runner.ALL_KINDS)
    assert "S10" not in ids(report), \
        [f.violation.detail for f in report.findings if f.rule.id == "S10"]
    assert "C1" not in ids(report), \
        [f.violation.detail for f in report.findings if f.rule.id == "C1"]
    assert "S15" in ids(report)


def test_copied_records_are_not_reported_as_two_entries_sharing_a_header(tmp_path):
    """S10's extents are one per entry a reader receives, not one per record.

    Its last section sorts the entries by offset and compares each with the
    next, to catch data running into the following header. Fifty records for
    one name put fifty identical extents in that list, and every neighbouring
    pair then looked like two entries at one offset: forty-nine findings
    reading `subject extra/bomb.bin, offset 479, also the header of
    extra/bomb.bin`, each saying that an entry collides with itself.

    The duplication is one fact and S15 states it once. What S10 keeps for a
    name is the record a reader resolves to, which is the entry whose extent
    can actually run into something.
    """
    report = runner.run(one_name_many_records(tmp_path), runner.ALL_KINDS)
    s10 = [f for f in report.findings if f.rule.id == "S10"]
    assert s10 == [], [(f.violation.subject, f.violation.detail) for f in s10]


def test_an_ordinary_archive_is_not_reported(tmp_path):
    """Every container this suite builds has one record per name, and a rule
    that fired on them would fire on every package ever built by a normal
    tool."""
    report = runner.run(build_package(tmp_path), runner.ALL_KINDS)
    assert "S15" not in ids(report), ids(report)


def test_the_rule_is_not_claimed_against_an_unpacked_container(tmp_path):
    """A directory has no central directory to carry a name twice, and a
    filesystem cannot hold one name twice in one place. Reported as not
    assessed rather than as passed, like every other rule about the archive."""
    package = build_package(tmp_path, "unpacked.iirds")
    unpacked = Path(tmp_path) / "unpacked"
    zipfile.ZipFile(package).extractall(unpacked)

    report = runner.check(unpacked)
    assert "S15" in report.not_applicable.get("unpacked", ()), report.not_applicable
    assert "S15" not in report.ran
