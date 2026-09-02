"""Byte-level surgery on real archives, for the fixtures S10 needs.

A ZIP describes every entry twice: in a local file header before the data
and in the central directory at the end. `zipfile` will not write the two
apart, so the archives that disagree are made by building an ordinary one
and changing one field of one record -- the principle `bend` states: one
field, nothing else, so the finding under test is the only thing that can
answer.

Offsets below follow the PKWARE APPNOTE: the local header (4.3.7) is thirty
fixed bytes -- flags at 6, method at 8, crc-32 at 14, compressed size at 18,
uncompressed size at 22, name length at 26, extra length at 28 -- then the
name, the extra field and the data; the central record (4.3.12) is
forty-six fixed bytes with flags at 8, sizes at 20/24, the name length at
28, the extra and comment lengths at 30/32 and the local header's offset at
42; the end-of-central-directory record (4.3.16) carries the directory's
offset at 16.
"""
from __future__ import annotations

import io
import zipfile

LOCAL = b"PK\x03\x04"
CENTRAL = b"PK\x01\x02"
EOCD = b"PK\x05\x06"
DESCRIPTOR = b"PK\x07\x08"


def u16(raw, at):
    return int.from_bytes(raw[at:at + 2], "little")


def u32(raw, at):
    return int.from_bytes(raw[at:at + 4], "little")


def le(value, width):
    return int(value).to_bytes(width, "little")


def central_entry(data: bytes, name: str) -> int:
    """Offset of the central directory record for `name`."""
    wanted = name.encode("utf-8")
    cursor = data.find(EOCD)
    assert cursor >= 0, "no end-of-central-directory record"
    cursor = u32(data, cursor + 16)
    while data[cursor:cursor + 4] == CENTRAL:
        length = u16(data, cursor + 28)
        if data[cursor + 46:cursor + 46 + length] == wanted:
            return cursor
        cursor += 46 + length + u16(data, cursor + 30) + u16(data, cursor + 32)
    raise AssertionError("no central directory record for %s" % name)


def local_header(data: bytes, name: str) -> int:
    """Offset of the local file header the directory gives for `name`."""
    at = u32(data, central_entry(data, name) + 42)
    assert data[at:at + 4] == LOCAL, name
    return at


def data_start(data: bytes, local: int) -> int:
    return local + 30 + u16(data, local + 26) + u16(data, local + 28)


def descriptor_at(data: bytes, name: str) -> int:
    """Where the directory's compressed size puts the entry's data descriptor."""
    central = central_entry(data, name)
    return data_start(data, local_header(data, name)) + u32(data, central + 20)


def bend(raw: bytes, at: int, replacement: bytes) -> bytes:
    """One field of a real archive changed and nothing else."""
    return raw[:at] + replacement + raw[at + len(replacement):]


def splice(raw: bytes, at: int, old_length: int, new: bytes) -> bytes:
    """Replace `old_length` bytes at `at` with `new`, keeping every offset
    the directory and its end record hold in step with the change."""
    delta = len(new) - old_length
    out = bytearray(raw[:at] + new + raw[at + old_length:])
    eocd = out.rfind(EOCD)
    directory = u32(out, eocd + 16)
    cursor = directory + delta if directory > at else directory
    if directory > at:
        out[eocd + 16:eocd + 20] = le(cursor, 4)
    while out[cursor:cursor + 4] == CENTRAL:
        offset = u32(out, cursor + 42)
        if offset > at:
            out[cursor + 42:cursor + 46] = le(offset + delta, 4)
        cursor += 46 + u16(out, cursor + 28) + u16(out, cursor + 30) + u16(out, cursor + 32)
    return bytes(out)


class _Unseekable:
    """A sink `zipfile` cannot seek on, so it writes entries the way a
    stream writer does: sizes deferred to a data descriptor (bit 3)."""

    def __init__(self):
        self.buffer = io.BytesIO()

    def write(self, chunk):
        return self.buffer.write(chunk)

    def flush(self):
        pass


def streamed(path, force_zip64: bool = False) -> bytes:
    """The package at `path`, rewritten entry for entry through a stream
    writer: every entry carries bit 3 and a data descriptor, the mimetype
    stays first and stored."""
    sink = _Unseekable()
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(sink, "w") as target:
        for info in source.infolist():
            fresh = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            fresh.compress_type = info.compress_type
            with target.open(fresh, "w", force_zip64=force_zip64) as handle:
                handle.write(source.read(info.filename))
    return sink.buffer.getvalue()


def rewrite(path, data: bytes):
    path.write_bytes(data)
    return path
