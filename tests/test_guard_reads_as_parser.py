"""The checks before the parser read the document the parser reads.

rdflib parses `metadata.rdf` as UTF-8 whatever its XML declaration names. Two
checks come before it: one refuses a document that declares XML entities, one
refuses a document that is not RDF/XML. Both read the document under the
encoding it declared, so where the declaration made that reading differ from
UTF-8 they answered for a text the parser never saw, and the parser read what
they had passed. They also read what the parser reads now, and these tests
hold the outcome whatever a document declares.
"""
from __future__ import annotations

import pytest

import iirds

BODY = ('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
        '         xmlns:iirds="http://iirds.tekom.de/iirds#">\n'
        '  <iirds:Package rdf:about="http://e/p">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:title>%s</iirds:title>\n'
        '  </iirds:Package>\n'
        '</rdf:RDF>\n')

#: Names a document may declare, and what may stand in front of its document
#: type declaration. The parser reads every one of these documents as UTF-8.
DECLARED = [(declared, prolog)
            for declared in ("UTF-8", "utf8", "UTF_8", "u-t-f-8", "cp1361", "cp864",
                             "windows-1252", "latin-1", "utf-16", "x-nonesuch")
            for prolog in ("", "<!-- Gr\u00f6\u00dfe -->\n")]


def _declaring(declared, prolog, subset, body):
    return ('<?xml version="1.0" encoding="%s"?>\n%s<!DOCTYPE rdf:RDF [%s]>\n'
            % (declared, prolog, subset) + body).encode("utf-8")


def _parsed(raw):
    """What parse_metadata hands on. This release still raises for a
    declaration naming an encoding it cannot use -- a refusal all the same,
    which the validator reports under C16.1 -- so that raise is no graph."""
    try:
        return iirds.parse_metadata(iirds.METADATA_RDF, raw, base=iirds.PACKAGE_BASE)
    except UnicodeError:
        raise
    except (LookupError, ValueError) as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


@pytest.mark.parametrize("declared, prolog", DECLARED)
def test_a_document_declaring_entities_is_refused_whatever_it_declares(declared, prolog):
    raw = _declaring(declared, prolog, '<!ENTITY t "Operating instructions">', BODY % "&t;")
    graph, error = _parsed(raw)
    assert graph is None and error, (declared, prolog)


@pytest.mark.parametrize("declared, prolog", DECLARED)
def test_a_document_that_is_not_rdfxml_is_refused_whatever_it_declares(declared, prolog):
    raw = _declaring(declared, prolog, "", "<manual><title>x</title></manual>\n")
    graph, error = _parsed(raw)
    assert graph is None and error, (declared, prolog)


@pytest.mark.parametrize("declared", ["UTF-8", "utf8", "windows-1252"])
def test_a_document_with_nothing_to_refuse_is_still_read(declared):
    graph, error = _parsed(_declaring(declared, "", "", BODY % "Operating instructions"))
    assert error is None and graph is not None, (declared, error)


def test_a_document_whose_names_are_not_utf8_is_refused_not_raised():
    """Its root element named in the code page it declares. The parser reads
    UTF-8 and refuses it; the UTF-8 reading before it has to say so rather
    than raise -- older expat hands such a name on unchecked, and decoding it
    raised out of parse_metadata, which promises never to."""
    root = ("<iirds:\u00c9l\u00e9ments xmlns:iirds=\"http://iirds.tekom.de/iirds#\" "
            "xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\" rdf:about=\"urn:test:p\"/>\n")
    raw = ('<?xml version="1.0" encoding="latin-1"?>\n' + root).encode("latin-1")
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF, raw, base=iirds.PACKAGE_BASE)
    assert graph is None and error, error
