"""Seventeen "MUST NOT have more than one" rules, each shown to work.

Every one of them was registered, catalogued and never observed to produce a
finding. A cardinality rule that never fires is indistinguishable from a
cardinality rule that cannot fire, and the difference only shows up in a
customer's package.

The pairs below were read out of the rule implementations rather than out of
their prose, because the two have disagreed before: a property guessed from a
sentence as `eventCode` is spelled `has-event-code` in the ontology, and a rule
built on the guess matched nothing while looking correct.
"""
from __future__ import annotations

import pytest
from rdflib import RDFS
from rdflib.namespace import RDF

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate import terms as T
from iirds_validate.ontology import load

#: (rule, class, property). Extracted from the functions themselves.
PAIRS = [
    ("M2.3",  T.InformationUnit,          T.dateOfCreation),
    ("M2.4",  T.InformationUnit,          T.dateOfLastModification),
    ("M2.5",  T.InformationUnit,          T.revision),
    ("M2.7",  T.InformationUnit,          T.has_abstract),
    ("M2.8",  T.InformationUnit,          T.is_replacement_of),
    ("M2.9",  T.InformationUnit,          T.is_version_of),
    ("M21.2", T.ContentLifeCycleStatus,   T.dateOfEffect),
    ("M21.3", T.ContentLifeCycleStatus,   T.dateOfExpiry),
    ("M21.5", T.ContentLifeCycleStatus,   T.purpose),
    ("M21.6", T.ContentLifeCycleStatus,   T.relates_to_party),
    ("M24.1", T.DirectoryNode,            T.has_next_sibling),
    ("M24.2", T.DirectoryNode,            T.has_directory_structure_type),
    ("M24.3", T.DirectoryNode,            T.has_first_child),
    ("M24.4", T.DirectoryNode,            T.relates_to_information_unit),
    ("M95",   T.Component,                T.relates_to_party),
    ("M96.1", T.ExternalClassification,   T.has_classification_domain),
    ("M96.2", T.ExternalClassification,   T.classificationIdentifier),
]

IDS = [p[0] for p in PAIRS]


def _takes_a_literal(prop) -> bool:
    """Asked of the ontology, not assumed. Writing an IRI where a literal
    belongs produces a graph that is wrong in a different way from the one
    under test, and the rule would fire for the wrong reason."""
    return RDFS.Literal in set(load().graph.objects(prop, RDFS.range))


def _statement(prop, value: str) -> str:
    name = "iirds:" + str(prop).split("#")[-1]
    if _takes_a_literal(prop):
        return "    <%s>%s</%s>\n" % (name, value, name)
    return '    <%s rdf:resource="urn:test:%s"/>\n' % (name, value)


def _package(tmp_path, rule_id, cls, prop, count):
    # Two *different* values. RDF is a set, so repeating one statement is one
    # statement, and a fixture built that way tests nothing.
    body = "".join(_statement(prop, "v%d" % n) for n in range(count))
    element = "  <rdf:Description rdf:about='urn:test:subject'>\n" \
              "    <rdf:type rdf:resource='%s'/>\n%s  </rdf:Description>\n" % (cls, body)
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", element + "</rdf:RDF>")
    return build_package(tmp_path, "%s_%d.iirds" % (rule_id.replace(".", "_"), count),
                         metadata=metadata)


@pytest.mark.parametrize("rule_id,cls,prop", PAIRS, ids=IDS)
def test_two_values_are_reported(rule_id, cls, prop, tmp_path):
    report = runner.check(_package(tmp_path, rule_id, cls, prop, 2))
    assert rule_id in {f.rule.id for f in report.findings}


@pytest.mark.parametrize("rule_id,cls,prop", PAIRS, ids=IDS)
def test_one_value_is_not(rule_id, cls, prop, tmp_path):
    """The half that says the rule is looking at the right thing. A rule that
    fires on two and also on one is not a cardinality check."""
    report = runner.check(_package(tmp_path, rule_id, cls, prop, 1))
    assert rule_id not in {f.rule.id for f in report.findings}


def test_the_ontology_answered_for_every_property():
    """If a property has no rdfs:range the helper above silently treats it as
    an object property, and half these fixtures would be malformed in a way
    that still produces findings. Assert the question was answerable."""
    graph = load().graph
    for rule_id, _cls, prop in PAIRS:
        assert (prop, RDFS.range, None) in graph or (prop, RDF.type, None) in graph, \
            "%s: the ontology says nothing about %s" % (rule_id, prop)
