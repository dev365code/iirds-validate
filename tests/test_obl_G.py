"""Obligations about the metadata graph, each held by a package that breaks it.

Every test here quotes the requirement it holds -- its id in
docs/requirements.json and its sentence -- builds packages that break the
sentence, and asserts that a rule claiming the id reports each one; where the
sentence leaves something allowed, a package on that side stays clean.
Through the claimants rather than a rule's id, as tests/test_covers_is_earned.py
does: naming the rule says the rule fires, which it would go on doing after
the claim was dropped.
"""
from __future__ import annotations

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.registry import all_rules

IIRDS = "http://iirds.tekom.de/iirds#"


def claimants(requirement):
    return {rule.id for rule in all_rules() if requirement in rule.covers}


def fired(tmp_path, name, metadata):
    return {f.rule.id for f in runner.run(build_package(tmp_path, name, metadata=metadata),
                                          runner.ALL_KINDS).findings}


def with_nodes(nodes):
    return MINIMAL_RDF.replace("</rdf:RDF>", nodes + "</rdf:RDF>")


# ---------------------------------------------------------------------------
# x6-5-1-types-of-documents-and-topics#1
#   "Instances of the iirds:Document class MUST have one or more relations to
#    one of the standardized iirds:DocumentTypes defined in
#    iirds:InformationType > iirds:DocumentType."
# and the sentence after it: "Additional proprietary iirds:DocumentType
# instances MAY be used."
# ---------------------------------------------------------------------------

DOCUMENT = """
  <iirds:Document rdf:about="urn:test:doc">
    <iirds:title>A document</iirds:title>
    %s
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>application/xhtml+xml</iirds:format>
        <iirds:source>content/topic1.xhtml</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Document>
"""

STANDARD = '<iirds:has-document-type rdf:resource="%sAssemblyInstructions"/>' % IIRDS
OWN = '<iirds:has-document-type rdf:resource="urn:test:own-type"/>'
OWN_TYPE = '\n  <iirds:DocumentType rdf:about="urn:test:own-type"/>\n'
OWN_CLASS = """
  <rdf:Description rdf:about="urn:test:OwnTypes">
    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>
    <rdfs:subClassOf rdf:resource="%sDocumentType"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:own-kind">
    <rdf:type rdf:resource="urn:test:OwnTypes"/>
  </rdf:Description>
""" % IIRDS

#: Each has no relation to any of the standardised document types.
DOCUMENTS_THAT_BREAK_IT = {
    "no document type": DOCUMENT % "",
    "a document type written as text":
        DOCUMENT % "<iirds:has-document-type>AssemblyInstructions</iirds:has-document-type>",
    "only a proprietary document type": DOCUMENT % OWN + OWN_TYPE,
    "only an instance of a proprietary subclass":
        DOCUMENT % '<iirds:has-document-type rdf:resource="urn:test:own-kind"/>' + OWN_CLASS,
    "a term of the standard that is no document type":
        DOCUMENT % ('<iirds:has-document-type rdf:resource="%sTopic"/>' % IIRDS),
    "a document type the package never describes":
        DOCUMENT % '<iirds:has-document-type rdf:resource="urn:test:undescribed"/>',
}

#: The sentence leaves each of these allowed.
DOCUMENTS_THAT_KEEP_IT = {
    "a standardised document type": DOCUMENT % STANDARD,
    "a standardised one beside a proprietary one": DOCUMENT % (STANDARD + OWN) + OWN_TYPE,
    "a standardised one as the type it applies to":
        DOCUMENT % ('<iirds:is-applicable-for-document-type rdf:resource="%sAssemblyInstructions"/>'
                    % IIRDS),
}


def test_a_document_related_to_no_standardised_document_type_is_reported(tmp_path):
    """Three ways to miss the standardised types -- no relation, a relation
    to something that is not a document type, and one to a document type
    the standard does not define -- and one rule for each."""
    claiming = claimants("x6-5-1-types-of-documents-and-topics#1")
    for shape, nodes in DOCUMENTS_THAT_KEEP_IT.items():
        found = fired(tmp_path, "doc_ok.iirds", with_nodes(nodes))
        assert not claiming & found, (shape, sorted(claiming & found))
    for shape, nodes in DOCUMENTS_THAT_BREAK_IT.items():
        found = fired(tmp_path, "doc_bad.iirds", with_nodes(nodes))
        assert claiming & found, (shape, sorted(found))


# ---------------------------------------------------------------------------
# x6-9-1-directory-nodes#4
#   "The root node of a directory structure MUST have one property
#    iirds:has-directory-structure-type."
# A root is a node nothing points at by iirds:has-first-child or
# iirds:has-next-sibling -- the reading M24.5 and M25 already take.
# ---------------------------------------------------------------------------

def _node(name, *properties):
    return ('\n  <iirds:DirectoryNode rdf:about="urn:test:%s">%s</iirds:DirectoryNode>\n'
            % (name, "".join(properties)))


def _to(prop, target):
    return '<iirds:%s rdf:resource="%s"/>' % (prop, target)


TOC = _to("has-directory-structure-type", IIRDS + "TableOfContents")
FIRST = _to("has-first-child", "urn:test:child")
CLOSED = _to("has-next-sibling", IIRDS + "nil")
CHILD = _node("child", _to("relates-to-information-unit", "urn:test:topic1"), CLOSED)

#: Each has a root without exactly one structure type.
STRUCTURES_THAT_BREAK_IT = {
    "the only root has no type": _node("root", FIRST, CLOSED) + CHILD,
    "a second root has no type": (_node("root", TOC, FIRST, CLOSED) + CHILD
                                  + _node("second", _to("has-first-child", "urn:test:child2"),
                                          CLOSED)
                                  + _node("child2", CLOSED)),
    "a root has two types": (_node("root", TOC, _to("has-directory-structure-type",
                                                    IIRDS + "Index"), FIRST, CLOSED) + CHILD),
    "a node nothing points at, with no type": (_node("root", TOC, FIRST, CLOSED) + CHILD
                                               + _node("stray", CLOSED)),
    # A topic is not a directory node (section 6.11.1 makes the two disjoint),
    # so a sibling link from one leaves the node it points at a root.
    "a second root only a topic points at": (
        _node("root", TOC, FIRST, CLOSED) + CHILD
        + _node("second", _to("has-first-child", "urn:test:child2"), CLOSED)
        + _node("child2", CLOSED)
        + '\n  <rdf:Description rdf:about="urn:test:topic1">'
          '<iirds:has-next-sibling rdf:resource="urn:test:second"/></rdf:Description>\n'),
}

#: The sentence binds roots and says nothing of the nodes inside a level.
STRUCTURES_THAT_KEEP_IT = {
    "one root with one type": _node("root", TOC, FIRST, CLOSED) + CHILD,
    "two roots, each with one type": (_node("root", TOC, FIRST, CLOSED) + CHILD
                                      + _node("second", TOC,
                                              _to("has-first-child", "urn:test:child2"), CLOSED)
                                      + _node("child2", CLOSED)),
}


def test_a_root_directory_node_without_one_structure_type_is_reported(tmp_path):
    """M24.6 asks whether some root carries the type, which a second root
    without one does not change; the sentence binds every root."""
    claiming = claimants("x6-9-1-directory-nodes#4")
    for shape, nodes in STRUCTURES_THAT_KEEP_IT.items():
        found = fired(tmp_path, "toc_ok.iirds", with_nodes(nodes))
        assert not claiming & found, (shape, sorted(claiming & found))
    for shape, nodes in STRUCTURES_THAT_BREAK_IT.items():
        found = fired(tmp_path, "toc_bad.iirds", with_nodes(nodes))
        assert claiming & found, (shape, sorted(found))


# ---------------------------------------------------------------------------
# x6-10-2-translation#2
#   "Information units that are related by iirds:is-translation-of MUST have
#    an iirds:is-version-of relation to the same iirds:InformationObject."
# iiRDS 1.3 defines iirds:is-translation-of; no earlier edition does.
# ---------------------------------------------------------------------------

def _unit(name, *properties):
    return ('\n  <iirds:Topic rdf:about="urn:test:%s"><iirds:title>%s</iirds:title>%s'
            '</iirds:Topic>\n' % (name, name, "".join(properties)))


OBJECT_A = '\n  <iirds:InformationObject rdf:about="urn:test:object-a"/>\n'
OBJECT_B = '\n  <iirds:InformationObject rdf:about="urn:test:object-b"/>\n'
TRANSLATES = _to("is-translation-of", "urn:test:en")
OF_A = _to("is-version-of", "urn:test:object-a")
OF_B = _to("is-version-of", "urn:test:object-b")

#: Each pair shares no information object.
TRANSLATIONS_THAT_BREAK_IT = {
    "neither is a version of anything": _unit("en") + _unit("de", TRANSLATES),
    "only the original is": OBJECT_A + _unit("en", OF_A) + _unit("de", TRANSLATES),
    "only the translation is": OBJECT_A + _unit("en") + _unit("de", TRANSLATES, OF_A),
    "of two different objects": (OBJECT_A + OBJECT_B + _unit("en", OF_A)
                                 + _unit("de", TRANSLATES, OF_B)),
    "of one topic rather than an object": (_unit("t0") + _unit("en", _to("is-version-of", "urn:test:t0"))
                                           + _unit("de", TRANSLATES, _to("is-version-of", "urn:test:t0"))),
    "of one piece of text": (_unit("en", "<iirds:is-version-of>object-a</iirds:is-version-of>")
                             + _unit("de", TRANSLATES,
                                     "<iirds:is-version-of>object-a</iirds:is-version-of>")),
    "of a name the package never describes": (_unit("en", OF_A) + _unit("de", TRANSLATES, OF_A)),
    "a version of nothing, of an original described elsewhere": _unit(
        "de", _to("is-translation-of", "http://example.com/child/en")),
}

#: The sentence asks for one object in common and nothing of units that are
#: not translations. Where the original is not an information unit this
#: package describes -- one in a nested package, whose metadata the parent
#: must not carry (section 5.3), or one delivered elsewhere -- a unit that is
#: a version of an object may share it, and nothing here can say it does
#: not; and the sentence binds information units, not renditions.
TRANSLATIONS_THAT_KEEP_IT = {
    "of the same object": OBJECT_A + _unit("en", OF_A) + _unit("de", TRANSLATES, OF_A),
    "no translation at all": OBJECT_A + OBJECT_B + _unit("en", OF_A) + _unit("de", OF_B),
    "of an original described elsewhere": (OBJECT_A + _unit(
        "de", _to("is-translation-of", "http://example.com/child/en"), OF_A)),
    "between two renditions": (
        '\n  <iirds:Rendition rdf:about="urn:test:r-de"><iirds:is-translation-of '
        'rdf:resource="urn:test:r-en"/></iirds:Rendition>\n'
        '  <iirds:Rendition rdf:about="urn:test:r-en"/>\n'),
}


def test_translations_that_share_no_information_object_are_reported(tmp_path):
    claiming = claimants("x6-10-2-translation#2")
    for shape, nodes in TRANSLATIONS_THAT_KEEP_IT.items():
        found = fired(tmp_path, "translation_ok.iirds", with_nodes(nodes))
        assert not claiming & found, (shape, sorted(claiming & found))
    for shape, nodes in TRANSLATIONS_THAT_BREAK_IT.items():
        found = fired(tmp_path, "translation_bad.iirds", with_nodes(nodes))
        assert claiming & found, (shape, sorted(found))


# ---------------------------------------------------------------------------
# x6-3-1-reference-part-of-file-by-selector#5
#   "Only a standard from the following list of fragment selectors MUST be
#    used: [https://www.w3.org/TR/annotation-model/#fragment-selector]."
# The list is the Web Annotation Data Model's table of fragment
# specifications, each named by an IRI.
# ---------------------------------------------------------------------------

SELECTOR_NS = MINIMAL_RDF.replace(
    "xmlns:iirds=", 'xmlns:dcterms="http://purl.org/dc/terms/"\n         xmlns:iirds=', 1)

LISTED = ("http://tools.ietf.org/rfc/rfc3236", "http://tools.ietf.org/rfc/rfc3778",
          "http://tools.ietf.org/rfc/rfc5147", "http://tools.ietf.org/rfc/rfc3023",
          "http://tools.ietf.org/rfc/rfc3870", "http://tools.ietf.org/rfc/rfc7111",
          "http://www.w3.org/TR/media-frags/", "http://www.w3.org/TR/SVG/",
          "http://www.idpf.org/epub/linking/cfi/epub-cfi.html")

FRAGMENT_TOPIC = """
  <iirds:Topic rdf:about="urn:test:t">
    <iirds:title>T</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>application/pdf</iirds:format>
        <iirds:source>content/topic1.xhtml</iirds:source>
        <iirds:has-selector>
          <iirds:FragmentSelector>%s<rdf:value>page=10</rdf:value></iirds:FragmentSelector>
        </iirds:has-selector>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Topic>
"""


def _fragment(conforms_to):
    return SELECTOR_NS.replace("</rdf:RDF>", (FRAGMENT_TOPIC % conforms_to) + "</rdf:RDF>")


def _standard(iri):
    return '<dcterms:conformsTo rdf:resource="%s"/>' % iri


RANGE_TOPIC = FRAGMENT_TOPIC.replace(
    "<iirds:FragmentSelector>%s<rdf:value>page=10</rdf:value></iirds:FragmentSelector>",
    "<iirds:RangeSelector>%s<rdf:value>10-17</rdf:value>"
    "<iirds:has-start-selector><iirds:FragmentSelector>"
    '<dcterms:conformsTo rdf:resource="http://tools.ietf.org/rfc/rfc3778"/>'
    "<rdf:value>page=10</rdf:value></iirds:FragmentSelector></iirds:has-start-selector>"
    "<iirds:has-end-selector><iirds:FragmentSelector>"
    '<dcterms:conformsTo rdf:resource="http://tools.ietf.org/rfc/rfc3778"/>'
    "<rdf:value>page=17</rdf:value></iirds:FragmentSelector></iirds:has-end-selector>"
    "</iirds:RangeSelector>")
assert RANGE_TOPIC != FRAGMENT_TOPIC


def _range(conforms_to):
    return SELECTOR_NS.replace("</rdf:RDF>", (RANGE_TOPIC % conforms_to) + "</rdf:RDF>")


#: Each names something that is not one of the table's IRIs.
FRAGMENTS_THAT_BREAK_IT = {
    "a specification the table does not list": _standard("http://www.w3.org/TR/xpath-31/"),
    "a listed one under another scheme": _standard("https://tools.ietf.org/rfc/rfc3778"),
    "text that names no specification": "<dcterms:conformsTo>page numbers</dcterms:conformsTo>",
}


def test_a_fragment_selector_conforming_to_a_specification_off_the_list_is_reported(tmp_path):
    """Every IRI of the table passes, as the IRI or as its text; anything else
    is reported. The table names each specification by one IRI, and that IRI
    is what a consumer compares against."""
    claiming = claimants("x6-3-1-reference-part-of-file-by-selector#5")
    for iri in LISTED:
        for written in (_standard(iri), "<dcterms:conformsTo>%s</dcterms:conformsTo>" % iri,
                        "<dcterms:conformsTo>\n        %s\n      </dcterms:conformsTo>" % iri):
            found = fired(tmp_path, "fragment_ok.iirds", _fragment(written))
            assert not claiming & found, (written, sorted(claiming & found))
    for shape, written in FRAGMENTS_THAT_BREAK_IT.items():
        found = fired(tmp_path, "fragment_bad.iirds", _fragment(written))
        assert claiming & found, (shape, sorted(found))
    # A range that names a specification of its own names it as a selector,
    # and the sentence binds it; a range naming none (Example 13) is left to
    # its ends, which are fragment selectors.
    found = fired(tmp_path, "range_bad.iirds", _range(_standard("http://example.org/own-syntax")))
    assert claiming & found, ("a range naming its own syntax", sorted(found))
    found = fired(tmp_path, "range_ok.iirds", _range(""))
    assert not claiming & found, ("a range naming nothing", sorted(claiming & found))
