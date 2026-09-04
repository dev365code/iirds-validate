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


def test_the_one_package_per_container_sentence_is_covered_in_both_limbs(tmp_path):
    """§6.2#5 -- "Each iiRDS package MUST have exactly one corresponding
    iirds:Package instance in the metadata" -- is violated by a count, and a
    count is wrong in two directions. Claiming the sentence means reporting
    both, so both are written here rather than the one that was easy.

    The third shape is the one that looks like a hole and is not. A lone
    package naming a parent leaves `container_packages()` empty, and M3 says
    nothing -- but that package is still *the* corresponding instance, wrongly
    declaring itself a member of another. That is §6.2#7, word for word, and
    R7 reports it. Counting it as a missing correspondence would put two
    findings on one mistake and claim a sentence M3 does not check.
    """
    import re

    none = re.sub(r"\s*<iirds:Package[\s\S]*?</iirds:Package>\n", "\n", MINIMAL_RDF)
    assert "<iirds:Package" not in none, "the fixture edit matched nothing"
    empty = {f.rule.id for f in runner.check(
        build_package(tmp_path, "m3_none.iirds", metadata=none)).findings}
    assert "M3" in empty, "no iirds:Package at all"

    two = ids(tmp_path, "m3_two.iirds",
              '  <iirds:Package rdf:about="urn:test:second">\n'
              "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
              "  </iirds:Package>\n")
    assert "M3" in two, "two packages representing one container"

    cycle = MINIMAL_RDF.replace("</rdf:RDF>", '''
  <iirds:Package rdf:about="urn:test:b">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:is-part-of-package rdf:resource="urn:test:package"/>
  </iirds:Package>
</rdf:RDF>''').replace(
        "</iirds:Package>",
        '  <iirds:is-part-of-package rdf:resource="urn:test:b"/>\n'
        "    </iirds:Package>", 1)
    assert "urn:test:b" in cycle, "the fixture edit matched nothing"
    circular = {f.rule.id for f in runner.check(
        build_package(tmp_path, "m3_cycle.iirds", metadata=cycle)).findings}
    assert "M3" in circular, (
        "two packages naming each other as parent leave the container with no "
        "corresponding instance at all, which is the same sentence: %s"
        % sorted(circular))

    orphan = MINIMAL_RDF.replace(
        "</iirds:Package>",
        '  <iirds:is-part-of-package rdf:resource="urn:test:elsewhere"/>\n'
        "    </iirds:Package>")
    assert orphan != MINIMAL_RDF, "the fixture edit matched nothing"
    astray = {f.rule.id for f in runner.check(
        build_package(tmp_path, "m3_orphan.iirds", metadata=orphan)).findings}
    assert "R7" in astray and "M3" not in astray, sorted(astray)


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


# ---------------------------------------------------------------------------
# "MUST be provided as a non-empty string" -- said twice, about two properties,
# and read two different ways until these two tests were written side by side.
#
# Four shapes break such a sentence: the property is absent, it holds an empty
# string, it holds an empty string beside a good one, and it holds something
# that is not a string at all. The last was silent in both properties and in
# both encodings -- `str(value).strip()` is happy with an IRI, and SHACL's
# sh:pattern matches the IRI's own text -- so the differential gate saw two
# implementations agreeing, which is all it can see.
#
# The ontology settles it rather than a reading: both properties are declared
# `rdfs:range rdfs:Literal`, and iirds:classificationIdentifier's own
# description asks for "a string conforming to a non-IRI identifier".
# ---------------------------------------------------------------------------

def _identity(inner):
    return ('  <iirds:IdentityDomain rdf:about="urn:test:dom"/>\n'
            '  <iirds:Identity rdf:about="urn:test:ident">\n'
            '    <iirds:has-identity-domain rdf:resource="urn:test:dom"/>\n'
            + inner + "  </iirds:Identity>\n")


def _classification(inner):
    return ('  <iirds:ClassificationDomain rdf:about="urn:test:cdom"/>\n'
            '  <iirds:ExternalClassification rdf:about="urn:test:xc">\n'
            '    <iirds:has-classification-domain rdf:resource="urn:test:cdom"/>\n'
            + inner + "  </iirds:ExternalClassification>\n")


#: property -> (builder, the rules that together claim the sentence). The
#: absent limb belongs to a different rule in each family -- M19.2 answers it
#: for the identity, M96.2 for the classification -- which is exactly why the
#: claim is checked over the rules that claim the id, not over one of them.
NON_EMPTY_STRING = {
    "iirds:identifier": (_identity, {"M19.2"}),
    "iirds:classificationIdentifier": (_classification, {"M96.2", "M96.3"}),
}


@pytest.mark.parametrize("prop", sorted(NON_EMPTY_STRING), ids=sorted(NON_EMPTY_STRING))
def test_the_non_empty_string_sentence_is_covered_in_every_limb(tmp_path, prop):
    build, claimants = NON_EMPTY_STRING[prop]
    seen = {}

    def limb(name, inner):
        got = ids(tmp_path, "nes_%d.iirds" % abs(hash((prop, name))), build(inner))
        seen[name] = sorted(claimants & got)
        assert claimants & got, "%s, %s: reported by nobody who claims the sentence: %s" % (
            prop, name, sorted(got))

    limb("absent", "")
    limb("empty", "    <%s></%s>\n" % (prop, prop))
    limb("empty beside a good one",
         "    <%s></%s>\n    <%s>A-1</%s>\n" % (prop, prop, prop, prop))
    limb("an IRI, which is not a string",
         '    <%s rdf:resource="urn:test:elsewhere"/>\n' % prop)
    limb("a blank node, which is not a string either",
         "    <%s rdf:parseType=\"Resource\"><rdfs:label>x</rdfs:label></%s>\n"
         % (prop, prop))

    good = ids(tmp_path, "nes_ok_%d.iirds" % abs(hash(prop)),
               build("    <%s>A-1</%s>\n" % (prop, prop)))
    assert not (claimants & good), "the control fires: %s" % sorted(claimants & good)


#: §6.3.3: "the referenced parent iiRDS container MUST NOT have any outgoing
#: iirds:is-part-of-package relations." One sentence, three shapes.
BROKEN_NESTING = {
    "a package that is part of itself": (
        '  <iirds:Package rdf:about="urn:test:a">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:a"/>\n'
        '  </iirds:Package>\n'),
    "a chain three deep": (
        '  <iirds:Package rdf:about="urn:test:a">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:b"/>\n'
        '  </iirds:Package>\n'
        '  <iirds:Package rdf:about="urn:test:b">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:c"/>\n'
        '  </iirds:Package>\n'
        '  <iirds:Package rdf:about="urn:test:c">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '  </iirds:Package>\n'),
    "two packages inside each other": (
        '  <iirds:Package rdf:about="urn:test:a">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:b"/>\n'
        '  </iirds:Package>\n'
        '  <iirds:Package rdf:about="urn:test:b">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:a"/>\n'
        '  </iirds:Package>\n'),
}

#: The standard's own Example 16: one level, and the parent points at nothing.
GOOD_NESTING = (
    '  <iirds:Package rdf:about="urn:test:parent">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '  </iirds:Package>\n'
    '  <iirds:Package rdf:about="urn:test:nested">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:is-part-of-package rdf:resource="urn:test:parent"/>\n'
    '  </iirds:Package>\n')


@pytest.mark.parametrize("shape", sorted(BROKEN_NESTING), ids=sorted(BROKEN_NESTING))
def test_r5_reports_a_parent_that_is_itself_inside_something(tmp_path, shape):
    """Nesting is one level deep by construction: §6.3.3 says the package a
    child names must have no is-part-of-package of its own. Nothing here
    implemented that sentence, so a package part of itself, a chain and a
    cycle were each read as ordinary nesting and reported by nobody."""
    assert "R5" in ids(tmp_path, "r5_%s.iirds" % abs(hash(shape)),
                       BROKEN_NESTING[shape], replace=HEAD)


def test_r5_is_silent_about_the_nesting_the_standard_prints(tmp_path):
    """Example 16's shape: one child, one parent, and the parent is inside
    nothing."""
    assert "R5" not in ids(tmp_path, "r5_good.iirds", GOOD_NESTING, replace=HEAD)


#: The parent's file, with a unit of its own pointing at the package this
#: document says is nested. §5.3 forbids exactly this: "An iiRDS package that
#: contains a nested iiRDS package MUST NOT contain metadata about the content
#: of the nested iiRDS package."
CONTENT_OF_THE_NESTED = (
    '  <iirds:Package rdf:about="urn:test:parent">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '  </iirds:Package>\n'
    '  <iirds:Package rdf:about="urn:test:nested">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:is-part-of-package rdf:resource="urn:test:parent"/>\n'
    '  </iirds:Package>\n'
    '  <iirds:Topic rdf:about="urn:test:topic">\n'
    '    <iirds:title>Borrowed from the child</iirds:title>\n'
    '    <iirds:is-part-of-package rdf:resource="urn:test:nested"/>\n'
    '  </iirds:Topic>\n')

#: The same three subjects with the unit pointing where it belongs.
CONTENT_OF_OUR_OWN = CONTENT_OF_THE_NESTED.replace(
    '<iirds:is-part-of-package rdf:resource="urn:test:nested"/>\n'
    '  </iirds:Topic>',
    '<iirds:is-part-of-package rdf:resource="urn:test:parent"/>\n'
    '  </iirds:Topic>')


def test_r6_reports_a_unit_belonging_to_the_package_this_document_says_is_nested(tmp_path):
    """The finding is compelled whichever container this turns out to be, which
    is why it can be reported without deciding. Read this as the parent's file
    and §5.3 is broken: the outer package is carrying metadata about the
    content of the nested one. Read it as the child's own file -- someone
    handing over the inner container -- and §6.2 is broken instead, because a
    package's own instance must not be a member of another package. There is
    no reading in which the document is clean, so no disambiguation is
    needed to say so."""
    assert "R6" in ids(tmp_path, "r6_bad.iirds", CONTENT_OF_THE_NESTED, replace=HEAD)


def test_r6_is_silent_when_the_unit_belongs_to_the_package_this_container_is(tmp_path):
    """The ordinary shape, and the one both Consortium samples use: every unit
    points at the package the container itself is about. Nesting is present
    and the unit is not the nested package's content."""
    assert "R6" not in ids(tmp_path, "r6_own.iirds", CONTENT_OF_OUR_OWN, replace=HEAD)


def test_r6_is_silent_about_the_nesting_the_standard_prints(tmp_path):
    """Example 16 again: a parent that declares its child and describes none
    of the child's content. The published shape must stay clean, because the
    Consortium prints a parent whose whole metadata is one version triple."""
    assert "R6" not in ids(tmp_path, "r6_example16.iirds", GOOD_NESTING, replace=HEAD)


def test_r6_leaves_a_package_subject_to_r5(tmp_path):
    """The relation is split between two rules by its subject, and this is the
    seam. In a chain the middle package is nested and the outer one points at
    it, so dropping the "not a package" test would have this rule report what
    R5 already reports. Written because the rule passed its other tests
    without that test doing anything.

    Not because a package is outside §5.3's reach: §6.2 lists iirds:Package
    among the subclasses of iirds:InformationUnit, so a package nested inside
    a nested package really is the nested package's content, and the first
    version of this docstring said the opposite. The reason is that one graph
    should not draw two findings under two requirement ids for one triple,
    and §6.3.3 -- R5's sentence -- is the one that names this shape."""
    got = ids(tmp_path, "r6_chain.iirds", BROKEN_NESTING["a chain three deep"],
              replace=HEAD)
    assert "R5" in got, "the chain is R5's finding"
    assert "R6" not in got, "reported once, under the requirement that names the shape"


def test_r6_does_not_see_the_childs_units_copied_in_without_the_relation(tmp_path):
    """The boundary of the rule, pinned so that crossing it is deliberate.

    §5.3's sentence is about metadata describing the nested package's content,
    and the commonest way to break it is not the one this reports: a generator
    that flattens the child's units into the parent's metadata and simply
    leaves out the iirds:is-part-of-package relations describes that content
    and draws nothing. Recorded as a gap in docs/divergences.md rather than
    approximated, because "metadata about the content" has no other graph form
    to key on without guessing which units belong to whom.
    """
    flattened = (
        '  <iirds:Package rdf:about="urn:test:outer">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '  </iirds:Package>\n'
        '  <iirds:Package rdf:about="urn:test:nested">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n'
        '  </iirds:Package>\n'
        '  <iirds:Topic rdf:about="urn:test:childs-topic">\n'
        '    <iirds:title>A topic of the nested package, described here</iirds:title>\n'
        '  </iirds:Topic>\n')
    assert "R6" not in ids(tmp_path, "r6_flat.iirds", flattened, replace=HEAD), (
        "if this starts firing the rule has been widened -- say so in "
        "docs/divergences.md and in the changelog, because the sentence it "
        "covers would then be covered further than it was")


def test_r7_reports_the_container_package_naming_a_parent(tmp_path):
    """§6.2: "The corresponding iirds:Package instance of an iiRDS package
    MUST NOT be a member of another iiRDS package expressed by the property
    iirds:is-part-of-package."

    The realistic spelling of the nesting defect, and nothing reported it: a
    child handed over on its own, whose metadata still names the parent it was
    packed inside. The parent is not described here, so the package stays the
    one this container is about -- and carries a relation the sentence above
    forbids it. R6 cannot see this: it keys on units pointing at a package
    *this document declares nested*, and nothing here is declared nested."""
    childs_own = HEAD.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        '    <iirds:is-part-of-package rdf:resource="urn:test:parent-elsewhere"/>\n')
    assert "R7" in ids(tmp_path, "r7_childown.iirds", "", replace=childs_own)


def test_r7_is_silent_about_a_child_declared_in_its_parents_file(tmp_path):
    """§6.3.3 asks the parent's metadata to carry exactly this relation on the
    nested child, so the relation is not the defect -- carrying it on the
    package that represents *this* container is. Example 16's shape."""
    assert "R7" not in ids(tmp_path, "r7_example16.iirds", GOOD_NESTING, replace=HEAD)


def test_r7_is_silent_about_a_package_inside_itself(tmp_path):
    """"a member of *another* iiRDS package". Naming itself is not that, and
    R5 already reports the shape under the sentence that does name it."""
    got = ids(tmp_path, "r7_loop.iirds", BROKEN_NESTING["a package that is part of itself"],
              replace=HEAD)
    assert "R5" in got
    assert "R7" not in got


def test_r6_sees_a_subject_the_document_never_types(tmp_path):
    """The rule keys on "not a package" rather than "is an information unit",
    and its reasoning says an untyped subject is therefore not a way out. That
    sentence was in the docstring and in no test: narrowing the filter to
    typed information units changed nothing anywhere in the suite."""
    untyped = CONTENT_OF_THE_NESTED[:CONTENT_OF_THE_NESTED.index(
        '  <iirds:Topic')] + (
        '  <rdf:Description rdf:about="urn:test:topic">\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:nested"/>\n'
        '  </rdf:Description>\n')
    assert "R6" in ids(tmp_path, "r6_untyped.iirds", untyped, replace=HEAD)


def test_r6_names_the_unit_and_not_the_package(tmp_path):
    """Which node a finding hangs off is what a reader goes and looks at, and
    both nodes are in the graph, so naming the wrong one is invisible to a
    test that only counts rule ids."""
    metadata = (HEAD + CONTENT_OF_THE_NESTED + "</rdf:RDF>\n").replace(
        'xmlns:iirds=', EXTRA_NS + ' xmlns:iirds=', 1)
    package = build_package(tmp_path, "r6_subject.iirds", metadata=metadata)
    subjects = [f.violation.subject for f in runner.check(package).findings
                if f.rule.id == "R6"]
    assert subjects == ["urn:test:topic"], subjects


def with_nested(tmp_path, name, body, entries=()):
    metadata = (HEAD + body + "</rdf:RDF>\n").replace(
        'xmlns:iirds=', EXTRA_NS + ' xmlns:iirds=', 1)
    package = build_package(tmp_path, name, metadata=metadata, extra=entries)
    return {f.rule.id for f in runner.check(package).findings}


def a_nested_container(tmp_path):
    where = tmp_path / "inner"
    where.mkdir(parents=True, exist_ok=True)
    return build_package(where, "inner.iirds").read_bytes()


def test_r8_reports_a_declared_nested_package_that_is_not_in_the_archive(tmp_path):
    """§6.3.3: "All nested iiRDS containers MUST be included side by side in
    the iiRDS ZIP archive of the highest level iiRDS package." The metadata
    declares a nested package and the archive carries none, which no rule
    said anything about."""
    assert "R8" in with_nested(tmp_path, "r8_absent.iirds", GOOD_NESTING)


def test_r8_is_silent_when_the_nested_container_is_here(tmp_path):
    assert "R8" not in with_nested(
        tmp_path, "r8_present.iirds", GOOD_NESTING,
        entries=(("content/inner.iirds", a_nested_container(tmp_path)),))


def test_r8_is_not_satisfied_by_a_file_that_only_ends_in_iirds(tmp_path):
    """Without the header test this rule is answered by sixteen bytes of
    anything under a name ending in .iirds, which is a worse state than not
    having the rule: it would read as evidence."""
    assert "R8" in with_nested(
        tmp_path, "r8_decoy.iirds", GOOD_NESTING,
        entries=(("content/inner.iirds", b"not a zip at all"),))


def test_r8_is_silent_when_nothing_is_declared_nested(tmp_path):
    """A container carrying no nesting declaration owes no nested container,
    and one carrying a stray .iirds is not thereby a parent."""
    assert "R8" not in with_nested(tmp_path, "r8_none.iirds", "")


#: The container's own package declaring the handover profile, so the run is
#: read as iiRDS/H. Nothing else about the handover profile matters here.
HANDOVER_HEAD = HEAD.replace(
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
    "    <iirds:formatRestriction>H</iirds:formatRestriction>\n")

#: One nested child declared the way §6.3.3 asks, which is legal in an
#: unrestricted package and forbidden in a handover one.
A_NESTED_CHILD = ('  <iirds:Package rdf:about="urn:test:nested">\n'
                  '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
                  '    <iirds:is-part-of-package rdf:resource="urn:test:package"/>\n'
                  '  </iirds:Package>\n')


def handover_ids(tmp_path, name, body, entries=()):
    metadata = (HANDOVER_HEAD + body + "</rdf:RDF>\n").replace(
        'xmlns:iirds=', EXTRA_NS + ' xmlns:iirds=', 1)
    package = build_package(tmp_path, name, metadata=metadata, extra=entries)
    return {f.rule.id for f in runner.check(package).findings}


def test_r9_refuses_a_nested_package_declared_in_a_handover_package(tmp_path):
    """§6.7.3: "iiRDS/H packages MUST use this variant of hierarchy formation
    and MUST NOT contain nested packages." Component trees are the handover
    profile's way of saying what is inside what, and nesting is the thing it
    replaces. Neither this sentence nor §8.3.1.2's was claimed by any rule."""
    assert "R9" in handover_ids(tmp_path, "r9_declared.iirds", A_NESTED_CHILD)


def test_r9_refuses_a_nested_archive_in_a_handover_package(tmp_path):
    """§8.3.1.2: "an iiRDS/H package MUST NOT contain another iiRDS ZIP
    archive." The other half, and the archive half: a handover container
    carrying a nested container is refused even when its metadata declares
    nothing, because the sentence is about the archive."""
    where = tmp_path / "inner9"
    where.mkdir(parents=True, exist_ok=True)
    inner = build_package(where, "inner.iirds").read_bytes()
    assert "R9" in handover_ids(tmp_path, "r9_archive.iirds", "",
                                entries=(("content/inner.iirds", inner),))


def test_r9_leaves_an_unrestricted_package_alone(tmp_path):
    """§8.3.1.2 opens by permitting exactly this: "While unrestricted iiRDS
    packages MAY be nested by nesting iiRDS ZIP archives in each other for
    compatibility reasons". The prohibition is the handover profile's."""
    assert "R9" not in with_nested(tmp_path, "r9_unrestricted.iirds", A_NESTED_CHILD)


def test_r9_is_silent_about_a_handover_package_that_nests_nothing(tmp_path):
    assert "R9" not in handover_ids(tmp_path, "r9_plain.iirds", "")


#: A handover package that declares itself nested inside an outer package it
#: does not describe: the profile is read off the package this container is
#: about, so adding a description of that outer package moves the answer.
BYPASS_DEFECT = MINIMAL_RDF.replace(
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
    "    <iirds:formatRestriction>H</iirds:formatRestriction>\n"
    '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n')

BYPASS_STUB = ('  <iirds:Package rdf:about="urn:test:outer">\n'
               '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
               '  </iirds:Package>\n')


def test_describing_the_outer_package_does_not_buy_a_clean_pass(tmp_path):
    """Three lines that used to switch the handover profile off and take the
    run to no findings at all.

    Adding a description of the outer package is not itself a defect -- the
    standard prints exactly that shape, a parent whose whole metadata is one
    version triple, in §6.3.3 Example 16 -- so the repair is not to refuse it.
    The repair is that the archive is asked whether the nested container it
    now claims is actually here. Measured before that rule existed: the second
    row below reported one warning and the third reported nothing at all and
    exited zero.

    The fourth row is left passing on purpose and is not a hole this project
    knows how to close: a container that carries a real nested iiRDS container
    is, in everything observable, a parent with a child, and the handover
    claim then sits on a package the metadata says is inside it rather than on
    this container. The profile is read off the package this container is
    about; §6.3.3 Example 16 puts the child's own restriction in the child's
    own file, which this validator does not open.
    """
    where = tmp_path / "inner_bypass"
    where.mkdir(parents=True, exist_ok=True)
    real = build_package(where, "inner.iirds").read_bytes()
    stubbed = BYPASS_DEFECT.replace("</rdf:RDF>", BYPASS_STUB + "</rdf:RDF>")

    def run(name, metadata, extra=()):
        report = runner.check(build_package(tmp_path, name, metadata=metadata, extra=extra))
        return report.ok, {f.rule.id for f in report.findings}

    ok, plain = run("bypass_plain.iirds", BYPASS_DEFECT)
    assert not ok and {"M15.9", "M15.11a"} <= plain, plain

    ok, stub_only = run("bypass_stub.iirds", stubbed)
    assert not ok, "the stub used to leave one warning and a passing run"
    assert "R8" in stub_only, stub_only

    ok, decoy = run("bypass_decoy.iirds", stubbed,
                    (("content/nested.iirds", b"not a zip at all"),))
    assert not ok, "sixteen bytes under a name ending .iirds used to be enough"
    assert "R8" in decoy, decoy

    ok, honest = run("bypass_honest.iirds", stubbed,
                     (("content/nested.iirds", real),))
    assert ok, honest


def test_r6_and_r7_answer_for_different_documents(tmp_path):
    """The two nesting sentences divide the ambiguous document between them
    and must not both claim it. R6 reads a parent's file: a unit of this
    container pointing at a package the same file says is nested. R7 reads a
    child's own file: the package this container is about, naming a parent
    the file does not describe. Neither shape is the other's, and a finding
    counted twice under two requirement ids would inflate the coverage figure
    while telling a reader the same thing in two voices."""
    unit = ('  <iirds:Topic rdf:about="urn:test:topic">\n'
            '    <iirds:title>A unit</iirds:title>\n'
            '    <iirds:is-part-of-package rdf:resource="urn:test:nested"/>\n'
            '  </iirds:Topic>\n')
    parents_file = GOOD_NESTING.replace("urn:test:parent", "urn:test:package") + unit
    got = ids(tmp_path, "seam_parent.iirds", parents_file, replace=HEAD)
    assert "R6" in got and "R7" not in got, got

    childs_own = HEAD.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        '    <iirds:is-part-of-package rdf:resource="urn:test:parent-elsewhere"/>\n')
    got = ids(tmp_path, "seam_child.iirds", "", replace=childs_own)
    assert "R7" in got and "R6" not in got, got
