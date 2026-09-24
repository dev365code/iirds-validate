"""What this tool does with a document's encoding declaration.

Four states, and it used to tell two of them apart. A document whose
declaration and bytes agreed on a codec this tool cannot read was refused with
the codec's own words -- `can't decode byte 0xfc in position 297` -- which
named no repair. A document whose declaration was a lie was refused when the
bytes happened not to be UTF-8 and accepted in silence when they happened to
be: the asymmetry was the defect, because what is wrong with the file is the
same in both.

The silence was total. A package declaring `windows-1252` over UTF-8 bytes
produced a report byte-identical to the UTF-8 control once the digest and the
path were set aside -- measured, `difference keys: []`.

What decides the ambiguous case is not a round trip. UTF-8 bytes read as
cp1252 give `fÃ¼r` and encode back to the original bytes exactly, so a round
trip calls that document consistent and would put mojibake in the graph --
worse than today, where it is read as UTF-8 and comes out right. What tells
the three apart is whether the bytes are valid UTF-8 *and* carry a byte over
127: only then do the two readings differ, which is why an ASCII-only document
declaring a single-byte code page draws nothing. One declaring UTF-16 or an
EBCDIC page over those bytes reads as other text, and is refused.

No silent substitution, in any state: `errors="replace"` turns a document
nobody can read into one that parses and says something else.
"""
from __future__ import annotations

import zipfile

import pytest

import iirds
from iirds_validate import runner

BODY = ('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
        '         xmlns:iirds="https://iirds.tekom.de/iirds#">\n'
        '  <iirds:Package rdf:about="http://e/p">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:has-title>%s</iirds:has-title>\n'
        '  </iirds:Package>\n'
        '</rdf:RDF>\n')
GERMAN = "Bedienungsanleitung für Größe"
PLAIN = "Operating instructions"

#: declared encoding, the codec the bytes are actually in, the title
CONTROLS = {
    "declared 1252 and written in 1252": ("windows-1252", "cp1252", GERMAN),
    "declared 1252 and written in utf-8": ("windows-1252", "utf-8", GERMAN),
    "declared utf-8 and written in 1252": ("utf-8", "cp1252", GERMAN),
    "declared an encoding no codec answers to": ("x-nonesuch", "utf-8", GERMAN),
    "declared utf-8 and written in utf-8": ("utf-8", "utf-8", GERMAN),
    "declared 1252 and written in ascii": ("windows-1252", "utf-8", PLAIN),
}


def document(declared, codec, title):
    head = '<?xml version="1.0" encoding="%s"?>\n' % declared
    return (head + BODY % title).encode(codec)


def package(directory, name, raw):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/iirds+zip")
        archive.writestr("META-INF/metadata.rdf", raw)
    return path


def report_of(directory, state):
    declared, codec, title = CONTROLS[state]
    built = package(directory, "t.iirds", document(declared, codec, title))
    return runner.check(built).as_dict()


def findings_of(report):
    return sorted((f["rule"], f["severity"]) for f in report["findings"])


@pytest.mark.parametrize("state", sorted(CONTROLS), ids=sorted(CONTROLS))
def test_parse_metadata_answers_rather_than_raises(state, tmp_path):
    """The contract is `(graph, None)` or `(None, error)`, and one state
    raises `LookupError` out of the reader that decides whether the document
    is RDF/XML at all. `parse_metadata` is published; a caller of the library
    is told a string and handed an exception."""
    declared, codec, title = CONTROLS[state]
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF,
                                        document(declared, codec, title),
                                        base=iirds.PACKAGE_BASE)
    assert graph is not None or error, "neither a graph nor a reason"


def test_a_declaration_that_is_a_lie_is_not_silent(tmp_path):
    """The whole of the defect in one comparison.

    A package declaring `windows-1252` over UTF-8 bytes is a package whose
    declaration is false, and this tool reads it as UTF-8 and says nothing.
    Set the digest and the path aside and the report is the control's.
    """
    lie = report_of(tmp_path / "a", "declared 1252 and written in utf-8")
    control = report_of(tmp_path / "b", "declared utf-8 and written in utf-8")
    for report in (lie, control):
        for key in ("packageDigest", "package", "judgedBy"):
            report.pop(key, None)
    assert lie != control, (
        "a false encoding declaration produces the same report as a true one")


def test_a_document_this_tool_cannot_read_says_what_to_do(tmp_path):
    """`windows-1252` is a codec Python has and this tool refuses, with the
    codec's own sentence about a byte at an offset. A reader is told which
    byte and not what to do."""
    report = report_of(tmp_path, "declared 1252 and written in 1252")
    said = " ".join(str(f.get("detail", "")) + " " + str(f.get("fix", ""))
                    for f in report["findings"])
    assert "position" not in said or "utf-8" in said.lower(), said
    assert "windows-1252" in said, (
        "the refusal does not name the encoding the document declares: %s" % said)


def test_an_ascii_document_declaring_another_encoding_draws_nothing(tmp_path):
    """The condition that keeps this from firing on every conformant package
    that happens to declare a codepage: where every byte is under 128 the two
    readings are the same document, so there is nothing to report."""
    ascii_only = report_of(tmp_path / "a", "declared 1252 and written in ascii")
    control = report_of(tmp_path / "b", "declared utf-8 and written in utf-8")
    assert findings_of(ascii_only) == findings_of(control), (
        "an ASCII document declaring a codepage draws findings a UTF-8 one "
        "does not: %s against %s"
        % (findings_of(ascii_only), findings_of(control)))


@pytest.mark.parametrize("state", [
    "declared 1252 and written in 1252",
    "declared 1252 and written in utf-8",
    "declared an encoding no codec answers to",
])
def test_a_declaration_the_reader_reads_differently_is_refused(tmp_path, state):
    """Refused where the declaration and this reader are two readings of the
    file, whatever made them differ.

    One of these three was decided by the bytes instead. rdflib decodes as
    UTF-8 whatever the declaration says and fails on the first byte above
    0x7F, so `windows-1252` over German text was refused while the same
    declaration over UTF-8 bytes -- a declaration that is simply false --
    decoded, parsed and passed. The refusal was never about the declaration;
    it was a decode error, and it caught the honest document and missed the
    lying one.

    The ASCII case is deliberately not here. Where every byte is under 128
    the two readings are the same text, and
    `test_an_ascii_document_declaring_another_encoding_draws_nothing` holds
    that they stay silent -- a first version of this rule refused them and
    would have failed conformant packages that declare a codepage and say
    nothing but English.
    """
    report = report_of(tmp_path, state)
    fired = {f["rule"] for f in report["findings"]}
    assert "C16.1" in fired, (
        "declared %r and this was not refused: %s"
        % (CONTROLS[state][0], sorted(fired)))
    assert not report["ok"], report["ok"]

    said = " ".join(str(f.get("detail", "")) + " " + str(f.get("fix", ""))
                    for f in report["findings"])
    assert CONTROLS[state][0] in said, (
        "the refusal does not name the declaration it refused: %s" % said)


# ---------------------------------------------------------------------------
# What a declaration may make this reader do. The first version decoded the
# whole document under whatever the declaration named, printed the name as
# written, stopped short of a byte order mark, and took `<?xml-stylesheet` for
# a declaration.
# ---------------------------------------------------------------------------

def _parsed(raw):
    return iirds.parse_metadata(iirds.METADATA_RDF, raw, base=iirds.PACKAGE_BASE)


def test_an_encoding_outside_the_ones_read_here_is_refused_unread():
    """punycode's decoder takes time that grows with the square of its input,
    and decoding under the declared name put that cost in the sender's hands.
    A name outside the encodings this reader decodes is refused by name, with
    nothing decoded."""
    import time

    body = "<!-- %s -->\n%s" % ("ab" * 200000, BODY % PLAIN)
    raw = ('<?xml version="1.0" encoding="punycode"?>\n' + body).encode("ascii")
    started = time.monotonic()
    graph, error = _parsed(raw)
    assert time.monotonic() - started < 1.0
    assert graph is None and "punycode" in error, error


@pytest.mark.parametrize("declared", ["shift_jis", "gb18030", "big5", "euc-jp", "utf-7",
                                      "idna", "undefined", "rot13", "mbcs", "x\x00y"])
def test_parse_metadata_answers_whatever_is_declared(declared):
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + BODY % PLAIN).encode("ascii")
    graph, error = _parsed(raw)
    assert graph is None and error, declared


def test_the_declared_name_reaches_the_report_as_printable_text():
    """A name is printed in the report; one that carried a terminal escape or
    a line break wrote a line of its own there."""
    declared = "x\x1b[31mRED\x1b[0m\nC16.1 forged"
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + BODY % PLAIN).encode("ascii")
    graph, error = _parsed(raw)
    assert graph is None
    assert "\x1b" not in error and "\n" not in error, repr(error)
    graph, error = _parsed(('<?xml version="1.0" encoding="%s"?>\n' % ("x" * 100000)
                            + BODY % PLAIN).encode("ascii"))
    assert graph is None and len(error) < 200, len(error)


def test_a_false_declaration_behind_a_byte_order_mark_is_refused():
    """An editor saving "UTF-8 with BOM" writes the mark in front of a
    declaration it did not change; xml.etree follows the declaration."""
    raw = b"\xef\xbb\xbf" + document("windows-1252", "utf-8", GERMAN)
    graph, error = _parsed(raw)
    assert graph is None and iirds.UNUSED_ENCODING in error, error


def test_a_stylesheet_instruction_is_not_a_declaration():
    raw = ('<?xml-stylesheet type="text/xsl" href="x.xsl" encoding="windows-1252"?>\n'
           + BODY % GERMAN).encode("utf-8")
    graph, error = _parsed(raw)
    assert error is None and graph is not None, error


#: Names a document may declare, and what may stand in front of its document
#: type declaration. The parser under the graph reads every one of these
#: documents as UTF-8, and the checks before it have to read the same text.
AS_THE_PARSER_READS = [(declared, prolog)
                       for declared in ("utf8", "UTF_8", "u-t-f-8", "cp1361", "cp864",
                                        "windows-1252", "latin-1", "utf-16", "x-nonesuch")
                       for prolog in ("", "<!-- Gr\u00f6\u00dfe -->\n")]


def _declaring(declared, prolog, subset, body):
    return ('<?xml version="1.0" encoding="%s"?>\n%s<!DOCTYPE rdf:RDF [%s]>\n'
            % (declared, prolog, subset) + body).encode("utf-8")


@pytest.mark.parametrize("declared, prolog", AS_THE_PARSER_READS)
def test_the_entity_guard_reads_what_the_parser_reads(declared, prolog):
    """The guard's answer is about the text rdflib parses, whatever the
    document declares; followed to the declaration, it answered about other
    text."""
    from iirds import _metadata

    raw = _declaring(declared, prolog, '<!ENTITY t "Operating instructions">', BODY % "&t;")
    assert _metadata._declares_entities(_metadata._decode(raw)) is True, (declared, prolog)
    graph, error = _parsed(raw)
    assert graph is None and error, (declared, prolog)


@pytest.mark.parametrize("declared, prolog", AS_THE_PARSER_READS)
def test_the_document_element_is_the_one_the_parser_reads(declared, prolog):
    from iirds import _metadata

    raw = _declaring(declared, prolog, "", "<manual><title>x</title></manual>\n")
    assert _metadata._document_element(_metadata._decode(raw)) == "manual", (declared, prolog)
    graph, error = _parsed(raw)
    assert graph is None and error, (declared, prolog)


def test_a_name_longer_than_any_codecs_is_refused_unread():
    """Asking for a codec costs time with the length of its name, and one
    this long can only be refused; it is, before any codec is asked, even
    where it would come to a codec's name."""
    declared = "latin" + "-" * 60 + "1"
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + BODY % PLAIN).encode("ascii")
    graph, error = _parsed(raw)
    assert graph is None and iirds.UNREADABLE_ENCODING in error, error


@pytest.mark.parametrize("declared", ["ANSI_X3.4-1968", "cp65001", "macintosh", "TIS-620"])
def test_a_single_byte_name_over_ascii_passes(declared):
    """ASCII's own IANA name, UTF-8's Windows one, and two single-byte pages
    a list of names refused."""
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + BODY % PLAIN).encode("ascii")
    graph, error = _parsed(raw)
    assert error is None and graph is not None, error


def test_the_remedy_followed_passes():
    """C16.1 says: write the file as UTF-8 and make the declaration say so.
    Rewriting the bytes and leaving `windows-1252` in front of them is two
    readings of one file, and stays refused."""
    from iirds_validate.registry import all_rules

    fix = next(rule.fix for rule in all_rules() if rule.id == "C16.1")
    assert "declaration say UTF-8" in fix, fix
    rewritten = document("windows-1252", "utf-8", GERMAN)
    assert _parsed(rewritten)[0] is None
    declared_too = rewritten.replace(b'encoding="windows-1252"', b'encoding="UTF-8"')
    assert _parsed(declared_too)[1] is None
