"""One identity domain names one kind of identity.

Appendix A gives `iirds:has-identity-type` on `iirds:IdentityDomain` as
`0..1`, and nothing checked it. The consequence is not only an ambiguous
domain: section 8.3.2 asks four times for a domain of a named identity type
whose party is the manufacturer, and a domain declaring two types satisfies
two of those four with one party -- so a package can answer the instance
question and the product-type question with the same statement and identify
one thing where the standard asks for two.
"""
from __future__ import annotations

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

IIRDS = "http://iirds.tekom.de/iirds#"


def domain(types):
    lines = "".join('    <iirds:has-identity-type rdf:resource="%s%s"/>\n' % (IIRDS, t)
                    for t in types)
    return MINIMAL_RDF.replace("</rdf:RDF>", """
  <iirds:IdentityDomain rdf:about="urn:test:domain">
    <rdfs:label xml:lang="en">Serial numbers</rdfs:label>
%s  </iirds:IdentityDomain>
</rdf:RDF>""" % lines)


def ids(tmp_path, name, types):
    return {f.rule.id for f in runner.run(
        build_package(tmp_path, name, metadata=domain(types)), runner.ALL_KINDS).findings}


def test_one_identity_type_is_fine(tmp_path):
    assert "R17" not in ids(tmp_path, "one.iirds", ("SerialNumber",))


def test_no_identity_type_is_fine(tmp_path):
    """`0..1`, not `1`. A domain that names no type is a different question,
    and section 8.3.2 asks it only of the domains its own bullets reach."""
    assert "R17" not in ids(tmp_path, "none.iirds", ())


def test_two_identity_types_are_reported(tmp_path):
    got = ids(tmp_path, "two.iirds", ("SerialNumber", "ProductType"))
    assert "R17" in got, sorted(got)


def test_a_domain_with_two_types_cannot_answer_both_handover_questions(tmp_path):
    """The reason the cardinality matters here rather than in the abstract.

    Section 8.3.2 wants an instance identity and a product type identity, each
    with a manufacturer. Merge the two domains into one that declares both
    types and the handover rules fall silent -- one party, both questions
    answered. With the cardinality checked, that package is reported.
    """
    from test_handover_rules_fire import HANDOVER, _package

    merged = HANDOVER.replace(
        '    <iirds:has-identity-type rdf:resource="%sProductType"/>\n' % IIRDS, "", 1).replace(
        '    <iirds:has-identity-type rdf:resource="%sSerialNumber"/>\n' % IIRDS,
        '    <iirds:has-identity-type rdf:resource="%sSerialNumber"/>\n'
        '    <iirds:has-identity-type rdf:resource="%sProductType"/>\n' % (IIRDS, IIRDS), 1)
    assert merged != HANDOVER
    got = {f.rule.id for f in runner.run(_package(tmp_path, "merged.iirds", merged),
                                         runner.ALL_KINDS).findings}
    assert "R17" in got, sorted(got)
