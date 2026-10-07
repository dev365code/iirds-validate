"""A nested container a streaming writer wrote is still a nested container.

ZIP APPNOTE 4.4.4, general purpose bit 3: when it is set, the crc-32 and the
two sizes are zero in the local header and the correct values follow the data
in a data descriptor. 4.3.9: the descriptor follows the last byte of the data;
4.3.9.3, its signature 0x08074b50 may be there or not, and a reader meets
both; 4.3.9.2, where the entry carries the ZIP64 extended information record
(0x0001) the two sizes in it are eight bytes.

A writer that cannot seek sets bit 3 on every entry, the stored mimetype
included. The archive is still what section 5.2 describes -- first entry,
stored, twenty-one bytes of application/iirds+zip -- and checked on its own it
draws no finding. Nested, it was read by the size field in its local header,
where such a writer puts zero, and no nesting rule saw it.
"""
from __future__ import annotations

import io
import struct
import zipfile

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.package import nested_containers, open_package

PAYLOAD = b"application/iirds+zip"
CRC = zipfile.crc32(PAYLOAD)


class _Pipe(io.RawIOBase):
    """Somewhere a ZIP can be written and not sought back into."""

    def __init__(self):
        self.written = bytearray()

    def writable(self):
        return True

    def seekable(self):
        return False

    def write(self, data):
        self.written += data
        return len(data)


def streamed_child(iri="urn:test:child") -> bytes:
    """A whole child container, written the way a streaming writer writes it."""
    pipe = _Pipe()
    with zipfile.ZipFile(pipe, "w") as archive:
        first = zipfile.ZipInfo("mimetype", date_time=(1980, 1, 1, 0, 0, 0))
        archive.writestr(first, PAYLOAD)
        archive.writestr(zipfile.ZipInfo("META-INF/metadata.rdf", date_time=(1980, 1, 1, 0, 0, 0)),
                         MINIMAL_RDF.replace("urn:test:package", iri))
        archive.writestr(zipfile.ZipInfo("content/topic1.xhtml", date_time=(1980, 1, 1, 0, 0, 0)),
                         "<html/>")
    return bytes(pipe.written)


def test_a_streaming_writer_sets_bit_3_on_the_mimetype_too():
    """The premise, so the tests below are about the case they name."""
    raw = streamed_child()
    assert raw[:4] == b"PK\x03\x04" and struct.unpack("<H", raw[6:8])[0] & 0x08
    assert struct.unpack("<I", raw[18:22])[0] == 0


def found(tmp_path, raw):
    outer = build_package(tmp_path, "outer.iirds", extra=(("content/child.iirds", raw),))
    return nested_containers(open_package(outer))


def test_a_streamed_child_is_a_nested_container(tmp_path):
    assert found(tmp_path, streamed_child()) == ["content/child.iirds"]


def test_a_streamed_child_the_parent_does_not_declare_is_reported(tmp_path):
    outer = build_package(tmp_path, "undeclared.iirds",
                          extra=(("content/child.iirds", streamed_child()),))
    got = [f for f in runner.check(outer).findings if f.rule.id == "R60"]
    assert [f.violation.subject for f in got] == ["content/child.iirds"]


STORED_SIZES = (len(PAYLOAD), len(PAYLOAD))


def head(*, flags=0, sizes=STORED_SIZES, extra=b"", payload=PAYLOAD, descriptor=b""):
    """The start of a child archive, one field at a time: its first local
    header, the mimetype, and what follows the data."""
    name = b"mimetype"
    return (struct.pack("<4sHHHHHIIIHH", b"PK\x03\x04", 20, flags, 0, 0, 0,
                        0 if flags & 0x08 else CRC, sizes[0], sizes[1], len(name), len(extra))
            + name + extra + payload + descriptor + b"PK\x03\x04")


ZIP64_RECORD = struct.pack("<HHQQ", 0x0001, 16, 0, 0)


@pytest.mark.parametrize("raw,is_one", [
    (head(flags=0x08, sizes=(0, 0),
          descriptor=b"PK\x07\x08" + struct.pack("<III", CRC, 21, 21)), True),
    (head(flags=0x08, sizes=(0, 0),
          descriptor=struct.pack("<III", CRC, 21, 21)), True),
    (head(flags=0x08, sizes=(0, 0), extra=ZIP64_RECORD,
          descriptor=b"PK\x07\x08" + struct.pack("<IQQ", CRC, 21, 21)), True),
    (head(flags=0x08, sizes=(0, 0), extra=ZIP64_RECORD,
          descriptor=b"PK\x07\x08" + struct.pack("<III", CRC, 21, 21)), False),
    (head(flags=0x08, sizes=(0, 0), payload=PAYLOAD + b"\n",
          descriptor=b"PK\x07\x08" + struct.pack("<III", zipfile.crc32(PAYLOAD + b"\n"), 22, 22)),
     False),
    (head(sizes=(0xFFFFFFFF, 0xFFFFFFFF), extra=struct.pack("<HHQQ", 0x0001, 16, 21, 21)), True),
], ids=["descriptor with its signature", "descriptor without it",
        "ZIP64 record, eight-byte sizes", "ZIP64 record, four-byte sizes",
        "twenty-two bytes, streamed", "ZIP64 sizes without bit 3"])
def test_the_sizes_are_read_where_the_writer_put_them(tmp_path, raw, is_one):
    """Each shape exact: the descriptor has to say twenty-one, twice, in the
    width its entry calls for -- a descriptor too short for a ZIP64 entry, or
    a mimetype one byte long, is not the container section 5.2 describes."""
    assert found(tmp_path, raw) == (["content/child.iirds"] if is_one else [])
