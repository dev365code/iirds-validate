"""The "MUST NOT have more than one" rules, each shown to work, and the
appendix rows they answer.

Every one of them was registered, catalogued and never observed to produce a
finding. A cardinality rule that never fires is indistinguishable from a
cardinality rule that cannot fire, and the difference only shows up in a
customer's package.

The pairs below were read out of the rule implementations rather than out of
their prose, because the two have disagreed before: a property guessed from a
sentence as `eventCode` is spelled `has-event-code` in the ontology, and a rule
built on the guess matched nothing while looking correct.

**And the specification states the same thing thirty times, in a form nothing
here was reading.** Appendix A's class tables give a cardinality for every
property of every class, and thirty of those rows read `0..1 iirds:<property>
(at most one)`. Twenty-nine were in the coverage report's unmapped remainder
while the rule answering them sat in `schema.py` claiming nothing — the work
was done and the claim was never made. So the rows are derived from the
obligation index here rather than listed, and each is required to name a rule
that both fires on a second value and stays quiet on the first.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from rdflib import RDFS
from rdflib.namespace import RDF

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate import terms as T
from iirds_validate.model import HOV, IIRDS
from iirds_validate.ontology import load
from iirds_validate.registry import all_rules

ROOT = Path(__file__).resolve().parents[1]

#: The prefixes appendix A writes its property names with.
PREFIXES = {"iirds": IIRDS, "iirdsHov": HOV}

#: (rule, class, property). Extracted from the functions themselves.
PAIRS = [
    ("M2.3",  T.InformationUnit,          T.dateOfCreation),
    ("M2.4",  T.InformationUnit,          T.dateOfLastModification),
    ("M2.5",  T.InformationUnit,          T.revision),
    ("M2.7",  T.InformationUnit,          T.has_abstract),
    ("M2.8",  T.InformationUnit,          T.is_replacement_of),
    ("M2.9",  T.InformationUnit,          T.is_version_of),
    ("M21.2", T.ContentLifeCycleStatus,   T.dateOfEffect),
    ("M21.3", T.ContentLifeCycleStatus,   T.dateOfExpiry),
    ("M21.5", T.ContentLifeCycleStatus,   T.purpose),
    ("M21.6", T.ContentLifeCycleStatus,   T.relates_to_party),
    ("M24.1", T.DirectoryNode,            T.has_next_sibling),
    ("M24.2", T.DirectoryNode,            T.has_directory_structure_type),
    ("M24.3", T.DirectoryNode,            T.has_first_child),
    ("M24.4", T.DirectoryNode,            T.relates_to_information_unit),
    ("M95",   T.Component,                T.relates_to_party),
    ("M96.1", T.ExternalClassification,   T.has_classification_domain),
    ("M96.2", T.ExternalClassification,   T.classificationIdentifier),
]

IDS = [p[0] for p in PAIRS]


def _takes_a_literal(prop) -> bool:
    """Asked of the ontology, not assumed. Writing an IRI where a literal
    belongs produces a graph that is wrong in a different way from the one
    under test, and the rule would fire for the wrong reason."""
    return RDFS.Literal in set(load().graph.objects(prop, RDFS.range))


def _qname(prop) -> str:
    """The property written the way the fixture must spell it.

    This read `"iirds:" + local name` for as long as every property it was
    given was a core one. Appendix A gives `iirdsHov:has-document-category` on
    `iirds:Document`, and spelling that one `iirds:` mints a term of the core
    namespace that the standard does not define -- a different defect, in a
    fixture built to exhibit this one.
    """
    text = str(prop)
    for prefix, namespace in PREFIXES.items():
        if text.startswith(str(namespace)):
            return "%s:%s" % (prefix, text[len(str(namespace)):])
    raise AssertionError("no prefix for %s" % prop)


def _statement(prop, value: str) -> str:
    name = _qname(prop)
    if _takes_a_literal(prop):
        return "    <%s>%s</%s>\n" % (name, value, name)
    return '    <%s rdf:resource="urn:test:%s"/>\n' % (name, value)


def _package(tmp_path, rule_id, cls, prop, count):
    # Two *different* values. RDF is a set, so repeating one statement is one
    # statement, and a fixture built that way tests nothing.
    body = "".join(_statement(prop, "v%d" % n) for n in range(count))
    element = "  <rdf:Description rdf:about='urn:test:subject'>\n" \
              "    <rdf:type rdf:resource='%s'/>\n%s  </rdf:Description>\n" % (cls, body)
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", element + "</rdf:RDF>")
    prefix = _qname(prop).partition(":")[0]
    if 'xmlns:%s=' % prefix not in metadata:
        metadata = metadata.replace(
            'xmlns:iirds="%s">' % IIRDS,
            'xmlns:iirds="%s"\n         xmlns:%s="%s">' % (IIRDS, prefix, PREFIXES[prefix]))
    return build_package(tmp_path, "%s_%d.iirds" % (rule_id.replace(".", "_"), count),
                         metadata=metadata)


@pytest.mark.parametrize("rule_id,cls,prop", PAIRS, ids=IDS)
def test_two_values_are_reported(rule_id, cls, prop, tmp_path):
    report = runner.check(_package(tmp_path, rule_id, cls, prop, 2))
    assert rule_id in {f.rule.id for f in report.findings}


@pytest.mark.parametrize("rule_id,cls,prop", PAIRS, ids=IDS)
def test_one_value_is_not(rule_id, cls, prop, tmp_path):
    """The half that says the rule is looking at the right thing. A rule that
    fires on two and also on one is not a cardinality check."""
    report = runner.check(_package(tmp_path, rule_id, cls, prop, 1))
    assert rule_id not in {f.rule.id for f in report.findings}


def test_the_ontology_answered_for_every_property():
    """If a property has no rdfs:range the helper above silently treats it as
    an object property, and half these fixtures would be malformed in a way
    that still produces findings. Assert the question was answerable."""
    graph = load().graph
    for rule_id, _cls, prop in PAIRS:
        assert (prop, RDFS.range, None) in graph or (prop, RDF.type, None) in graph, \
            "%s: the ontology says nothing about %s" % (rule_id, prop)


# ---------------------------------------------------------------------------
# Appendix A's `0..1` rows
# ---------------------------------------------------------------------------

#: The sentence every one of these rows is, exactly. Anchored, because a
#: pattern that skips what it cannot parse is how a row goes missing without
#: anyone deciding it should: the count below is what would notice, and a
#: count is only as good as the pattern that fed it.
ROW = re.compile(r"^0\.\.1 (\w+):([\w-]+) \(at most one\)$")


def appendix_rows():
    """`requirement id -> (class, property)`, derived from the obligation index.

    Not a list. The rows are the specification's own table, and a hand-copied
    subset of somebody else's table is a subset nobody can see the edge of --
    which is what the twenty-nine unclaimed rows were.

    The overview in A.5 restates all thirty, and the index marks that
    restatement as a double count, so it is dropped here for the same reason
    the coverage report drops it: one obligation, counted once.
    """
    index = json.loads((ROOT / "docs" / "requirements.json").read_text("utf-8"))
    twice = set(index["reductions"]["restated_in_the_overview"])
    twice |= set(index["reductions"]["keyword_definition"])
    rows = {}
    for requirement in index["requirements"]:
        if not requirement["absolute"] or requirement["id"] in twice:
            continue
        if "at most one" not in requirement["sentence"]:
            continue
        match = ROW.match(requirement["sentence"].strip())
        assert match, "unparsed `at most one` row: %s -- %s" % (
            requirement["id"], requirement["sentence"])
        prefix, local = match.groups()
        assert prefix in PREFIXES, "%s names an unknown prefix %r" % (requirement["id"], prefix)
        # `rdfclasses_core_ClassificationDomain#2` -- the class is the last
        # segment before the row number, in the core namespace. The index
        # states it a second way, in its own `subject` column, and the two are
        # made to agree: reading a class out of an identifier is a guess about
        # somebody else's naming, and a guess that happens to be right for
        # thirty rows is still a guess until it is checked against the column
        # that says it outright.
        cls = requirement["id"].rpartition("#")[0].rpartition("_")[2]
        subject = requirement.get("subject") or ""
        assert subject.partition(":")[2] == cls, (
            "%s: the id says %s and the index's subject column says %r"
            % (requirement["id"], cls, subject))
        rows[requirement["id"]] = (IIRDS[cls], PREFIXES[prefix][local])
    return rows


APPENDIX = appendix_rows()
APPENDIX_IDS = sorted(APPENDIX)

#: Appendix A states a row against the class that declares the property, and
#: one of those classes is abstract: `iirds:InformationUnit` is marked "not
#: intended to be used directly", so a package typing a node with it breaks
#: L10 and M1 as well as the row. The fixture would still be evidence -- a
#: rule claiming the row fires on it -- but it would be evidence entangled
#: with two other rules, and a fixture that breaks more than the sentence
#: under test is how a rule comes to be credited for another rule's finding.
#:
#: `iirds:Topic` rather than the first subclass alphabetically: `Document`
#: carries section 6.5.1's own MUST about document types and `Package` carries
#: the one-package-per-container rule, so either would put the second sentence
#: straight back.
CONCRETE = {IIRDS.InformationUnit: IIRDS.Topic}


def _subject_class(cls):
    """The class the fixture types its subject with -- `cls` unless the
    ontology says `cls` is not to be used directly."""
    return CONCRETE.get(cls, cls)


def test_every_abstract_class_in_the_rows_has_a_concrete_stand_in():
    """The substitution above is checked against the ontology, both ways.

    A stand-in that is not a subclass would test a different class entirely
    and pass, because these rules read `instances_of`, which follows the
    subclass closure and would simply find nothing. And a class marked
    abstract with no entry here goes back to breaking three sentences at once.
    """
    from iirds_validate.rules.lint import abstract_terms

    ontology = load()
    abstract = abstract_terms(ontology)
    for cls in sorted({cls for cls, _prop in APPENDIX.values()}, key=str):
        if cls in abstract:
            assert cls in CONCRETE, "%s is abstract and has no stand-in" % cls
    for cls, stand_in in sorted(CONCRETE.items(), key=lambda kv: str(kv[0])):
        assert cls in abstract, "%s is not abstract; it needs no stand-in" % cls
        assert stand_in in ontology.subclasses_of(cls), (
            "%s is not a subclass of %s" % (stand_in, cls))
        assert stand_in not in abstract, "%s is abstract too" % stand_in


def test_the_appendix_rows_are_all_there():
    """Thirty rows. Pinned because everything below is parametrized over them,
    and an empty or halved derivation would report a tidy pass over nothing --
    `empty_parameter_set_mark` catches nothing at all, not thirty become two.
    """
    assert len(APPENDIX) == 30, sorted(APPENDIX)


def test_the_two_readings_of_a_row_agree():
    """The hand-written pairs above and the derived rows are two statements of
    the same fact, and this is where they are made to meet.

    `PAIRS` was read out of the rule bodies; `APPENDIX` is read out of the
    specification. A rule that watches `iirds:has-event-code` on the wrong
    class, or an appendix row parsed onto the wrong property, shows up here as
    a disagreement rather than as two files that each look right.
    """
    from_spec = {(cls, prop) for cls, prop in APPENDIX.values()}
    for rule_id, cls, prop in PAIRS:
        if (cls, prop) in from_spec:
            continue
        # The rest are cardinalities the appendix states as `1`, not `0..1`;
        # they are here as rules, not as rows. Named so that "not in the
        # appendix table" cannot quietly grow.
        assert rule_id in ("M96.1", "M96.2"), (
            "%s watches %s on %s, which appendix A does not give as 0..1"
            % (rule_id, prop, cls))


@pytest.mark.parametrize("requirement", APPENDIX_IDS)
def test_every_at_most_one_row_is_claimed_by_a_rule(requirement):
    """A row in the coverage report's remainder that a rule already answers is
    the cheapest kind of gap there is, and the most embarrassing: the check
    runs on every package and the standard's own sentence goes on being listed
    as unmapped."""
    claimants = sorted(r.id for r in all_rules() if requirement in r.covers)
    assert claimants, "%s (%s) is claimed by no rule" % (
        requirement, APPENDIX[requirement][1])


def _fired(tmp_path, requirement, cls, prop, count):
    report = runner.check(_package(tmp_path, requirement.replace("#", "_"),
                                   _subject_class(cls), prop, count))
    return {f.rule.id for f in report.findings}


@pytest.mark.parametrize("requirement", APPENDIX_IDS)
def test_the_row_is_answered_by_a_rule_that_claims_it(requirement, tmp_path):
    """The claim, earned by a pair of packages.

    Two different values of the property on one instance of the class is the
    only way to break `0..1`, and one value is what the row permits -- so a
    rule that fires on both is not answering this row, and a rule that fires
    on neither is not answering anything.

    The third assertion is what lets these fixtures be minimal. Some of them
    break a second sentence by existing at all: a bare `iirds:Document` has no
    document type, which is section 6.5.1's MUST, and scaffolding thirty
    fixtures into full conformance would be thirty chances to make the
    scaffolding the thing under test. Instead both packages carry the same
    second defect, so the *difference* between them is the row and nothing
    else -- and that is asserted rather than assumed.
    """
    cls, prop = APPENDIX[requirement]
    claimants = {r.id for r in all_rules() if requirement in r.covers}
    assert claimants, "%s (%s) is claimed by no rule" % (requirement, prop)

    one = _fired(tmp_path, requirement, cls, prop, 1)
    two = _fired(tmp_path, requirement, cls, prop, 2)

    assert not (claimants & one), (
        "%s: one %s on an %s is what the row permits, and %s reported it"
        % (requirement, prop, cls, sorted(claimants & one)))
    assert claimants & two, (
        "%s: two %s on an %s, and no rule claiming the row fired "
        "(claimed by %s; fired: %s)"
        % (requirement, prop, cls, sorted(claimants), sorted(two)))
    # A second rule reading the same property is not a change of subject. The
    # catalogue holds two ids for one reading here: M6 states section 6.2.2's
    # sentence about information objects and M2.9 the appendix row, and both
    # are `_at_most_one(InformationUnit, is-version-of)`. M6 cannot claim the
    # row -- the name heuristic asks a claimant to name the row's class, and
    # M6's title is the specification's own "each information unit", which is
    # the better title. Anything the second value changes that is *not* a rule
    # reading this property is the fixture breaking a second sentence.
    reads_it = {rule_id for rule_id, terms in _properties_read_by_rule().items()
                if prop in terms}
    assert (two - one) - claimants <= reads_it, (
        "%s: the second value changed more than the row -- %s"
        % (requirement, sorted((two - one) - claimants - reads_it)))
    assert two - one, "%s: the second value changed nothing at all" % requirement


def test_the_claims_this_module_holds_are_the_rows_it_tests():
    """`NAMED_CASES` says which test holds a claim, and it checks that the test
    exists and nothing more -- so a claim can point at a test that says nothing
    about it, which is a coverage figure resting on a name.

    Both ends are asserted. Nothing may point here that this module does not
    test, and every row this module tests must be held by something -- not
    necessarily by this test. `rdfclasses_core_IdentityDomain#2` is R17's row
    and was already held by the test written for R17, which is the more
    specific evidence; registering it here as well made two entries for one
    key in a dict literal, where the last one silently wins. Demanding a
    monopoly is what produced that.
    """
    from test_covers_is_earned import NAMED_CASES, held

    here = "test_cardinality_rules_fire:test_the_row_is_answered_by_a_rule_that_claims_it"
    registered = {rid for rid, where in NAMED_CASES.items() if where == here}
    assert registered <= set(APPENDIX_IDS), (
        "registered against this module but not tested here: %s"
        % sorted(registered - set(APPENDIX_IDS)))
    assert set(APPENDIX_IDS) <= held(), (
        "tested here and held by nothing: %s" % sorted(set(APPENDIX_IDS) - held()))


def _properties_read_by_rule():
    """`rule id -> the ontology terms its body names as `T.<term>``.

    Asked of the body rather than of the helper call, because M6 is the reason
    this exists and M6 does not call the helper: it states section 6.2.2's
    reading of "exactly one" in its own loop over `ctx.information_units()`,
    and reads `T.is_version_of` directly. A version of this that looked only
    at `_at_most_one(...)` call sites saw M2.9 and not M6, which is the same
    blindness in a smaller place.

    The decorators are skipped: what a rule *claims* is not what it reads.
    """
    import ast

    source = (ROOT / "src" / "iirds_validate" / "rules" / "schema.py").read_text("utf-8")
    by_function = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef):
            continue
        body = ast.Module(body=node.body, type_ignores=[])
        names = {a.attr for a in ast.walk(body) if isinstance(a, ast.Attribute)
                 and isinstance(a.value, ast.Name) and a.value.id == "T"}
        by_function[node.name] = {getattr(T, n) for n in names if hasattr(T, n)}
    return {rule.id: by_function[rule.fn.__name__] for rule in all_rules()
            if getattr(rule.fn, "__name__", None) in by_function}


def _labels_by_rule():
    """`rule id -> the property label the rule's own body passes to the helper`.

    Read out of the source rather than out of the catalogue, because the two
    are exactly what this is comparing.
    """
    import ast

    source = (ROOT / "src" / "iirds_validate" / "rules" / "schema.py").read_text("utf-8")
    by_function = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef):
            continue
        for call in ast.walk(node):
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id in ("_at_most_one", "_exactly_one")
                    and len(call.args) == 4
                    and isinstance(call.args[3], ast.Constant)):
                by_function.setdefault(node.name, set()).add(call.args[3].value)
    return {rule.id: by_function[rule.fn.__name__]
            for rule in all_rules()
            if getattr(rule.fn, "__name__", None) in by_function}


def test_a_cardinality_rule_names_the_property_it_reads():
    """A title that names a property the rule does not read.

    M21.4's title said "MUST NOT have more than one property iirds:purpose"
    and its body reads `iirds:dateOfStatus`; M21.5 is the rule that reads
    `iirds:purpose`. Both are catalogue wordings, and the catalogue crosses
    them -- the rule's own docstring has said so all along, in a sentence
    nothing could act on. The title is what `iirds explain` prints, what the
    emitted shape carries as `sh:name`, and what a reader sees first, so a
    reader following it removed the wrong statement.

    Only properties, and only the ones this ontology defines: these titles
    name classes too, and a title naming `iirds:Party` beside
    `iirds:has-party-role` is saying what the rule is about, not what it
    reads.
    """
    ontology = load()
    properties = set()
    for root in ("iirdsRelationConcept", "iirdsAttribute"):
        properties |= {str(p).split("#")[-1]
                       for p in ontology.subproperties_of(IIRDS[root])}

    rules = {r.id: r for r in all_rules()}
    wrong = []
    for rule_id, labels in sorted(_labels_by_rule().items()):
        reads = {label.split(":")[-1] for label in labels}
        named = {m for m in re.findall(r"iirds:([\w-]+)", rules[rule_id].title)
                 if m in properties}
        if named and not named <= reads:
            wrong.append((rule_id, sorted(named - reads), sorted(reads)))
    assert wrong == [], (
        "these rules' titles name a property the rule does not read: %s" % wrong)


def test_the_ontology_defines_every_class_and_property_the_rows_name():
    """The derivation reads the class out of an identifier and the property out
    of a sentence, and both are somebody else's text. A typo on either side
    produces a fixture that states nothing about a term nothing checks, and
    every assertion above would still pass -- the claimant fires on two values
    it never sees, because the graph has no instance of the class at all.
    """
    ontology = load()
    for requirement, (cls, prop) in sorted(APPENDIX.items()):
        assert ontology.is_defined(cls), "%s: %s is not a class of the ontology" % (
            requirement, cls)
        assert ontology.is_defined(prop), "%s: %s is not a term of the ontology" % (
            requirement, prop)
