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


@pytest.mark.parametrize("form", sorted(FORMS))
def test_the_name_read_is_the_one_declared(form):
    raw = stored(form, "<?xml version='1.0'\tencoding = '{lower}' standalone='no'?>")
    assert iirds.declared_encoding(raw) == FORMS[form][2].lower()


def test_a_declaration_out_of_order_behind_a_utf32_mark_is_refused_as_that():
    """E39: refused, and said to declare no encoding at all; it declares
    UTF-32, in a declaration production [23] does not allow."""
    graph, error = parsed(stored("utf-32le marked", '<?xml encoding="UTF-32" version="1.0"?>'))
    assert graph is None and iirds.MALFORMED_DECLARATION in error and "[23]" in error, error
    assert "declares no encoding" not in error, error


def test_the_note_on_a_decode_failure_names_the_declaration_the_grammar_reads(tmp_path):
    """The C16.1 note names what the document declares, read by the same
    reading the checks use, single quotes and white space around Eq
    included."""
    raw = ("<?xml version='1.0' encoding = 'UTF-8'?>\n" + BODY.replace(
        "Test package", "Größe")).encode("windows-1252")
    report = runner.check(build_package(tmp_path, metadata=raw))
    [finding] = [f for f in report.findings if f.rule.id == "C16.1"]
    assert "encoding='UTF-8', which these bytes are not" in finding.violation.detail, (
        finding.violation.detail)
