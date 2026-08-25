"""Container rules — the ZIP itself."""
from __future__ import annotations

from conftest import MIMETYPE, MINIMAL_RDF
from iirds_validate import runner
from iirds_validate.model import METADATA_RDF


def ids(report):
    return {f.rule.id for f in report.findings}


def test_clean_package_passes(make_package):
    report = runner.check(make_package())
    assert report.ok, [f.violation.message for f in report.findings]


def test_wrong_extension(make_package):
    assert "C3" in ids(runner.check(make_package(name="test.zip")))


def test_missing_mimetype(make_package):
    assert "C4" in ids(runner.check(make_package(mimetype=None)))


def test_mimetype_with_trailing_newline(make_package):
    assert "C5" in ids(runner.check(make_package(mimetype=b"application/iirds+zip\n")))


def test_mimetype_must_be_first_and_stored(make_package):
    assert "C6" in ids(runner.check(make_package(mimetype_first=False)))
    assert "C6" in ids(runner.check(make_package(mimetype_stored=False)))


def test_missing_metadata(make_package):
    assert "C8" in ids(runner.check(make_package(metadata=None)))


def test_content_in_root_is_rejected(make_package):
    """C11.1 owns the root; C12 owns META-INF. .xhtml counts as content even
    though the reference tool's pattern misses it — see container.py."""
    report = runner.check(make_package(content=("stray.xhtml",)))
    assert "C11.1" in ids(report)


def test_broken_xml_is_reported_not_crashed(make_package):
    report = runner.check(make_package(metadata="<rdf:RDF><unclosed>"))
    assert "C16.1" in ids(report)
    assert not report.ok


def test_undecodable_metadata_is_reported_not_crashed(make_package):
    """The other way a metadata document fails to be read.

    A byte order mark says which codec applies and the bytes then have to
    survive it; a transfer cut short is enough that they do not. That decode
    was the one step in the SDK's reader outside a try, so it raised through
    a function whose contract is (graph, None) or (None, error) -- and out of
    this tool as a traceback, on a 733-byte container. Nothing hostile is
    needed: a supplier saving as utf-16 and a truncated copy will do.
    """
    from conftest import MINIMAL_RDF
    truncated = (b"\xff\xfe" + MINIMAL_RDF.encode("utf-16-le"))[:-1]
    report = runner.check(make_package(metadata=truncated))
    assert "C16.1" in ids(report)
    assert "S2" in ids(report), "no graph rule could run; that has to be said"
    assert not report.ok


def _entry_name_that_is_not_utf8(tmp_path):
    """An archive whose entry name claims to be UTF-8 and is not.

    Bit 11 of the general purpose flag says "this name is UTF-8", so
    `zipfile` decodes it strictly and raises. Nothing in the ZIP format
    stops a supplier setting the bit over other bytes.
    """
    import io
    import struct
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, MIMETYPE)
        archive.writestr(METADATA_RDF, MINIMAL_RDF)
        archive.writestr("content/AAA.txt", b"x")
    raw = bytearray(buf.getvalue())
    for signature, flag_at, name_at, len_at in ((b"PK\x03\x04", 6, 30, 26),
                                                (b"PK\x01\x02", 8, 46, 28)):
        at = 0
        while True:
            at = raw.find(signature, at)
            if at < 0:
                break
            length = struct.unpack_from("<H", raw, at + len_at)[0]
            if b"AAA" in bytes(raw[at + name_at:at + name_at + length]):
                raw[at + name_at + 8] = 0xFF
                struct.pack_into("<H", raw, at + flag_at,
                                 struct.unpack_from("<H", raw, at + flag_at)[0] | 0x800)
            at += 4
    path = tmp_path / "badname.iirds"
    path.write_bytes(bytes(raw))
    return path


def test_an_undecodable_entry_name_is_reported_not_crashed(tmp_path):
    """The other end of "no package may end a run before a rule has run".

    That guard was put on the parse and not on the open, so a container
    whose entry name is not the encoding it declares took the whole run
    with it -- a traceback out of `zipfile`, before any rule existed to
    report anything. The reader was never involved.
    """
    report = runner.check(_entry_name_that_is_not_utf8(tmp_path))
    assert "C1" in ids(report), sorted(ids(report))
    assert not report.ok


def test_not_a_zip(tmp_path):
    path = tmp_path / "broken.iirds"
    path.write_bytes(b"this is not a zip file")
    report = runner.check(path)
    assert "C1" in ids(report)
    assert not report.ok
