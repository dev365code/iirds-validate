"""The 61 generated rules, each shown to fire on the thing it is about.

They were registered from a table and never exercised. `test_schema_tables.py`
checks that each row names a real ontology class and the class the catalogue
names for that rule -- so the *table* is right. Nothing checked that the
function built from the row does anything at all.

That distinction is not academic. S8 sat in exactly this state for months and
was inverted the whole time: it could only ever have fired wrongly, and no test
would have caught it either way, because no test made it fire.

One generator, sixty-one cases: put an anonymous instance of the class in the
graph and require that rule, and only rules about that class, to object.
"""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.registry import all_rules
from iirds_validate.rules.schema_tables import MUST_HAVE_IRI as _TABLE
from iirds_validate.rules.schema_tables import NAMESPACES

#: The table gained a fourth element — the appendix A row each rule
#: answers, read by `tests/test_appendix_a_iri_claims.py`. Everything here
#: asks the same three questions of every row, so it takes the three.
MUST_HAVE_IRI = [(row[0], row[1], row[2]) for row in _TABLE]

RULES = {r.id: r for r in all_rules()}

#: An anonymous node typed as the class, written the namespace-agnostic way so
#: one template covers every prefix in the table.
BLANK_INSTANCE = '''  <rdf:Description>
    <rdf:type rdf:resource="%s"/>
    <rdfs:label xml:lang="en">Anonymous</rdfs:label>
  </rdf:Description>
'''


def _package(tmp_path, rule_id, class_iri):
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", BLANK_INSTANCE % class_iri + "</rdf:RDF>")
    return build_package(tmp_path, "%s.iirds" % rule_id.replace(".", "_"), metadata=metadata)


@pytest.mark.parametrize("rule_id,prefix,class_name", MUST_HAVE_IRI,
                         ids=[r[0] for r in MUST_HAVE_IRI])
def test_it_fires_on_an_anonymous_instance_of_its_class(rule_id, prefix, class_name, tmp_path):
    """The sensitivity half: the rule reports what it exists to report."""
    package = _package(tmp_path, rule_id, str(NAMESPACES[prefix][class_name]))
    version = RULES[rule_id].versions[-1] if RULES[rule_id].versions else None
    report = runner.run(package, runner.CONFORMANCE_KINDS, version=version)

    assert rule_id in {f.rule.id for f in report.findings}


@pytest.mark.parametrize("rule_id,prefix,class_name", MUST_HAVE_IRI,
                         ids=[r[0] for r in MUST_HAVE_IRI])
def test_it_stays_quiet_when_the_instance_is_named(rule_id, prefix, class_name, tmp_path):
    """The half that is not circular, and the half that matters.

    A rule that fires on the defect proves only that it fires; one that also
    stays silent on the correct form proves it is looking at the right thing.
    S8 would have failed this and passed the other.
    """
    named = BLANK_INSTANCE.replace("<rdf:Description>",
                                   '<rdf:Description rdf:about="urn:test:named">')
    metadata = MINIMAL_RDF.replace(
        "</rdf:RDF>", named % str(NAMESPACES[prefix][class_name]) + "</rdf:RDF>")
    package = build_package(tmp_path, "ok_%s.iirds" % rule_id.replace(".", "_"),
                            metadata=metadata)
    version = RULES[rule_id].versions[-1] if RULES[rule_id].versions else None
    report = runner.run(package, runner.CONFORMANCE_KINDS, version=version)

    assert rule_id not in {f.rule.id for f in report.findings}


#: The same anonymous instance, typed with a class the *package* declares
#: beneath the one the rule is about. Section 7 lets a package do this and
#: requires a consumer to process the instance as the parent, so a rule that
#: asks only about exact typing is looking at a smaller population than the
#: standard gives it -- and a smaller one than its own SHACL shape sees, since
#: sh:targetClass follows the data graph's rdfs:subClassOf by definition.
SUBCLASSED_INSTANCE = '''  <rdf:Description rdf:about="urn:acme:Proprietary">
    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>
    <rdfs:subClassOf rdf:resource="%s"/>
  </rdf:Description>
  <rdf:Description>
    <rdf:type rdf:resource="urn:acme:Proprietary"/>
    <rdfs:label xml:lang="en">Anonymous</rdfs:label>
  </rdf:Description>
'''


def _subclassed(tmp_path, rule_id, class_iri, about=""):
    body = SUBCLASSED_INSTANCE % class_iri
    if about:
        body = body.replace('  <rdf:Description>\n    <rdf:type rdf:resource="urn:acme:Proprietary"/>',
                            '  <rdf:Description rdf:about="%s">\n'
                            '    <rdf:type rdf:resource="urn:acme:Proprietary"/>' % about)
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", body + "</rdf:RDF>")
    return build_package(tmp_path, "s7_%s%s.iirds" % (rule_id.replace(".", "_"),
                                                      "_named" if about else ""),
                         metadata=metadata)


def _iri_is_required(prefix, class_name) -> bool:
    """Does the ontology say instances of this class need an IRI?

    Read at run time from the bundled ontology, so a change there moves the
    population instead of leaving a hand list to rot. Fifty rows say "IRI:
    required"; ten say nothing about IRIs at all, and iirds:PlanningTime says
    "IRI: optional" outright.
    """
    from rdflib import URIRef

    from iirds_validate.ontology import Ontology
    described = URIRef("http://iirds.tekom.de/iirds#description")
    for _s, _p, text in Ontology().graph.triples(
            (URIRef(str(NAMESPACES[prefix][class_name])), described, None)):
        if "IRI:" in str(text):
            tail = str(text)[str(text).index("IRI:"):].lower()
            return "required" in tail
    return False


#: The two populations these rules divide into, and the reason they must.
REQUIRED = [r for r in MUST_HAVE_IRI if _iri_is_required(r[1], r[2])]
UNSTATED = [r for r in MUST_HAVE_IRI if not _iri_is_required(r[1], r[2])]


def test_the_two_populations_are_both_real():
    """A split that put everything on one side would make one of the two
    parametrisations below vacuous, and a vacuous parametrisation is green."""
    assert (len(REQUIRED), len(UNSTATED)) == (56, 5)
    assert len(REQUIRED) + len(UNSTATED) == len(MUST_HAVE_IRI)
    # The five: four whose ontology entry says nothing about an IRI, and
    # iirds:PlanningTime, which says "IRI: optional" in as many words.
    assert sorted(r[0] for r in UNSTATED) == ["M82", "M83", "M84", "M85", "M88"]


@pytest.mark.parametrize("rule_id,prefix,class_name", UNSTATED,
                         ids=[r[0] for r in UNSTATED])
def test_a_declared_subclass_is_left_alone_where_no_iri_is_asked_for(
        rule_id, prefix, class_name, tmp_path):
    """Section 7's whole point, and the population these rules must not reach.

    These rows exist because the reference tool asserts that elements of the
    class carry rdf:about. It reads the XML tree, so the population it can see
    is the one typed with the class itself, and the ontology never asks for an
    IRI here -- one entry says "IRI: optional" in as many words. Reaching past
    that turns a package's own subclass, the construct section 7 exists to
    allow, into an error the standard's own text does not ask for.
    """
    package = _subclassed(tmp_path, rule_id, str(NAMESPACES[prefix][class_name]))
    version = RULES[rule_id].versions[-1] if RULES[rule_id].versions else None
    report = runner.run(package, runner.CONFORMANCE_KINDS, version=version)

    assert rule_id not in {f.rule.id for f in report.findings}


@pytest.mark.parametrize("rule_id,prefix,class_name", REQUIRED,
                         ids=[r[0] for r in REQUIRED])
def test_it_fires_on_an_anonymous_instance_of_a_declared_subclass(
        rule_id, prefix, class_name, tmp_path):
    """The branch the other two never drove.

    Both existing parametrisations type the instance with the class itself, so
    between them they exercise one half of what the rule is generalising over
    and report a general result. `context.py` carries this project's own
    warning about it: exact typing is how section 7 gets forgotten one rule at
    a time.
    """
    package = _subclassed(tmp_path, rule_id, str(NAMESPACES[prefix][class_name]))
    version = RULES[rule_id].versions[-1] if RULES[rule_id].versions else None
    report = runner.run(package, runner.CONFORMANCE_KINDS, version=version)

    assert rule_id in {f.rule.id for f in report.findings}


@pytest.mark.parametrize("rule_id,prefix,class_name", MUST_HAVE_IRI,
                         ids=[r[0] for r in MUST_HAVE_IRI])
def test_it_stays_quiet_when_that_subclassed_instance_is_named(
        rule_id, prefix, class_name, tmp_path):
    """Widening the population is only right if it does not widen the finding."""
    package = _subclassed(tmp_path, rule_id, str(NAMESPACES[prefix][class_name]),
                          about="urn:test:named")
    version = RULES[rule_id].versions[-1] if RULES[rule_id].versions else None
    report = runner.run(package, runner.CONFORMANCE_KINDS, version=version)

    assert rule_id not in {f.rule.id for f in report.findings}

