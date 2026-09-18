"""A metadata file this reader will not decode is not a damaged file.

`metadata.rdf` declaring `encoding="windows-1252"` is refused, and refusing is
defensible: XML 1.0 requires a processor to support UTF-8 and UTF-16 and
nothing else, and rdflib decodes as UTF-8 whatever the declaration says. What
is not defensible is what the reader was told -- that an encoding error means
"the bytes were damaged or cut short in transit and the file has to be sent
again". Those bytes are intact: `xml.etree`, in the same interpreter, parses
the same document and finds its elements. Sending it again delivers the same
file, and the remedy a reader can act on is to write it as UTF-8.

Found by running a real third-party package against this tool.
"""
from __future__ import annotations

import zipfile

from conftest import MIMETYPE
from iirds_validate import runner

DECLARED = ('<?xml version="1.0" encoding="windows-1252"?>\n'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            'xmlns:iirds="http://iirds.tekom.de/iirds#">\n'
            '  <iirds:Package rdf:about="urn:p">'
            '<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>'
            '<iirds:title>Gr\xfc\xdfe</iirds:title></iirds:Package>\n'
            '</rdf:RDF>\n')


def _package(tmp_path, body: bytes, name="encoded.iirds"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        first = zipfile.ZipInfo("mimetype")
        first.compress_type = zipfile.ZIP_STORED
        archive.writestr(first, MIMETYPE)
        archive.writestr("META-INF/metadata.rdf", body)
        archive.writestr("content/topic1.xhtml", b"<html/>")
    return path


def test_the_bytes_are_not_damaged_and_a_parser_reads_them(tmp_path):
    """The premise, held here so the finding below cannot drift away from it."""
    from xml.etree import ElementTree

    root = ElementTree.fromstring(DECLARED.encode("windows-1252"))
    assert len(list(root.iter())) == 4, "the fixture must be a document that parses"


def test_a_declared_encoding_is_reported_as_the_encoding_it_declares(tmp_path):
    package = _package(tmp_path, DECLARED.encode("windows-1252"))
    report = runner.run(package, runner.ALL_KINDS)
    said = [f for f in report.findings if f.rule.id == "C16.1"]
    assert said, sorted({f.rule.id for f in report.findings})
    detail = said[0].violation.detail or ""
    assert "windows-1252" in detail, (
        "the reader is not told which encoding the document declares: %r" % detail)


def test_the_remedy_does_not_tell_a_reader_to_resend_an_intact_file(tmp_path):
    """The remedy is what a reader acts on, and acting on this one achieves
    nothing: the file arrives identical."""
    package = _package(tmp_path, DECLARED.encode("windows-1252"))
    report = runner.run(package, runner.ALL_KINDS)
    remedy = next(f.rule.fix for f in report.findings if f.rule.id == "C16.1")
    assert "write it as UTF-8" in remedy or "as UTF-8" in remedy, (
        "the remedy does not name the one thing that fixes this package")


def test_utf8_metadata_is_unaffected(tmp_path):
    """The control: the ordinary case must not gain a finding."""
    report = runner.run(_package(tmp_path, DECLARED.replace(
        'encoding="windows-1252"', 'encoding="utf-8"').encode("utf-8")), runner.ALL_KINDS)
    assert not [f for f in report.findings if f.rule.id == "C16.1"], sorted(
        {f.rule.id for f in report.findings})
