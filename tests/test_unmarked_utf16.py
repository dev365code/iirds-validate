"""UTF-16 without a byte order mark, read only where a declaration names it.

XML 1.0 (fifth edition), section 4.3.3:

    In the absence of information provided by an external transport protocol
    (e.g. HTTP or MIME), it is a fatal error for an entity including an
    encoding declaration to be presented to the XML processor in an encoding
    other than that named in the declaration, or for an entity which begins
    with neither a Byte Order Mark nor an encoding declaration to use an
    encoding other than UTF-8.

A ZIP member has no transport protocol to name its encoding, so a document in
UTF-16 with neither a byte order mark nor an encoding declaration is that
fatal error. The same section says an entity encoded in UTF-16 MUST begin with
a byte order mark, and that its terms "UTF-8" and "UTF-16" do not apply to
UTF-16LE or UTF-16BE; appendix F reads such a stream as mislabeled, lacking a
required encoding declaration. It was read all the same: the shape of its
first bytes said UTF-16, and the reader believed them, as expat does.

With a declaration that names its byte order, or names UTF-16, it is still
read. The missing mark is then an error by section 1.2 -- one a processor may
report and recover from -- and not a fatal one; docs/divergences.md says so,
and what RFC 2781 says about the two labels.
"""
from __future__ import annotations

import pytest

import iirds
from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

BODY = MINIMAL_RDF.split("\n", 1)[1]

#: Each byte order: the codec that writes it, its mark, and the other order.
ORDERS = {"UTF-16LE": ("utf-16-le", b"\xff\xfe", "UTF-16BE"),
          "UTF-16BE": ("utf-16-be", b"\xfe\xff", "UTF-16LE")}

#: What stands in front of the document element, and what becomes of the
#: document in either byte order with no mark: refused, in the category
#: given, or read (None).
UNMARKED = {
    "nothing": ("", iirds.UNDECLARED_ENCODING),
    "a version only": ('<?xml version="1.0"?>\n', iirds.UNDECLARED_ENCODING),
    "a version and standalone": ('<?xml version="1.0" standalone="yes"?>\n',
                                 iirds.UNDECLARED_ENCODING),
    "white space": ("\n\t", iirds.UNDECLARED_ENCODING),
    "a comment": ("<!-- a comment -->\n", iirds.UNDECLARED_ENCODING),
    "a processing instruction": ("<?pi x?>\n", iirds.UNDECLARED_ENCODING),
    "its own byte order": ('<?xml version="1.0" encoding="{own}"?>\n', None),
    "its own byte order in lower case": ('<?xml version="1.0" encoding="{lower}"?>\n', None),
    "UTF-16": ('<?xml version="1.0" encoding="UTF-16"?>\n', iirds.UNREADABLE_ENCODING),
    "the other byte order": ('<?xml version="1.0" encoding="{other}"?>\n',
                             iirds.CONTRADICTED_ENCODING),
    "UTF-8": ('<?xml version="1.0" encoding="UTF-8"?>\n', iirds.CONTRADICTED_ENCODING),
}


def unmarked(order, head, body=BODY):
    codec, _mark, other = ORDERS[order]
    return (head.format(own=order, lower=order.lower(), other=other) + body).encode(codec)


def parsed(raw):
    return iirds.parse_metadata(iirds.METADATA_RDF, raw, base=iirds.PACKAGE_BASE)


@pytest.mark.parametrize("order", sorted(ORDERS))
@pytest.mark.parametrize("case", list(UNMARKED))
def test_unmarked_utf16_is_read_only_where_a_declaration_names_it(order, case):
    """E05, E06 and E07 among them, read before; E08 and its byte-order twins
    read only with order-specific labels."""
    head, refused = UNMARKED[case]
    graph, error = parsed(unmarked(order, head))
    if refused is None:
        assert error is None and graph is not None, (order, case, error)
    else:
        assert graph is None and refused in error, (order, case, error)


#: What appendix F says of the first bytes, by what stands first: `<?` is a
#: row of its own, which leaves the encoding to the declaration, and anything
#: else is its last row, a stream mislabeled.
READINGS = {"": "mislabeled, lacking a required encoding declaration",
            "<!-- a comment -->\n": "mislabeled, lacking a required encoding declaration",
            '<?xml version="1.0"?>\n': "to the encoding declaration to settle, and none",
            "<?pi x?>\n": "to the encoding declaration to settle, and none"}


@pytest.mark.parametrize("order", sorted(ORDERS))
@pytest.mark.parametrize("head", list(READINGS))
def test_the_refusal_calls_only_the_first_sentence_fatal(order, head):
    """The fatal error is the entity that begins with neither a mark nor an
    encoding declaration. The MUST that UTF-16 begin with a mark, and the
    terms that do not reach UTF-16LE or UTF-16BE, are given as what they are,
    and appendix F's reading of the bytes beside them -- the row they match:
    E07's declaration opens `<?`, which the row for `3C 00 3F 00` leaves to
    the encoding declaration, and it was called mislabeled, the last row's
    word."""
    graph, error = parsed(unmarked(order, head))
    assert graph is None and iirds.UNDECLARED_ENCODING in error, error
    assert order in error and "4.3.3" in error, error
    assert error.count("fatal") == 1, error
    assert "MUST begin with a byte order mark" in error, error
    assert "do not apply to UTF-16LE or UTF-16BE" in error, error
    assert "appendix F" in error and READINGS[head] in error, error


@pytest.mark.parametrize("order", sorted(ORDERS))
@pytest.mark.parametrize("front", ["\n", "<!-- a comment -->\n"])
def test_a_declaration_out_of_place_is_told_to_stand_first(order, front):
    """A declaration behind white space or a comment is none, and the document
    begins with neither a mark nor an encoding declaration. It was told to
    declare its byte order, which it does; the remedy puts the declaration at
    its start, and done, the document is read."""
    declaration = '<?xml version="1.0" encoding="{own}"?>\n'
    graph, error = parsed(unmarked(order, front + declaration))
    assert graph is None and iirds.UNDECLARED_ENCODING in error, error
    assert "declare %s in an XML declaration at its start" % order in error, error
    graph, error = parsed(unmarked(order, declaration + front))
    assert error is None and graph is not None, error


@pytest.mark.parametrize("order", sorted(ORDERS))
@pytest.mark.parametrize("head", ["", '<?xml version="1.0"?>\n', " \n",
                                  '<?xml version="1.0" encoding="UTF-16"?>\n',
                                  '<?xml version="1.0" encoding="{own}"?>\n'])
def test_behind_a_mark_utf16_need_declare_nothing(order, head):
    """The controls: a byte order mark settles UTF-16, which needs no encoding
    declaration. RFC 2781 says text labelled UTF-16LE or UTF-16BE carries no
    mark; a document that has one and declares its byte order was read, and
    is read."""
    codec, mark, _other = ORDERS[order]
    graph, error = parsed(mark + (head.format(own=order) + BODY).encode(codec))
    assert error is None and graph is not None, (order, head, error)


#: The cases these were found as: unmarked UTF-16, little- and big-endian,
#: with nothing in front, and little-endian behind a declaration naming no
#: encoding.
PASSED = {"E05": ("UTF-16LE", ""), "E06": ("UTF-16BE", ""),
          "E07": ("UTF-16LE", '<?xml version="1.0"?>\n')}


@pytest.mark.parametrize("case", sorted(PASSED))
def test_a_package_whose_metadata_is_unmarked_undeclared_utf16_fails(case, tmp_path):
    report = runner.check(build_package(tmp_path, metadata=unmarked(*PASSED[case])))
    refused = [f for f in report.findings if f.rule.id == "C16.1"]
    assert refused and not report.ok, (case, sorted({f.rule.id for f in report.findings}))
    assert iirds.UNDECLARED_ENCODING in refused[0].violation.detail, refused[0].violation.detail


@pytest.mark.parametrize("declared", ["UTF-16LE", "csUTF16LE"])
def test_a_package_whose_metadata_names_its_utf16_passes(declared, tmp_path):
    """RFC 2781 §3.3: a little-endian stream can name its byte order.
    The generic UTF-16 label needs a mark under XML 1.0 §4.3.3.
    """
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + BODY).encode("utf-16-le")
    report = runner.check(build_package(tmp_path, metadata=raw))
    assert report.ok, sorted({f.rule.id for f in report.findings})


@pytest.mark.parametrize("order", sorted(ORDERS))
def test_an_entity_declared_in_unmarked_utf16_that_is_read_is_refused(order):
    """Unmarked UTF-16 now reaches the parser only under a declaration that
    names it, and the entity guard reads it there as the parser will."""
    head = ('<?xml version="1.0" encoding="{own}"?>\n'
            '<!DOCTYPE rdf:RDF [<!ENTITY t "Test package">]>\n')
    graph, error = parsed(unmarked(order, head, BODY.replace("Test package", "&t;")))
    assert graph is None and "XML entities" in error, error


#: A node element named in CJK as the document element, which RDF/XML allows:
#: in UTF-16 its second character holds no null byte.
WIDE_NAMED = ('<日:Package xmlns:日="http://iirds.tekom.de/iirds#" '
              'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
              'rdf:about="urn:test:package"><日:iiRDSVersion>1.3</日:iiRDSVersion>'
              '</日:Package>')


@pytest.mark.parametrize("order", sorted(ORDERS))
def test_one_character_settles_the_byte_order(order):
    """Every legal first character is ASCII, so in UTF-16 the first two bytes
    settle the byte order. Asked of four, the shape missed a document whose
    second character holds no null byte, and it was refused as bytes that are
    not UTF-8, not for the declaration it lacks. Under one naming its byte
    order it is read."""
    codec = ORDERS[order][0]
    raw = WIDE_NAMED.encode(codec)
    assert iirds.first_bytes_encoding(raw) == order
    graph, error = parsed(raw)
    assert graph is None and iirds.UNDECLARED_ENCODING in error, error
    graph, error = parsed(unmarked(order, '<?xml version="1.0" encoding="{own}"?>', WIDE_NAMED))
    assert error is None and graph is not None, error


# ---------------------------------------------------------------------------
# UTF-16 the parser would find for itself. It sniffs the first bytes it is
# handed, as this reader does, and a document decoded and written out as UTF-8
# can begin like UTF-16 to it: U+0000 in either of its first two characters.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("head", ["", '<?xml version="1.0"?>\n',
                                  '<?xml version="1.0" encoding="{own}"?>\n'])
@pytest.mark.parametrize("order", sorted(ORDERS))
def test_utf16_behind_a_utf8_mark_is_refused(order, head, tmp_path):
    """The mark says UTF-8, and read as UTF-8 the rest is ASCII with U+0000
    between its characters, which XML lets stand nowhere. Written out again,
    it began like UTF-16, and the parser read it as that, the mark and any
    declaration behind it held against nothing."""
    raw = b"\xef\xbb\xbf" + unmarked(order, head)
    graph, error = parsed(raw)
    assert graph is None and error, (order, head)
    assert not runner.check(build_package(tmp_path, metadata=raw)).ok


@pytest.mark.parametrize("head", ["", '<?xml version="1.0" encoding="ISO-10646-UCS-4"?>\n'])
def test_ucs4_in_octet_order_3412_cut_short_is_refused(head, tmp_path):
    """`FE FF 00 00` is UCS-4 in an unusual octet order to appendix F, and a
    UTF-16 mark to this reader, which reads U+0000 between the characters
    after it. Cut by two bytes it was read, nine statements, behind a
    declaration of ISO-10646-UCS-4 or none."""
    body = head + BODY
    whole = b"\xfe\xff\x00\x00" + b"".join(
        bytes((unit[2], unit[3], unit[0], unit[1]))
        for unit in (ord(character).to_bytes(4, "big") for character in body))
    graph, error = parsed(whole[:-2])
    assert graph is None and error, error
    assert not runner.check(build_package(tmp_path, metadata=whole[:-2])).ok


@pytest.mark.parametrize("order", ["utf-16-le", "utf-16-be"])
@pytest.mark.parametrize("declared", ["UTF-16", "utf-16", "csUTF16"])
def test_generic_utf16_without_a_mark_is_refused(order, declared, tmp_path):
    """XML 1.0 §4.3.3 requires a BOM for the generic UTF-16 encoding.
    RFC 2781 §3.3's order-specific labels and IANA UCS-2 are separate.
    """
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + BODY).encode(order)
    graph, error = parsed(raw)
    assert graph is None and "byte order mark" in error, error
    assert "4.3.3" in error and declared in error
    assert not runner.check(build_package(tmp_path, metadata=raw)).ok


@pytest.mark.parametrize("order", ["utf-16-le", "utf-16-be"])
@pytest.mark.parametrize("declared", ["ISO-10646-UCS-2", "csUnicode"])
def test_ucs2_cannot_declare_a_supplementary_character(order, declared, tmp_path):
    """IANA record 1000 restricts UCS-2 to the BMP. XML 1.0 §4.3.3
    requires the declaration to name the encoding represented by the bytes.
    """
    body = BODY.replace("A topic", "outside 😀")
    raw = ('<?xml version="1.0" encoding="%s"?>\n' % declared + body).encode(order)
    graph, error = parsed(raw)
    assert graph is None and iirds.CONTRADICTED_ENCODING in error, error
    assert "BMP" in error and declared in error
    assert not runner.check(build_package(tmp_path, metadata=raw)).ok


def test_first_bytes_outside_appendix_f_are_not_named_utf16():
    """XML 1.0 Appendix F.1 does not identify FE 00 3C 00 as UTF-16."""
    raw = b"\xfe\x00\x3c\x00" + BODY.encode("utf-16-le")
    assert iirds.first_bytes_encoding(raw) is None
    graph, error = parsed(raw)
    assert graph is None and "no Appendix F byte pattern" in error
    assert "read as UTF-8" in error and "UTF-16LE" not in error


@pytest.mark.parametrize("order", ["2143", "3412"])
def test_unusual_ucs4_byte_orders_are_named_as_unsupported(order):
    """XML 1.0 Appendix F.1 identifies the two unusual UCS-4 octet orders;
    this reader refuses them instead of claiming a conventional codec.
    """
    raw = b"\x00\x00\xfe\xff" + ('<?xml version="1.0" encoding="ISO-10646-UCS-4"?>\n'
                                      + BODY).encode("utf-32-be")
    indices = [int(n) - 1 for n in order]
    raw = b"".join(bytes(raw[i + k] for k in indices) for i in range(0, len(raw), 4))
    graph, error = parsed(raw)
    assert graph is None and "unusual byte order" in error
    assert order in error and "not supported" in error
