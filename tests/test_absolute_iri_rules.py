"""Three classes the standard asks for an absolute IRI, not a recommended one.

Section 6.2.1 says "It is RECOMMENDED to use absolute IRIs in rdf:about", and
that recommendation is M5. Three sentences elsewhere say MUST about a named
class:

    6.2.2   An information object MUST have an absolute IRI ...
    6.8.1   Instances of class iirds:IdentityDomain MUST have an absolute IRI ...
    6.8.4   Instances of class iirds:ClassificationDomain MUST have an absolute
            IRI ...

The first two are in the 1.0 text as well as the 1.3 text; the third appears
with the class. `docs/divergences.md` records the day the "must have an IRI"
family stopped demanding absoluteness -- appendix A says `IRI: REQUIRED` and a
relative IRI is an IRI -- and the reason it gives is "absoluteness is M5's
question, and M5 is RECOMMENDED". That was right about sixty classes and wrong
about these three, so a package breaching one of the MUSTs above came back with
a warning whose remedy ends "RECOMMENDED, not required."

The narrowing stays. What is added is the three sentences it was measured
against.
"""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import runner
from iirds_validate.model import Severity

HEAD = MINIMAL_RDF.replace("</rdf:RDF>", "")

#: The class, the rule that must report a relative IRI on it, and the sentence.
MUST_BE_ABSOLUTE = [
    ("iirds:InformationObject", "R34", "x6-2-2-information-objects#3"),
    ("iirds:IdentityDomain", "R35", "x6-8-1-complex-identity#4"),
    ("iirds:ClassificationDomain", "R36", "x6-8-4-external-classification#8"),
]


def pkg(make_package, body, **kw):
    return make_package(metadata=HEAD + body + "</rdf:RDF>\n", **kw)


def instance(class_name, about):
    return '  <%s rdf:about="%s"/>\n' % (class_name, about)


@pytest.mark.parametrize("class_name,rule_id,_requirement", MUST_BE_ABSOLUTE)
def test_a_relative_iri_on_one_of_these_classes_is_an_error(
        make_package, class_name, rule_id, _requirement):
    """The whole point: this fails the build, where M5 alone did not."""
    report = runner.check(pkg(make_package, instance(class_name, "domain1")))
    reported = [f for f in report.findings if f.rule.id == rule_id]
    assert reported, "%s did not report a relative IRI on %s: %s" % (
        rule_id, class_name, sorted(f.rule.id for f in report.findings))
    assert all(f.severity is Severity.ERROR for f in reported)
    assert not report.ok, "a MUST was breached and the package passed"


@pytest.mark.parametrize("class_name,rule_id,_requirement", MUST_BE_ABSOLUTE)
def test_an_absolute_iri_on_the_same_class_is_not_reported(
        make_package, class_name, rule_id, _requirement):
    """The control. Without it the test above passes on a rule that fires on
    every instance of the class, which is a different rule."""
    report = runner.check(pkg(make_package, instance(class_name, "urn:test:d1")))
    assert rule_id not in {f.rule.id for f in report.findings}


@pytest.mark.parametrize("class_name,rule_id,_requirement", MUST_BE_ABSOLUTE)
def test_an_empty_rdf_about_is_reported_too(
        make_package, class_name, rule_id, _requirement):
    """`rdf:about=""` resolves to the document base and comes back looking like
    an IRI. It identifies the document rather than the instance, which is the
    case M5 already carries a second clause for."""
    report = runner.check(pkg(make_package, instance(class_name, "")))
    assert rule_id in {f.rule.id for f in report.findings}


def test_the_recommendation_is_not_promoted_everywhere(make_package):
    """Section 6.2.1 is still RECOMMENDED for every other class, and the
    reference tool's corpus is graded on that. Promoting absoluteness wholesale
    is the conflation `docs/divergences.md` records being removed."""
    report = runner.check(pkg(make_package, instance("iirds:Component", "component/spindle")))
    assert "M5" in {f.rule.id for f in report.findings}
    assert all(f.severity is Severity.WARNING
               for f in report.findings if f.rule.id == "M5")
    assert report.ok, "a relative IRI outside the three classes must not fail a build"


def test_the_three_rules_claim_the_three_sentences():
    """A claim rather than a resemblance: the rule that reports the breach is
    the rule that says it covers the sentence."""
    from iirds_validate.registry import all_rules
    by_id = {rule.id: rule for rule in all_rules()}
    for _class_name, rule_id, requirement in MUST_BE_ABSOLUTE:
        rule = by_id.get(rule_id)
        assert rule is not None, "%s is not registered" % rule_id
        assert requirement in (rule.covers or ()), \
            "%s does not claim %s" % (rule_id, requirement)


def test_the_generated_family_does_not_say_absolute_when_it_means_named():
    """The message sixty-one rules print.

    `docs/divergences.md` records that this family stopped asking for an
    absolute IRI and asks for an identifier that is not a blank node. The check
    was narrowed and the sentence it prints was not, so every one of them told
    a reader that absoluteness had been tested. A user acts on the finding, not
    on the divergence table.
    """
    from pathlib import Path

    from iirds_validate.rules import schema_tables
    text = Path(schema_tables.__file__).read_text("utf-8")
    assert "must have an absolute IRI" not in text, \
        "the generated family still claims to have tested absoluteness"
