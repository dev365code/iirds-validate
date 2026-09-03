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
