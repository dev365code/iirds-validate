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


UNTYPED_RDF = ('  <rdf:Description rdf:about="urn:test:%s">'
               "<rdfs:label>%s</rdfs:label></rdf:Description>\n")


@pytest.mark.parametrize("cls,name", [("ProductVariant", "Rotor"), ("Component", "Pump")],
                         ids=["product-variant", "component"])
def test_a_type_declared_only_in_the_json_ld_is_reported(cls, name, tmp_path):
    """The rule asked whether metadata.rdf *mentions* the node, not whether
    the type declaration is there -- and mentioning is not being present.

    A node carrying only `rdfs:label` in metadata.rdf and its `rdf:type` in
    metadata.jsonld is a product variant to every rule (they read the merged
    graph) and is not one in the file section 6.7.4 names. The subclass loop
    beside this one, and the has-component loop added after it, both compare
    the exact triple; this one did not, and the inconsistency is the tell.
    """
    key = cls.lower()
    got = fired(tmp_path, "untyped_%s.iirds" % key,
                rdf_body=UNTYPED_RDF % (key, name),
                jsonld_nodes=({"@id": "urn:test:%s" % key, "@type": "iirds:" + cls,
                               "rdfs:label": name},))
    assert "R11" in got, sorted(got)


@pytest.mark.parametrize("edition", ["1.2", "1.1", "1.0"])
def test_an_older_package_carrying_both_files_is_still_reported(edition, tmp_path):
    """The rule was scoped to 1.3 because the cached 1.0 release does not
    mention JSON-LD, which is true and is not a reason.

    It already returns unless the package carries both metadata files, so the
    edition gate cannot prevent a false finding -- there is none to prevent --
    and can only suppress a true one. A 1.2 package with both files and a
    product variant in one of them breaches section 6.7.4's sentence, which
    1.0 states in the same words. L9 needs the same two files and is scoped to
    every edition, for the same reason: it judges the package, not the year.
    """
    metadata = MINIMAL_RDF.replace("<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
                                   "<iirds:iiRDSVersion>%s</iirds:iiRDSVersion>" % edition)
    jsonld = json.dumps({"@context": {"iirds": IIRDS, "rdfs": RDFS_},
                         "@graph": [{"@id": "urn:test:package", "@type": "iirds:Package",
                                     "iirds:iiRDSVersion": edition,
                                     "iirds:title": "Test package"},
                                    {"@id": "urn:test:variant", "@type": "iirds:ProductVariant",
                                     "rdfs:label": "Rotor"}]})
    got = {f.rule.id for f in runner.run(
        build_package(tmp_path, "old_%s.iirds" % edition, metadata=metadata, jsonld=jsonld),
        runner.ALL_KINDS).findings}
    assert "R11" in got, sorted(got)


def test_a_blank_node_in_both_files_is_not_called_misplaced(tmp_path):
    """rdflib labels blank nodes per parse, so the same anonymous component
    written into both files is two nodes in the merged graph and the rule said
    one of them was "stated outside metadata.rdf" -- which is not what
    happened. The package fails anyway, on L9 and on the rule that requires an
    IRI, so this is a false sentence rather than a false failure; a finding
    that names a defect the package does not have is still worth not making.
    """
    got = fired(tmp_path, "blank_component.iirds",
                rdf_body='  <iirds:Component><rdfs:label>Pump</rdfs:label></iirds:Component>\n',
                jsonld_nodes=({"@type": "iirds:Component", "rdfs:label": "Pump"},))
    assert "R11" not in got, sorted(got)


SUBCLASS_DECL = ('  <rdf:Description rdf:about="http://my.co/ns#Trim">\n'
                 '    <rdfs:subClassOf rdf:resource="%sProductVariant"/>\n'
                 "  </rdf:Description>\n" % IIRDS)
TRIM = {"@id": "urn:test:trim", "@type": "http://my.co/ns#Trim", "rdfs:label": "Sport"}
TRIM_DECL = {"@id": "http://my.co/ns#Trim", "rdfs:subClassOf": {"@id": "iirds:ProductVariant"}}


def test_a_variant_typed_with_the_packages_own_subclass_is_present(tmp_path):
    """Section 7 lets a package declare its own class beneath an iiRDS one and
    requires consumers to treat instances of it as the parent. A variant typed
    that way, wholly inside metadata.rdf, is present there.

    The question is asked through the subclass closure for that reason, and
    without this test dropping the closure changed nothing anybody could see:
    the rule would report a conformant package, which is the failure the
    `Context.is_instance` docstring names -- "exact typing is how section 7
    gets forgotten one rule at a time" -- in a function written to avoid it.
    """
    body = SUBCLASS_DECL + ('  <rdf:Description rdf:about="urn:test:trim">\n'
                            '    <rdf:type rdf:resource="http://my.co/ns#Trim"/>\n'
                            "    <rdfs:label>Sport</rdfs:label>\n  </rdf:Description>\n")
    assert "R11" not in fired(tmp_path, "subclass_present.iirds",
                              rdf_body=body, jsonld_nodes=(TRIM, TRIM_DECL))


def test_a_variant_typed_with_a_subclass_declared_only_in_the_json_ld_is_reported(tmp_path):
    """The other direction, so the closure cannot be satisfied by accepting
    everything: the same shape with nothing of it in metadata.rdf."""
    assert "R11" in fired(tmp_path, "subclass_absent.iirds",
                          jsonld_nodes=(TRIM, TRIM_DECL))
