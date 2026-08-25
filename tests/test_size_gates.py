"""The size gates, observed firing — in both package forms.

MAX_METADATA_BYTES and MAX_CONTENT_BYTES had no test anywhere in this
suite: neither gate had ever been seen to fire, and a gate that has never
caught anything is a gate nobody has tested. Observing them caught a real
hole: `DirectoryPackage.info()` answered None, so both gates were silently
disabled for the unpacked form — the same oversized document an archive
refuses was read and parsed whole when checked before zipping, which is
precisely when people check big work-in-progress packages.
"""
from __future__ import annotations

from pathlib import Path

from conftest import MIMETYPE, MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.context import MAX_METADATA_BYTES
from iirds_validate.model import METADATA_RDF
from iirds_validate.model import MIMETYPE_FILE as MIMETYPE_NAME
from iirds_validate.rules.content import MAX_CONTENT_BYTES

OVER_METADATA = MINIMAL_RDF.encode("utf-8") + b" " * MAX_METADATA_BYTES
OVER_CONTENT = (b'<?xml version="1.0" encoding="utf-8"?>'
                b'<html xmlns="http://www.w3.org/1999/xhtml"><head>'
                b"<title>t</title></head><body><p>big</p></body></html>"
                + b" " * MAX_CONTENT_BYTES)


def _unpacked(tmp_path, metadata: bytes, content: bytes) -> Path:
    root = tmp_path / "unpacked"
    (root / "META-INF").mkdir(parents=True)
    (root / "content").mkdir()
    (root / "mimetype").write_bytes(MIMETYPE)
    (root / "META-INF" / "metadata.rdf").write_bytes(metadata)
    (root / "content" / "topic1.xhtml").write_bytes(content)
    return root


def _findings(path):
    return runner.check(path).findings


def test_oversized_metadata_is_refused_in_an_archive(tmp_path):
    package = build_package(tmp_path, metadata=OVER_METADATA)
    hits = [f for f in _findings(package) if f.rule.id == "C16.1"]
    assert hits and "byte limit" in hits[0].violation.detail


def test_oversized_metadata_is_refused_in_a_directory_too(tmp_path):
    """Same document, unpacked form, same refusal — or the advertised
    check-before-you-zip workflow is the one place the gate is off."""
    root = _unpacked(tmp_path, OVER_METADATA, b"<html/>")
    hits = [f for f in _findings(root) if f.rule.id == "C16.1"]
    assert hits and "byte limit" in hits[0].violation.detail


def test_oversized_content_is_refused_in_an_archive(tmp_path):
    package = build_package(tmp_path, content=(),
                            extra=(("content/topic1.xhtml", OVER_CONTENT),))
    hits = [f for f in _findings(package)
            if f.rule.id == "B1" and "refused" in f.violation.message]
    assert hits and "byte limit" in hits[0].violation.detail


def test_oversized_content_is_refused_in_a_directory_too(tmp_path):
    root = _unpacked(tmp_path, MINIMAL_RDF.encode("utf-8"), OVER_CONTENT)
    hits = [f for f in _findings(root)
            if f.rule.id == "B1" and "refused" in f.violation.message]
    assert hits and "byte limit" in hits[0].violation.detail


def test_no_entry_is_ever_read_without_a_bound(make_package, monkeypatch):
    """The memory vector, sealed where it is spent rather than at each caller.

    `ZipFile.read()` with no size decompresses the whole member in one call
    and only then truncates it to the size the central directory declares --
    a field whoever built the archive writes. So the cost is the payload's,
    not the declared size's: an entry claiming a hundred bytes over a hundred
    megabytes of deflate bought 450 MB resident on a 100 KB archive, and the
    report passed it.

    Asserted here rather than counted in each caller, because the next caller
    is the one nobody remembers. Every read the run makes has to name a size.
    """
    import zipfile

    original = zipfile.ZipExtFile.read
    unbounded = []

    def watched(self, n=-1):
        if n is None or n < 0:
            unbounded.append(getattr(self, "name", "?"))
        return original(self, n)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", watched)
    runner.run(make_package(), runner.ALL_KINDS)

    assert not unbounded, (
        "these entries were decompressed whole before anything looked at their "
        "size: %s" % sorted(set(unbounded)))


def _declaring(tmp_path, name, payload: bytes, claim: int):
    """An archive whose central directory lies about one entry's size."""
    import io
    import struct
    import zipfile
    import zlib

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo(MIMETYPE_NAME)
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, MIMETYPE)
        archive.writestr(METADATA_RDF, MINIMAL_RDF)
        archive.writestr(name, payload)
    raw = bytearray(buf.getvalue())
    at = 0
    while True:
        at = raw.find(b"PK\x01\x02", at)
        if at < 0:
            break
        length = struct.unpack_from("<H", raw, at + 28)[0]
        if bytes(raw[at + 46:at + 46 + length]) == name.encode():
            struct.pack_into("<I", raw, at + 24, claim)
            struct.pack_into("<I", raw, at + 16, zlib.crc32(payload[:claim]))
        at += 4
    path = tmp_path / "declared.iirds"
    path.write_bytes(bytes(raw))
    return path


def test_a_declared_size_neither_switches_the_gate_on_nor_off(tmp_path):
    """The gate is on what came back, not on what the archive claimed.

    Both directions matter and only one of them was ever noticed. An entry
    claiming less than it holds turned the gate off and cost the payload to
    read. An entry claiming more than it holds turns it on, and would have a
    conformant package refused unread on a number its sender chose.
    """
    honest = b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"/>'
    inflated = _declaring(tmp_path, "content/topic1.xhtml", honest,
                          claim=MAX_CONTENT_BYTES * 2)
    refusals = [f for f in _findings(inflated)
                if "byte limit" in (f.violation.detail or "")]
    assert not refusals, "a small entry was refused on the size it declared"
