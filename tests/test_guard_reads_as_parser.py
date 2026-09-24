"""The checks before the parser read the document the parser reads.

rdflib parses `metadata.rdf` as UTF-8 whatever its XML declaration names. Two
checks come before it: one refuses a document that declares XML entities, one
refuses a document that is not RDF/XML. Both read the document under the
encoding it declared, so where the declaration made that reading differ from
UTF-8 they answered for a text the parser never saw, and the parser read what
they had passed. They read what the parser reads now, and these tests hold
the outcome whatever a document declares.
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
    return iirds.parse_metadata(iirds.METADATA_RDF, raw, base=iirds.PACKAGE_BASE)


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
