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

#: (table, rule id, prefix, class). MUST_HAVE_IRI rows carry a fourth element
#: — the appendix A row the rule answers, or None where two rules check the
#: same class and which one answers it is a question for a person. What is
#: checked here is the same three things about every row, so the fourth is
#: dropped; `tests/test_appendix_a_iri_claims.py` is where it is read.
ALL_ROWS = [("MUST_HAVE_IRI", row[0], row[1], row[2]) for row in MUST_HAVE_IRI] + \
           [("NOT_USED_DIRECTLY", row[0], row[1], row[2]) for row in NOT_USED_DIRECTLY]


def disagreements_with_the_catalogue(rows):
    """Rows whose class is not the class the catalogue names for that rule.

    Written as a function so the guard below can be pointed at a deliberately
    corrupted table and shown to bite. An assertion nobody has watched fail is
    an assertion nobody knows the shape of.
    """
    return [(rule_id, CATALOG[rule_id]["path"].strip(), class_name)
            for _table, rule_id, _prefix, class_name in rows
            if rule_id in CATALOG
            and CATALOG[rule_id]["path"].strip() != class_name]


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


def test_every_row_names_the_class_the_catalogue_names():
    """The check the other two do not make.

    `test_every_row_names_a_real_ontology_class` asks whether the class exists;
    `test_every_row_is_a_catalogued_schema_rule` asks whether the rule exists.
    Neither asks whether *this* class belongs to *that* rule, so swapping
    Document for Component across two rows broke nothing — and 61 of the 157
    rules are generated from exactly this mapping.

    `propose_class_rules.py --check` does not cover it either, for a reason
    worth stating: it regenerates the table and compares it against the
    committed one, so it compares the generator's output with the generator's
    output. A generator that resolves the wrong class agrees with itself
    perfectly. The catalogue's `path` field is the external datum — plusmeta's
    reading of the same specification — and it was sitting unused.
    """
    assert disagreements_with_the_catalogue(ALL_ROWS) == []


def test_the_guard_above_actually_detects_a_swap():
    """Proof that the assertion is not vacuous.

    Corrupt a copy of the table the way a careless regeneration would — two
    rows exchanging classes, both still real, both still catalogued schema
    rules, so every other test in this file still passes — and require the
    guard to name both.
    """
    rows = list(ALL_ROWS)
    # Two rows whose classes actually differ, or the swap is a no-op and this
    # test would fail for a reason that has nothing to do with the guard.
    pair = next(((i, j) for i in range(len(rows)) for j in range(i + 1, len(rows))
                 if rows[i][3] != rows[j][3]), None)
    assert pair is not None, "the table has only one distinct class name"
    i, j = pair
    (t1, id1, p1, c1), (t2, id2, p2, c2) = rows[i], rows[j]
    swapped = list(rows)
    swapped[i], swapped[j] = (t1, id1, p1, c2), (t2, id2, p2, c1)

    caught = {rule_id for rule_id, _expected, _found in
              disagreements_with_the_catalogue(swapped)}
    assert caught == {id1, id2}, caught


def test_no_rule_id_appears_in_two_tables():
    ids = [row[1] for row in ALL_ROWS]
    assert len(ids) == len(set(ids))


def test_the_tables_are_actually_registered():
    registered = {r.id for r in all_rules()}
    for _table, rule_id, _prefix, _class in ALL_ROWS:
        assert rule_id in registered, rule_id


def test_using_an_abstract_class_directly_is_lint_not_conformance(make_package):
    """iirds:Qualification is abstract — the standard subclasses are Role and
    SkillLevel — and the ontology says so in the class's own description.

    But M93, which the catalogue files under that wording, is implemented by
    the reference tool as a check that the element has an rdf:about. Reporting
    it as a MUST would fail packages nothing else fails, on an interpretation
    nothing else shares, so the observation is L10 and it is a warning.
    """
    from conftest import MINIMAL_RDF
    from iirds_validate import runner

    metadata = MINIMAL_RDF.replace("</rdf:RDF>", """  <iirds:Qualification rdf:about="urn:test:q1">
    <rdfs:label xml:lang="en">Service technician</rdfs:label>
  </iirds:Qualification>
</rdf:RDF>""")
    package = make_package(metadata=metadata)

    conformance = runner.check(package)
    assert "M93" not in {f.rule.id for f in conformance.findings}
    assert conformance.ok, [f.violation.message for f in conformance.findings]

    interop = runner.lint(package)
    hits = [f for f in interop.findings if f.rule.id == "L10"]
    assert hits and "Qualification" in hits[0].violation.message
    assert "Role" in (hits[0].violation.detail or "")
    assert interop.ok, "L10 is advisory"

    # Using the standard subclass instead is clean on both axes.
    fixed = metadata.replace("iirds:Qualification", "iirds:Role")
    fixed_pkg = make_package(name="fixed.iirds", metadata=fixed)
    assert runner.check(fixed_pkg).ok
    assert not [f for f in runner.lint(fixed_pkg).findings if f.rule.id == "L10"]


def test_must_have_iri_fires_on_a_blank_node(make_package):
    from conftest import MINIMAL_RDF
    from iirds_validate import runner

    metadata = MINIMAL_RDF.replace("</rdf:RDF>", """  <iirds:Component>
    <rdfs:label xml:lang="en">Nameless component</rdfs:label>
  </iirds:Component>
</rdf:RDF>""")
    report = runner.check(make_package(metadata=metadata))
    assert "M38" in {f.rule.id for f in report.findings}
