"""Guards on the generated rule tables.

The two tables in rules/schema_tables.py are produced by resolving the
catalogue's `path` field against the bundled ontology. That resolution happened
once, at generation time, on someone else's free text. These tests redo it on
every run, so a class name that stops existing — because the ontology moved, or
because the generator was rerun against a changed catalogue — fails the suite
rather than quietly matching nothing.
"""
from __future__ import annotations

import pytest
from rdflib.namespace import RDF, RDFS

from iirds_validate.ontology import load
from iirds_validate.registry import CATALOG, all_rules
from iirds_validate.rules.schema_tables import MUST_HAVE_IRI, NAMESPACES, NOT_USED_DIRECTLY

ALL_ROWS = [("MUST_HAVE_IRI", *row) for row in MUST_HAVE_IRI] + \
           [("NOT_USED_DIRECTLY", *row) for row in NOT_USED_DIRECTLY]


@pytest.mark.parametrize("table,rule_id,prefix,class_name",
                         ALL_ROWS, ids=[r[1] for r in ALL_ROWS])
def test_every_row_names_a_real_ontology_class(table, rule_id, prefix, class_name):
    iri = NAMESPACES[prefix][class_name]
    assert (iri, RDF.type, RDFS.Class) in load().graph, \
        "%s (%s) resolves to %s, which is not a class in the bundled ontology" % (
            rule_id, table, iri)


@pytest.mark.parametrize("table,rule_id,prefix,class_name",
                         ALL_ROWS, ids=[r[1] for r in ALL_ROWS])
def test_every_row_is_a_catalogued_schema_rule(table, rule_id, prefix, class_name):
    assert rule_id in CATALOG, "%s is not in the catalogue — a typo would register it as lint" % rule_id
    assert CATALOG[rule_id]["kind"] == "schema", rule_id


def test_no_rule_id_appears_in_two_tables():
    ids = [row[1] for row in ALL_ROWS]
    assert len(ids) == len(set(ids))


def test_the_tables_are_actually_registered():
    registered = {r.id for r in all_rules()}
    for _table, rule_id, _prefix, _class in ALL_ROWS:
        assert rule_id in registered, rule_id


def test_not_used_directly_fires_on_a_direct_instance(make_package):
    """iirds:Qualification is abstract: the standard subclasses are Role and
    SkillLevel. Typing an instance as Qualification itself is M93."""
    from conftest import MINIMAL_RDF
    from iirds_validate import runner

    metadata = MINIMAL_RDF.replace("</rdf:RDF>", """  <iirds:Qualification rdf:about="urn:test:q1">
    <rdfs:label xml:lang="en">Service technician</rdfs:label>
  </iirds:Qualification>
</rdf:RDF>""")
    report = runner.check(make_package(metadata=metadata))
    assert "M93" in {f.rule.id for f in report.findings}

    # ...and using the standard subclass instead is clean.
    fixed = metadata.replace("iirds:Qualification", "iirds:Role")
    assert runner.check(make_package(name="fixed.iirds", metadata=fixed)).ok


def test_must_have_iri_fires_on_a_blank_node(make_package):
    from conftest import MINIMAL_RDF
    from iirds_validate import runner

    metadata = MINIMAL_RDF.replace("</rdf:RDF>", """  <iirds:Component>
    <rdfs:label xml:lang="en">Nameless component</rdfs:label>
  </iirds:Component>
</rdf:RDF>""")
    report = runner.check(make_package(metadata=metadata))
    assert "M38" in {f.rule.id for f in report.findings}
