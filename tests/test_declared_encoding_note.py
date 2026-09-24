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

import pytest

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


def test_a_file_that_says_utf8_and_is_not_is_told_so_rather_than_accused(tmp_path):
    """The commonest one in the field, and the one the first fix stepped over.

    An editor saves in the platform's encoding and leaves the declaration
    alone, so the document says `utf-8` and its bytes are windows-1252. The
    note about the declaration was suppressed for exactly that value -- there
    was nothing to correct, the reasoning went, since the reader decodes as
    UTF-8 anyway -- and suppressing it puts the reader in the other branch of
    the remedy: no encoding named, so the bytes were damaged in transit, so
    send the file again. It arrives identical. What the reader needs is the
    contradiction: the file says UTF-8 and is not, and re-saving it as UTF-8
    is the whole repair.
    """
    body = DECLARED.replace('encoding="windows-1252"', 'encoding="utf-8"')
    package = _package(tmp_path, body.encode("windows-1252"), "lying.iirds")
    report = runner.run(package, runner.ALL_KINDS)
    said = [f for f in report.findings if f.rule.id == "C16.1"]
    assert said, sorted({f.rule.id for f in report.findings})
    detail = said[0].violation.detail or ""
    # Not `"utf-8" in detail`: the codec puts its own name in every decode
    # error it raises, so that assertion passed against the defect. The note
    # is what is being asked for, and the note says "declares".
    assert "declares" in detail, (
        "the reader is not told the file declares the encoding it fails to be: %r" % detail)


#: Declarations this reader refuses before any parser sees the document, by
#: name: a multi-byte encoding it does not decode, and one no codec answers
#: to. They were exceptions once, and neither a `UnicodeDecodeError`: the first
#: version of the note looked for that word, a supplier in Japan or China got
#: no note, and with no note the remedy sent them to the branch that asks for
#: the file to be sent again.
RAISING = {"shift_jis": "does not read", "euc-jp": "does not read", "bogus-9": "does not read"}


@pytest.mark.parametrize("declared", sorted(RAISING))
def test_a_declaration_this_reader_cannot_use_is_named(tmp_path, declared):
    body = DECLARED.replace('encoding="windows-1252"', 'encoding="%s"' % declared)
    package = _package(tmp_path, body.encode("ascii", "replace"), "raises.iirds")
    said = [f for f in runner.run(package, runner.ALL_KINDS).findings if f.rule.id == "C16.1"]
    assert said, "the document was refused and nothing reported it"
    detail = said[0].violation.detail or ""
    assert RAISING[declared] in detail, detail
    assert "declares" in detail, (
        "the reader is not told which declaration was refused: %r" % detail)


def test_an_error_that_merely_mentions_a_codec_gains_no_note(tmp_path):
    """The converse, and the reason the test is not a search for words.

    `rdf:ID="codec can"` is a vocabulary error in a document that decoded
    perfectly. The first version of this check searched the error text for
    "codec can", so the package's own bad name put a sentence about encodings
    into a finding that has nothing to do with them.
    """
    body = ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            'xmlns:iirds="http://iirds.tekom.de/iirds#">\n'
            '  <iirds:Package rdf:ID="codec can"/>\n</rdf:RDF>\n')
    package = _package(tmp_path, body.encode("utf-8"), "ncname.iirds")
    said = [f for f in runner.run(package, runner.ALL_KINDS).findings if f.rule.id == "C16.1"]
    assert said, "the document was refused and nothing reported it"
    assert "declares" not in (said[0].violation.detail or ""), said[0].violation.detail


def test_a_syntax_error_in_a_utf8_document_gains_no_note(tmp_path):
    """The other control: a declaration is not what is wrong here."""
    body = '<?xml version="1.0" encoding="utf-8"?>\n<rdf:RDF'
    package = _package(tmp_path, body.encode("utf-8"), "syntax.iirds")
    said = [f for f in runner.run(package, runner.ALL_KINDS).findings if f.rule.id == "C16.1"]
    assert said and "declares" not in (said[0].violation.detail or ""), said


def test_a_stylesheet_instruction_is_not_named_as_a_declaration(tmp_path):
    """The note names a declaration; `<?xml-stylesheet ... encoding=...?>` in a
    document that declares nothing is not one."""
    body = ('<?xml-stylesheet type="text/xsl" href="x.xsl" encoding="windows-1252"?>\n'
            + DECLARED.split("?>", 1)[1])
    package = _package(tmp_path, body.encode("cp1252"), "pi.iirds")
    said = [f for f in runner.run(package, runner.ALL_KINDS).findings if f.rule.id == "C16.1"]
    assert said, "a document that is not UTF-8 was not refused"
    assert "declares encoding" not in (said[0].violation.detail or ""), said[0].violation.detail
