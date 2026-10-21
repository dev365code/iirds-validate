"""What R61's closure says about a fact it derived from two statements.

A finding explains each type it rests on step by step, and a step that joins
two statements -- rdfs2, rdfs3, rdfs7 and rdfs9 join a statement with the
schema statement it meets -- names both, the statement first, so how it reads
does not depend on which of the two the closure met first. rdfs5 and rdfs11
join two schema statements in a chain; they name both as well, the lower one
first.
"""
from __future__ import annotations

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from conftest import build_package
from iirds_validate import runner
from iirds_validate.rules.schema import _disjoint_rdfs_facts

CORE = Namespace("http://iirds.tekom.de/iirds#")
EXAMPLE = Namespace("https://example.org/classes/")
PACKAGE = URIRef("urn:test:package")

#: The closure meets its facts in the order of their names, so which of a
#: chain's two statements it reaches first is the lower one's when that
#: subject's name sorts first, and the upper one's otherwise -- each case is
#: the other half of the join.
TRANSITIVE_STEPS = (
    ("rdfs11-lower-first", "rdfs11", (EXAMPLE.Alpha, RDFS.subClassOf, CORE.Document),
     (EXAMPLE.Alpha, RDFS.subClassOf, EXAMPLE.Beta), (EXAMPLE.Beta, RDFS.subClassOf, CORE.Document),
     ((EXAMPLE.subject, RDF.type, EXAMPLE.Alpha), (EXAMPLE.subject, RDF.type, CORE.Topic))),
    ("rdfs11-upper-first", "rdfs11", (EXAMPLE.Start, RDFS.subClassOf, CORE.Document),
     (EXAMPLE.Start, RDFS.subClassOf, EXAMPLE.Middle), (EXAMPLE.Middle, RDFS.subClassOf, CORE.Document),
     ((EXAMPLE.subject, RDF.type, EXAMPLE.Start), (EXAMPLE.subject, RDF.type, CORE.Topic))),
    ("rdfs5-lower-first", "rdfs5", (EXAMPLE.first, RDFS.subPropertyOf, RDF.type),
     (EXAMPLE.first, RDFS.subPropertyOf, EXAMPLE.middle), (EXAMPLE.middle, RDFS.subPropertyOf, RDF.type),
     ((EXAMPLE.subject, EXAMPLE.first, CORE.Document), (EXAMPLE.subject, RDF.type, CORE.Topic))),
    ("rdfs5-upper-first", "rdfs5", (EXAMPLE.zeta, RDFS.subPropertyOf, RDF.type),
     (EXAMPLE.zeta, RDFS.subPropertyOf, EXAMPLE.middle), (EXAMPLE.middle, RDFS.subPropertyOf, RDF.type),
     ((EXAMPLE.subject, EXAMPLE.zeta, CORE.Document), (EXAMPLE.subject, RDF.type, CORE.Topic))),
)


def _metadata(triples):
    graph = Graph()
    graph.add((PACKAGE, RDF.type, CORE.Package))
    graph.add((PACKAGE, CORE.iiRDSVersion, Literal("1.3")))
    graph.add((PACKAGE, CORE.title, Literal("Package")))
    for triple in triples:
        graph.add(triple)
    return graph.serialize(format="xml")


@pytest.mark.parametrize("case,pattern,joined,lower,upper,rest", TRANSITIVE_STEPS,
                         ids=[step[0] for step in TRANSITIVE_STEPS])
def test_a_transitive_step_names_both_statements_it_joins(tmp_path, case, pattern, joined, lower, upper, rest):
    """x6-11-1-disjointness#1
    Disjoint classes MUST NOT have instances in common.

    The chain's two statements, the lower first, rather than only the class or
    property in the middle of it."""
    package = build_package(tmp_path, case + ".iirds", metadata=_metadata((lower, upper) + rest))
    ctx = runner.load(package)
    try:
        _facts, origins, _direct = _disjoint_rdfs_facts(ctx)
    finally:
        ctx.package.close()

    def statement(triple):
        return "statement %s %s %s" % tuple(str(term) for term in triple)

    assert origins[joined] == "%s via %s (%s; %s)" % (pattern, upper[0], statement(lower), statement(upper))
