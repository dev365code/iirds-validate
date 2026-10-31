"""Proprietary property declarations refine each bundled domain and range."""
from __future__ import annotations

import copy
import json

import pytest
from rdflib import BNode, Graph, Namespace
from rdflib.namespace import RDF, RDFS

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.model import IIRDS
from iirds_validate.registry import all_rules
from iirds_validate.rules import schema

#: XML Schema 1.1 names, which rdflib's XSD namespace on the dependency
#: floor does not define.
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
LOCAL = Namespace("urn:local:")
P = LOCAL.property
Q = IIRDS["has-rendition"]


def package_graph(triples=(), version="1.3"):
    graph = Graph().parse(data=MINIMAL_RDF.replace(">1.3<", ">%s<" % version), format="xml")
    for triple in triples:
        graph.add(triple)
    return graph


def package_path(tmp_path, triples=(), version="1.3"):
    return build_package(tmp_path, "relations.iirds",
                         metadata=package_graph(triples, version).serialize(format="xml"))


def property_findings(path):
    return [f for f in runner.check(path).findings if f.rule.id == "R76"]


def rule_function():
    return next(r.fn for r in all_rules() if r.id == "R76")


@pytest.mark.parametrize("relation", [RDFS.domain, RDFS.range])
@pytest.mark.parametrize("version", ["1.0", "1.3"])
def test_unrelated_property_classes_are_reported(tmp_path, relation, version):
    '''"Proprietary properties MUST comply with domain and range of the iiRDS property."'''
    path = package_path(tmp_path, [(P, RDFS.subPropertyOf, Q), (P, relation, LOCAL.Separate)],
                        version)
    found = property_findings(path)
    # One finding: "the iiRDS property" is the nearest one P refines, and
    # iirdsRelationConcept above has-rendition is not compared again.
    assert [f.violation.subject for f in found] == [str(P)]
    assert all(f.severity.value == "error" for f in found)
    assert str(LOCAL.Separate) in found[0].violation.detail
    assert "has-rendition" in found[0].violation.detail
    assert ("InformationUnit" if relation == RDFS.domain else "Rendition") in found[0].violation.detail
    claim = "x7-3-3-adding-a-proprietary-property#2"
    assert sorted(r.id for r in all_rules() if claim in r.covers) == ["R76"]


@pytest.mark.parametrize("relation,expected", [(RDFS.domain, IIRDS.InformationUnit),
                                               (RDFS.range, IIRDS.Rendition)])
@pytest.mark.parametrize("shape", ["same", "below", "absent", "intersection", "blank"])
def test_refining_or_inherited_classes_are_accepted(tmp_path, relation, expected, shape):
    triples = [(P, RDFS.subPropertyOf, Q)]
    if shape == "same":
        triples.append((P, relation, expected))
    elif shape != "absent":
        cls = BNode() if shape == "blank" else LOCAL.Refinement
        triples += [(P, relation, cls), (cls, RDFS.subClassOf, expected)]
        if shape == "intersection":
            triples.append((P, relation, LOCAL.Separate))
    assert property_findings(package_path(tmp_path, triples)) == []


@pytest.mark.parametrize("relation", [RDFS.domain, RDFS.range])
@pytest.mark.parametrize("cycle", [False, True])
def test_property_chains_keep_the_comparison(tmp_path, relation, cycle):
    triples = [(P, RDFS.subPropertyOf, LOCAL.middle),
               (LOCAL.middle, RDFS.subPropertyOf, Q), (P, relation, LOCAL.Separate)]
    if cycle:
        triples.append((LOCAL.middle, RDFS.subPropertyOf, P))
    assert str(P) in [f.violation.subject for f in property_findings(package_path(tmp_path, triples))]


@pytest.mark.parametrize("relation", [RDFS.domain, RDFS.range])
def test_no_declared_class_reaches_the_expected_class(tmp_path, relation):
    triples = [(P, RDFS.subPropertyOf, Q), (P, relation, LOCAL.First),
               (P, relation, LOCAL.Second)]
    # One constraint of the one iiRDS property P refines, and neither class meets it.
    found = property_findings(package_path(tmp_path, triples))
    assert len(found) == 1
    assert str(LOCAL.First) in found[0].violation.detail and str(LOCAL.Second) in found[0].violation.detail


def test_datatype_range_refines_literal(tmp_path):
    triples = [(P, RDFS.subPropertyOf, IIRDS.title), (P, RDFS.range, XSD.string)]
    assert property_findings(package_path(tmp_path, triples)) == []


def test_reflexive_local_property_has_no_bundled_parent(tmp_path):
    assert property_findings(package_path(tmp_path, [(P, RDFS.subPropertyOf, P),
                                                   (P, RDFS.domain, LOCAL.Separate)])) == []


def test_bundled_property_is_not_proprietary(tmp_path):
    assert property_findings(package_path(tmp_path, [(Q, RDFS.subPropertyOf, Q),
                                                   (Q, RDFS.domain, LOCAL.Separate)])) == []


@pytest.mark.parametrize("relation", [RDFS.domain, RDFS.range])
def test_each_bundled_constraint_is_required(tmp_path, relation):
    expected = IIRDS.InformationUnit if relation == RDFS.domain else IIRDS.Rendition
    path = package_path(tmp_path, [(P, RDFS.subPropertyOf, Q), (P, relation, expected)])
    ctx = runner.load(path)
    try:
        ctx.ontology = copy.copy(ctx.ontology)
        ctx.ontology.graph = Graph() + ctx.ontology.graph
        ctx.ontology.graph.add((Q, relation, LOCAL.Additional))
        found = list(rule_function()(ctx))
        assert len(found) == 1
        assert str(LOCAL.Additional) in found[0].detail
    finally:
        ctx.package.close()


def test_a_bundled_property_without_domain_adds_no_domain_requirement(tmp_path):
    triples = [(P, RDFS.subPropertyOf, IIRDS.iirdsAttribute), (P, RDFS.domain, LOCAL.Separate)]
    assert property_findings(package_path(tmp_path, triples)) == []


@pytest.mark.parametrize("relation", [RDFS.domain, RDFS.range])
def test_separate_declarations_can_meet_separate_constraints(tmp_path, relation):
    expected = IIRDS.InformationUnit if relation == RDFS.domain else IIRDS.Rendition
    triples = [(P, RDFS.subPropertyOf, Q), (P, relation, expected),
               (P, relation, LOCAL.Additional)]
    ctx = runner.load(package_path(tmp_path, triples))
    try:
        ctx.ontology = copy.copy(ctx.ontology)
        ctx.ontology.graph = Graph() + ctx.ontology.graph
        ctx.ontology.graph.add((Q, relation, LOCAL.Additional))
        assert list(rule_function()(ctx)) == []
    finally:
        ctx.package.close()


def test_closure_ceiling_is_reported(tmp_path, monkeypatch):
    def at_ceiling(ctx):
        raise schema._ClosureCut(17)

    monkeypatch.setattr(schema, "_disjoint_rdfs_facts", at_ceiling)
    found = property_findings(package_path(tmp_path, [(P, RDFS.subPropertyOf, Q)]))
    assert len(found) == 1
    assert "stopped" in found[0].violation.message
    assert "17" in found[0].violation.detail
    assert str(17 * schema.MAX_DERIVED_PER_FACT) in found[0].violation.detail


def test_no_proprietary_subproperty_does_not_compute_closure(tmp_path, monkeypatch):
    calls = []

    def counted(ctx):
        calls.append(ctx)
        raise AssertionError("closure was not needed")

    monkeypatch.setattr(schema, "_disjoint_rdfs_facts", counted)
    ctx = runner.load(package_path(tmp_path, [(Q, RDFS.subPropertyOf, Q)]))
    try:
        assert list(rule_function()(ctx)) == []
        assert calls == []
    finally:
        ctx.package.close()


def test_blank_class_reports_are_identical(tmp_path):
    cls = BNode()
    path = package_path(tmp_path, [(P, RDFS.subPropertyOf, Q), (P, RDFS.domain, cls),
                                   (cls, RDFS.label, LOCAL.label)])
    assert property_findings(path)
    assert json.dumps(runner.check(path).as_dict(), sort_keys=True) == json.dumps(
        runner.check(path).as_dict(), sort_keys=True)


@pytest.mark.parametrize("unrelated", [False, True], ids=["alone", "beside-an-unrelated-statement"])
def test_a_subproperty_that_only_rdfs7_states_is_checked(tmp_path, unrelated):
    """rdfs7 makes P a subproperty of Q when the package states P's relation
    to Q with a predicate it declares below rdfs:subPropertyOf. Whether P is
    checked cannot hang on a statement about something else: the verdict is
    the same with an unrelated reflexive statement beside it and without."""
    triples = [(IIRDS.title, RDFS.subPropertyOf, RDFS.subPropertyOf), (P, IIRDS.title, Q),
               (P, RDFS.domain, LOCAL.Separate)]
    if unrelated:
        triples.append((LOCAL.other, RDFS.subPropertyOf, LOCAL.other))
    found = property_findings(package_path(tmp_path, triples))
    assert [f.violation.subject for f in found] == [str(P)]
    assert "has-rendition" in found[0].violation.detail


def test_a_statement_whose_object_is_subpropertyof_computes_the_closure(tmp_path, monkeypatch):
    calls = []

    def counted(ctx):
        calls.append(ctx)
        raise schema._ClosureCut(1)

    monkeypatch.setattr(schema, "_disjoint_rdfs_facts", counted)
    ctx = runner.load(package_path(tmp_path, [(IIRDS.title, RDFS.subPropertyOf,
                                               RDFS.subPropertyOf)]))
    try:
        list(rule_function()(ctx))
        assert len(calls) == 1
    finally:
        ctx.package.close()


def bundled_copies(version="1.3"):
    """A proprietary property under each bundled one that has a domain or a
    range, declaring exactly that property's own domain and range."""
    from iirds_validate import ontology as ontology_mod

    bundle = ontology_mod.load(version).graph
    triples = []
    for index, parent in enumerate(sorted({s for s, _p, _o in bundle.triples((None, RDFS.domain, None))}
                                           | {s for s, _p, _o in bundle.triples((None, RDFS.range, None))},
                                           key=str)):
        copy_of = LOCAL["copy-%d" % index]
        triples.append((copy_of, RDFS.subPropertyOf, parent))
        for relation in (RDFS.domain, RDFS.range):
            triples += [(copy_of, relation, cls) for cls in bundle.objects(parent, relation)]
    return triples


def test_a_property_declared_as_its_iirds_property_is_declared_complies(tmp_path):
    """Seventy bundled properties have a domain or a range. A proprietary one
    under each that copies them word for word complies with "the iiRDS
    property" -- dateOfCreation's xsd:dateTimeStamp and relates-to-vcard's
    vcard:Kind included, which are not below what the properties above them
    declare. Whether the bundle's own properties agree with each other is not
    a package's question."""
    triples = bundled_copies()
    assert len([t for t in triples if t[1] == RDFS.subPropertyOf]) == 70
    assert property_findings(package_path(tmp_path, triples)) == []


@pytest.mark.parametrize("parent,datatype", [
    (IIRDS.title, XSD.normalizedString),
    (IIRDS.classificationIdentifier, XSD.token),
    (IIRDS.title, RDF.langString),
    (IIRDS["duration"], XSD.dayTimeDuration),
    (IIRDS["duration"], XSD.yearMonthDuration),
])
def test_a_datatype_below_the_iirds_range_complies(tmp_path, parent, datatype):
    """RDF 1.1 Semantics puts every recognized datatype below rdfs:Literal,
    and XML Schema 1.1 derives dayTimeDuration and yearMonthDuration from
    duration by restriction."""
    path = package_path(tmp_path, [(P, RDFS.subPropertyOf, parent), (P, RDFS.range, datatype)])
    assert property_findings(path) == []


@pytest.mark.parametrize("parent,datatype", [
    (IIRDS.dateOfCreation, XSD.string),
    (IIRDS.dateOfCreation, XSD.dateTime),
    (IIRDS["duration"], XSD.dateTimeStamp),
    (IIRDS.title, LOCAL.NotADatatype),
])
def test_a_range_outside_the_iirds_range_is_reported(tmp_path, parent, datatype):
    path = package_path(tmp_path, [(P, RDFS.subPropertyOf, parent), (P, RDFS.range, datatype)])
    assert [f.violation.subject for f in property_findings(path)] == [str(P)]


def test_a_range_wider_than_the_iirds_range_is_reported(tmp_path):
    vcard_kind = IIRDS["relates-to-vcard"]
    path = package_path(tmp_path, [(P, RDFS.subPropertyOf, vcard_kind),
                                   (P, RDFS.range, RDFS.Resource)])
    assert [f.violation.subject for f in property_findings(path)] == [str(P)]


def test_a_bundled_property_declared_again_is_not_this_rules_subject(tmp_path):
    """Names the bundle defines are not this rule's subjects: section 7.3.3
    speaks of proprietary properties. A compliant proprietary property opens
    the check, and the package then gives has-rendition a domain of its own;
    R76 says nothing about has-rendition."""
    triples = [(P, RDFS.subPropertyOf, Q), (P, RDFS.domain, IIRDS.InformationUnit),
               (Q, RDFS.domain, LOCAL.Separate)]
    assert property_findings(package_path(tmp_path, triples)) == []


def test_an_iirds_name_the_bundle_does_not_define_is_proprietary(tmp_path):
    """A name in the iiRDS namespace that the bundle does not define -- one
    from another edition, or a typo -- is a property the package declares, and
    R76 holds it to the iiRDS property it refines. Beside it, M30 reports the
    statement as schema written into the iiRDS namespace, and the lint L13
    the name as one the vocabulary does not define: a reader who moves the
    property out of the namespace still has R76's comparison to answer."""
    undefined = IIRDS["has-local-rendition"]
    path = package_path(tmp_path, [(undefined, RDFS.subPropertyOf, Q),
                                   (undefined, RDFS.domain, LOCAL.Separate)])
    found = runner.run(path, runner.ALL_KINDS).findings
    assert [f.violation.subject for f in found if f.rule.id == "R76"] == [str(undefined)]
    assert {"M30", "L13"} <= {f.rule.id for f in found}


def test_the_run_note_names_what_the_substituted_bundle_supplies(tmp_path):
    """Every edition is compared with the 1.3 bundle's domains and ranges, and
    the run's note says so where it says the class hierarchy is borrowed."""
    report = runner.check(package_path(tmp_path, version="1.0"))
    note = next(note for note in report.notes if "no ontology bundled" in note)
    assert "property domains and ranges" in note


def test_the_derivations_read_are_the_ones_the_bundled_ranges_need():
    """Among datatypes, R76 reads the XML Schema derivations below a datatype
    a bundled range names. The bundle's datatype ranges are rdfs:Literal,
    xsd:dateTimeStamp and xsd:duration; XML Schema 1.1 derives
    dayTimeDuration and yearMonthDuration from duration and nothing from
    dateTimeStamp. A bundle naming another datatype as a range moves this."""
    from iirds_validate import ontology as ontology_mod

    bundle = ontology_mod.load("1.3").graph
    ranges = {cls for cls in bundle.objects(None, RDFS.range)
              if cls == RDFS.Literal or str(cls).startswith((str(XSD), str(RDF)))}
    assert ranges == {RDFS.Literal, XSD.dateTimeStamp, XSD.duration}
    derived = schema._DERIVED_DATATYPES
    assert derived == {(XSD.dayTimeDuration, XSD.duration), (XSD.yearMonthDuration, XSD.duration)}
