"""The last of the rules no test had ever made fire.

What is left after the generated table, the cardinality family, the container
rules and the handover profile: fifteen one-offs, each needing a graph shaped a
particular way. None of them is hard. They were skipped because each is
different, and a rule skipped for being inconvenient is indistinguishable from
a rule that does not work.
"""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

HEAD = MINIMAL_RDF.replace("</rdf:RDF>", "")
EXTRA_NS = ('xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:ext="http://example.com/product#"')


def ids(tmp_path, name, body, replace=None):
    metadata = (replace if replace is not None else HEAD) + body + "</rdf:RDF>\n"
    metadata = metadata.replace('xmlns:iirds=', EXTRA_NS + ' xmlns:iirds=', 1)
    package = build_package(tmp_path, name, metadata=metadata)
    return {f.rule.id for f in runner.check(package).findings}


def test_m8_the_enclosing_package_given_a_rendition(tmp_path):
    """A container does not render. The exemption is iirds:is-part-of-package:
    a *nested* package is content of its parent and may well have one, so the
    rule keys on the absence of that relation *to another package this
    document describes* to find the enclosing package -- the outer package is
    declared below, because §6.3.3 asks the child to reference an
    iirds:Package and a name nothing describes is not one."""
    given = ids(tmp_path, "m8.iirds", '''
  <rdf:Description rdf:about="urn:test:package">
    <iirds:has-rendition rdf:resource="urn:test:r99"/>
  </rdf:Description>
''')
    assert "M8" in given

    nested = ids(tmp_path, "m8b.iirds", '''
  <iirds:Package rdf:about="urn:test:outer">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
  </iirds:Package>
  <rdf:Description rdf:about="urn:test:package">
    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>
    <iirds:has-rendition rdf:resource="urn:test:r99"/>
  </rdf:Description>
''')
    assert "M8" not in nested, "a nested package is content, and content renders"


#: Five ways to name a parent that is not one. §6.3.3 asks the nested child's
#: package to "reference exactly one iirds:Package", and each of these
#: references something else -- so none of them makes the package a child.
NOT_A_PARENT = {
    "a parent this document does not describe":
        '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n',
    "a parent that is not a package":
        '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n'
        '  </rdf:Description>\n  <iirds:Topic rdf:about="urn:test:outer"/>\n'
        '  <rdf:Description rdf:about="urn:test:package">\n',
    "a parent written as a literal":
        '    <iirds:is-part-of-package>urn:test:outer</iirds:is-part-of-package>\n',
    "a parent with no name at all":
        '    <iirds:is-part-of-package><rdf:Description>'
        '<rdfs:label>outer</rdfs:label></rdf:Description></iirds:is-part-of-package>\n',
    "a self-loop beside a parent that is not here":
        '    <iirds:is-part-of-package rdf:resource="urn:test:package"/>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n',
}

#: The control: a parent this document does describe. Example 16's shape.
A_REAL_PARENT = ('    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n'
                 '  </rdf:Description>\n'
                 '  <iirds:Package rdf:about="urn:test:outer">\n'
                 '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
                 '  </iirds:Package>\n'
                 '  <rdf:Description rdf:about="urn:test:package">\n')

RENDERS = '    <iirds:has-rendition rdf:resource="urn:test:r99"/>\n'


@pytest.mark.parametrize("shape", sorted(NOT_A_PARENT), ids=sorted(NOT_A_PARENT))
def test_m8_is_not_silenced_by_a_parent_that_is_not_a_package_here(tmp_path, shape):
    """The exemption §6.3 grants a nested package is for content of another
    package. Granting it on the bare presence of the predicate meant any
    object at all bought it -- and the last of these five pairs the self-loop
    closed one commit ago with one meaningless IRI, which opened it again."""
    body = '  <rdf:Description rdf:about="urn:test:package">\n' + \
        NOT_A_PARENT[shape] + RENDERS + "  </rdf:Description>\n"
    assert "M8" in ids(tmp_path, "m8_%s.iirds" % abs(hash(shape)), body)


def test_m8_still_exempts_a_package_this_document_says_is_inside_another(tmp_path):
    """The control, and the shape of the standard's own Example 16: the parent
    is here and it is a package, so the child is content and content renders."""
    body = ('  <rdf:Description rdf:about="urn:test:package">\n'
            + A_REAL_PARENT + RENDERS + "  </rdf:Description>\n")
    assert "M8" not in ids(tmp_path, "m8_real.iirds", body)


@pytest.mark.parametrize("shape", sorted(NOT_A_PARENT), ids=sorted(NOT_A_PARENT))
def test_m3_counts_a_package_whose_named_parent_is_not_here(tmp_path, shape):
    """M3 reads the same predicate, so the same five hid a second package
    from "exactly one iirds:Package represents this container"."""
    body = ('  <rdf:Description rdf:about="urn:test:package">\n'
            + NOT_A_PARENT[shape] + "  </rdf:Description>\n"
            + '  <iirds:Package rdf:about="urn:test:second">\n'
            + "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
            + "  </iirds:Package>\n")
    assert "M3" in ids(tmp_path, "m3_%s.iirds" % abs(hash(shape)), body)


def test_m8_is_not_silenced_by_a_package_that_is_part_of_itself(tmp_path):
    """§6.2 draws the line with one word: the container's own instance "MUST
    NOT be a member of *another* iiRDS package expressed by the property
    iirds:is-part-of-package". A package naming itself is not a member of
    another package and is content of nothing, so it keeps the MUST NOT that
    §6.3 puts on the container. Read as the bare presence of the predicate,
    one triple a package cannot legally carry made the finding disappear."""
    assert "M8" in ids(tmp_path, "m8c.iirds", '''
  <rdf:Description rdf:about="urn:test:package">
    <iirds:is-part-of-package rdf:resource="urn:test:package"/>
    <iirds:has-rendition rdf:resource="urn:test:r99"/>
  </rdf:Description>
''')


def test_m9_a_source_that_points_outside_the_package(tmp_path):
    """iirds:source addresses a file inside the container, so an absolute path
    or a URL names something the consumer does not have."""
    outside = MINIMAL_RDF.replace("<iirds:source>content/topic1.xhtml</iirds:source>",
                                  "<iirds:source>/etc/passwd</iirds:source>")
    package = build_package(tmp_path, "m9.iirds", metadata=outside)
    assert "M9" in {f.rule.id for f in runner.check(package).findings}


def test_m10_a_rendition_with_no_source(tmp_path):
    without = MINIMAL_RDF.replace(
        "        <iirds:source>content/topic1.xhtml</iirds:source>\n", "")
    package = build_package(tmp_path, "m10.iirds", metadata=without)
    assert "M10" in {f.rule.id for f in runner.check(package).findings}


def test_m12_the_selector_base_class_used_directly(tmp_path):
    """The base class does not say how to address the part, so a consumer
    cannot resolve it. Typed exactly, not by subclass."""
    assert "M12" in ids(tmp_path, "m12.iirds", '''
  <iirds:Selector rdf:about="urn:test:sel"/>
''')


def test_m13_a_value_selector_missing_its_value_or_its_scheme(tmp_path):
    """rdf:value is the expression; dcterms:conformsTo says how to read it.
    A RangeSelector is exempt -- it delegates to its endpoints, which is
    M14's business, and asking it for a value reports every correct range."""
    no_value = ids(tmp_path, "m13a.iirds", '''
  <iirds:FragmentSelector rdf:about="urn:test:sel1">
    <dcterms:conformsTo rdf:resource="http://www.w3.org/TR/xpath/"/>
  </iirds:FragmentSelector>
''')
    assert "M13.1" in no_value

    no_scheme = ids(tmp_path, "m13b.iirds", '''
  <iirds:FragmentSelector rdf:about="urn:test:sel2">
    <rdf:value>//section[1]</rdf:value>
  </iirds:FragmentSelector>
''')
    assert "M13.2" in no_scheme


def test_m14_a_range_missing_an_endpoint(tmp_path):
    start_only = ids(tmp_path, "m14a.iirds", '''
  <iirds:RangeSelector rdf:about="urn:test:r1">
    <iirds:has-start-selector rdf:resource="urn:test:s1"/>
  </iirds:RangeSelector>
''')
    assert "M14.2" in start_only and "M14.1" not in start_only

    end_only = ids(tmp_path, "m14b.iirds", '''
  <iirds:RangeSelector rdf:about="urn:test:r2">
    <iirds:has-end-selector rdf:resource="urn:test:s2"/>
  </iirds:RangeSelector>
''')
    assert "M14.1" in end_only and "M14.2" not in end_only


def test_m16_an_event_without_its_code_or_its_type(tmp_path):
    """The code is what a technician reads off the panel; the type says what
    kind of thing it is. A consumer needs both to make an event findable.

    Declared as 1.1 because the catalogue scopes both rules to 1.0, 1.0.1 and
    1.1 and this project honours that. Whether the scoping is right is a
    separate question -- every `versions` array came from the reference tool
    and none has been checked against anything -- but a test that quietly
    declared 1.3 would be asserting the opposite of what the rule says about
    itself.
    """
    v11 = HEAD.replace("<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
                       "<iirds:iiRDSVersion>1.1</iirds:iiRDSVersion>")
    no_code = ids(tmp_path, "m16a.iirds", '''
  <iirds:Event rdf:about="urn:test:e1">
    <iirds:has-event-type rdf:resource="http://iirds.tekom.de/iirds#Error"/>
  </iirds:Event>
''', replace=v11)
    assert "M16.1" in no_code

    no_type = ids(tmp_path, "m16b.iirds", '''
  <iirds:Event rdf:about="urn:test:e2">
    <iirds:has-event-code>E-417</iirds:has-event-code>
  </iirds:Event>
''', replace=v11)
    assert "M16.2" in no_type


def test_m16_3_an_event_extension_that_is_never_declared_a_class(tmp_path):
    """A subclass nobody declared is a dangling name: the consumer sees the
    relationship and has nothing to resolve it to."""
    assert "M16.3" in ids(tmp_path, "m16c.iirds", '''
  <rdf:Description rdf:about="http://example.com/e#Overheat">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Event"/>
  </rdf:Description>
''')


def test_m17_components_referenced_only_through_an_external_vocabulary(tmp_path):
    """Narrower than "every referenced IRI must be declared", deliberately:
    tekom's own external-ontology sample references more components than it
    declares, and the strict reading fails the standard's own example. This is
    the case it does catch -- pointing outward and declaring nothing at all."""
    assert "M17" in ids(tmp_path, "m17.iirds", '''
  <rdf:Description rdf:about="urn:test:topic1">
    <iirds:relates-to-component rdf:resource="http://example.com/product#Spindle"/>
  </rdf:Description>
''')


def test_m18_product_variants_referenced_but_never_declared(tmp_path):
    """The same shape as M17, on the other relation. Product variants are a
    proprietary extension, so they travel inside the package: a consumer that
    cannot reach the external vocabulary has a relation and no subject."""
    referenced = ids(tmp_path, "m18.iirds", '''
  <rdf:Description rdf:about="urn:test:topic1">
    <iirds:relates-to-product-variant rdf:resource="http://example.com/product#Rotor3000"/>
  </rdf:Description>
''')
    assert "M18" in referenced

    declared = ids(tmp_path, "m18b.iirds", '''
  <rdf:Description rdf:about="urn:test:topic1">
    <iirds:relates-to-product-variant rdf:resource="urn:test:rotor"/>
  </rdf:Description>
  <iirds:ProductVariant rdf:about="urn:test:rotor">
    <rdfs:label xml:lang="en">Rotor 3000</rdfs:label>
  </iirds:ProductVariant>
''')
    assert "M18" not in declared


def test_m19_4_an_identity_domain_that_is_not_one(tmp_path):
    """Described in the package, and typed as something else. An undescribed
    reference is L1's business, not this rule's."""
    found = ids(tmp_path, "m19_4.iirds", '''
  <iirds:Identity rdf:about="urn:test:i1">
    <iirds:identifier>X1</iirds:identifier>
    <iirds:has-identity-domain rdf:resource="urn:test:not-a-domain"/>
  </iirds:Identity>
  <iirds:Component rdf:about="urn:test:not-a-domain">
    <rdfs:label xml:lang="en">A component, not a domain</rdfs:label>
  </iirds:Component>
''')
    assert "M19.4" in found


def test_m94_the_general_administrative_relation_used_directly(tmp_path):
    """The grouping relation says only that some administrative link exists,
    which a consumer cannot act on."""
    assert "M94" in ids(tmp_path, "m94.iirds", '''
  <rdf:Description rdf:about="urn:test:topic1">
    <iirds:relates-to-administrative-metadata rdf:resource="urn:test:something"/>
  </rdf:Description>
''')


def test_m96_3_an_empty_classification_identifier(tmp_path):
    """Worse than an absent one: it looks answered and matches nothing."""
    assert "M96.3" in ids(tmp_path, "m96_3.iirds", '''
  <iirds:ExternalClassification rdf:about="urn:test:c1">
    <iirds:classificationIdentifier></iirds:classificationIdentifier>
    <iirds:has-classification-domain rdf:resource="urn:test:d1"/>
  </iirds:ExternalClassification>
''')
