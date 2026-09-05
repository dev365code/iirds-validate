"""The other half of five sentences that name a class and a property.

`_points_at_an_instance_of` in `rules/schema.py` says it out loud: *"MUST have
an X which is assigned by property P" -- the X half. Three sentences of chapter
6 have this shape and each needs two rules: one to count the property, one to
ask what it points at.*

Three is what somebody found. Measuring it -- one package per relation, the
property written as a literal, and asking which MUST-level rule stays quiet --
says **eight**, and five of the eight never got their second rule:

    property                     counts it   asks what it points at
    has-content-lifecycle-…      M21.1       R10
    has-party-role               M22.1       M22.2
    relates-to-vcard             M23         R12
    has-document-type            M15.1       R19   <- this file
    has-start-selector           M14.1       R20
    has-end-selector             M14.2       R21
    has-identity-domain          M19.3/M36   R22
    has-classification-domain    M96.1       R23

The sharpest of the five is the document type. A `iirds:Document` with no
document type fails `iirds check`; the same document naming its type as the
string "OperatingInstructions" passed. **Writing text was better than leaving
it out**, which is the opposite of what the sentence says and the opposite of
what a reader would guess. The other four are not verdict flips -- a
neighbouring rule reports those packages for a different reason -- but the
finding a user reads names a sentence they did not break and offers the repair
for it.

Both halves claim the sentence, because neither half alone reports every
package that breaks it: none of the property is the counting rule's case, and
the wrong target is this one's. That is the convention the three finished pairs
already follow, and `test_covers_is_earned` records what happened the once it
was not followed -- "one of those three was claimed by a rule that stays quiet
in exactly the case its partner rule exists to report, and the partner did not
claim it".
"""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.registry import all_rules

IIRDS = "http://iirds.tekom.de/iirds#"

#: rule -> (class to instantiate, property, the class the ontology gives as its
#: range, an instance of something else). Read from the ontology when this was
#: written: the selectors take a `FragmentSelector` and not a `Selector`, which
#: is the sort of thing a list gets wrong and a range declaration does not.
FAMILY = {
    "R19": ("Document", "has-document-type", "DocumentType", "Party"),
    "R20": ("RangeSelector", "has-start-selector", "FragmentSelector", "Party"),
    "R21": ("RangeSelector", "has-end-selector", "FragmentSelector", "Party"),
    "R23": ("ExternalClassification", "has-classification-domain",
            "ClassificationDomain", "Party"),
}

#: The rule that counts the property, for each rule that asks about its target.
COUNTS_IT = {"R19": "M15.1", "R20": "M14.1", "R21": "M14.2", "R23": "M96.1"}

#: The sentence each pair answers between them.
SENTENCE = {
    "R19": "x6-5-1-types-of-documents-and-topics#1",
    "R20": "rdfrelations_core_has-start-selector#1",
    "R21": "rdfrelations_core_has-end-selector#1",
    "R23": "x6-8-4-external-classification#7",
}

IDS = sorted(FAMILY)


def package_with(tmp_path, name, body, version="1.3"):
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", body + "</rdf:RDF>")
    if version != "1.3":
        metadata = metadata.replace("1.3", version)
    return build_package(tmp_path, name, metadata=metadata)


def fired(tmp_path, name, body, kinds=None):
    report = runner.run(package_with(tmp_path, name, body),
                        kinds if kinds is not None else runner.ALL_KINDS)
    return {f.rule.id for f in report.findings}


def subject_with(cls, prop, value_xml):
    return ('  <iirds:%s rdf:about="urn:test:s1">\n    <iirds:%s%s\n'
            "  </iirds:%s>\n" % (cls, prop, value_xml, cls))


@pytest.mark.parametrize("rule_id", IDS)
def test_a_literal_where_the_class_belongs_is_reported(tmp_path, rule_id):
    cls, prop, _target, _other = FAMILY[rule_id]
    body = subject_with(cls, prop, ">text</iirds:%s>" % prop)
    assert rule_id in fired(tmp_path, "lit_%s.iirds" % rule_id, body)


@pytest.mark.parametrize("rule_id", IDS)
def test_an_instance_of_another_class_is_reported(tmp_path, rule_id):
    """A literal is one way to break the sentence; pointing at a described
    resource of the wrong class is the other, and it is the one a package
    written by a tool makes."""
    cls, prop, _target, other = FAMILY[rule_id]
    body = (subject_with(cls, prop, ' rdf:resource="urn:test:elsewhere"/>')
            + '  <iirds:%s rdf:about="urn:test:elsewhere"/>\n' % other)
    assert rule_id in fired(tmp_path, "wrong_%s.iirds" % rule_id, body)


@pytest.mark.parametrize("rule_id", IDS)
def test_an_instance_of_the_right_class_is_not(tmp_path, rule_id):
    cls, prop, target, _other = FAMILY[rule_id]
    body = (subject_with(cls, prop, ' rdf:resource="urn:test:target"/>')
            + '  <iirds:%s rdf:about="urn:test:target"/>\n' % target)
    assert rule_id not in fired(tmp_path, "ok_%s.iirds" % rule_id, body)


@pytest.mark.parametrize("rule_id", IDS)
def test_an_undescribed_target_is_left_to_l1(tmp_path, rule_id):
    """The exemption every rule in this family carries. An IRI the package
    never describes is a dangling reference, which L1 reports as one; calling
    it a typing error would report the same fact twice under two names and
    send the reader to the wrong repair.
    """
    cls, prop, _target, _other = FAMILY[rule_id]
    body = subject_with(cls, prop, ' rdf:resource="urn:test:nowhere"/>')
    assert rule_id not in fired(tmp_path, "dangling_%s.iirds" % rule_id, body)


@pytest.mark.parametrize("rule_id", IDS)
def test_the_counting_rule_is_the_one_that_reports_an_absent_property(tmp_path, rule_id):
    """The division of labour, asserted in both directions: the partner
    reports the package with none of the property and this rule does not,
    which is why neither claim stands without the other."""
    cls, _prop, _target, _other = FAMILY[rule_id]
    body = '  <iirds:%s rdf:about="urn:test:s1"/>\n' % cls
    ids = fired(tmp_path, "absent_%s.iirds" % rule_id, body)
    assert COUNTS_IT[rule_id] in ids, sorted(ids)
    assert rule_id not in ids, sorted(ids)


def test_naming_a_document_type_as_text_no_longer_passes(tmp_path):
    """The one verdict flip, and the reason this family was worth finding.

    A `iirds:Document` with no document type fails. The same document with
    `<iirds:has-document-type>OperatingInstructions</iirds:has-document-type>`
    passed every conformance rule -- so text was better than nothing, and a
    package could satisfy `iirds check` by writing the one thing the sentence
    forbids.
    """
    absent = runner.check(package_with(
        tmp_path, "dt_absent.iirds", '  <iirds:Document rdf:about="urn:test:d1"/>\n'))
    text = runner.check(package_with(
        tmp_path, "dt_text.iirds",
        '  <iirds:Document rdf:about="urn:test:d1">\n'
        "    <iirds:has-document-type>OperatingInstructions</iirds:has-document-type>\n"
        "  </iirds:Document>\n"))
    assert not absent.ok
    assert not text.ok, [f.violation.message for f in text.findings]


def test_the_other_document_type_property_is_watched_too(tmp_path):
    """M15.1 accepts either `iirds:has-document-type` or
    `iirds:is-applicable-for-document-type`, so a rule that read only the first
    would let the second carry anything -- and the second is the one an
    information unit that is not a Document uses."""
    body = ('  <iirds:Document rdf:about="urn:test:d1">\n'
            "    <iirds:is-applicable-for-document-type>OperatingInstructions"
            "</iirds:is-applicable-for-document-type>\n"
            "  </iirds:Document>\n")
    assert "R19" in fired(tmp_path, "dt_applicable.iirds", body)


@pytest.mark.parametrize("rule_id", IDS)
def test_these_rules_claim_nothing(rule_id):
    """Every sentence this family was drafted claiming turned out unearned,
    each for its own reason, and the reasons are in `rules/schema.py` beside
    the rules. The short of it: a rule that asks what a property points at
    does not answer a sentence about how many of the property there are, and
    the one sentence that is about the target -- section 6.5.1's -- asks for a
    *standardized* document type, which nothing checks.

    Pinned so that claiming one later is a deliberate edit with a package
    behind it, rather than a tuple quietly regrown.
    """
    rule = next(r for r in all_rules() if r.id == rule_id)
    assert rule.covers == (), rule.covers


def test_the_appendix_row_that_restates_it_is_not_claimed():
    """`rdfclasses_core_ExternalClassification#1` is the one obligation among
    the appendix's eighteen "Definition:" rows that a package can break --
    "Each classification MUST be related to the classification domain within
    which it is unambiguous" -- and it stays unclaimed.

    Both halves would have to claim it, and M96.1's title is the catalogue's
    wording: "An external classification", in prose. The name heuristic in
    `test_requirement_coverage` asks that a rule claiming a row about a
    qualified name mention that name, and it cannot read prose. Rewriting
    somebody else's sentence to satisfy a heuristic is what that gate's own
    docstring warns against -- "applying the heuristic there would only teach
    people to rename rules to satisfy it" -- so the coverage figure carries one
    fewer than the reading supports, in the direction that understates it.
    """
    claiming = {rule.id for rule in all_rules()
                if "rdfclasses_core_ExternalClassification#1" in (rule.covers or ())}
    assert claiming == set(), sorted(claiming)


@pytest.mark.parametrize("rule_id", IDS)
def test_the_new_rule_runs_where_its_partner_does(rule_id):
    """A rule that asks about the target of a property is meaningless in an
    edition without the property, and wrong to skip in one that has it. Taken
    from the partner rather than written out: M96.1 is 1.2 and later, the rest
    are all five."""
    by_id = {rule.id: rule for rule in all_rules()}
    assert by_id[rule_id].versions == by_id[COUNTS_IT[rule_id]].versions, (
        by_id[rule_id].versions, by_id[COUNTS_IT[rule_id]].versions)
    assert by_id[rule_id].kind == "schema"
    assert by_id[rule_id].prio == "MUST"


def test_the_identity_domain_already_had_its_second_rule(tmp_path):
    """There is no R22, and there should not be.

    The measurement that found this family used a literal as its probe: build
    a package with the property carrying text and see which MUST-level rule
    goes quiet. M19.4 -- "the object of iirds:has-identity-domain must be an
    instance of iirds:IdentityDomain" -- went quiet, because it exempted any
    node with no triples in the package and a literal has none. So a rule that
    had been doing this job all along looked like a rule that was missing, and
    a sixth member of the family was written beside it. Both fired on the same
    triple, which is the thing this family's own helper warns about: "report
    the same fact twice under two names and send the reader to the wrong
    repair".

    What the probe found was not a missing rule but two missing branches, and
    those belong to M19.4.
    """
    assert not [r for r in all_rules() if r.id == "R22"], "R22 is back"

    body = ('  <iirds:Identity rdf:about="urn:test:i1">\n'
            '    <iirds:has-identity-domain rdf:resource="urn:test:p1"/>\n'
            "  </iirds:Identity>\n"
            '  <iirds:Party rdf:about="urn:test:p1"/>\n')
    ids = [f.rule.id for f in runner.run(package_with(tmp_path, "one.iirds", body),
                                         runner.CONFORMANCE_KINDS).findings]
    assert ids.count("M19.4") == 1, ids
    assert len([i for i in ids if i in ("M19.4", "R22")]) == 1, ids


def test_the_two_branches_the_identity_rule_was_missing(tmp_path):
    """A literal, and a term the ontology defines that is not a domain. M19.4
    exempted both by asking whether the package describes the node: a literal
    carries no triples, and neither does a term whose definition lives in the
    ontology rather than here."""
    for name, value in (("lit", ">SN-1</iirds:has-identity-domain>"),
                        ("term", ' rdf:resource="http://iirds.tekom.de/iirds#Author"/>')):
        body = ('  <iirds:Identity rdf:about="urn:test:i1">\n'
                "    <iirds:has-identity-domain%s\n  </iirds:Identity>\n" % value)
        ids = fired(tmp_path, "m194_%s.iirds" % name, body, runner.CONFORMANCE_KINDS)
        assert "M19.4" in ids, (name, sorted(ids))


@pytest.mark.parametrize("rule_id", IDS)
def test_a_name_in_an_iirds_namespace_that_the_standard_does_not_define(tmp_path, rule_id):
    """`iirds:ThisIsNotAStandardizedDocumentType` is not a dangling reference.

    The exemption sends an IRI the package never describes to L1, on the
    reading that it is a pointer at nothing. That is right for `urn:x:whatever`
    and wrong for a name in the standard's own namespace: nobody mints those
    by accident, so it is an author reaching for a term of the standard and
    missing. `Context.names_a_defined_term` says so in those words, and R12
    already reads it that way.

    Not academic. The reference corpus's own designated counterexample for the
    document-type sentence, `metadata_iirds_sample-M15_false.rdf`, points
    `iirds:has-document-type` at exactly that name -- and the rule written to
    catch a document type that is not a standardised type was silent on it.
    """
    cls, prop, _target, _other = FAMILY[rule_id]
    body = subject_with(cls, prop,
                        ' rdf:resource="http://iirds.tekom.de/iirds#NoSuchThing"/>')
    assert rule_id in fired(tmp_path, "minted_%s.iirds" % rule_id, body)


@pytest.mark.parametrize("rule_id", IDS)
def test_an_empty_blank_node_is_reported_by_this_family(tmp_path, rule_id):
    """The exemption's stated destination does not accept this case.

    `rdf:parseType="Resource"` with nothing inside makes a blank node with no
    statements, so the family reads it as undescribed and leaves it to L1 --
    and L1 only looks at IRIs (`isinstance(obj, URIRef)`), so it never arrives.
    Reported by nothing at all, at any kind, which is worse than either rule
    reporting it twice.
    """
    cls, prop, _target, _other = FAMILY[rule_id]
    body = ('  <iirds:%s rdf:about="urn:test:s1">\n'
            '    <iirds:%s rdf:parseType="Resource"></iirds:%s>\n'
            "  </iirds:%s>\n" % (cls, prop, prop, cls))
    assert rule_id in fired(tmp_path, "bnode_%s.iirds" % rule_id, body)


#: The two cardinality sentences these rules were briefly and wrongly said to
#: answer, with the package that actually breaks each.
CARDINALITY = {
    "x6-8-1-complex-identity#3": (
        "M19.3", "Identity", "has-identity-domain", "IdentityDomain"),
    "x6-8-4-external-classification#7": (
        "M96.1", "ExternalClassification", "has-classification-domain",
        "ClassificationDomain"),
}


@pytest.mark.parametrize("requirement", sorted(CARDINALITY), ids=sorted(CARDINALITY))
def test_two_domains_is_what_breaks_the_cardinality_sentence(tmp_path, requirement):
    """"MUST point to exactly one domain by the property" is about how many,
    not about what.

    These two were briefly held by a package pointing at one domain of the
    wrong class -- which has exactly one and does not break the sentence. What
    it breaks is the sentence *after* it, "The domain is an instance of the
    iirdsIdentityDomain class", which carries no RFC 2119 keyword and is
    therefore not one of the obligations this project counts. Two domains is
    the counterexample, and the rule that counts them is the one that reports
    it.
    """
    rule_id, cls, prop, target = CARDINALITY[requirement]
    body = ('  <iirds:%s rdf:about="urn:test:s1">\n'
            '    <iirds:%s rdf:resource="urn:test:d1"/>\n'
            '    <iirds:%s rdf:resource="urn:test:d2"/>\n'
            "  </iirds:%s>\n"
            '  <iirds:%s rdf:about="urn:test:d1"/>\n'
            '  <iirds:%s rdf:about="urn:test:d2"/>\n'
            % (cls, prop, prop, cls, target, target))
    ids = fired(tmp_path, "two_%s.iirds" % rule_id, body, runner.CONFORMANCE_KINDS)
    assert rule_id in ids, sorted(ids)

    # and one domain of the right class does not, which is what makes the
    # package above a counterexample rather than a package that fails anyway.
    one = ('  <iirds:%s rdf:about="urn:test:s1">\n'
           '    <iirds:%s rdf:resource="urn:test:d1"/>\n  </iirds:%s>\n'
           '  <iirds:%s rdf:about="urn:test:d1"/>\n' % (cls, prop, cls, target))
    assert rule_id not in fired(tmp_path, "one_%s.iirds" % rule_id, one,
                                runner.CONFORMANCE_KINDS)


def test_the_finding_names_the_property_the_package_actually_used(tmp_path):
    """R19 reads two properties and its message must say which one.

    A body that formatted the message from the first path name passed every
    test in this file and every parity case: a package carrying only
    `iirds:is-applicable-for-document-type` was told to repair
    `iirds:has-document-type`, a property it does not have. Rule-id parity
    cannot see message text, so this reads it.
    """
    body = ('  <iirds:Topic rdf:about="urn:test:t9">\n'
            "    <iirds:is-applicable-for-document-type>text"
            "</iirds:is-applicable-for-document-type>\n  </iirds:Topic>\n")
    hits = [f for f in runner.run(package_with(tmp_path, "second.iirds", body),
                                  runner.CONFORMANCE_KINDS).findings if f.rule.id == "R19"]
    assert len(hits) == 1, hits
    assert "is-applicable-for-document-type" in hits[0].violation.message, \
        hits[0].violation.message
    assert "has-document-type must" not in hits[0].violation.message, \
        hits[0].violation.message


def test_no_title_claims_a_subject_class_the_rule_does_not_check():
    """These rules read a property wherever it occurs, so a title saying "on an
    iirds:Document" was a promise the body does not keep -- a `iirds:Topic`
    carrying the property was told it was a Document. The factory takes no
    subject class any more; this is the gate that keeps one from coming back
    into the prose."""
    from iirds_validate.rules.schema import TARGET_RULE_PATHS

    by_id = {r.id: r for r in all_rules()}
    for rule_id, paths in TARGET_RULE_PATHS.items():
        title = by_id[rule_id].title
        assert " on an " not in title, (rule_id, title)
        for path in paths:
            assert path in title, (rule_id, path, title)
