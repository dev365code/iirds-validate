"""The XML declaration, read once, by the grammar that defines it.

XML 1.0 (fifth edition), section 2.8 and the productions it names:

    [23] XMLDecl      ::= '<?xml' VersionInfo EncodingDecl? SDDecl? S? '?>'
    [24] VersionInfo  ::= S 'version' Eq ("'" VersionNum "'" | '"' VersionNum '"')
    [25] Eq           ::= S? '=' S?
    [26] VersionNum   ::= '1.' [0-9]+
    [32] SDDecl       ::= S 'standalone' Eq (("'" ('yes' | 'no') "'") | ('"' ('yes' | 'no') '"'))
    [80] EncodingDecl ::= S 'encoding' Eq ('"' EncName '"' | "'" EncName "'" )
    [81] EncName      ::= [A-Za-z] ([A-Za-z0-9._] | '-')*
     [3] S            ::= (#x20 | #x9 | #xD | #xA)+

The checks before the parser read the declaration to hold it against the
document's first bytes, and the decode after them removes it. One pattern did
the reading and another the removing, and they disagreed: a declaration giving
`encoding` before `version`, or twice, had an encoding removed that the check
had never read. Behind a byte order mark the parser saw only what was left, so
a declaration the grammar does not allow, contradicting the mark as well,
passed. Both now use one reading, and a declaration the grammar does not allow
is refused whatever stands in front of it.
"""
from __future__ import annotations

import re
import xml.parsers.expat as expat

import pytest

import iirds
from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

BODY = MINIMAL_RDF.split("\n", 1)[1]

#: How a document is stored: what stands in front of it, the codec of the
#: rest, and the name of that encoding a declaration agrees with.
FORMS = {
    "utf-8": (b"", "utf-8", "UTF-8"),
    "utf-8 marked": (b"\xef\xbb\xbf", "utf-8", "UTF-8"),
    "utf-16le marked": (b"\xff\xfe", "utf-16-le", "UTF-16"),
    "utf-16be marked": (b"\xfe\xff", "utf-16-be", "UTF-16"),
    "utf-32le marked": (b"\xff\xfe\x00\x00", "utf-32-le", "UTF-32"),
    "utf-32be marked": (b"\x00\x00\xfe\xff", "utf-32-be", "UTF-32"),
    "utf-16le unmarked": (b"", "utf-16-le", "UTF-16LE"),
    "utf-16be unmarked": (b"", "utf-16-be", "UTF-16BE"),
}


def stored(form, declaration):
    mark, codec, own = FORMS[form]
    return mark + (declaration.format(name=own, lower=own.lower()) + "\n" + BODY).encode(codec)


def parsed(raw):
    return iirds.parse_metadata(iirds.METADATA_RDF, raw, base=iirds.PACKAGE_BASE)


#: Declarations production [23] allows, in every form they can take here.
VALID = {
    "double quotes": '<?xml version="1.0" encoding="{name}"?>',
    "single quotes": "<?xml version='1.0' encoding='{name}'?>",
    "one of each quote": "<?xml version=\"1.0\" encoding='{name}'?>",
    "standalone yes": '<?xml version="1.0" encoding="{name}" standalone="yes"?>',
    "standalone no in single quotes": "<?xml version='1.0' encoding='{name}' standalone='no'?>",
    "tabs for white space": '<?xml\tversion="1.0"\tencoding="{name}"\t?>',
    "line ends for white space": '<?xml\r\nversion="1.0"\nencoding="{name}"\r?>',
    "white space around Eq": '<?xml version = "1.0" encoding =\t"{name}" ?>',
    "white space several at a time": '<?xml   version="1.0"    encoding="{name}"   ?>',
    "white space before ?>": '<?xml version="1.0" encoding="{name}" ?>',
    "the name in lower case": '<?xml version="1.0" encoding="{lower}"?>',
}

#: Declarations it does not, each with the production it breaks.
MALFORMED = {
    "encoding before version": ('<?xml encoding="{name}" version="1.0"?>', "[23]"),
    "encoding twice": ('<?xml version="1.0" encoding="{name}" encoding="{name}"?>', "[23]"),
    "version twice": ('<?xml version="1.0" version="1.0" encoding="{name}"?>', "[23]"),
    "standalone before encoding": ('<?xml version="1.0" standalone="yes" encoding="{name}"?>',
                                   "[23]"),
    "no version": ('<?xml encoding="{name}"?>', "[23]"),
    "nothing at all": ("<?xml ?>", "[23]"),
    "a pseudo-attribute XML has not got": ('<?xml version="1.0" encoding="{name}" lang="en"?>',
                                           "[23]"),
    "no ?> at the end": ('<?xml version="1.0" encoding="{name}">', "[23]"),
    "no Eq": ('<?xml version "1.0" encoding="{name}"?>', "[25]"),
    "a version without quotes": ('<?xml version=1.0 encoding="{name}"?>', "[24]"),
    "no white space before encoding": ('<?xml version="1.0"encoding="{name}"?>', "[80]"),
    "quotes that do not pair": ('<?xml version="1.0" encoding="{name}\'?>', "[80]"),
    "no white space before standalone": ('<?xml version="1.0" encoding="{name}"standalone="no"?>',
                                         "[32]"),
    "version 2.0": ('<?xml version="2.0" encoding="{name}"?>', "[26]"),
    "version 1": ('<?xml version="1" encoding="{name}"?>', "[26]"),
    "standalone Yes": ('<?xml version="1.0" encoding="{name}" standalone="Yes"?>', "[32]"),
    "a name that begins with a digit": ('<?xml version="1.0" encoding="8{name}"?>', "[81]"),
    "a name that begins with a space": ('<?xml version="1.0" encoding=" {name}"?>', "[81]"),
}


@pytest.mark.parametrize("form", sorted(FORMS))
@pytest.mark.parametrize("case", sorted(VALID))
def test_a_declaration_the_grammar_allows_is_read(form, case):
    graph, error = parsed(stored(form, VALID[case]))
    assert error is None and graph is not None, (form, case, error)


@pytest.mark.parametrize("form", sorted(FORMS))
@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_a_declaration_the_grammar_does_not_allow_is_refused_whatever_is_in_front(form, case):
    """Section 2.8 makes the XML declaration production [23]; a document whose
    declaration does not match it is not well-formed, which is a fatal error
    whether or not a byte order mark comes first."""
    declaration, production = MALFORMED[case]
    graph, error = parsed(stored(form, declaration))
    assert graph is None and iirds.MALFORMED_DECLARATION in error, (form, case, error)
    assert production in error, (form, case, error)


@pytest.mark.parametrize("case", sorted(VALID))
def test_expat_reads_each_declaration_the_grammar_allows(case):
    """The grammar above is expat's as well: stored as UTF-8 with nothing in
    front, where expat reads the declaration itself, each of these parses."""
    expat.ParserCreate().Parse(stored("utf-8", VALID[case]), True)


#: Two that expat reads although production [26] does not allow them: it
#: does not check VersionNum (libxml2 refuses both). The check in front of
#: the parser holds them, since the parser will not.
VERSIONS_EXPAT_READS = {"version 2.0", "version 1"}


@pytest.mark.parametrize("case", sorted(set(MALFORMED) - VERSIONS_EXPAT_READS))
def test_expat_refuses_each_declaration_the_grammar_does_not_allow(case):
    with pytest.raises(expat.ExpatError):
        expat.ParserCreate().Parse(stored("utf-8", MALFORMED[case][0]), True)


@pytest.mark.parametrize("case", sorted(VERSIONS_EXPAT_READS))
def test_a_version_the_grammar_does_not_allow_fails_the_package(case, tmp_path):
    report = runner.check(build_package(tmp_path, metadata=stored("utf-8", MALFORMED[case][0])))
    refused = [f for f in report.findings if f.rule.id == "C16.1"]
    assert refused and not report.ok, (case, sorted({f.rule.id for f in report.findings}))
    assert "[26] VersionNum" in refused[0].violation.detail, refused[0].violation.detail


#: The documents that passed: a declaration the grammar does not allow, behind
#: a mark or in unmarked UTF-16, whose encoding the decode removed unread.
#: (stored as, the declaration)
PASSED_UNREAD = {
    "E31": ("utf-8 marked", '<?xml encoding="UTF-8" version="1.0"?>'),
    "E32": ("utf-16le marked", '<?xml encoding="UTF-16" version="1.0"?>'),
    "E35": ("utf-8 marked", '<?xml version="1.0" standalone="yes" encoding="UTF-8"?>'),
    "E37": ("utf-16le marked", '<?xml encoding="UTF-8" version="1.0"?>'),
    "E38": ("utf-8 marked", '<?xml encoding="ISO-8859-1" version="1.0"?>'),
    "E41": ("utf-16le unmarked", '<?xml encoding="UTF-16BE" version="1.0"?>'),
    "E45": ("utf-16le marked", '<?xml version="1.0" encoding="UTF-16" encoding="UTF-8"?>'),
    "E46": ("utf-8 marked", '<?xml version="1.0" encoding="UTF-8" encoding="ISO-8859-1"?>'),
}


@pytest.mark.parametrize("case", sorted(PASSED_UNREAD))
def test_a_package_whose_declaration_the_decode_removed_unread_fails(case, tmp_path):
    form, declaration = PASSED_UNREAD[case]
    report = runner.check(build_package(tmp_path, metadata=stored(form, declaration)))
    refused = [f for f in report.findings if f.rule.id == "C16.1"]
    assert refused and not report.ok, (case, sorted({f.rule.id for f in report.findings}))
    assert iirds.MALFORMED_DECLARATION in refused[0].violation.detail, refused[0].violation.detail


def test_the_same_contradiction_written_in_order_is_still_one():
    """The control for E38: its declaration in the order production [23]
    gives contradicts the mark, as it did."""
    graph, error = parsed(stored("utf-8 marked", '<?xml version="1.0" encoding="ISO-8859-1"?>'))
    assert graph is None and iirds.CONTRADICTED_ENCODING in error, error


@pytest.mark.parametrize("front", ["<!-- a comment -->", "<?xml-stylesheet href='x.xsl'?>", " "])
def test_a_declaration_after_anything_else_is_none(front):
    """A declaration stands first or not at all. With anything in front of it
    -- a comment, another processing instruction, white space -- the document
    declares nothing, and the `<?xml` that follows is the parser's to refuse."""
    raw = (front + '<?xml version="1.0" encoding="UTF-8"?>\n' + BODY).encode("utf-8")
    assert iirds.declared_encoding(raw) is None
    graph, error = parsed(raw)
    assert graph is None and error, error


def test_a_target_that_only_begins_with_xml_is_not_a_declaration():
    raw = ('<?xml-stylesheet type="text/xsl" href="x.xsl" encoding="windows-1252"?>\n'
           + BODY).encode("utf-8")
    assert iirds.declared_encoding(raw) is None
    assert parsed(raw)[1] is None


@pytest.mark.parametrize("target", ["xml\u05d0", "xml\u05ea"])
@pytest.mark.parametrize("form", ["utf-8", "utf-8 marked", "utf-16le marked"])
def test_an_instruction_whose_target_begins_with_xml_is_read(form, target):
    """A target that begins with `xml` and goes on is a name XML reserves and
    allows. Read without a mark, one character a byte, the first byte of a
    Hebrew letter is `×`, which no name holds, and the instruction was refused
    as a declaration the grammar does not allow."""
    raw = stored(form, "<?%s?>" % target)
    graph, error = parsed(raw)
    assert error is None and graph is not None, (form, error)
    assert iirds.declared_encoding(raw) is None


#: Each mark, with the codec of what follows it and the name agreeing with it.
MARKS = {"utf-8": (b"\xef\xbb\xbf", "utf-8", "UTF-8"),
         "utf-16le": (b"\xff\xfe", "utf-16-le", "UTF-16"),
         "utf-16be": (b"\xfe\xff", "utf-16-be", "UTF-16"),
         "utf-32le": (b"\xff\xfe\x00\x00", "utf-32-le", "UTF-32")}


@pytest.mark.parametrize("declaration", ["", '<?xml version="1.0"?>\n',
                                         '<?xml version="1.0" encoding="{own}"?>\n',
                                         '<?xml version="1.0" encoding="ISO-8859-1"?>\n'])
@pytest.mark.parametrize("form", sorted(MARKS))
def test_a_second_byte_order_mark_is_a_character_the_document_is_refused_for(form, declaration,
                                                                            tmp_path):
    """A byte order mark is a signature once. Behind it U+FEFF is a character,
    and nothing lets one stand before the declaration or the document element.
    Decoded and written again as UTF-8 it read as a mark, and a declaration
    behind it, ISO-8859-1 behind a UTF-16 mark among them, passed unheld."""
    mark, codec, own = MARKS[form]
    raw = mark + ("\ufeff" + declaration.format(own=own) + BODY).encode(codec)
    graph, error = parsed(raw)
    assert graph is None and error, (form, declaration)
    assert iirds.declared_encoding(raw) is None
    assert not runner.check(build_package(tmp_path, metadata=raw)).ok


@pytest.mark.parametrize("front", [" ", "<!-- a comment -->", "\ufeff"])
def test_a_declaration_out_of_place_behind_a_utf32_mark_is_not_called_absent(front):
    """It declares UTF-32, where nothing lets a declaration stand. Refused
    still, as UTF-32 that no encoding declaration begins, and the remedy
    puts the declaration at its start, where it was said to declare nothing."""
    raw = stored("utf-32le marked", front + '<?xml version="1.0" encoding="UTF-32"?>')
    graph, error = parsed(raw)
    assert graph is None and iirds.UNDECLARED_ENCODING in error, error
    assert "no encoding declaration begins it" in error and "at its start" in error, error


@pytest.mark.parametrize("declaration, production, character", [
    ('<?xml version="1.0" encoding="a>b"?>', "[81] EncName", ">"),
    ('<?xml version="1.0" encoding="a?>b"?>', "[81] EncName", "?"),
    ('<?xml version="1.0>" encoding="{name}"?>', "[26] VersionNum", ">"),
    ('<?xml version="1.0" encoding="{name}" standalone="y>es"?>', "[32] SDDecl", ">"),
])
def test_a_value_the_first_close_cuts_is_refused_for_what_it_holds(declaration, production,
                                                                   character):
    """A declaration is read as far as the first `>`, since none holds one
    before its `?>`. A value holding one had its closing quote beyond it, and
    was said to have none; it holds a character its production does not
    allow, and that is the reason."""
    graph, error = parsed(stored("utf-8", declaration))
    assert graph is None and iirds.MALFORMED_DECLARATION in error, error
    assert "%s does not allow %s in the value" % (production, character) in error, error


@pytest.mark.parametrize("declaration, production", [
    ('<?xml version="1.0"\u00a0encoding="{name}"?>', "[3] S"),
    ('<?xml version="1.0" encoding="{name}"\u3000?>', "[3] S"),
    ('<?xml version="1.0"\x0cencoding="{name}"?>', "[3] S"),
    ('<?xml version\u00a0="1.0" encoding="{name}"?>', "[25] Eq"),
    ('<?xml Version="1.0" encoding="{name}"?>', "[24] VersionInfo"),
    ('<?xml version="1.0" ENCODING="{name}"?>', "[80] EncodingDecl"),
    ('<?xml version="1.0" encoding="{name}" Standalone="no"?>', "[32] SDDecl"),
])
def test_what_stops_a_declaration_is_named_by_the_production_it_breaks(declaration, production):
    """White space that is not XML's, and a pseudo-attribute in another case,
    were reported as pseudo-attributes production [23] has not got."""
    graph, error = parsed(stored("utf-8 marked", declaration))
    assert graph is None and iirds.MALFORMED_DECLARATION in error, error
    assert "production %s" % production in error and "no pseudo-attribute" not in error, error


def test_an_empty_name_is_shown_as_one():
    graph, error = parsed(stored("utf-8", '<?xml version="1.0" encoding=""?>'))
    assert graph is None and error.endswith("[81] EncName does not allow the name ''"), error


@pytest.mark.parametrize("form", sorted(FORMS))
def test_the_name_read_is_the_one_declared(form):
    raw = stored(form, "<?xml version='1.0'\tencoding = '{lower}' standalone='no'?>")
    assert iirds.declared_encoding(raw) == FORMS[form][2].lower()


# ---------------------------------------------------------------------------
# Which names are read. Section 4.3.3: a processor "SHOULD match character
# encoding names in a case-insensitive way and SHOULD either interpret an
# IANA-registered name as the encoding registered at IANA for that name or
# treat it as unknown". The registered names and aliases of UTF-8, UTF-16 and
# UTF-32 are read as what IANA registers them as. A spelling IANA does not
# register is read only if both processors a consumer is likely to have read
# it; measured on expat 2.6.1 and libxml2 2.9.14, with text in which a
# misreading shows, expat reads none, so none is.
# ---------------------------------------------------------------------------

#: (stored as, the alias IANA registers beside the name of its encoding)
ALIASES = [("utf-8", "csUTF8"), ("utf-8 marked", "csUTF8"),
           ("utf-16le marked", "csUTF16"), ("utf-16be marked", "csUTF16"),
           ("utf-16le marked", "csUTF16LE"), ("utf-16be marked", "csUTF16BE"),
           ("utf-16le unmarked", "csUTF16LE"), ("utf-16le marked", "csUnicode"),
           ("utf-32le marked", "csUTF32"), ("utf-32be marked", "csUTF32BE"),
           ("utf-32le marked", "csUCS4")]


@pytest.mark.parametrize("form, alias", ALIASES, ids=["%s %s" % pair for pair in ALIASES])
def test_an_alias_iana_registers_is_read_as_its_name(form, alias, tmp_path):
    """E14 among them: `csUTF16` behind a UTF-16LE mark was refused as a name
    this reader does not read."""
    raw = stored(form, '<?xml version="1.0" encoding="%s"?>' % alias)
    graph, error = parsed(raw)
    assert error is None and graph is not None, (form, alias, error)
    assert runner.check(build_package(tmp_path, metadata=raw)).ok


#: (stored as, a spelling IANA does not register)
SPELLINGS = [("utf-8", "utf8"), ("utf-8", "UTF_8"), ("utf-8", "utf--8"),
             ("utf-8 marked", "utf8"), ("utf-8 marked", "utf_8"),
             ("utf-16le marked", "utf16"), ("utf-16be marked", "UTF_16"),
             ("utf-16le marked", "UTF-16-LE"), ("utf-16le unmarked", "utf16le"),
             ("utf-32le marked", "utf32"), ("utf-32le marked", "UTF_32LE")]


@pytest.mark.parametrize("form, spelling", SPELLINGS, ids=["%s %s" % pair for pair in SPELLINGS])
def test_a_spelling_iana_does_not_register_is_refused_by_name(form, spelling, tmp_path):
    """E42 and E43 among them: `utf8` behind a UTF-8 mark was read, and
    `utf16` behind a UTF-16 one refused. Both are refused now, for the same
    reason, with or without a mark."""
    raw = stored(form, '<?xml version="1.0" encoding="%s"?>' % spelling)
    graph, error = parsed(raw)
    assert graph is None and iirds.UNREADABLE_ENCODING in error, (form, spelling, error)
    assert "not an IANA-registered encoding name" in error and spelling in error, error
    assert not runner.check(build_package(tmp_path, metadata=raw)).ok


@pytest.mark.parametrize("declared", ["cp65001", "u8", "utf", "utf-8-sig", "utf8_ucs2"])
def test_a_name_python_reads_as_utf8_and_iana_does_not_register_is_refused(declared):
    """Python answers to each of these with its UTF-8 codec, and passed them
    as UTF-8 over UTF-8 bytes; neither expat nor libxml2 reads one of them."""
    graph, error = parsed(stored("utf-8", '<?xml version="1.0" encoding="%s"?>' % declared))
    assert graph is None and iirds.UNREADABLE_ENCODING in error, (declared, error)
    assert "not an IANA-registered encoding name" in error, error


# ---------------------------------------------------------------------------
# What the refusals say.
# ---------------------------------------------------------------------------

def test_a_declaration_out_of_order_behind_a_utf32_mark_is_refused_as_that():
    """E39: refused, and said to declare no encoding at all; it declares
    UTF-32, in a declaration production [23] does not allow."""
    graph, error = parsed(stored("utf-32le marked", '<?xml encoding="UTF-32" version="1.0"?>'))
    assert graph is None and iirds.MALFORMED_DECLARATION in error and "[23]" in error, error
    assert "declares no encoding" not in error, error


@pytest.mark.parametrize("form", ["utf-32le marked", "utf-32be marked"])
@pytest.mark.parametrize("declaration", ["", '<?xml version="1.0"?>'])
def test_utf32_behind_a_mark_declaring_nothing_breaks_a_must(form, declaration):
    """E20. Section 4.3.3 says an entity in an encoding other than UTF-8 or
    UTF-16 MUST begin with an encoding declaration -- an error, by section
    1.2 -- and makes a fatal error only of one that begins with neither a byte
    order mark nor a declaration. Refused still; said as the sentence that
    applies."""
    graph, error = parsed(stored(form, declaration))
    assert graph is None and iirds.UNDECLARED_ENCODING in error, error
    assert "MUST" in error and "1.2" in error and "fatal" not in error, error


@pytest.mark.parametrize("codec, said", [("utf-32-le", "UTF-32LE"), ("utf-32-be", "UTF-32BE")])
def test_unmarked_utf32_declaring_nothing_is_refused_for_its_encoding(codec, said):
    """E24: refused before, by the parser, as an invalid token. With neither a
    mark nor a declaration, section 4.3.3 makes an encoding other than UTF-8 a
    fatal error, and that is the reason given."""
    graph, error = parsed(BODY.encode(codec))
    assert graph is None and iirds.UNDECLARED_ENCODING in error, error
    assert said in error and "fatal error" in error and "4.3.3" in error, error


def test_unmarked_utf32_declaring_another_encoding_is_contradicted():
    raw = ('<?xml version="1.0" encoding="UTF-8"?>\n' + BODY).encode("utf-32-le")
    graph, error = parsed(raw)
    assert graph is None and iirds.CONTRADICTED_ENCODING in error and "UTF-32LE" in error, error


def test_utf16_declared_over_bytes_that_keep_ascii_is_a_contradiction():
    """E44: refused as a declaration this reader reads differently. Appendix F
    reads `3C 3F 78 6D` as UTF-8 or an encoding in which ASCII characters are
    ASCII bytes, so the bytes contradict the declaration, which section 4.3.3
    makes a fatal error."""
    graph, error = parsed(stored("utf-8", '<?xml version="1.0" encoding="UTF-16"?>'))
    assert graph is None and iirds.CONTRADICTED_ENCODING in error, error
    assert "appendix F" in error and "4.3.3" in error, error


@pytest.mark.parametrize("declared", ["UTF-8", "csUTF8"])
def test_the_note_on_a_decode_failure_names_the_declaration_the_grammar_reads(declared,
                                                                              tmp_path):
    """The C16.1 note names what the document declares, read by the same
    reading the checks use, single quotes and white space around Eq
    included -- and calls a declaration of UTF-8, by its name or by the alias
    IANA registers beside it, the contradiction it is."""
    raw = ("<?xml version='1.0' encoding = '%s'?>\n" % declared + BODY.replace(
        "Test package", "Größe")).encode("windows-1252")
    report = runner.check(build_package(tmp_path, metadata=raw))
    [finding] = [f for f in report.findings if f.rule.id == "C16.1"]
    assert "encoding=%r, which these bytes are not" % declared in finding.violation.detail, (
        finding.violation.detail)


@pytest.mark.parametrize("order", ["le", "be"])
@pytest.mark.parametrize("label", ["UTF-32", "csUTF32", "ISO-10646-UCS-4", "csUCS4",
                                   "UTF-32{order}", "csUTF32{order}"])
def test_unmarked_utf32_is_read_when_its_declaration_names_its_order(order, label, tmp_path):
    """XML 1.0 §4.3.3 and Appendix F.1: a matching declaration labels
    unmarked UCS-4; the no-BOM/no-declaration fatal condition does not apply.
    https://www.w3.org/TR/2008/REC-xml-20081126/#charencoding
    """
    declared = label.format(order=order.upper())
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + BODY).encode('utf-32-' + order)
    graph, error = parsed(raw)
    assert graph is not None and error is None, error
    report = runner.check(build_package(tmp_path, metadata=raw))
    assert report.ok, [(f.rule.id, f.violation.detail) for f in report.findings]


@pytest.mark.parametrize("declared,codec,accepted", [
    ("latin1", "latin-1", True), ("csISOLatin1", "latin-1", True),
    ("ISO-8859-1", "latin-1", True), ("windows-1252", "cp1252", True),
    ("cswindows1252", "cp1252", True), ("US-ASCII", "ascii", True),
    ("csASCII", "ascii", True), ("csUTF8", "utf-8", True),
    ("UTF-7", "utf-7", True), ("Shift_JIS", "shift_jis", True),
    ("GB18030", "gb18030", True), ("utf8", "utf-8", False),
    ("cp65001", "utf-8", False), ("cp1252", "utf-8", False),
    ("ascii", "utf-8", False), ("x-utf8", "utf-8", False),
])
def test_encoding_names_follow_the_complete_iana_registry(declared, codec, accepted):
    """XML 1.0 §4.3.3: name/alias membership is case insensitive, and a
    registered encoding may be read by its codec. IANA registry record 3
    names US-ASCII and csASCII, but not ASCII.
    https://www.iana.org/assignments/character-sets/character-sets.xhtml
    """
    title = "本文" if codec == "shift_jis" else "café"
    body = BODY if codec == "ascii" else BODY.replace("A topic", title)
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + body).encode(codec)
    graph, error = parsed(raw)
    if accepted:
        assert graph is not None and error is None, error
        if codec != "ascii":
            assert any(str(value) == title for value in graph.objects())
    else:
        assert graph is None and iirds.UNREADABLE_ENCODING in error, error
        assert "not an IANA-registered encoding name" in error and "4.3.3" in error


def test_a_registered_name_without_a_python_codec_is_unreadable():
    """XML 1.0 §4.3.3 permits treating an unsupported IANA name as unknown.
    The registry's ISO-10646-UTF-1 record has no Python text codec.
    """
    graph, error = parsed(stored("utf-8", '<?xml version="1.0" encoding="ISO-10646-UTF-1"?>'))
    assert graph is None and iirds.UNREADABLE_ENCODING in error
    assert "registered at IANA" in error and "no text codec" in error
    assert "XML 1.0 §4.3.3" in error
    assert "save as UTF-8 and update the declaration" in error


def test_every_registered_name_without_a_codec_has_a_cited_remedy():
    """XML 1.0 §4.3.3: unsupported registered names keep their refusal,
    identify that policy, and offer a supported reading with matching bytes.
    """
    from iirds import _metadata

    unsupported = [r["name"] for r in _metadata._CHARSETS
                   if _metadata._encoding_form(r["name"]) is None
                   and _metadata._codec_for(r["name"]) is None]
    assert "ISO-10646-UTF-1" in unsupported and "IBM1047" in unsupported
    for declared in unsupported:
        error = _metadata._unread(iirds.METADATA_RDF, declared)
        assert "XML 1.0 §4.3.3" in error, error
        assert "save as UTF-8 and update the declaration" in error, error
        raw = stored("utf-8", '<?xml version="1.0" encoding="%s"?>' % declared)
        graph, error = parsed(raw)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", declared):
            # Some IANA names contain ':' or '+', which EncName forbids.
            # XMLDecl syntax is judged before any codec is selected.
            assert graph is None and iirds.MALFORMED_DECLARATION in error, error
            continue
        assert graph is None and iirds.UNREADABLE_ENCODING in error, (declared, error)
        assert "registered at IANA" in error and "no text codec" in error, error
        assert "XML 1.0 §4.3.3" in error, error
        assert "supported registered encoding name with matching bytes" in error, error
        assert "save as UTF-8 and update the declaration" in error, error


@pytest.mark.parametrize("declared,codec", [
    ("IBM037", "cp037"), ("IBM500", "cp500"),
    ("IBM01140", "cp1140"), ("IBM273", "cp273"),
])
def test_ebcdic_declaration_selects_its_registered_codec(make_package, declared, codec):
    """XML 1.0 §4.3.3 and Appendix F.1: 4C 6F A7 94 identifies EBCDIC;
    the complete encoding declaration determines which code page is used.
    """
    title = "A topicé [ ]" + (" €" if codec == "cp1140" else "")
    text = '<?xml version="1.0" encoding="%s"?>\n' % declared + BODY.replace("A topic", title)
    raw = text.encode(codec)
    assert raw[:4] == b"\x4c\x6f\xa7\x94"
    graph, error = parsed(raw)
    assert graph is not None and error is None, error
    assert any(str(value) == title for value in graph.objects())
    report = runner.check(make_package(metadata=raw))
    assert report.ok, [(f.rule.id, f.violation.detail) for f in report.findings]


@pytest.mark.parametrize("declared", ["UTF-8", "IBM1026", "csUnicode"])
def test_ebcdic_declaration_must_explain_its_observed_bytes(declared):
    """XML 1.0 §4.3.3 refuses bytes other than the declared encoding.
    A declaration read in the cp037 view must re-encode to the stored bytes.
    """
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + BODY).encode("cp037")
    graph, error = parsed(raw)
    assert graph is None and iirds.CONTRADICTED_ENCODING in error, error
    assert "EBCDIC" in error and "4.3.3" in error


@pytest.mark.parametrize("declaration", ['<?xml version="1.0"?>', '<?xml-stylesheet href="x"?>'])
def test_ebcdic_signature_needs_a_readable_encoding_declaration(declaration):
    """XML 1.0 §4.3.3 requires a declaration for non-UTF-8/16 entities;
    Appendix F's EBCDIC signature alone does not select the code page.
    """
    graph, error = parsed((declaration + "\n" + BODY).encode("cp037"))
    assert graph is None and iirds.UNDECLARED_ENCODING in error, error
    assert "EBCDIC-family bytes" in error and "no readable encoding declaration" in error


def test_ebcdic_without_the_appendix_f_signature_is_not_guessed():
    """XML 1.0 Appendix F.1 gives <?xml's signature, not every EBCDIC prefix."""
    graph, error = parsed(BODY.encode("cp037"))
    assert graph is None and error
    assert iirds.first_bytes_encoding(BODY.encode("cp037")) is None


def test_ebcdic_cp1026_is_not_retried_after_the_cp037_view():
    """XML 1.0 §2.8 [23]/Appendix F.1: the sole cp037 declaration view
    cannot read cp1026's double quotes; no other code page is guessed.
    """
    raw = ('<?xml version="1.0" encoding="IBM1026"?>\n' + BODY).encode("cp1026")
    graph, error = parsed(raw)
    assert graph is None and iirds.MALFORMED_DECLARATION in error, error
    assert "EBCDIC-family bytes" in error and "no readable encoding declaration" in error


@pytest.mark.parametrize("declared,registered", [("IBM875", False), ("IBM1047", True)])
def test_ebcdic_unavailable_names_use_the_existing_unreadable_path(declared, registered):
    """XML 1.0 §4.3.3: unsupported names may be treated as unknown.
    IBM875 is absent from this IANA snapshot; IBM1047 is registered without
    a Python codec under its registered name or aliases.
    """
    from iirds import _metadata

    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + BODY).encode("cp037")
    graph, error = parsed(raw)
    assert graph is None and iirds.UNREADABLE_ENCODING in error, error
    assert (_metadata._registered(declared) is not None) is registered
    assert ("registered at IANA" if registered else "not an IANA-registered") in error


@pytest.mark.parametrize("element,namespace,rule", [
    ("svg", "http://www.w3.org/2000/svg", "R42"),
    ("html", "http://www.w3.org/1999/xhtml", "B6"),
])
def test_content_identification_uses_the_ebcdic_byte_signature(make_package, element,
                                                            namespace, rule):
    """iiRDS 1.3 §8.2.1.1/§8.2.1.2: EBCDIC XML reaches the same
    bounded root-namespace identification via XML Appendix F.1.
    """
    from test_obl_c import A_PROFILE

    raw = ('<?xml version="1.0" encoding="IBM037"?><%s xmlns="%s"/>'
           % (element, namespace)).encode("cp037")
    report = runner.check(make_package(metadata=A_PROFILE,
                                      extra=(("content/ebcdic.bin", raw),)))
    assert [f.violation.subject for f in report.findings if f.rule.id == rule] == ["content/ebcdic.bin"]
