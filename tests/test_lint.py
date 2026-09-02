"""Interoperability rules — valid packages that a consumer still cannot use."""
from __future__ import annotations

from rdflib import URIRef

from conftest import MINIMAL_RDF
from iirds_validate import runner

DANGLING = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    '    <iirds:relates-to-event rdf:resource="urn:test:event-that-does-not-exist"/>\n'
    "  </iirds:Topic>")


def ids(report):
    return {f.rule.id for f in report.findings}


def test_dangling_reference_is_caught_but_is_not_a_conformance_error(make_package):
    """The exact failure that motivated this project.

    Both forms are valid iiRDS, so `check` stays silent — as it should. `lint`
    is where you find out the reference goes nowhere.
    """
    package = make_package(metadata=DANGLING)

    conformance = runner.check(package)
    assert conformance.ok, "a reference to an undescribed IRI breaks no MUST"

    interop = runner.lint(package)
    assert "L1" in ids(interop)
    assert interop.ok, "L1 is a warning: the package is valid, just not usable"


def test_missing_content_file(make_package):
    report = runner.lint(make_package(content=()))
    assert "L2" in ids(report)
    assert not report.ok, "a rendition pointing at a file nobody packed is an error"


def test_clean_package_has_no_lint_findings(make_package):
    report = runner.lint(make_package())
    assert not report.findings, [f.violation.message for f in report.findings]


# ---------------------------------------------------------------------------
# A name in the iiRDS namespace that the vocabulary does not define
#
# The checker trusted the namespace and never the name: `is_iirds_term` is a
# prefix test, and `is_defined` -- which asks the bundled vocabulary -- was
# applied to iiRDS IRIs nowhere. So a typed name in the standard's own
# namespace passed every one of 173 rules, in any of the three positions a
# term can occupy, and a consumer resolving it finds no class, no property
# and no label.
# ---------------------------------------------------------------------------

#: `relates-to-component` with two letters swapped: a predicate that resolves
#: to nothing, on a package that is otherwise clean.
TYPO_PREDICATE = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    '    <iirds:relates-to-componnet rdf:resource="urn:test:component/spindle"/>\n'
    "  </iirds:Topic>")

#: A class of the standard's, misspelled, beside a real one -- so that the
#: rules which ask "does this package declare any Component at all" stay
#: silent and the typo is the only thing left to find.
TYPO_CLASS = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    "  </iirds:Topic>\n"
    '  <iirds:Component rdf:about="urn:test:component/spindle">\n'
    "    <iirds:title>Main spindle</iirds:title>\n"
    "  </iirds:Component>\n"
    '  <iirds:Componentt rdf:about="urn:test:component/guard">\n'
    "    <iirds:title>Guard</iirds:title>\n"
    "  </iirds:Componentt>")

#: The value half: a document type the standard does not have, written in the
#: standard's namespace. Singular where the vocabulary is plural.
TYPO_VALUE = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    '    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstruction"/>\n'
    "  </iirds:Topic>")

#: The one that is not a typo: the standard defines this in the machinery
#: domain, and this names it in core. Fifty-one files of the reference corpus
#: do the same, which is why this rule is a warning rather than an error.
WRONG_NAMESPACE = MINIMAL_RDF.replace(
    "  </iirds:Topic>",
    '    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#EnvironmentalProtectionInstruction"/>\n'
    "  </iirds:Topic>")


def findings_for(report, rule_id):
    return [f for f in report.findings if f.rule.id == rule_id]


def test_a_misspelled_predicate_in_the_iirds_namespace_is_reported(make_package):
    report = runner.lint(make_package(metadata=TYPO_PREDICATE))
    assert "L13" in ids(report)


def test_a_misspelled_class_in_the_iirds_namespace_is_reported(make_package):
    """Beside a correctly spelled sibling, so that this is the typo being
    found and not the absence of the class it belongs to."""
    report = runner.lint(make_package(metadata=TYPO_CLASS))
    assert "L13" in ids(report)


def test_a_value_the_vocabulary_does_not_define_is_reported(make_package):
    report = runner.lint(make_package(metadata=TYPO_VALUE))
    assert "L13" in ids(report)


def test_a_term_of_another_iirds_domain_named_in_core_is_reported(make_package):
    report = runner.lint(make_package(metadata=WRONG_NAMESPACE))
    assert "L13" in ids(report)


def test_the_undefined_term_finding_is_a_warning_and_not_a_conformance_error(make_package):
    """Fifty-one files of the reference corpus, seven of them fixtures the
    catalogue marks as passing, name one term this way. Whether section 7 forbids
    it is a question for the standard's editors; until it is answered this
    reports without failing a build."""
    package = make_package(metadata=TYPO_PREDICATE)
    assert runner.check(package).ok, "no MUST is broken by a name that resolves to nothing"
    assert runner.lint(package).ok, "L13 is advice until the standard's editors answer"


def test_a_clean_package_names_no_undefined_term(make_package):
    assert "L13" not in ids(runner.lint(make_package()))


def test_each_undefined_term_is_reported_once_however_often_it_occurs(make_package):
    twice = TYPO_PREDICATE.replace(
        "  </iirds:Topic>",
        '    <iirds:relates-to-componnet rdf:resource="urn:test:component/other"/>\n'
        "  </iirds:Topic>")
    assert len(findings_for(runner.lint(make_package(metadata=twice)), "L13")) == 1


def test_the_report_suggests_the_term_that_was_meant(make_package):
    """327 terms is a small enough vocabulary to search, and the suggestion is
    most of this rule's value: `relates-to-componnet` is unreadable as an
    error and obvious as a correction."""
    found = findings_for(runner.lint(make_package(metadata=TYPO_PREDICATE)), "L13")
    assert "relates-to-component" in (found[0].violation.detail or "")


def test_no_suggestion_is_offered_where_nothing_is_near(make_package):
    """A name with no neighbour gets none: a wrong suggestion costs more than
    no suggestion, because a reader acts on it."""
    far = MINIMAL_RDF.replace(
        "  </iirds:Topic>",
        '    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#Zzzzqqqxyw"/>\n'
        "  </iirds:Topic>")
    found = findings_for(runner.lint(make_package(metadata=far)), "L13")
    assert found and "did you mean" not in (found[0].violation.detail or "").lower()


# ---------------------------------------------------------------------------
# The suggestion has to be the term that was meant, or nothing
#
# A first version compared raw local names case-sensitively and took the best
# difflib match: `installation` was answered with `Deinstallation` -- the
# opposite -- because a substring beats a case difference, and a predicate
# written in camelCase was answered with a class. A wrong suggestion costs
# more than none, because a reader acts on it, so the strategy is measured:
# every defined term is mutated the ways authors actually mutate names, and
# the number answered with a term other than the original must be zero.
# ---------------------------------------------------------------------------

def _value_package(iri):
    return MINIMAL_RDF.replace(
        "  </iirds:Topic>",
        '    <iirds:has-document-type rdf:resource="%s"/>\n  </iirds:Topic>' % iri)


def _l13_detail(report, subject_suffix):
    for f in findings_for(report, "L13"):
        if f.violation.subject.endswith(subject_suffix):
            return f.violation.detail or ""
    raise AssertionError("L13 did not report %s" % subject_suffix)


def test_a_case_slip_is_answered_with_the_same_word_and_not_its_opposite(make_package):
    """`installation` is `Installation` with one letter down, not
    `Deinstallation` with two letters added -- however a substring measure
    scores it."""
    detail = _l13_detail(runner.lint(make_package(metadata=_value_package(
        "http://iirds.tekom.de/iirds#installation"))), "#installation")
    assert "Installation" in detail and "Deinstallation" not in detail


def test_the_standards_own_example_53_gets_its_correction(make_package):
    """The 1.3 specification's Example 53 writes `iirds:vdi2770`; the
    vocabulary defines `VDI2770`. The rule is right to report it, and the
    obvious correction has to be offered."""
    detail = _l13_detail(runner.lint(make_package(metadata=_value_package(
        "http://iirds.tekom.de/iirds#vdi2770"))), "#vdi2770")
    assert "VDI2770" in detail


def test_a_predicate_is_answered_with_a_property_and_never_with_a_class(make_package):
    """`hasDocumentType` is `has-document-type` written the other common way.
    The nearest name by letters is the class `DocumentType`, which a reader
    cannot put in a predicate position; the position is known and decides."""
    typo = MINIMAL_RDF.replace(
        "  </iirds:Topic>",
        '    <iirds:hasDocumentType rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n'
        "  </iirds:Topic>")
    detail = _l13_detail(runner.lint(make_package(metadata=typo)), "#hasDocumentType")
    assert "has-document-type" in detail and "#DocumentType" not in detail


def test_a_short_name_with_two_letters_swapped_still_gets_its_correction(make_package):
    """`titel` for `title`: two letters swapped is one slip of the fingers,
    and a similarity ratio built for long names calls a five-letter word
    with one slip a stranger."""
    typo = MINIMAL_RDF.replace("<iirds:title>A topic</iirds:title>", "<iirds:titel>A topic</iirds:titel>")
    detail = _l13_detail(runner.lint(make_package(metadata=typo)), "#titel")
    assert "title" in detail


def test_a_same_named_term_in_the_same_namespace_wins_over_a_sibling_vocabulary(make_package):
    """`Operation` exists in core and in handover. A handover package that
    misspells it wants the handover one back, not core's."""
    typo = MINIMAL_RDF.replace(
        "  </iirds:Topic>",
        '    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds/domain/handover#Operatoin"/>\n'
        "  </iirds:Topic>")
    detail = _l13_detail(runner.lint(make_package(metadata=typo)), "#Operatoin")
    assert detail == "did you mean Operation?", detail      # same namespace: the name alone
    from iirds_validate import ontology
    from iirds_validate.rules import lint as L
    handover = "http://iirds.tekom.de/iirds/domain/handover#"
    assert L._suggest(URIRef(handover + "Operatoin"), "value", ontology.load("1.3")) == URIRef(handover + "Operation")


def test_the_vocabulary_iri_itself_is_not_an_undefined_name(make_package):
    """`http://iirds.tekom.de/iirds#` as a value -- say, what a package
    declares it conforms to -- names the vocabulary, not a term in it."""
    report = runner.lint(make_package(metadata=_value_package("http://iirds.tekom.de/iirds#")))
    assert not [f for f in findings_for(report, "L13") if f.violation.subject.endswith("iirds#")]


def test_trailing_whitespace_is_named_because_the_two_spellings_look_identical(make_package):
    detail = _l13_detail(runner.lint(make_package(metadata=_value_package(
        "http://iirds.tekom.de/iirds#OperatingInstructions "))), "OperatingInstructions ")
    assert "whitespace" in detail.lower()


def test_a_name_this_package_describes_is_said_to_be_described_here(make_package):
    """Fifty-one corpus files type and label `iirds:EnvironmentalProtectionInstruction`
    themselves. A consumer reading the package finds that; one that trusts
    the namespace looks the name up in the vocabulary and finds nothing. The
    finding says which, rather than claiming no label exists."""
    described = MINIMAL_RDF.replace(
        "  </iirds:Topic>",
        '    <iirds:has-subject rdf:resource="http://iirds.tekom.de/iirds#EnvironmentalProtectionInstruction"/>\n'
        "  </iirds:Topic>\n"
        '  <iirds:InformationSubject rdf:about="http://iirds.tekom.de/iirds#EnvironmentalProtectionInstruction">\n'
        "    <rdfs:label>Environmental protection instruction</rdfs:label>\n"
        "  </iirds:InformationSubject>")
    detail = _l13_detail(runner.lint(make_package(metadata=described)), "#EnvironmentalProtectionInstruction")
    assert "described in this package" in detail


def test_the_remedy_fits_the_position_the_name_was_used_in(make_package):
    """A property wants rdfs:subPropertyOf, a class rdfs:subClassOf, an
    instance an rdf:type -- one sentence for all three sends two of them the
    wrong way."""
    value = findings_for(runner.lint(make_package(metadata=_value_package(
        "http://iirds.tekom.de/iirds#Zzzzqqqxyw"))), "L13")[0]
    assert "rdf:type" in (value.violation.fix or "")
    predicate = findings_for(runner.lint(make_package(metadata=TYPO_PREDICATE)), "L13")[0]
    assert "rdfs:subPropertyOf" in (predicate.violation.fix or "")


def test_no_mutation_of_any_defined_term_is_answered_with_a_different_term():
    """The measurement behind the strategy, kept as the gate that holds it.

    Every term the vocabulary defines, mutated the ways names actually get
    mutated -- first letter's case, all lower case, a letter dropped, two
    letters swapped, hyphens written as camelCase, trailing whitespace -- and
    asked what was meant. Answered with another term: never. Answered with
    nothing: a handful of three-letter names whose one-edit neighbours are
    several, where guessing would be the wrong kind of help.
    """
    from rdflib import OWL, RDF, RDFS

    from iirds_validate import ontology
    from iirds_validate.rules import lint as L

    o = ontology.load("1.3")
    classes = set(o.graph.subjects(RDF.type, RDFS.Class)) | set(o.graph.subjects(RDF.type, OWL.Class))
    props = (set(o.graph.subjects(RDF.type, RDF.Property)) | set(o.graph.subjects(RDF.type, OWL.ObjectProperty))
             | set(o.graph.subjects(RDF.type, OWL.DatatypeProperty)))

    def mutations(name):
        out = {"case": name[0].swapcase() + name[1:], "lower": name.lower(), "space": name + " "}
        if len(name) > 3:
            half = len(name) // 2
            out["drop"] = name[:half] + name[half + 1:]
            out["swap"] = name[:half] + name[half + 1] + name[half] + name[half + 2:]
        if "-" in name:
            parts = name.split("-")
            out["camel"] = parts[0] + "".join(p.capitalize() for p in parts[1:])
        return out

    correct = none = 0
    wrong = []
    for term in sorted(o.defined_terms(), key=str):
        namespace, _, name = str(term).rpartition("#")
        position = "class" if term in classes else "predicate" if term in props else "value"
        for how, mutated in mutations(name).items():
            got = L._suggest(URIRef(namespace + "#" + mutated), position, o)
            if got == term:
                correct += 1
            elif got is None:
                none += 1
            else:
                wrong.append((how, name, mutated, str(got)))
    assert wrong == [], wrong[:10]
    assert none <= 12, none
    assert correct >= 1660, correct
