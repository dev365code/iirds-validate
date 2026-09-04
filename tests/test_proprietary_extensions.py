"""Section 7.1: an extension you use has to be in metadata.rdf.

    x7-1-iirds-extension-scenarios#4  All proprietary extensions that are used
        in a package MUST be contained in the file metadata.rdf in the iiRDS
        package.

Section 7.3 says what one is, in three kinds: a proprietary **class** (added
as a subclass or equivalent class of an iiRDS class), a proprietary
**property** (added as a subproperty of an iiRDS property), and a proprietary
**instance** (added as an instance of an iiRDS class). The sentence pairs with
the one after it — "the file metadata.rdf MUST NOT contain the iiRDS schema" —
so the pair is about where a vocabulary lives: yours in metadata.rdf, the
standard's not.

The claim on that sentence was withdrawn once, because the third kind reads as
though it covered every node in the package. Telling a company's vocabulary
term from its data is the decision this file records, and the ontology makes
it rather than a list:

    **A class is a vocabulary class when the bundled ontology supplies
    instances of it.** The standard ships the terms of its own vocabularies --
    twenty document types, eight party roles, eight identity types, five
    classification types -- and ships no documents, because documents are
    data. A company adding a term of that kind extends the vocabulary; a
    company adding a document does not.

Two consequences worth stating, because both were measured rather than
assumed. `iirds:ClassificationDomain` and `iirds:ExternalClassification` carry
no ontology instances, so they are data classes and an eCl@ss IRI is never
reported here -- which is the false positive this rule would otherwise be
full of, section 6.8.4 being entirely about pointing outside. And
`iirds:ProductVariant` and `iirds:Component` are data classes too, though the
standard calls them proprietary extensions in so many words; they keep their
own sentences and their own rule, R11.

Over the hundred and thirty metadata files this repository vendors, the type
and predicate populations are empty and the instance population is three
`rdf:resource=""` in the reference tool's own deliberate-defect fixtures.
"""
from __future__ import annotations

import json

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

IIRDS = "http://iirds.tekom.de/iirds#"
RDFS_ = "http://www.w3.org/2000/01/rdf-schema#"
MY = "http://my.co/ns#"


def package(tmp_path, name, rdf_body="", jsonld_nodes=None):
    """`rdf_body` goes into metadata.rdf; `jsonld_nodes`, when given, into a
    metadata.jsonld beside it. No jsonld at all when it is None, which is the
    shape that shows a name described in neither file."""
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", rdf_body + "</rdf:RDF>")
    jsonld = None
    if jsonld_nodes is not None:
        graph = [{"@id": "urn:test:package", "@type": "iirds:Package",
                  "iirds:iiRDSVersion": "1.3", "iirds:title": "Test package"}]
        graph.extend(jsonld_nodes)
        jsonld = json.dumps({"@context": {"iirds": IIRDS, "rdfs": RDFS_},
                             "@graph": graph})
    return build_package(tmp_path, name, metadata=metadata, jsonld=jsonld)


def fired(tmp_path, name, **kwargs):
    return {f.rule.id for f in runner.run(package(tmp_path, name, **kwargs),
                                          runner.ALL_KINDS).findings}


def under_check(tmp_path, name, **kwargs):
    """What `iirds check` reports. The three populations below were all silent
    here, and one of them was silent in every mode."""
    return {f.rule.id for f in runner.check(package(tmp_path, name, **kwargs)).findings}


# --- the three kinds, used and described nowhere ---------------------------

USES_A_CLASS = ('  <rdf:Description rdf:about="urn:test:t9">\n'
                '    <rdf:type rdf:resource="%sManual"/>\n'
                "  </rdf:Description>\n" % MY)

USES_A_PROPERTY = ('  <rdf:Description rdf:about="urn:test:topic1">\n'
                   '    <ext:partNumber xmlns:ext="%s">X-1</ext:partNumber>\n'
                   "  </rdf:Description>\n" % MY)

USES_AN_INSTANCE = ('  <rdf:Description rdf:about="urn:test:doc9">\n'
                    '    <rdf:type rdf:resource="%sDocument"/>\n'
                    '    <iirds:has-document-type rdf:resource="%sHandbook"/>\n'
                    "  </rdf:Description>\n" % (IIRDS, MY))

USED_NOWHERE = {
    "a proprietary class": USES_A_CLASS,
    "a proprietary property": USES_A_PROPERTY,
}


@pytest.mark.parametrize("what", sorted(USED_NOWHERE), ids=sorted(USED_NOWHERE))
def test_an_extension_described_in_no_file_is_reported(tmp_path, what):
    """The shape the withdrawal left open. A package can use a name of its own
    and define it in a side ontology, or not at all, and `iirds check` said
    nothing about any of the three -- the property one was reported by nothing
    in any mode, L5 having only the class."""
    body = USED_NOWHERE[what]
    assert "R18" in fired(tmp_path, "nowhere_%d.iirds" % abs(hash(what)), rdf_body=body), what
    assert "R18" in under_check(tmp_path, "chk_%d.iirds" % abs(hash(what)), rdf_body=body), (
        "%s: conformance must not be silent about it" % what)


# --- the same three, described in metadata.jsonld only ---------------------

JSONLD_ONLY = {
    "a proprietary class": (
        USES_A_CLASS,
        {"@id": MY + "Manual", "@type": "rdfs:Class",
         "rdfs:subClassOf": {"@id": "iirds:Document"}}),
    "a proprietary property": (
        USES_A_PROPERTY,
        {"@id": MY + "partNumber",
         "@type": "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property",
         "rdfs:subPropertyOf": {"@id": "iirds:identifier"}}),
    "a proprietary vocabulary instance": (
        USES_AN_INSTANCE,
        {"@id": MY + "Handbook", "@type": "iirds:DocumentType",
         "rdfs:label": "Handbook"}),
}


@pytest.mark.parametrize("what", sorted(JSONLD_ONLY), ids=sorted(JSONLD_ONLY))
def test_an_extension_only_in_the_json_ld_is_reported(tmp_path, what):
    body, node = JSONLD_ONLY[what]
    got = fired(tmp_path, "jsonld_%d.iirds" % abs(hash(what)),
                rdf_body=body, jsonld_nodes=(node,))
    assert "R18" in got, (what, sorted(got))


@pytest.mark.parametrize("what", sorted(JSONLD_ONLY), ids=sorted(JSONLD_ONLY))
def test_the_same_extension_in_metadata_rdf_is_not_reported(tmp_path, what):
    """The control, and the only one that matters: a package that does what
    the sentence asks must be silent, or the rule is a rule about nothing."""
    body, node = JSONLD_ONLY[what]
    declaration = {
        "a proprietary class":
            '  <rdf:Description rdf:about="%sManual">\n'
            '    <rdf:type rdf:resource="%sClass"/>\n'
            '    <rdfs:subClassOf rdf:resource="%sDocument"/>\n'
            "  </rdf:Description>\n" % (MY, RDFS_, IIRDS),
        "a proprietary property":
            '  <rdf:Description rdf:about="%spartNumber">\n'
            '    <rdf:type rdf:resource="http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"/>\n'
            '    <rdfs:subPropertyOf rdf:resource="%sidentifier"/>\n'
            "  </rdf:Description>\n" % (MY, IIRDS),
        "a proprietary vocabulary instance":
            '  <rdf:Description rdf:about="%sHandbook">\n'
            '    <rdf:type rdf:resource="%sDocumentType"/>\n'
            "  </rdf:Description>\n" % (MY, IIRDS),
    }[what]
    got = fired(tmp_path, "ok_%d.iirds" % abs(hash(what)),
                rdf_body=declaration + body, jsonld_nodes=(node,))
    assert "R18" not in got, (what, sorted(got))


# --- what the rule must not reach ------------------------------------------

NOT_AN_EXTENSION = {
    "an external classification, which is meant to point outside":
        '  <iirds:ExternalClassification rdf:about="urn:test:xc">\n'
        '    <iirds:has-classification-domain rdf:resource="https://eclass.eu/0173-1"/>\n'
        "    <iirds:classificationIdentifier>27-27-40-01</iirds:classificationIdentifier>\n"
        "  </iirds:ExternalClassification>\n",
    "a rendition referred to by a relative IRI":
        '  <rdf:Description rdf:about="urn:test:topic1">\n'
        '    <iirds:has-rendition rdf:resource="content/topic1.xhtml"/>\n'
        "  </rdf:Description>\n",
    "a well-known vocabulary used as a predicate":
        '  <rdf:Description rdf:about="urn:test:topic1">\n'
        '    <dcterms:title xmlns:dcterms="http://purl.org/dc/terms/">t</dcterms:title>\n'
        "  </rdf:Description>\n",
    #: The reading this rule settled on, kept as a case because it is the one
    #: the first version got wrong. A name referred to in a vocabulary slot and
    #: typed by nobody is a dangling reference: the package never adds the
    #: extension, so there is no extension of the package's for section 7.1 to
    #: place. L1 has that sentence, and `test_lint.py` pins in its own words
    #: that "a reference to an undescribed IRI breaks no MUST" -- reading it
    #: the other way reversed a settled decision as a side effect, and did:
    #: `iirds:relates-to-event` takes an `iirds:Event`, the ontology seeds
    #: that class with one generic term, and a reference to an event that does
    #: not exist became a MUST breach.
    "a vocabulary name referred to and typed by nobody": USES_AN_INSTANCE,
    "a document, which is data and not a vocabulary term":
        '  <rdf:Description rdf:about="urn:test:doc9">\n'
        '    <rdf:type rdf:resource="%sDocument"/>\n'
        '    <iirds:is-version-of rdf:resource="urn:test:elsewhere"/>\n'
        "  </rdf:Description>\n" % IIRDS,
}


@pytest.mark.parametrize("what", sorted(NOT_AN_EXTENSION), ids=sorted(NOT_AN_EXTENSION))
def test_what_is_not_a_proprietary_extension_is_not_reported(tmp_path, what):
    """Each of these is a name from outside the iiRDS vocabulary, used, and
    described nowhere -- and none of them is a proprietary extension. The
    first is section 6.8.4's whole purpose; the second and fourth are ordinary
    references, which L1 has its own sentence for; the third is a vocabulary
    the standard itself uses."""
    got = fired(tmp_path, "notext_%d.iirds" % abs(hash(what)),
                rdf_body=NOT_AN_EXTENSION[what])
    assert "R18" not in got, (what, sorted(got))


def test_the_vocabulary_classes_are_read_from_the_ontology_not_listed():
    """The decision this rule rests on, asserted against the ontology rather
    than against a list somebody typed. A list would be a copy of the
    vocabulary and would drift from it; the point of deriving it is that a
    class the standard starts supplying terms for becomes a vocabulary class
    without anybody noticing it has to."""
    from iirds_validate.ontology import load
    from iirds_validate.rules.requirements import vocabulary_classes

    vocab = vocabulary_classes(load())
    for name in ("DocumentType", "PartyRole", "IdentityType",
                 "ContentLifeCycleStatusValue", "ClassificationType"):
        assert IIRDS + name in {str(c) for c in vocab}, name
    for name in ("Document", "Topic", "Fragment", "Package", "Rendition",
                 "ClassificationDomain", "ExternalClassification",
                 "ProductVariant", "Component"):
        assert IIRDS + name not in {str(c) for c in vocab}, name
