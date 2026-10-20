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

import importlib.util

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

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


# Appendix A.1.3 repeats the whole range sentence for each endpoint property.
def _endpoint_range(starts, ends):
    endpoints = "".join(
        '<iirds:has-%s-selector><iirds:FragmentSelector>'
        '<dcterms:conformsTo rdf:resource="http://tools.ietf.org/rfc/rfc3778"/>'
        '<rdf:value>page=%d</rdf:value></iirds:FragmentSelector>'
        '</iirds:has-%s-selector>' % (end, number + 1, end)
        for end, count in (("start", starts), ("end", ends))
        for number in range(count))
    topic = FRAGMENT_TOPIC.replace(
        '<iirds:FragmentSelector>%s<rdf:value>page=10</rdf:value></iirds:FragmentSelector>',
        '<iirds:RangeSelector>%s</iirds:RangeSelector>')
    return SELECTOR_NS.replace('</rdf:RDF>', (topic % endpoints) + '</rdf:RDF>')


@pytest.mark.parametrize("starts,ends,expected", [
    (0, 1, "M14.1"), (2, 1, "M14.1"), (1, 0, "M14.2"), (1, 2, "M14.2")],
    ids=["no-start", "two-starts", "no-end", "two-ends"])
def test_a_range_with_zero_or_two_endpoint_selectors_is_reported(tmp_path, starts, ends, expected):
    """rdfrelations_core_has-start-selector#1
    rdfrelations_core_has-end-selector#1
    Description: A range selector MUST reference one start and one end selector.
    """
    for requirement in ("rdfrelations_core_has-start-selector#1",
                        "rdfrelations_core_has-end-selector#1"):
        claiming = claimants(requirement)
        found = fired(tmp_path, "range_endpoints_bad.iirds", _endpoint_range(starts, ends))
        assert expected in found, (starts, ends, sorted(found))
        assert expected in claiming & found, (requirement, starts, ends, sorted(found))


def test_a_range_with_one_start_and_one_end_selector_passes(tmp_path):
    """rdfrelations_core_has-start-selector#1
    rdfrelations_core_has-end-selector#1
    Description: A range selector MUST reference one start and one end selector.
    """
    found = fired(tmp_path, "range_endpoints_ok.iirds", _endpoint_range(1, 1))
    assert not {"M14.1", "M14.2"} & found, sorted(found)


@pytest.mark.parametrize("classes", [
    ("Document", "Topic"), ("Rendition", "Selector"), ("ProductVariant", "Component")],
    ids=["information-unit-siblings", "top-level-classes", "product-metadata-siblings"])
def test_a_resource_typed_with_two_disjoint_classes_is_reported(tmp_path, classes):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    types = "".join('<rdf:type rdf:resource="%s%s"/>' % (IIRDS, cls) for cls in classes)
    metadata = with_nodes('<rdf:Description rdf:about="urn:test:mixed">%s</rdf:Description>'
                          % types)
    found = fired(tmp_path, "disjoint_bad.iirds", metadata)
    assert "R61" in found, (classes, sorted(found))
    assert "R61" in claimants("x6-11-1-disjointness#1") & found
    if importlib.util.find_spec("pyshacl") is not None:
        from test_shapes_parity import assert_parity
        assert "R61" in assert_parity(tmp_path, "disjoint_shape_bad.iirds", metadata)


def test_a_resource_typed_with_a_subclass_and_its_parent_is_not_disjoint(tmp_path):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    metadata = with_nodes(DOCUMENT % STANDARD +
                          '<rdf:Description rdf:about="urn:test:doc">'
                          '<rdf:type rdf:resource="%sInformationUnit"/>'
                          '</rdf:Description>' % IIRDS)
    found = fired(tmp_path, "disjoint_parent.iirds", metadata)
    assert "R61" not in found, sorted(found)
    if importlib.util.find_spec("pyshacl") is not None:
        from test_shapes_parity import assert_parity
        assert "R61" not in assert_parity(tmp_path, "disjoint_shape_parent.iirds", metadata)


def test_a_document_also_typed_as_a_topic_changes_the_exit_code(tmp_path):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    from iirds_validate.cli import main

    metadata = with_nodes(DOCUMENT % STANDARD)
    disjoint = metadata.replace('<iirds:Document rdf:about="urn:test:doc">',
                                '<iirds:Document rdf:about="urn:test:doc">'
                                '<rdf:type rdf:resource="%sTopic"/>' % IIRDS, 1)
    clean = build_package(tmp_path, "one_class.iirds", metadata=metadata)
    broken = build_package(tmp_path, "two_disjoint_classes.iirds", metadata=disjoint)
    report = runner.run(broken, runner.ALL_KINDS)
    assert {f.rule.id for f in report.findings if str(f.severity) == "error"} == {"R61"}
    assert main(["check", str(clean), "-q"]) == 0
    assert main(["check", str(broken), "-q"]) == 1


CORE = Namespace(IIRDS)
MACHINERY = Namespace("http://iirds.tekom.de/iirds/domain/machinery#")
HANDOVER = Namespace("http://iirds.tekom.de/iirds/domain/handover#")
EXAMPLE = Namespace("https://example.org/classes/")

# Types and declarations are input facts, separate from the implementation's
# hierarchy and conflict detector. The last field is the expected verdict.
DISJOINT_PROBES = [
    ("document-topic", (CORE.Document, CORE.Topic), (), True),
    ("topic-fragment", (CORE.Topic, CORE.Fragment), (), True),
    ("package-document", (CORE.Package, CORE.Document), (), True),
    ("product-siblings", (CORE.ProductVariant, CORE.Component), (), True),
    ("machinery-siblings", (MACHINERY.SetupTime, CORE.WorkingTime), (), True),
    ("handover-siblings", (HANDOVER.DocumentCategory, CORE.DocumentType), (), True),
    ("administrative-siblings", (CORE.Identity, CORE.Party), (), True),
    ("document-rendition", (CORE.Document, CORE.Rendition), (), True),
    ("topic-rendition", (CORE.Topic, CORE.Rendition), (), True),
    ("document-selector", (CORE.Document, CORE.FragmentSelector), (), True),
    ("document-concept", (CORE.Document, CORE.Concept), (), True),
    ("machinery-action", (MACHINERY.SetupTime, CORE.Action), (), True),
    ("proprietary-topic", (EXAMPLE.MyTopic, CORE.Document),
     ((EXAMPLE.MyTopic, RDFS.subClassOf, CORE.Topic),), True),
    ("proprietary-siblings", (EXAMPLE.FirstTopic, EXAMPLE.SecondTopic),
     ((EXAMPLE.FirstTopic, RDFS.subClassOf, CORE.Topic),
      (EXAMPLE.SecondTopic, RDFS.subClassOf, CORE.Topic)), True),
    ("parent-child", (CORE.Document, CORE.InformationUnit), (), False),
    ("external-class", (CORE.Document, EXAMPLE.Unrelated), (), False),
    ("repeated-type", (CORE.Document, CORE.Document), (), False),
    ("multiple-parents", (MACHINERY.ConsumableSupply,), (), False),
    ("equivalent-document", (EXAMPLE.AliasDocument, CORE.Document),
     ((EXAMPLE.AliasDocument, OWL.equivalentClass, CORE.Document),), False),
    ("equivalent-topic", (EXAMPLE.AliasTopic, CORE.Document),
     ((EXAMPLE.AliasTopic, OWL.equivalentClass, CORE.Topic),), True),
    ("transitive-extension", (EXAMPLE.LeafTopic, CORE.Document),
     ((EXAMPLE.LeafTopic, RDFS.subClassOf, EXAMPLE.MiddleTopic),
      (EXAMPLE.MiddleTopic, RDFS.subClassOf, CORE.Topic)), True),
    ("equivalent-parent", (EXAMPLE.FirstTopic, EXAMPLE.SecondTopic),
     ((EXAMPLE.FirstTopic, RDFS.subClassOf, EXAMPLE.TopicAlias),
      (EXAMPLE.TopicAlias, OWL.equivalentClass, CORE.Topic),
      (EXAMPLE.SecondTopic, RDFS.subClassOf, CORE.Topic)), True),
    ("equivalent-cycle", (EXAMPLE.AliasDocument, CORE.Document),
     ((EXAMPLE.AliasDocument, OWL.equivalentClass, EXAMPLE.OtherAlias),
      (EXAMPLE.OtherAlias, OWL.equivalentClass, CORE.Document),
      (CORE.Document, OWL.equivalentClass, EXAMPLE.AliasDocument)), False),
    ("subclass-cycle", (EXAMPLE.MyTopic, EXAMPLE.OtherTopic),
     ((EXAMPLE.MyTopic, RDFS.subClassOf, EXAMPLE.OtherTopic),
      (EXAMPLE.OtherTopic, RDFS.subClassOf, EXAMPLE.MyTopic),
      (EXAMPLE.MyTopic, RDFS.subClassOf, CORE.Topic)), False),
    ("outside-siblings", (EXAMPLE.FirstTopic, EXAMPLE.SecondTopic),
     ((EXAMPLE.FirstTopic, RDFS.subClassOf, EXAMPLE.Outside),
      (EXAMPLE.SecondTopic, RDFS.subClassOf, EXAMPLE.Outside)), False),
]


def _disjoint_probe_metadata(types, declarations=(), version="1.3"):
    graph = Graph().parse(data=MINIMAL_RDF, format="xml")
    package = URIRef("urn:test:package")
    graph.set((package, CORE.iiRDSVersion, Literal(version)))
    subject = package if CORE.Package in types else URIRef("urn:test:mixed")
    for cls in types:
        graph.add((subject, RDF.type, cls))
    # Ancillary properties must describe the same class as the probe resource.
    from iirds_validate.ontology import Ontology

    hierarchy = Ontology("1.3").graph
    for first, predicate, second in declarations:
        if predicate == RDFS.subClassOf:
            hierarchy.add((first, predicate, second))
        elif predicate == OWL.equivalentClass:
            hierarchy.add((first, RDFS.subClassOf, second))
            hierarchy.add((second, RDFS.subClassOf, first))
    classes = set().union(*(set(hierarchy.transitive_objects(cls, RDFS.subClassOf)) for cls in types))
    if CORE.InformationUnit in classes:
        graph.set((subject, CORE["title"], Literal("A resource")))
    graph.add((subject, RDFS.label, Literal("A resource", lang="en")))
    rendition = URIRef("urn:test:probe-rendition")
    if CORE.InformationUnit in classes and CORE.Package not in types:
        graph.add((subject, CORE["has-rendition"], rendition))
    graph.add((rendition, RDF.type, CORE.Rendition))
    for resource in ((subject, rendition) if CORE.Rendition in classes else (rendition,)):
        graph.add((resource, CORE["format"], Literal("application/xhtml+xml")))
        graph.add((resource, CORE.source, Literal("content/topic1.xhtml")))
    if CORE.Document in classes:
        graph.add((subject, CORE["has-document-type"], CORE.AssemblyInstructions))
    if CORE.Selector in classes:
        graph.add((subject, RDF.value, Literal("page=1")))
        graph.add((subject, DCTERMS.conformsTo, URIRef("http://tools.ietf.org/rfc/rfc3778")))
    if CORE.Identity in classes:
        graph.add((subject, CORE.identifier, Literal("resource-1")))
    domain = URIRef("urn:test:probe-domain")
    identity_type = URIRef("urn:test:probe-identity-type")
    if CORE.Identity in classes:
        graph.add((subject, CORE["has-identity-domain"], domain))
    graph.add((domain, RDF.type, CORE.IdentityDomain))
    graph.add((domain, RDFS.label, Literal("Identifier domain", lang="en")))
    graph.add((domain, CORE["has-identity-type"], identity_type))
    graph.add((identity_type, RDF.type, CORE.IdentityType))
    graph.add((identity_type, RDFS.label, Literal("Identifier type", lang="en")))
    if CORE.Party in classes:
        graph.add((subject, CORE["has-party-role"], CORE.Author))
    if CORE.Party in classes:
        card = URIRef("urn:test:probe-card")
        vcard = Namespace("http://www.w3.org/2006/vcard/ns#")
        graph.add((subject, CORE["relates-to-vcard"], card))
        graph.add((card, RDF.type, vcard.Individual))
        graph.add((card, vcard.fn, Literal("A person")))
    for triple in declarations:
        graph.add(triple)
    for cls in {node for triple in declarations for node in (triple[0], triple[2])
                if str(node).startswith(str(EXAMPLE))}:
        graph.add((cls, RDF.type, RDFS.Class))
        graph.add((cls, RDFS.label, Literal("Extension class", lang="en")))
    metadata = graph.serialize(format="xml")
    duplicates = {cls: types.count(cls) - 1 for cls in set(types) if types.count(cls) > 1}
    if duplicates:
        from copy import deepcopy
        from xml.etree.ElementTree import fromstring, tostring

        tree = fromstring(metadata)
        for description in tree:
            if description.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about") == str(subject):
                for statement in list(description):
                    if statement.tag == "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}type":
                        cls = URIRef(statement.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource"))
                        for _ in range(duplicates.get(cls, 0)):
                            description.append(deepcopy(statement))
        metadata = tostring(tree, encoding="unicode")
    return metadata


@pytest.mark.parametrize("name,types,declarations,expected", DISJOINT_PROBES,
                         ids=[probe[0] for probe in DISJOINT_PROBES])
def test_disjoint_probe_python(tmp_path, name, types, declarations, expected):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    metadata = _disjoint_probe_metadata(types, declarations)
    report = runner.run(build_package(tmp_path, name + ".iirds", metadata=metadata), runner.ALL_KINDS)
    found = {finding.rule.id for finding in report.findings}
    unrelated = {finding.rule.id for finding in report.findings
                 if str(finding.severity) == "error"} - {"R61"}
    # M1 forbids explicit InformationUnit even alongside its subclass. That
    # separate prohibition does not make the two classes disjoint.
    assert unrelated == ({"M1"} if CORE.InformationUnit in types else set()), (name, unrelated)
    assert ("R61" in found) is expected, (name, sorted(found))
    if expected:
        assert claimants("x6-11-1-disjointness#1") & found


@pytest.mark.parametrize("name,types,declarations,expected", DISJOINT_PROBES,
                         ids=[probe[0] for probe in DISJOINT_PROBES])
def test_disjoint_probe_shacl(tmp_path, name, types, declarations, expected):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    from conftest import shacl_or_skip
    shacl_or_skip()
    from test_shapes_parity import shacl_fired
    metadata = _disjoint_probe_metadata(types, declarations)
    found = fired(tmp_path, name + ".iirds", metadata)
    shacl = shacl_fired(metadata)
    assert ("R61" in shacl) == ("R61" in found) == expected, (name, sorted(found), sorted(shacl))


@pytest.mark.parametrize("version", ("1.0", "1.0.1", "1.1", "1.2", "1.3"))
def test_disjoint_probe_is_scoped_to_the_verified_edition(tmp_path, version):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    metadata = _disjoint_probe_metadata((CORE.Document, CORE.Topic), version=version)
    report = runner.run(build_package(tmp_path, "edition.iirds", metadata=metadata), runner.ALL_KINDS)
    assert ("R61" in {f.rule.id for f in report.findings}) == (version == "1.3")


def test_disjoint_probe_detail_names_types_and_disjoint_ancestors(tmp_path):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    metadata = _disjoint_probe_metadata((CORE.Document, CORE.Rendition))
    report = runner.run(build_package(tmp_path, "detail.iirds", metadata=metadata), runner.ALL_KINDS)
    details = [f.violation.detail for f in report.findings if f.rule.id == "R61"]
    assert len(details) == 1
    assert all(str(cls) in details[0] for cls in (CORE.Document, CORE.Rendition, CORE.InformationUnit))


@pytest.mark.parametrize("rule_id,endpoint", [("M14.1", "start"), ("M14.2", "end")])
def test_range_endpoint_titles_name_the_whole_joint_obligation(rule_id, endpoint):
    """rdfrelations_core_has-start-selector#1
    rdfrelations_core_has-end-selector#1
    Description: A range selector MUST reference one start and one end selector.
    """
    rule = next(rule for rule in all_rules() if rule.id == rule_id)
    assert rule.title == ("A RangeSelector MUST have exactly one iirds:has-start-selector "
                          "and one iirds:has-end-selector (%s check)" % endpoint)
    assert rule.fix == ("Add the missing endpoint selector, or keep one correct endpoint selector "
                        "if several are present. A range needs one start and one end to select "
                        "a definite portion of the content.")


def test_joint_endpoint_titles_do_not_hide_an_unrelated_property(monkeypatch):
    """Joint endpoint claims leave the crossed purpose/dateOfStatus title detectable."""
    from dataclasses import replace

    import test_cardinality_rules_fire as cardinality

    rules = [replace(rule, title="MUST NOT have more than one property iirds:purpose")
             if rule.id == "M21.4" else rule for rule in all_rules()]
    monkeypatch.setattr(cardinality, "all_rules", lambda: rules)
    with pytest.raises(AssertionError, match="purpose"):
        cardinality.test_a_cardinality_rule_names_the_property_it_reads()


def test_repeated_type_probe_contains_two_explicit_statements():
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    from xml.etree.ElementTree import fromstring

    metadata = _disjoint_probe_metadata((CORE.Document, CORE.Document))
    written = [node for node in fromstring(metadata).iter("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}type")
               if node.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource") == str(CORE.Document)]
    assert len(written) == 2
    graph = Graph().parse(data=metadata, format="xml")
    assert set(graph.objects(URIRef("urn:test:mixed"), RDF.type)) == {CORE.Document}


MIXED_DECLARATIONS = ((EXAMPLE.Mixed, RDFS.subClassOf, CORE.Document),
                      (EXAMPLE.Mixed, RDFS.subClassOf, CORE.Topic))
DISJOINT_CLOSURE_PROBES = [
    ("mixed-single", (EXAMPLE.Mixed,), MIXED_DECLARATIONS, True,
     (CORE.Document, CORE.Topic)),
    ("mixed-with-parent", (EXAMPLE.Mixed, CORE.Document), MIXED_DECLARATIONS, True,
     (CORE.Document, CORE.Topic)),
    ("ordinary-parent-child", (CORE.Document, CORE.InformationUnit), (), False, ()),
    ("rdfs-equivalent-mixed", (EXAMPLE.First,),
     ((EXAMPLE.First, RDFS.subClassOf, EXAMPLE.Second),
      (EXAMPLE.Second, RDFS.subClassOf, EXAMPLE.First),
      (EXAMPLE.First, RDFS.subClassOf, CORE.Topic),
      (EXAMPLE.Second, RDFS.subClassOf, CORE.Document)), True, (CORE.Document, CORE.Topic)),
    ("deep-mixed", (EXAMPLE.MixedProduct,),
     ((EXAMPLE.MixedProduct, RDFS.subClassOf, CORE.ProductVariant),
      (EXAMPLE.MixedProduct, RDFS.subClassOf, CORE.Component)), True,
     (CORE.ProductVariant, CORE.Component)),
    ("comparable-siblings", (EXAMPLE.Child,),
     ((EXAMPLE.Parent, RDFS.subClassOf, CORE.Topic),
      (EXAMPLE.Child, RDFS.subClassOf, CORE.Topic),
      (EXAMPLE.Child, RDFS.subClassOf, EXAMPLE.Parent)), False, ()),
    ("equivalent-mixed", (EXAMPLE.MixedAlias,),
     MIXED_DECLARATIONS + ((EXAMPLE.MixedAlias, OWL.equivalentClass, EXAMPLE.Mixed),),
     True, (CORE.Document, CORE.Topic)),
    ("mixed-roots", (EXAMPLE.MixedRoots,),
     ((EXAMPLE.MixedRoots, RDFS.subClassOf, CORE.Document),
      (EXAMPLE.MixedRoots, RDFS.subClassOf, CORE.Rendition)), True,
     (CORE.InformationUnit, CORE.Rendition)),
]


@pytest.mark.parametrize("name,types,declarations,expected,basis", DISJOINT_CLOSURE_PROBES,
                         ids=[probe[0] for probe in DISJOINT_CLOSURE_PROBES])
def test_disjoint_closure_python(tmp_path, name, types, declarations, expected, basis):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    metadata = _disjoint_probe_metadata(types, declarations)
    report = runner.run(build_package(tmp_path, name + ".iirds", metadata=metadata), runner.ALL_KINDS)
    findings = [f for f in report.findings if f.rule.id == "R61"]
    assert len(findings) == int(expected), (name, findings)
    unrelated = {f.rule.id for f in report.findings
                 if str(f.severity) == "error"} - {"R61"}
    assert unrelated == ({"M1"} if CORE.InformationUnit in types else set())
    if expected:
        detail = findings[0].violation.detail
        assert all(str(cls) in detail for cls in (*types, *basis)), detail
        assert "explicit type(s)" in detail and "disjoint ancestors" in detail, detail
        assert "->" in detail, detail


@pytest.mark.parametrize("name,types,declarations,expected,basis", DISJOINT_CLOSURE_PROBES,
                         ids=[probe[0] for probe in DISJOINT_CLOSURE_PROBES])
def test_disjoint_closure_shacl(tmp_path, name, types, declarations, expected, basis):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    from conftest import shacl_or_skip
    pyshacl = shacl_or_skip()
    from test_shapes_parity import CORE as SHAPES
    from test_shapes_parity import SH

    metadata = _disjoint_probe_metadata(types, declarations)
    python = fired(tmp_path, name + ".iirds", metadata)
    _ok, results, _text = pyshacl.validate(Graph().parse(data=metadata, format="xml"),
                                         shacl_graph=SHAPES, advanced=True, inference="none")
    r61 = {result for result, _p, source in results.triples((None, SH.sourceShape, None))
           if str(source).rsplit("#", 1)[-1] == "R61"}
    assert len(r61) == int(expected), (name, _text)
    assert ("R61" in python) == bool(r61) == expected


@pytest.mark.parametrize("version", ("1.0", "1.0.1", "1.1", "1.2"))
def test_disjoint_closure_keeps_previous_editions_silent_python(tmp_path, version):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    metadata = _disjoint_probe_metadata((EXAMPLE.Mixed,), MIXED_DECLARATIONS, version=version)
    assert "R61" not in fired(tmp_path, "mixed-old.iirds", metadata)


@pytest.mark.parametrize("version", ("1.0", "1.0.1", "1.1", "1.2"))
def test_disjoint_closure_keeps_previous_editions_silent_shacl(tmp_path, version):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    from conftest import shacl_or_skip
    shacl_or_skip()
    from test_shapes_parity import _applicable, shacl_fired

    metadata = _disjoint_probe_metadata((EXAMPLE.Mixed,), MIXED_DECLARATIONS, version=version)
    python = fired(tmp_path, "mixed-old.iirds", metadata)
    raw = shacl_fired(metadata)
    # Shapes encode 1.3; the repository compares rules applicable to the edition.
    assert "R61" in raw
    applicable = raw & _applicable(version, "")
    assert ("R61" in applicable) == ("R61" in python)
    assert "R61" not in applicable


@pytest.mark.parametrize("declares_subclass", [False, True], ids=["bundled", "package-axioms"])
def test_disjoint_closure_uses_package_functions_only_for_package_axioms(monkeypatch,
                                                                       declares_subclass):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    from conftest import shacl_or_skip
    pyshacl = shacl_or_skip()
    from test_shapes_parity import CORE as SHAPES
    from test_shapes_parity import SH

    declarations = ((EXAMPLE.Outside, RDFS.subClassOf, EXAMPLE.Other),) if declares_subclass else ()
    graph = Graph().parse(data=_disjoint_probe_metadata((CORE.Document,), declarations), format="xml")
    original_query = Graph.query
    package_functions = []

    def observed_query(self, query, *args, **kwargs):
        if "cls" in (kwargs.get("initBindings") or {}):
            package_functions.append(query)
        return original_query(self, query, *args, **kwargs)

    monkeypatch.setattr(Graph, "query", observed_query)
    _ok, results, _text = pyshacl.validate(graph, shacl_graph=SHAPES,
                                         advanced=True, inference="none")
    assert not any(str(source).rsplit("#", 1)[-1] == "R61"
                   for _result, _p, source in results.triples((None, SH.sourceShape, None)))
    assert bool(package_functions) == declares_subclass


MEMBERSHIP_SUBJECT = URIRef("urn:test:membership")
MEMBERSHIP_PACKAGE = URIRef("urn:test:package")
MEMBERSHIP_SCHEMA = Namespace("https://schema.org/")
DISJOINT_MEMBERSHIP_PROBES = [
    ("domain", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (MEMBERSHIP_SUBJECT, CORE["format"], Literal("text/html"))), True, "domain", CORE["format"]),
    ("range", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.Holder, CORE["has-rendition"], MEMBERSHIP_SUBJECT)), True, "range", CORE["has-rendition"]),
    ("subproperty", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.renderFormat, RDFS.subPropertyOf, CORE["format"]),
      (MEMBERSHIP_SUBJECT, EXAMPLE.renderFormat, Literal("text/html"))),
     True, "subPropertyOf", EXAMPLE.renderFormat),
    ("root-cycle", MEMBERSHIP_PACKAGE,
     ((MEMBERSHIP_PACKAGE, RDF.type, EXAMPLE.RootAlias),
      (EXAMPLE.RootAlias, RDFS.subClassOf, CORE.InformationUnit),
      (EXAMPLE.RootAlias, RDFS.subClassOf, CORE.Rendition),
      (CORE.InformationUnit, RDFS.subClassOf, EXAMPLE.RootAlias)), True, "explicit", EXAMPLE.RootAlias),
    ("root-equivalence", MEMBERSHIP_PACKAGE,
     ((CORE.InformationUnit, OWL.equivalentClass, CORE.Rendition),), True, "explicit", CORE.Package),
    ("rendition-format", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Rendition),
      (MEMBERSHIP_SUBJECT, CORE["format"], Literal("text/html"))), False, "", CORE["format"]),
    ("no-domain", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (MEMBERSHIP_SUBJECT, EXAMPLE.freeProperty, Literal("text/html"))), False, "", EXAMPLE.freeProperty),
    ("datatype-range", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.Holder, CORE["format"], MEMBERSHIP_SUBJECT)), False, "", CORE["format"]),
    ("domain-includes", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.renderFormat, MEMBERSHIP_SCHEMA.domainIncludes, CORE.Rendition),
      (MEMBERSHIP_SUBJECT, EXAMPLE.renderFormat, Literal("text/html"))), False, "", EXAMPLE.renderFormat),
    ("package-domain", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.renderFormat, RDFS.domain, CORE.Rendition),
      (MEMBERSHIP_SUBJECT, EXAMPLE.renderFormat, Literal("text/html"))), True, "domain", EXAMPLE.renderFormat),
    ("package-range", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.renderLink, RDFS.range, CORE.Rendition),
      (EXAMPLE.Holder, EXAMPLE.renderLink, MEMBERSHIP_SUBJECT)), True, "range", EXAMPLE.renderLink),
    ("inferred-only", MEMBERSHIP_SUBJECT,
     ((EXAMPLE.documentProperty, RDFS.domain, CORE.Document),
      (EXAMPLE.renderProperty, RDFS.domain, CORE.Rendition),
      (MEMBERSHIP_SUBJECT, EXAMPLE.documentProperty, Literal("document")),
      (MEMBERSHIP_SUBJECT, EXAMPLE.renderProperty, Literal("rendition"))), True, "domain", EXAMPLE.renderProperty),
    ("subproperty-cycle", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.renderFormat, RDFS.subPropertyOf, EXAMPLE.parentFormat),
      (EXAMPLE.parentFormat, RDFS.subPropertyOf, EXAMPLE.renderFormat),
      (EXAMPLE.parentFormat, RDFS.subPropertyOf, CORE["format"]),
      (MEMBERSHIP_SUBJECT, EXAMPLE.renderFormat, Literal("text/html"))),
     True, "subPropertyOf", EXAMPLE.renderFormat),
    ("custom-datatype", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.TextType, RDF.type, RDFS.Datatype),
      (EXAMPLE.renderLink, RDFS.range, EXAMPLE.TextType),
      (EXAMPLE.Holder, EXAMPLE.renderLink, MEMBERSHIP_SUBJECT)), False, "", EXAMPLE.renderLink),
    ("xsd-datatype", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.renderLink, RDFS.range, URIRef("http://www.w3.org/2001/XMLSchema#string")),
      (EXAMPLE.Holder, EXAMPLE.renderLink, MEMBERSHIP_SUBJECT)), False, "", EXAMPLE.renderLink),
    ("literal-range", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.renderLink, RDFS.range, Literal("Rendition")),
      (EXAMPLE.Holder, EXAMPLE.renderLink, MEMBERSHIP_SUBJECT)), False, "", EXAMPLE.renderLink),
    ("same-as", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (EXAMPLE.OtherResource, RDF.type, CORE.Rendition),
      (MEMBERSHIP_SUBJECT, OWL.sameAs, EXAMPLE.OtherResource)), False, "", OWL.sameAs),
    ("explicit-siblings", MEMBERSHIP_SUBJECT,
     ((MEMBERSHIP_SUBJECT, RDF.type, CORE.Document),
      (MEMBERSHIP_SUBJECT, RDF.type, CORE.Topic)), True, "explicit", CORE.Document),
]


def _disjoint_membership_metadata(triples):
    graph = Graph()
    graph.add((MEMBERSHIP_PACKAGE, RDF.type, CORE.Package))
    graph.add((MEMBERSHIP_PACKAGE, CORE.iiRDSVersion, Literal("1.3")))
    graph.add((MEMBERSHIP_PACKAGE, CORE.title, Literal("Package")))
    for triple in triples:
        graph.add(triple)
    return graph.serialize(format="xml")


@pytest.mark.parametrize("name,subject,triples,expected,path,property_", DISJOINT_MEMBERSHIP_PROBES,
                         ids=[probe[0] for probe in DISJOINT_MEMBERSHIP_PROBES])
def test_disjoint_membership_python(tmp_path, name, subject, triples, expected, path, property_):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    metadata = _disjoint_membership_metadata(triples)
    report = runner.run(build_package(tmp_path, name + ".iirds", metadata=metadata), runner.ALL_KINDS)
    findings = [f for f in report.findings if f.rule.id == "R61"]
    assert len(findings) == int(expected), (name, findings)
    if expected:
        assert findings[0].violation.subject == str(subject)
        detail = findings[0].violation.detail
        assert path in detail and str(property_) in detail, detail
        assert "disjoint ancestors" in detail
        if name != "explicit-siblings":
            assert all(str(cls) in detail for cls in (CORE.InformationUnit, CORE.Rendition)), detail
        assert claimants("x6-11-1-disjointness#1") & {f.rule.id for f in findings}


@pytest.mark.parametrize("name,subject,triples,expected,path,property_", DISJOINT_MEMBERSHIP_PROBES,
                         ids=[probe[0] for probe in DISJOINT_MEMBERSHIP_PROBES])
def test_disjoint_membership_shacl(tmp_path, name, subject, triples, expected, path, property_):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    from conftest import shacl_or_skip
    pyshacl = shacl_or_skip()
    from test_shapes_parity import CORE as SHAPES
    from test_shapes_parity import SH

    metadata = _disjoint_membership_metadata(triples)
    found = fired(tmp_path, name + ".iirds", metadata)
    _ok, results, text = pyshacl.validate(Graph().parse(data=metadata, format="xml"),
                                        shacl_graph=SHAPES, advanced=True, inference="none")
    r61 = {result for result, _p, source in results.triples((None, SH.sourceShape, None))
           if str(source).rsplit("#", 1)[-1] == "R61"}
    assert len(r61) == int(expected), (name, text)
    if expected:
        assert {results.value(result, SH.value) for result in r61} == {subject}
    assert ("R61" in found) == bool(r61) == expected


DISJOINT_RDFS7_PROBES = [
    ("type-alias", EXAMPLE.x,
     ((EXAMPLE.asType, RDFS.subPropertyOf, RDF.type),
      (EXAMPLE.asType, RDFS.subPropertyOf, CORE.iirdsAttribute),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Document),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Topic)),
     (CORE.Document, CORE.Topic), "subPropertyOf", True),
    ("domain-alias", EXAMPLE.d,
     ((EXAMPLE.dom, RDFS.subPropertyOf, RDFS.domain),
      (EXAMPLE.p, EXAMPLE.dom, CORE.Rendition),
      (EXAMPLE.d, RDF.type, CORE.Document),
      (EXAMPLE.d, EXAMPLE.p, Literal("x"))),
     (CORE.InformationUnit, CORE.Rendition), "domain", True),
    ("bundled-conflict", CORE.Creator,
     ((EXAMPLE.x, RDF.type, CORE.Document),
      (EXAMPLE.x, CORE["has-document-type"], CORE.Creator)),
     (CORE.AdministrativeMetadata, CORE.InformationType), "bundled", True),
    ("type-compatible", EXAMPLE.x,
     ((EXAMPLE.asType, RDFS.subPropertyOf, RDF.type),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Document)), (), "", True),
    ("domain-compatible", EXAMPLE.d,
     ((EXAMPLE.dom, RDFS.subPropertyOf, RDFS.domain),
      (EXAMPLE.p, EXAMPLE.dom, CORE.Document),
      (EXAMPLE.d, RDF.type, CORE.Document),
      (EXAMPLE.d, EXAMPLE.p, Literal("x"))), (), "", True),
    ("bundled-compatible", CORE.Creator,
     ((EXAMPLE.party, CORE["has-party-role"], CORE.Creator),), (), "", True),
    ("range-alias", EXAMPLE.d,
     ((EXAMPLE.ran, RDFS.subPropertyOf, RDFS.range),
      (EXAMPLE.p, EXAMPLE.ran, CORE.Rendition),
      (EXAMPLE.d, RDF.type, CORE.Document),
      (EXAMPLE.holder, EXAMPLE.p, EXAMPLE.d)),
     (CORE.InformationUnit, CORE.Rendition), "range", True),
    ("class-alias", EXAMPLE.x,
     ((EXAMPLE.extends, RDFS.subPropertyOf, RDFS.subClassOf),
      (EXAMPLE.Mixed, EXAMPLE.extends, CORE.Document),
      (EXAMPLE.Mixed, EXAMPLE.extends, CORE.Topic),
      (EXAMPLE.x, RDF.type, EXAMPLE.Mixed)),
     (CORE.Document, CORE.Topic), "explicit", False),
    ("property-alias-fixed-point", EXAMPLE.x,
     ((EXAMPLE.edge, RDFS.subPropertyOf, RDFS.subPropertyOf),
      (EXAMPLE.asType, EXAMPLE.edge, RDF.type),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Document),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Topic)),
     (CORE.Document, CORE.Topic), "subPropertyOf", False),
    ("domain-fixed-point", EXAMPLE.d,
     ((EXAMPLE.edge, RDFS.subPropertyOf, RDFS.subPropertyOf),
      (EXAMPLE.dom, EXAMPLE.edge, RDFS.domain),
      (EXAMPLE.p, EXAMPLE.dom, CORE.Rendition),
      (EXAMPLE.d, RDF.type, CORE.Document),
      (EXAMPLE.d, EXAMPLE.p, Literal("x"))),
     (CORE.InformationUnit, CORE.Rendition), "domain", False),
]


@pytest.mark.parametrize("name,subject,triples,witnesses,origin,supported", DISJOINT_RDFS7_PROBES,
                         ids=[probe[0] for probe in DISJOINT_RDFS7_PROBES])
def test_disjoint_rdfs7_python(tmp_path, name, subject, triples, witnesses, origin, supported):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    package = build_package(tmp_path, name + ".iirds", metadata=_disjoint_membership_metadata(triples))
    report = runner.run(package, runner.ALL_KINDS)
    findings = [finding for finding in report.findings if finding.rule.id == "R61"]
    assert len(findings) == bool(witnesses), (name, findings)
    if witnesses:
        assert findings[0].violation.subject == str(subject)
        detail = findings[0].violation.detail
        assert all(str(cls) in detail for cls in witnesses), detail
        assert origin in detail, detail
        if name == "type-alias":
            assert str(EXAMPLE.asType) in detail
        if name == "bundled-conflict":
            assert str(CORE.PartyRole) in detail and str(CORE["has-document-type"]) in detail
        assert claimants("x6-11-1-disjointness#1") & {finding.rule.id for finding in findings}


@pytest.mark.parametrize("name,subject,triples,witnesses,origin,supported", DISJOINT_RDFS7_PROBES,
                         ids=[probe[0] for probe in DISJOINT_RDFS7_PROBES])
def test_disjoint_rdfs7_shacl(tmp_path, name, subject, triples, witnesses, origin, supported):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    from pathlib import Path

    from conftest import shacl_or_skip
    pyshacl = shacl_or_skip()
    from test_shapes_parity import CORE as SHAPES
    from test_shapes_parity import SH

    metadata = _disjoint_membership_metadata(triples)
    python = fired(tmp_path, name + ".iirds", metadata)
    _ok, results, text = pyshacl.validate(Graph().parse(data=metadata, format="xml"),
                                        shacl_graph=SHAPES, advanced=True, inference="none")
    found = {result for result, _p, source in results.triples((None, SH.sourceShape, None))
             if str(source).rsplit("#", 1)[-1] == "R61"}
    if supported:
        assert len(found) == bool(witnesses), (name, text)
        if witnesses:
            assert {results.value(result, SH.value) for result in found} == {subject}
        assert ("R61" in python) == bool(found) == bool(witnesses)
    else:
        # These schema paths require normalization beyond the emitted query.
        # The named counterexamples pin the documented partial SHACL support.
        readme = (Path(__file__).resolve().parents[1] / "shapes/README.md").read_text()
        assert "rdfs7 schema normalization" in readme
        assert "R61" in python and not found, (name, text)


def test_disjoint_rdfs7_facts_leave_the_package_graph_unchanged(tmp_path):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.
    """
    from iirds_validate.context import load_context
    from iirds_validate.package import Package
    from iirds_validate.rules.schema import r61_disjoint_classes_have_no_common_instance

    probe = next(probe for probe in DISJOINT_RDFS7_PROBES if probe[0] == "property-alias-fixed-point")
    package = build_package(tmp_path, "unchanged.iirds", metadata=_disjoint_membership_metadata(probe[2]))
    with Package(package) as opened:
        ctx = load_context(opened)
        before = set(ctx.graph)
        findings = list(r61_disjoint_classes_have_no_common_instance(ctx))
        assert len(findings) == 1
        assert set(ctx.graph) == before
        assert (EXAMPLE.x, RDF.type, CORE.Document) not in ctx.graph


DISJOINT_FIXED_POINT_PROBES = [
    ("rdfs2-feedback", EXAMPLE.x,
     ((RDF.type, RDFS.subPropertyOf, RDFS.subPropertyOf),
      (EXAMPLE.declare, RDFS.domain, RDF.type),
      (EXAMPLE.asType, EXAMPLE.declare, EXAMPLE.marker),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Document),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Topic)), True, False),
    ("rdfs5-feedback", EXAMPLE.p,
     ((RDFS.subPropertyOf, RDFS.subPropertyOf, RDF.type),
      (EXAMPLE.p, RDFS.subPropertyOf, EXAMPLE.q),
      (EXAMPLE.q, RDFS.subPropertyOf, CORE.Document),
      (EXAMPLE.p, RDF.type, CORE.Topic)), True, False),
    ("datatype-branch", EXAMPLE.x,
     ((EXAMPLE.DocValue, RDF.type, RDFS.Datatype),
      (EXAMPLE.DocValue, RDFS.subClassOf, CORE.Document),
      (EXAMPLE.prop, RDFS.range, EXAMPLE.DocValue),
      (EXAMPLE.holder, EXAMPLE.prop, EXAMPLE.x),
      (EXAMPLE.x, RDF.type, CORE.Topic)), True, False),
    ("joint-feedback", EXAMPLE.p,
     ((RDF.type, RDFS.subPropertyOf, RDFS.subPropertyOf),
      (RDFS.subPropertyOf, RDFS.subPropertyOf, RDF.type),
      (EXAMPLE.declare, RDFS.domain, EXAMPLE.Meta),
      (EXAMPLE.Meta, RDFS.subClassOf, RDFS.subPropertyOf),
      (EXAMPLE.asSchema, EXAMPLE.declare, EXAMPLE.marker),
      (EXAMPLE.p, EXAMPLE.asSchema, EXAMPLE.q),
      (EXAMPLE.q, RDFS.subPropertyOf, CORE.Document),
      (EXAMPLE.p, RDF.type, CORE.Topic)), True, False),
    ("literal-object", EXAMPLE.holder,
     ((EXAMPLE.prop, RDFS.range, CORE.Document),
      (EXAMPLE.prop, RDFS.range, CORE.Topic),
      (EXAMPLE.holder, EXAMPLE.prop, Literal("value"))), False, True),
    ("ordinary-xsd", EXAMPLE.x,
     ((EXAMPLE.prop, RDFS.range, URIRef("http://www.w3.org/2001/XMLSchema#string")),
      (EXAMPLE.holder, EXAMPLE.prop, EXAMPLE.x),
      (EXAMPLE.x, RDF.type, CORE.Topic)), False, True),
    ("unconnected-metamodel", EXAMPLE.x,
     ((RDF.type, RDFS.subPropertyOf, RDFS.subPropertyOf),
      (EXAMPLE.declare, RDFS.domain, EXAMPLE.Meta),
      (EXAMPLE.Meta, RDFS.subClassOf, EXAMPLE.ParentMeta),
      (EXAMPLE.asType, EXAMPLE.declare, EXAMPLE.marker),
      (EXAMPLE.x, EXAMPLE.asType, EXAMPLE.External)), False, True),
    ("rdfs3-feedback", EXAMPLE.x,
     ((RDF.type, RDFS.subPropertyOf, RDFS.subPropertyOf),
      (EXAMPLE.declare, RDFS.range, RDF.type),
      (EXAMPLE.marker, EXAMPLE.declare, EXAMPLE.asType),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Document),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Topic)), True, False),
    ("rdfs9-feedback", EXAMPLE.x,
     ((RDF.type, RDFS.subPropertyOf, RDFS.subPropertyOf),
      (EXAMPLE.asType, RDF.type, EXAMPLE.Meta),
      (EXAMPLE.Meta, RDFS.subClassOf, RDF.type),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Document),
      (EXAMPLE.x, EXAMPLE.asType, CORE.Topic)), True, False),
    ("rdfs11-feedback", EXAMPLE.x,
     ((RDFS.subClassOf, RDFS.subPropertyOf, RDF.type),
      (EXAMPLE.x, RDFS.subClassOf, EXAMPLE.Middle),
      (EXAMPLE.Middle, RDFS.subClassOf, CORE.Document),
      (EXAMPLE.x, RDF.type, CORE.Topic)), True, True),
    ("rdfs1-feedback", URIRef("http://www.w3.org/2001/XMLSchema#string"),
     ((RDFS.Datatype, RDFS.subClassOf, CORE.Document),
      (URIRef("http://www.w3.org/2001/XMLSchema#string"), RDF.type, CORE.Topic)), True, False),
    ("rdfs4-feedback", EXAMPLE.x,
     ((RDFS.Resource, RDFS.subClassOf, CORE.Document),
      (RDFS.Resource, RDFS.subClassOf, CORE.Rendition),
      (EXAMPLE.x, EXAMPLE.p, EXAMPLE.y)), True, False),
    ("rdfs6-feedback", EXAMPLE.p,
     ((EXAMPLE.p, RDF.type, RDF.Property),
      (EXAMPLE.p, RDF.type, CORE.Topic),
      (RDFS.subPropertyOf, RDFS.domain, CORE.Document)), True, False),
    ("rdfs8-feedback", EXAMPLE.ValueClass,
     ((EXAMPLE.ValueClass, RDF.type, RDFS.Class),
      (EXAMPLE.ValueClass, RDF.type, CORE.Topic),
      (RDFS.subClassOf, RDFS.range, CORE.Document),
      (EXAMPLE.ValueClass, RDFS.domain, CORE.Document)), True, False),
    ("rdfs10-feedback", EXAMPLE.ValueClass,
     ((EXAMPLE.ValueClass, RDF.type, RDFS.Class),
      (EXAMPLE.ValueClass, RDF.type, CORE.Topic),
      (RDFS.subClassOf, RDFS.subPropertyOf, RDF.type),
      (EXAMPLE.ValueClass, RDFS.subClassOf, CORE.Document)), True, True),
    ("rdfs12-feedback", EXAMPLE.x,
     ((EXAMPLE.prop, RDF.type, RDFS.ContainerMembershipProperty),
      (RDFS.member, RDFS.domain, CORE.Document),
      (EXAMPLE.x, EXAMPLE.prop, Literal("member")),
      (EXAMPLE.x, RDF.type, CORE.Topic)), True, False),
    ("rdfs13-feedback", EXAMPLE.x,
     ((EXAMPLE.ValueType, RDF.type, RDFS.Datatype),
      (RDFS.Literal, RDFS.subClassOf, CORE.Document),
      (EXAMPLE.x, RDF.type, EXAMPLE.ValueType),
      (EXAMPLE.x, RDF.type, CORE.Topic)), True, False),
]


@pytest.mark.parametrize("name,subject,triples,expected,supported", DISJOINT_FIXED_POINT_PROBES,
                         ids=[probe[0] for probe in DISJOINT_FIXED_POINT_PROBES])
def test_disjoint_fixed_point_python(tmp_path, name, subject, triples, expected, supported):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.

    RDFS entailment patterns may feed type and schema consequences into each other.
    """
    package = build_package(tmp_path, name + ".iirds", metadata=_disjoint_membership_metadata(triples))
    report = runner.run(package, runner.ALL_KINDS)
    all_r61 = [finding for finding in report.findings if finding.rule.id == "R61"]
    findings = [finding for finding in all_r61 if finding.violation.subject == str(subject)]
    assert len(findings) == int(expected), (name, all_r61)
    if expected:
        detail = findings[0].violation.detail
        witnesses = (CORE.InformationUnit, CORE.Rendition) if name == "rdfs4-feedback" else (CORE.Document, CORE.Topic)
        assert all(str(cls) in detail for cls in witnesses), detail
        assert claimants("x6-11-1-disjointness#1") & {finding.rule.id for finding in findings}
        if name in {"rdfs2-feedback", "rdfs5-feedback", "datatype-branch", "joint-feedback"}:
            assert len(all_r61) == 1, all_r61
    else:
        assert not all_r61, all_r61


@pytest.mark.parametrize("name,subject,triples,expected,supported", DISJOINT_FIXED_POINT_PROBES,
                         ids=[probe[0] for probe in DISJOINT_FIXED_POINT_PROBES])
def test_disjoint_fixed_point_shacl(tmp_path, name, subject, triples, expected, supported):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.

    The generated query has partial support; it does not materialize an RDFS fixed point.
    """
    from pathlib import Path

    from conftest import shacl_or_skip
    pyshacl = shacl_or_skip()
    from test_shapes_parity import CORE as SHAPES
    from test_shapes_parity import SH

    metadata = _disjoint_membership_metadata(triples)
    python = fired(tmp_path, name + ".iirds", metadata)
    _ok, results, text = pyshacl.validate(Graph().parse(data=metadata, format="xml"),
                                        shacl_graph=SHAPES, advanced=True, inference="none")
    found = {result for result, _p, source in results.triples((None, SH.sourceShape, None))
             if str(source).rsplit("#", 1)[-1] == "R61"}
    if supported:
        assert ("R61" in python) == bool(found) == expected, (name, text)
    else:
        readme = (Path(__file__).resolve().parents[1] / "shapes/README.md").read_text()
        assert name in readme, name
        assert "R61" in python and not found, (name, text)


def test_disjoint_fixed_point_schema_consequences_are_reusable(tmp_path):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.

    RDFS transitive schema conclusions must exist as facts for later rules.
    """
    from iirds_validate.context import load_context
    from iirds_validate.package import Package
    from iirds_validate.rules.schema import (
        _disjoint_rdfs_facts,
        r61_disjoint_classes_have_no_common_instance,
    )

    probe = next(probe for probe in DISJOINT_FIXED_POINT_PROBES if probe[0] == "rdfs5-feedback")
    triples = probe[2] + ((EXAMPLE.A, RDFS.subClassOf, EXAMPLE.B),
                         (EXAMPLE.B, RDFS.subClassOf, EXAMPLE.C),
                         (EXAMPLE.ValueClass, RDF.type, RDFS.Class),
                         (EXAMPLE.Property, RDF.type, RDF.Property),
                         (RDFS.subClassOf, RDF.type, RDF.Property))
    package = build_package(tmp_path, "schema-consequences.iirds",
                            metadata=_disjoint_membership_metadata(triples))
    with Package(package) as opened:
        ctx = load_context(opened)
        before = set(ctx.graph)
        facts, _origins, direct = _disjoint_rdfs_facts(ctx)
        assert (EXAMPLE.p, RDFS.subPropertyOf, CORE.Document) in facts
        assert (EXAMPLE.p, RDF.type, CORE.Document) in facts
        assert (EXAMPLE.A, RDFS.subClassOf, EXAMPLE.C) in facts
        assert (EXAMPLE.ValueClass, RDFS.subClassOf, RDFS.Resource) in facts
        assert (EXAMPLE.ValueClass, RDFS.subClassOf, EXAMPLE.ValueClass) in facts
        assert (EXAMPLE.Property, RDFS.subPropertyOf, EXAMPLE.Property) in facts
        assert (EXAMPLE.A, EXAMPLE.C) not in direct
        findings = list(r61_disjoint_classes_have_no_common_instance(ctx))
        assert len(findings) == 1 and findings[0].subject == str(EXAMPLE.p)
        assert set(ctx.graph) == before


def _rdfs2_bundled_statement_metadata(ordinary_domain=False):
    domain = ((CORE["has-party-role"], RDFS.domain, CORE.Party) if ordinary_domain else
              (RDF.type, RDFS.domain, CORE.InformationUnit))
    return _disjoint_membership_metadata(((EXAMPLE.party, CORE["has-party-role"], CORE.Creator), domain))


def _rdfs2_bundled_statement_findings(tmp_path, ordinary_domain=False):
    metadata = _rdfs2_bundled_statement_metadata(ordinary_domain)
    package = build_package(tmp_path, "bundled-statement.iirds", metadata=metadata)
    return [finding for finding in runner.run(package, runner.ALL_KINDS).findings
            if finding.rule.id == "R61"]


def test_rdfs2_bundled_statement_reports_each_common_instance(tmp_path):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.

    RDFS rdfs2 applies rdf:type's domain to bundled and entailed type statements.
    """
    from pathlib import Path

    findings = _rdfs2_bundled_statement_findings(tmp_path)
    assert len(findings) == 2, findings
    by_subject = {finding.violation.subject: finding for finding in findings}
    assert set(by_subject) == {str(CORE.Creator), str(EXAMPLE.party)}
    for subject in (CORE.Creator, EXAMPLE.party):
        detail = by_subject[str(subject)].violation.detail
        assert "inferred from the domain of " + str(RDF.type) in detail, detail
        assert all(str(cls) in detail for cls in (CORE.AdministrativeMetadata, CORE.InformationUnit)), detail
    assert "known from the bundled type of " + str(CORE.Creator) in by_subject[str(CORE.Creator)].violation.detail
    assert "inferred from the domain of " + str(CORE["has-party-role"]) in by_subject[str(EXAMPLE.party)].violation.detail
    assert claimants("x6-11-1-disjointness#1") & {finding.rule.id for finding in findings}
    readme = (Path(__file__).resolve().parents[1] / "shapes/README.md").read_text()
    assert "| `bundled-domain` |" in readme
    feedback = next(line for line in readme.splitlines() if line.startswith("| `rdfs2-feedback` |"))
    assert "party" in feedback


def test_rdfs2_bundled_statement_ordinary_domain_is_compatible(tmp_path):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.

    An ordinary Party domain preserves compatible AdministrativeMetadata types.
    """
    assert not _rdfs2_bundled_statement_findings(tmp_path, ordinary_domain=True)


@pytest.mark.parametrize("ordinary_domain", [False, True], ids=["bundled-domain", "ordinary-domain"])
def test_rdfs2_bundled_statement_comparison(tmp_path, ordinary_domain):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.

    Pin Python findings and raw SHACL silence for the deferred rdfs2 inputs.
    """
    from pathlib import Path

    from conftest import shacl_or_skip
    pyshacl = shacl_or_skip()
    from test_shapes_parity import CORE as SHAPES
    from test_shapes_parity import SH

    findings = _rdfs2_bundled_statement_findings(tmp_path, ordinary_domain)
    assert len(findings) == (0 if ordinary_domain else 2)
    for subject in (CORE.Creator, EXAMPLE.party):
        assert sum(f.violation.subject == str(subject) for f in findings) == int(not ordinary_domain)
    _ok, results, text = pyshacl.validate(
        Graph().parse(data=_rdfs2_bundled_statement_metadata(ordinary_domain), format="xml"),
        shacl_graph=SHAPES, advanced=True, inference="none")
    raw = {result for result, _p, source in results.triples((None, SH.sourceShape, None))
           if str(source).rsplit("#", 1)[-1] == "R61"}
    assert len(raw) == 0, text
    if not ordinary_domain:
        readme = (Path(__file__).resolve().parents[1] / "shapes/README.md").read_text()
        assert "| `bundled-domain` |" in readme
        assert "| `rdfs2-feedback` |" in readme
