"""Why four rules do not apply to every version, checked rather than inherited.

Every `versions` array in the catalogue came from the reference tool and none
had ever been checked against anything. Nineteen rules are scoped to less than
all versions: fifteen are the iiRDS/H profile, which arrived with 1.3 and could
not apply earlier. The other four are the interesting ones, and one of them
turns a rule off in the two most recent releases of the standard.

Pinned here because the failure mode is silent in both directions. A scoping
that is too narrow switches a MUST off for the versions people actually ship;
one that is too broad claims a rule applies where its vocabulary did not exist.
Neither produces a finding, a traceback, or any other sign.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate import terms as T
from iirds_validate.registry import all_rules
from iirds_validate.resources import read_text, version_terms

ROOT = Path(__file__).resolve().parents[1]
ALL_VERSIONS = ("1.0", "1.0.1", "1.1", "1.2", "1.3")
RULES = {r.id: r for r in all_rules()}

#: Every rule scoped to less than all versions, with the reason. A rule
#: appearing here without one, or disappearing from it, fails the test below.
SCOPED = {
    "M8":    (("1.1", "1.2", "1.3"),
              "the prohibition on the enclosing package carrying a rendition "
              "arrives in 1.1"),
    "M24.4": (("1.1", "1.2", "1.3"),
              "the cardinality on iirds:relates-to-information-unit arrives in 1.1"),
    "M16.1": (("1.0", "1.0.1", "1.1"),
              "relaxed from MUST to MAY: 1.3 reads 'Instances of the iirds:Event class "
              "MAY have the following properties'"),
    "M16.2": (("1.0", "1.0.1", "1.1"), "relaxed from MUST to MAY with M16.1"),
    "M49":   (("1.1", "1.2", "1.3"), "iirds:IdentityType arrives in 1.1 with the identity-type system"),
    "M76":   (("1.1", "1.2", "1.3"), "mch:ProtectiveEquipment arrives in 1.1"),
    "R5":    (("1.3",),
              "section 6.3.3 exists in the cached 1.3 and not in the cached 1.0; "
              "1.1 and 1.2 are not on hand, so 1.3 is the only edition this can "
              "claim the sentence for"),
    "R6":    (("1.3",),
              "section 5.3 has no nesting chapter in the cached 1.0 either, so the "
              "same edition limit as R5 and for the same reason"),
    "R8":    (("1.3",),
              "section 6.3.3 again, the sentence that puts the nested containers in "
              "the archive; the cached 1.0 has no nesting chapter"),
    "R9":    (("1.3",),
              "sections 8.3.1.2 and 6.7.3 are the handover profile's, and the string "
              "iiRDS/H does not occur in the cached 1.0 at all"),
    "M96.1": (("1.2", "1.3"), "iirds:ExternalClassification arrives in 1.2"),
    "M96.2": (("1.2", "1.3"), "iirds:classificationIdentifier arrives in 1.2"),
    "M96.3": (("1.2", "1.3"), "iirds:classificationIdentifier arrives in 1.2"),
    "M97.1": (("1.2", "1.3"), "iirds:ClassificationDomain arrives in 1.2"),
    "M97.2": (("1.2", "1.3"), "iirds:ClassificationDomain arrives in 1.2"),
    "R1":    (("1.2", "1.3"), "iirds:ClassificationType arrives in 1.2 with the rest of "
                              "the external classification vocabulary"),
    "R2":    (("1.3",), "iirdsHov:DocumentCategory is part of iiRDS/H, which arrives in 1.3"),
    "R23":   (("1.2", "1.3"),
              "the half of M96.1's sentence that asks what the domain is; taken from "
              "M96.1 rather than written out, because a rule about the target of a "
              "property is meaningless in an edition without the property"),
    "R17":   (("1.1", "1.2", "1.3"),
              "iirds:has-identity-type arrives in 1.1 with the identity-type system, "
              "which is M49's reason as well"),
}

#: iiRDS/H arrived with 1.3, so its rules cannot apply to anything earlier.
HANDOVER = {r.id for r in all_rules() if tuple(r.versions) == ("1.3",)}


def test_the_only_version_scoped_rules_are_the_ones_accounted_for():
    """A new scoping appearing without a reason is the thing this catches. It
    would otherwise be invisible: a rule that stops running on the versions
    people ship produces nothing at all."""
    scoped = {r.id for r in all_rules()
              if r.versions and tuple(r.versions) != ALL_VERSIONS}
    assert scoped == set(SCOPED) | HANDOVER


def test_every_1_3_only_rule_belongs_to_the_handover_profile():
    """iiRDS/H arrived with 1.3, so its rules cannot apply earlier. R2 is here
    for the same reason without an M15 identifier: it implements a
    specification requirement the catalogue has no id for, and R4 for the same
    reason again -- it owns the softening the five named-party MUSTs share."""
    assert HANDOVER, "iiRDS/H rules must exist"
    # By the profile the rule declares, not by the shape of its id. R13 to
    # R16 are section 8.3.2's Package list and carry variants=("H",); reading
    # the id would have made "belongs to the handover profile" mean "is
    # called M15-something", which is a different sentence.
    by_id = {rule.id: rule for rule in all_rules()}
    outside = sorted(r for r in HANDOVER
                     if "H" not in by_id[r].variants and r not in SCOPED)
    assert outside == [], outside


@pytest.mark.parametrize("rule_id", sorted(SCOPED), ids=sorted(SCOPED))
def test_the_scoping_is_what_was_verified(rule_id):
    assert tuple(RULES[rule_id].versions) == SCOPED[rule_id][0]


def _event_package(tmp_path, version):
    metadata = MINIMAL_RDF.replace(
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
        "<iirds:iiRDSVersion>%s</iirds:iiRDSVersion>" % version).replace("</rdf:RDF>", '''
  <iirds:Event rdf:about="urn:test:e1">
    <rdfs:label xml:lang="en">Overheat</rdfs:label>
  </iirds:Event>
</rdf:RDF>''')
    return build_package(tmp_path, "ev%s.iirds" % version.replace(".", "_"), metadata=metadata)


def test_an_event_with_no_code_is_a_defect_in_1_1_and_not_in_1_3(tmp_path):
    """The same package, two declared versions, two correct answers.

    This is the one scoping that switches a rule off for current releases, so
    it is asserted from both ends rather than trusted. iiRDS 1.0 to 1.1 said
    instances of iirds:Event MUST carry a code and a type; 1.3 says MAY. The
    reference tool's own spec link for these two rules points at the 1.3
    document, where the sentence reads MAY -- so a reader following it sees
    this validator apparently contradicting the standard. It does not; the
    link is to a later edition of a sentence that changed.
    """
    old = {f.rule.id for f in runner.check(_event_package(tmp_path, "1.1")).findings}
    assert {"M16.1", "M16.2"} <= old

    current = {f.rule.id for f in runner.check(_event_package(tmp_path, "1.3")).findings}
    assert not {"M16.1", "M16.2"} & current


def test_a_handover_rule_does_not_reach_back_into_earlier_versions(tmp_path):
    """iiRDS/H did not exist before 1.3, so a 1.2 package declaring the profile
    must not be measured against requirements the standard had not written."""
    metadata = MINIMAL_RDF.replace(
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
        "<iirds:iiRDSVersion>1.2</iirds:iiRDSVersion>"
        "<iirds:formatRestriction>H</iirds:formatRestriction>")
    report = runner.check(build_package(tmp_path, "h12.iirds", metadata=metadata))
    assert not {f.rule.id for f in report.findings} & HANDOVER


def test_no_rule_claims_a_version_whose_vocabulary_it_predates():
    """The check `tools/version_inventory.py` performs, run in the suite.

    A rule declaring itself applicable to a version in which its own class or
    property did not exist is wrong in a way that produces nothing at all: it
    runs, matches nothing, reports a clean package. What it corrupts is the
    claim -- `iirds rules` says the rule applies where it cannot.

    Five rules were in that state, all naming the external classification
    vocabulary that arrives in 1.2 while the catalogue dated them from 1.0.
    """
    from iirds_validate.model import VERSIONS
    from version_inventory import terms_named_by

    inventory = version_terms()

    problems = []
    for rule in all_rules():
        named = terms_named_by(rule)
        # `or VERSIONS`, not `or ()`. An empty tuple is how the registry spells
        # "every edition", and reading it as "no edition" left twenty-three
        # rules unchecked here -- the same defect the tool was repaired for,
        # still standing in the copy of it that runs in the suite.
        for version in rule.versions or VERSIONS:
            if version in inventory:
                absent = [t for t in named if t not in inventory[version]]
                if absent:
                    problems.append((rule.id, version, sorted(absent)))
    assert problems == []


def test_every_published_edition_has_an_inventory():
    """This began with 1.0 and 1.0.1 in an "unavailable" list, because the
    GitHub tags carry only 1.1 and 1.2. The Consortium's own site publishes
    every edition's schema files, so the list is now empty — and the check
    still refuses to conflate "not checked" with "checked and clean" if an
    edition ever appears faster than its schemas do."""
    import json

    data = json.loads(read_text("version-terms.json"))
    assert data["_unavailable"] == []
    assert set(data["terms"]) == {"1.0", "1.0.1", "1.1", "1.2", "1.3"}


def test_the_term_reader_follows_the_helpers_a_rule_calls():
    """`terms_named_by` read one level: `inspect.getsource(rule.fn)`.

    Nearly every rule here is three lines calling a builder, because the
    builders are where the duplication went, and each move took the terms out
    of the checker's sight. Parameterising the section 8.3.2 family shrank
    M15.7b's inventory from `iirds:Manufacturer` to `iirds:Document`. What is
    left is a version check that reads the shape of the code rather than what
    the rule looks for, and gets quieter every time the code improves.

    Both kinds of helper, because the first repair followed only the
    underscore-prefixed ones -- the rule modules' convention among themselves,
    and not the whole of what they call. M3 reaches `iirds:Package` and
    `iirds:is-part-of-package` through `package_nodes` and
    `container_packages`, which are public, and six rules were hiding a term
    that way.
    """
    from version_inventory import terms_named_by

    by_id = {rule.id: rule for rule in all_rules()}
    named = set(terms_named_by(by_id["M15.7b"]))
    assert str(T.Manufacturer) in named, (
        "a term reached through a private helper: %s" % sorted(named))

    named = set(terms_named_by(by_id["M3"]))
    assert str(T.Package) in named and str(T.is_part_of_package) in named, (
        "a term reached through a public helper: %s" % sorted(named))


def test_nothing_reads_an_empty_versions_as_no_edition():
    """`versions=()` is how the registry spells "every edition", and twenty-five
    rules use it. Read as `rule.versions or ()` it means the opposite, and a
    loop over that runs zero times — which is not an error anywhere, just a
    check that silently stops checking.

    It happened twice: `tools/version_inventory.py` looped that way over
    twenty-three rules, and after that was repaired the copy of the same loop
    inside this suite kept doing it. Both were found by accident.

    The spelling `or VERSIONS` is right and `or ()` is the bug, so the bug is
    what is forbidden. Whether the two spellings of the default should be one
    is a separate question and an open one; this only stops the readers from
    disagreeing about what the empty one means.
    """
    import ast

    #: Read as code, not as text: this test's own docstring names the spelling
    #: it forbids, and a grep over lines matched it. `ast` sees expressions.
    class _Finder(ast.NodeVisitor):
        def __init__(self, name):
            self.name, self.found = name, []

        def visit_BoolOp(self, node):
            if isinstance(node.op, ast.Or) and len(node.values) == 2:
                left, right = node.values
                if (isinstance(left, ast.Attribute) and left.attr == "versions"
                        and isinstance(right, ast.Tuple) and not right.elts):
                    self.found.append("%s:%d" % (self.name, node.lineno))
            self.generic_visit(node)

    offenders = []
    for folder in ("src", "tools", "tests"):
        for path in sorted((Path(__file__).resolve().parents[1] / folder).rglob("*.py")):
            finder = _Finder(path.name)
            try:
                finder.visit(ast.parse(path.read_text("utf-8")))
            except SyntaxError:
                continue
            offenders.extend(finder.found)
    assert offenders == [], (
        "these read an empty `versions` as no edition rather than as every "
        "edition, which turns a loop into a no-op: %s" % offenders)


# ---------------------------------------------------------------------------
# What the inventory can and cannot see
#
# `tools/version_inventory.py` finds a rule's terms by reading its source for
# `T.<name>`, and passes any rule that names none -- vacuously, with a clean
# line. That is the truth for a container rule whose subject is ZIP bytes. It
# is not the truth for a rule that reads the graph, and the difference was
# invisible until L16 declared all five editions while eight of the relations
# it watches are absent from 1.0.
# ---------------------------------------------------------------------------

def test_the_inventory_sees_terms_a_factory_bound_rather_than_a_body_spelled():
    """A rule built by a factory names its terms at the call site.

    R19 to R23 are one builder called four times, so their `T.` constants are
    arguments and never appear in the function the inventory reads. The terms
    are not hidden, though -- they are sitting in the function object, as
    default arguments and closure cells -- so this is a limit of where the tool
    looked rather than of what it could know.
    """
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "tools"))
    from version_inventory import terms_named_by

    by_id = {r.id: r for r in all_rules()}
    named = terms_named_by(by_id["R19"])
    assert "http://iirds.tekom.de/iirds#has-document-type" in named, named
    assert "http://iirds.tekom.de/iirds#is-applicable-for-document-type" in named, named
    assert "http://iirds.tekom.de/iirds#DocumentType" in named, named


def test_the_rules_the_inventory_cannot_answer_for_are_declared():
    """A rule that reads the graph and names no term is not answered by this
    check, and it passed with a clean line.

    Enumerated so a new one has to be looked at, and stale entries refused so
    the list cannot outlive the rules.

    **Which kind** of silence each is, the list does not say, after two goes at
    it. Written by hand, five of fourteen reasons were false -- M2.1's said its
    classes come from the generated table, and that table has no
    `InformationUnit` row. Derived from the source, the split turned on how the
    access is spelled rather than on what is read: L13 and L14 both scan the
    ontology's whole defined-term set and landed on opposite sides. A label
    this project cannot make true is worse than no label.
    """
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "tools"))
    from version_inventory import NAMES_NO_TERM, _reads_the_graph, terms_named_by

    silent = {r.id for r in all_rules() if _reads_the_graph(r) and not terms_named_by(r)}
    assert silent == set(NAMES_NO_TERM), sorted(silent ^ set(NAMES_NO_TERM))
    for rule_id, note in NAMES_NO_TERM.items():
        assert len(note) > 20, (rule_id, note)


def test_a_rule_that_is_not_a_plain_function_does_not_take_the_check_down():
    """A rule is whatever callable was registered, and `functools.partial` and
    a callable class instance are both legal.

    Reading `__defaults__` unguarded raised an AttributeError out of the middle
    of `make versions`. Guarding it without unwrapping was worse: `getsource`
    raises on a partial too, so the reached source came back empty and the rule
    read as naming no term *and* as not touching the graph -- neither answered
    nor refused, silently. The first version of this test asserted the empty
    list, which pinned the blindness as the expectation.
    """
    import functools
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "tools"))
    from version_inventory import _iirds_terms_bound_into, _source_the_rule_reaches

    def inner(ctx, prop):
        for _subject, _value in ctx.graph.subject_objects(prop):
            pass

    partial = functools.partial(inner, prop=T.title)
    assert str(T.title) in _iirds_terms_bound_into(partial)
    assert "ctx.graph" in _source_the_rule_reaches(partial)

    class Callable:
        def __call__(self, ctx):
            return None

    assert _iirds_terms_bound_into(Callable()) == []


def test_a_keyword_only_default_is_seen_and_a_shared_table_is_not_charged():
    """A keyword-only default is how a factory pins one argument, and it
    returned nothing.

    A dict is deliberately not walked, which is the other half. Walking dict
    values was added to close the "terms live in a table" hole and does not:
    a table a rule indexes is a module global, in neither the defaults nor the
    closure. What it did was charge a rule closing over a shared table with
    every term in it -- so a rule correct for its edition failed over a term
    it never reads. The hole it was for stays open and is written down.
    """
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "tools"))
    from version_inventory import _iirds_terms_bound_into

    def keyword_only(ctx, *, prop=T.title):
        return prop

    # A mutable default is the shape being reproduced, not a style choice:
    # the walker's question is what sits in `__defaults__`, and a table is
    # what a factory would put there.
    def closes_over_a_table(ctx, table={"a": T.title, "b": T.revision}):  # noqa: B006
        return table["a"]

    assert str(T.title) in _iirds_terms_bound_into(keyword_only)
    assert _iirds_terms_bound_into(closes_over_a_table) == []


#: What each derived population holds that an older edition's vocabulary does
#: not. Measured, because the numbers are the reason `NAMES_NO_TERM` records
#: "not answered here" rather than "nothing to answer".
OUTRUNS_THE_EDITION = {
    "relation_properties": {"1.0": 8, "1.0.1": 8, "1.1": 6, "1.2": 3, "1.3": 0},
    "vocabulary_classes": {"1.0": 4, "1.0.1": 4, "1.1": 2, "1.2": 1, "1.3": 0},
    # Not attributed to a rule. `classes()` is what `vocabulary_classes` starts
    # from, and it was pinned here as L13's -- L13 scans `defined_terms()`,
    # which is 327 terms and 46 missing from 1.0, not 78 and 8. Kept because
    # the class list moving is worth seeing; named for what it is.
    "every class the ontology declares": {"1.0": 8, "1.0.1": 8, "1.1": 5,
                                          "1.2": 2, "1.3": 0},
}


def test_how_far_each_derived_population_outruns_the_older_editions():
    """Only the newest ontology ships, so a rule that derives its population
    from it derives the same population whatever a package declares.

    L16 filters by the declared edition -- a name 1.0 does not have is not one
    of its relations, and L15's sentence is the right one about it. R18 does
    not, and whether it should is a question per rule rather than a defect
    established here: R18 asks whether a proprietary extension is described,
    which is orthogonal to when a term arrived.

    Recomputed from each edition's own published ontology by a reviewer: both
    populations are strictly monotone across 1.0 to 1.3 with no class or
    property changing side, so neither rule can reclassify anything on an older
    edition. That is why this stays a pinned measurement and not a repair.

    Pinned so the question stays visible and so a change in either direction --
    a rule starting to filter, or the ontology moving -- is a diff somebody
    reads.
    """
    from iirds_validate.ontology import load
    from iirds_validate.rules.lint import relation_properties
    from iirds_validate.rules.requirements import vocabulary_classes

    ontology = load()
    editions = version_terms()
    populations = {
        "relation_properties": relation_properties(ontology),
        "vocabulary_classes": vocabulary_classes(ontology),
        "every class the ontology declares": ontology.classes(),
    }
    for name, population in populations.items():
        terms = {str(term) for term in population}
        measured = {v: len(terms - set(editions[v])) for v in editions}
        assert measured == OUTRUNS_THE_EDITION[name], (name, measured)


def test_a_helper_called_through_its_module_is_followed_too():
    """`schema.py` is about to be split by specification section, and the
    split's call style decides whether this check can still see anything.

    The walker resolves a name with `getattr(rule's own module, name)`. After a
    split, `from .schema_relations import _points_at_an_instance_of` leaves the
    name in the module namespace and is followed; `from . import
    schema_relations` and then `schema_relations._points_at_an_instance_of(...)`
    is not -- the helper's body drops out of the reached source, the terms it
    names drop out with it, and the rule reads as naming nothing. The check
    then says nothing about it and says so with a clean line.

    A structural move must not be able to blind a gate, and the gate must not
    depend on a convention somebody has to remember. It falls back to the rules
    package now, so either style is followed.
    """
    import sys
    import types
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "tools"))
    from version_inventory import _source_the_rule_reaches

    from iirds_validate.rules import schema

    probe = types.ModuleType("probe_module_qualified")
    sys.modules["probe_module_qualified"] = probe
    try:
        def body(ctx):
            return schema._points_at_an_instance_of(ctx, T.title, T.Document, "x")

        body.__module__ = "probe_module_qualified"
        reached = _source_the_rule_reaches(body)
        assert "undescribed reference" in reached, (
            "the helper's body is not in the reached source; a rule calling it "
            "this way would read as naming no term")
    finally:
        del sys.modules["probe_module_qualified"]
