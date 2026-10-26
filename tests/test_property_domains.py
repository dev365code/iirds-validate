"""Proprietary property declarations refine each bundled domain and range."""
from __future__ import annotations

import copy
import json

import pytest
from rdflib import BNode, Graph, Namespace
from rdflib.namespace import RDFS, XSD

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.model import IIRDS
from iirds_validate.registry import all_rules
from iirds_validate.rules import schema

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
    assert [f.violation.subject for f in found] == [str(P), str(P)]
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
    assert len(property_findings(package_path(tmp_path, triples))) == 2


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
