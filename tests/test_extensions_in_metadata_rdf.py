"""Proprietary extensions must be in metadata.rdf, not only in metadata.jsonld.

Three sentences say it, once generally and twice about a named extension:

    x7-1-iirds-extension-scenarios#4  All proprietary extensions that are used
        in a package MUST be contained in the file metadata.rdf.
    x6-7-4-product-variants#1  As product variants are a proprietary iiRDS
        extension, they MUST be present in the metadata.rdf.
    x6-7-1-component-trees-in-the-package#2  The component tree is a
        proprietary iiRDS extension, it MUST be stored in the metadata.rdf.

Every rule but L9 reads the two serialisations merged, which is right and is
exactly what hides this: a product variant stated only in metadata.jsonld is
in the graph every other rule sees, and in none of the files this sentence
names. L9 reports that the two disagree, which is a different sentence, and
says nothing when the disagreement is the one these forbid.
"""
from __future__ import annotations

import json

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

IIRDS = "http://iirds.tekom.de/iirds#"
RDFS_ = "http://www.w3.org/2000/01/rdf-schema#"


def package(tmp_path, name, rdf_body="", jsonld_nodes=()):
    """The same graph, split: `rdf_body` into metadata.rdf, `jsonld_nodes` into
    metadata.jsonld only."""
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", rdf_body + "</rdf:RDF>")
    graph = [{"@id": "urn:test:package", "@type": "iirds:Package",
              "iirds:iiRDSVersion": "1.3", "iirds:title": "Test package"}]
    graph.extend(jsonld_nodes)
    jsonld = json.dumps({"@context": {"iirds": IIRDS, "rdfs": RDFS_}, "@graph": graph})
    return build_package(tmp_path, name, metadata=metadata, jsonld=jsonld)


def fired(tmp_path, name, **kwargs):
    return {f.rule.id for f in runner.run(package(tmp_path, name, **kwargs),
                                          runner.ALL_KINDS).findings}


VARIANT = {"@id": "urn:test:variant", "@type": "iirds:ProductVariant",
           "rdfs:label": "Rotor 3000"}
COMPONENT = {"@id": "urn:test:pump", "@type": "iirds:Component", "rdfs:label": "Pump"}
SUBCLASS = {"@id": "http://my.co/ns#Manual", "@type": "rdfs:Class",
            "rdfs:subClassOf": {"@id": "iirds:Document"}}

VARIANT_RDF = ('  <iirds:ProductVariant rdf:about="urn:test:variant">'
               '<rdfs:label>Rotor 3000</rdfs:label></iirds:ProductVariant>\n')
COMPONENT_RDF = ('  <iirds:Component rdf:about="urn:test:pump">'
                 '<rdfs:label>Pump</rdfs:label></iirds:Component>\n')
SUBCLASS_RDF = ('  <rdf:Description rdf:about="http://my.co/ns#Manual">\n'
                '    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>\n'
                '    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Document"/>\n'
                '  </rdf:Description>\n')


def test_a_product_variant_only_in_the_json_ld_is_reported(tmp_path):
    assert "R11" in fired(tmp_path, "variant.iirds", jsonld_nodes=(VARIANT,))


def test_a_component_only_in_the_json_ld_is_reported(tmp_path):
    assert "R11" in fired(tmp_path, "component.iirds", jsonld_nodes=(COMPONENT,))


def test_a_proprietary_class_only_in_the_json_ld_is_reported(tmp_path):
    assert "R11" in fired(tmp_path, "subclass.iirds", jsonld_nodes=(SUBCLASS,))


def test_the_same_extensions_in_both_files_are_not_reported(tmp_path):
    assert "R11" not in fired(
        tmp_path, "both.iirds",
        rdf_body=VARIANT_RDF + COMPONENT_RDF + SUBCLASS_RDF,
        jsonld_nodes=(VARIANT, COMPONENT, SUBCLASS))


def test_a_package_with_no_json_ld_at_all_is_not_reported(tmp_path):
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", VARIANT_RDF + "</rdf:RDF>")
    got = {f.rule.id for f in runner.run(
        build_package(tmp_path, "rdf_only.iirds", metadata=metadata), runner.ALL_KINDS).findings}
    assert "R11" not in got


TREE_RDF = ('  <iirds:Component rdf:about="urn:test:pump">'
            '<rdfs:label>Pump</rdfs:label></iirds:Component>\n'
            '  <iirds:Component rdf:about="urn:test:motor">'
            '<rdfs:label>Motor</rdfs:label></iirds:Component>\n')
TREE_NODES = ({"@id": "urn:test:pump", "@type": "iirds:Component", "rdfs:label": "Pump",
               "iirds:has-component": {"@id": "urn:test:motor"}},
              {"@id": "urn:test:motor", "@type": "iirds:Component", "rdfs:label": "Motor"})


def test_a_component_tree_whose_edges_are_only_in_the_json_ld_is_reported(tmp_path):
    """Section 6.7.1 says "The component **tree** ... MUST be stored in the
    metadata.rdf", and a tree is its nodes and its edges.

    Checking the nodes alone passed a package whose components are in both
    files and whose `iirds:has-component` relations -- the thing that makes
    them a tree rather than a list -- are in one. A consumer reading
    metadata.rdf gets two components and no hierarchy, which is the whole of
    what section 6.7.1 is for.
    """
    assert "R11" in fired(tmp_path, "tree_edges.iirds",
                          rdf_body=TREE_RDF, jsonld_nodes=TREE_NODES)


def test_the_same_tree_in_both_files_is_not_reported(tmp_path):
    edges = TREE_RDF.replace(
        '<rdfs:label>Pump</rdfs:label>',
        '<rdfs:label>Pump</rdfs:label><iirds:has-component rdf:resource="urn:test:motor"/>')
    assert "R11" not in fired(tmp_path, "tree_both.iirds",
                              rdf_body=edges, jsonld_nodes=TREE_NODES)


#: What section 7.1's general sentence reaches and this rule does not. Kept as
#: a test rather than a sentence, because the claim on that sentence was
#: withdrawn on this evidence and a withdrawal with no package behind it is
#: the thing this repository stopped doing.
BEYOND_THE_RULE = [
    ("a company-specific instance of an iiRDS vocabulary class",
     {"@id": "http://my.co/ns#Handbook", "@type": "iirds:DocumentType",
      "rdfs:label": "Handbook"}),
    ("an instance of a proprietary class",
     {"@id": "urn:test:doc", "@type": "http://my.co/ns#Manual", "rdfs:label": "a manual"}),
    ("a proprietary property declaration",
     {"@id": "http://my.co/ns#partNumber",
      "@type": "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property",
      "rdfs:subPropertyOf": {"@id": "iirds:identifier"}}),
]


@pytest.mark.parametrize("what,node", BEYOND_THE_RULE,
                         ids=[w.replace(" ", "-") for w, _ in BEYOND_THE_RULE])
def test_the_general_sentence_reaches_further_than_this_rule(tmp_path, what, node):
    """Section 7.1: "All proprietary extensions that are used in a package MUST
    be contained in the file metadata.rdf", and section 7.1's own definition of
    one is "company-specific and project-specific **instances and classes**".

    This rule checks three populations and there are more. Telling a
    proprietary vocabulary instance from an ordinary data node -- one whose
    class the standard supplies terms for, against one whose class is a
    document -- is a rule's worth of decision, so the claim on the general
    sentence went instead of riding along on this one. Each case is a package
    that breaches it and that nothing reports; L9 sees the disagreement and
    claims a different sentence.
    """
    got = fired(tmp_path, "beyond_%d.iirds" % abs(hash(what)), jsonld_nodes=(node,))
    assert "R11" not in got, (what, sorted(got))
    assert "L9" in got, "the disagreement is still reported, under its own sentence"
