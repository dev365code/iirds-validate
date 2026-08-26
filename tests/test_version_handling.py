"""Version detection must never turn into a silent pass."""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import runner

NO_VERSION = MINIMAL_RDF.replace("    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n", "")


def test_missing_version_still_runs_the_rules(make_package):
    """Filtering rules by the declared version means a package with no version
    declaration is checked by nothing at all and reported clean. Here the newest
    version is assumed instead, and the assumption is written into the report."""
    report = runner.check(make_package(metadata=NO_VERSION))

    assert report.checked > 40, "rules must still run without a declared version"
    assert "M4" in {f.rule.id for f in report.findings}, "and the omission is itself a finding"
    assert any("no iirds:iiRDSVersion" in n for n in report.notes)


def test_unknown_version_falls_back_and_says_so(make_package):
    weird = MINIMAL_RDF.replace("1.3</iirds:iiRDSVersion>", "9.9</iirds:iiRDSVersion>")
    report = runner.check(make_package(metadata=weird))
    assert report.checked > 40
    assert any("9.9" in n for n in report.notes)


def test_version_filtering_still_works(make_package):
    """Everything 1.3 added to the rule set belongs to the handover profile.

    So the version axis only becomes visible on an iiRDS/H package: the same
    package declared as 1.2 must be checked by fewer rules than as 1.3.
    """
    handover = MINIMAL_RDF.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        "    <iirds:formatRestriction>H</iirds:formatRestriction>\n")
    older = handover.replace("1.3</iirds:iiRDSVersion>", "1.2</iirds:iiRDSVersion>")

    new = runner.check(make_package(name="new.iirds", metadata=handover, jsonld="{}"))
    old = runner.check(make_package(name="old.iirds", metadata=older, jsonld="{}"))

    assert new.variant == "H" and old.variant == "H"
    assert old.checked < new.checked, "1.3 added handover rules that 1.2 must not run"


def test_unrestricted_package_skips_handover_rules(make_package):
    report = runner.check(make_package())
    assert report.variant == "unrestricted"
    assert report.skipped > 0
    assert "M15.2" not in {f.rule.id for f in report.findings}


# ---------------------------------------------------------------------------
# Which package the version and the profile are read off
#
# Detection decides the ontology and the applicable rule set, so getting the
# wrong package here is not a cosmetic error: it silently changes what "valid"
# means for the whole run.
# ---------------------------------------------------------------------------

#: §7 lets a package type its own subclasses and requires a consumer to treat
#: an instance as its parent class. Read with exact typing, this package is
#: not a package at all.
SUBCLASS_PACKAGE = MINIMAL_RDF.replace(
    '  <iirds:Package rdf:about="urn:test:package">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n',
    '  <rdf:Description rdf:about="urn:test:DeliveryPackage">\n'
    '    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Package"/>\n'
    '  </rdf:Description>\n'
    '  <rdf:Description rdf:about="urn:test:package">\n'
    '    <rdf:type rdf:resource="urn:test:DeliveryPackage"/>\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:formatRestriction>H</iirds:formatRestriction>\n').replace(
    "  </iirds:Package>\n", "  </rdf:Description>\n")

#: A package that contains another one. The child declares the handover
#: profile; the container does not, and the container is what is being judged.
NESTED_CHILD = MINIMAL_RDF.replace(
    "</rdf:RDF>",
    '  <iirds:Package rdf:about="urn:test:child">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:formatRestriction>H</iirds:formatRestriction>\n'
    '    <iirds:is-part-of-package rdf:resource="urn:test:package"/>\n'
    '  </iirds:Package>\n</rdf:RDF>')

#: Two packages side by side, neither nested, each declaring one half of the
#: answer. Whatever is chosen, both halves must come off the same node.
SPLIT_HALVES = MINIMAL_RDF.replace(
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
    "    <iirds:formatRestriction>H</iirds:formatRestriction>\n").replace(
    "</rdf:RDF>",
    '  <iirds:Package rdf:about="urn:test:second">\n'
    '    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n'
    '  </iirds:Package>\n</rdf:RDF>')

#: One package, two versions. M4 reports it; detection still has to answer.
TWO_VERSIONS = MINIMAL_RDF.replace(
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
    "    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n")

#: A metadata document whose only package says it is part of a parent that is
#: not here. Nothing is left after the nesting filter, and the package still
#: has to be read -- it is the thing being validated.
ORPHAN_CHILD = MINIMAL_RDF.replace(
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
    "    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n"
    "    <iirds:formatRestriction>A</iirds:formatRestriction>\n"
    '    <iirds:is-part-of-package rdf:resource="urn:test:absent"/>\n')

#: The shape of tests/corpus/plusmeta/files/metadata_iirds_sample-M5_false.rdf:
#: a package declared to be part of itself. The only one in the corpus.
SELF_LOOP = MINIMAL_RDF.replace(
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
    "    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n"
    "    <iirds:formatRestriction>A</iirds:formatRestriction>\n"
    '    <iirds:is-part-of-package rdf:resource="urn:test:package"/>\n')


def _ids(report):
    return {f.rule.id for f in report.findings}


def test_a_package_typed_with_its_own_subclass_is_still_the_package(make_package):
    """Read with exact typing, a §7-subclassed package is invisible: no
    version, no profile, and every handover rule stands down. The package
    below fails one of them, so the proof is a finding, not a rule count."""
    report = runner.run(make_package(metadata=SUBCLASS_PACKAGE), runner.ALL_KINDS)

    assert (report.version, report.variant) == ("1.3", "H"), (
        "a package typed with a subclass it declares itself is still the "
        "package this container is about")
    assert "M15.11a" in _ids(report), (
        "the handover rules did not run, so the profile was not detected")


def test_a_nested_child_does_not_set_the_containers_profile(make_package):
    """A package inside a package declares its own profile. Reading it as
    the container's turns on seventeen handover MUSTs against a package
    that never claimed to be one -- the false-reject direction."""
    report = runner.run(make_package(metadata=NESTED_CHILD), runner.ALL_KINDS)

    assert report.variant == "unrestricted", (
        "the profile came off the nested child rather than the container")
    assert "M15.11a" not in _ids(report)


def test_the_version_and_the_profile_come_off_one_package(make_package):
    """Read with two independent accumulators, a run can answer with a
    version from one package and a profile from another -- a combination
    no package in the container ever declared."""
    report = runner.run(make_package(metadata=SPLIT_HALVES), runner.ALL_KINDS)

    assert (report.version, report.variant) in (("1.0", "unrestricted"), (None, "H")), (
        "version %r and profile %r were read off different packages"
        % (report.version, report.variant))
    assert "M3" in _ids(report), "and two container packages is itself a finding"


def test_a_package_declaring_two_versions_is_judged_against_the_newer(make_package):
    """The same rule the missing-version case follows, eight lines down in
    context.py: nothing passes by silence. Taking the lower one read as the
    kinder choice and was not -- a 1.3 package with a second declaration of
    1.0 stopped being checked by nine rules, and a genuine violation of one
    of them left the report while M4 arrived in its place. M4 reports the
    pair either way; what the newer reading keeps is the finding."""
    report = runner.run(make_package(metadata=TWO_VERSIONS), runner.ALL_KINDS)

    assert report.version == "1.3"
    assert report.effective_version == "1.3"
    assert "M4" in _ids(report)


def test_a_second_version_does_not_switch_a_rule_off(make_package):
    """The concrete cost of the choice above. M8 is 1.1+, and the package
    below breaks it: adding an older version declaration must not be a way
    to make that finding go away."""
    broken = MINIMAL_RDF.replace(
        "</rdf:RDF>",
        '  <rdf:Description rdf:about="urn:test:package">\n'
        '    <iirds:has-rendition rdf:resource="urn:test:elsewhere"/>\n'
        '  </rdf:Description>\n</rdf:RDF>')
    both = broken.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        "    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n")

    assert "M8" in _ids(runner.run(make_package(name="one.iirds", metadata=broken),
                                   runner.ALL_KINDS))
    assert "M8" in _ids(runner.run(make_package(name="two.iirds", metadata=both),
                                   runner.ALL_KINDS))


def test_a_version_python_cannot_count_does_not_take_the_run_down(make_package):
    """`"²".isdigit()` is true and `int("²")` raises, so a declared version
    holding one passed the test that guards the conversion and then failed
    the conversion. Detection runs before any rule, outside the net where a
    rule that raises becomes a finding -- so one character in one literal
    ended the whole validation with a traceback."""
    weird = MINIMAL_RDF.replace("<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
                                "<iirds:iiRDSVersion>1.\u00b2</iirds:iiRDSVersion>")
    report = runner.check(make_package(metadata=weird))

    assert report.effective_version == "1.3", "an unreadable version falls back"
    assert any("1.\u00b2" in note for note in report.notes), (
        "and the run says which value it could not read")


def test_the_published_versions_sort_as_numbers_under_a_plain_sort():
    """Detection does not rest on this any more -- it sorts by number, and
    the test above pins that -- but everything else that puts a version in
    order still uses text, and this says how far that is safe: over the
    versions the standard has actually published, text order and number
    order agree. A 1.10 would break it, since text puts it between 1.1 and
    1.2, and this turns red on the day one appears rather than on the day
    something depends on it."""
    from conftest import version_tuple
    from iirds_validate.model import VERSIONS

    assert sorted(VERSIONS) == sorted(VERSIONS, key=version_tuple), (
        "iiRDS %s no longer sorts the same as text and as numbers" % (VERSIONS,))


def test_a_child_whose_parent_is_absent_still_declares_itself(make_package):
    """A parent this document does not carry is not a parent. §6.3.3 licenses
    the nesting triple only "in the metadata.rdf file of the parent iiRDS
    container", where §6.2 requires the parent's own instance to be present --
    and Example 16 prints the child's own metadata.rdf with no
    is-part-of-package at all. So this package is not below anything: it is
    what this container is about, and the primary reading answers it. L1
    reports the dangling reference on the same run."""
    report = runner.run(make_package(metadata=ORPHAN_CHILD), runner.ALL_KINDS)

    assert (report.version, report.variant) == ("1.0", "A")


#: The same shape with a second, ordinary package beside it. Two packages
#: represent this container, and the self-loop is not what makes one of them
#: a nested child.
SELF_LOOP_AND_SIBLING = SELF_LOOP.replace(
    "</rdf:RDF>",
    '  <iirds:Package rdf:about="urn:test:second">\n'
    '    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n'
    '  </iirds:Package>\n</rdf:RDF>')


def test_a_package_that_is_part_of_itself_is_still_this_container(make_package):
    """A package cannot be a part of itself, and §6.2 forbids only membership
    in *another* package -- so a self-loop does not make one. Two packages
    then represent this container, which is exactly what M3 is for. Read as
    the bare presence of the predicate, one of them dropped out of the count
    and the finding never arrived."""
    report = runner.run(make_package(metadata=SELF_LOOP_AND_SIBLING), runner.ALL_KINDS)

    assert "M3" in _ids(report), (
        "a package that is part of itself is nested inside nothing, so two "
        "packages represent this container and that is the finding")


def test_a_package_that_is_part_of_itself_still_declares_itself(make_package):
    """A package that is part of itself is nested inside nothing, so it *is*
    this container and the primary reading answers it -- no fallback tier
    involved. Both assertions below held before that was true, for the other
    reason: nothing was a container package, everything went back in the
    pool, and M3 says nothing about a count of zero. The test above is the
    one that tells the two apart. The corpus carries exactly one such
    package, `metadata_iirds_sample-M5_false.rdf`."""
    report = runner.run(make_package(metadata=SELF_LOOP), runner.ALL_KINDS)

    assert (report.version, report.variant) == ("1.0", "A")
    assert "M3" not in _ids(report)


def vendored_ontologies():
    """The ontology versions this project actually ships, by directory."""
    from iirds_validate import resources

    return sorted(name for name in resources.listdir("ontologies")
                  if resources.exists("ontologies", name, "iirds-core.rdf"))


def test_no_ontology_this_project_ships_declares_a_subclass_of_package():
    """The premise the design rests on. Detection runs before the ontology
    is chosen -- it cannot consult one -- so it closes over the subclasses
    the *package* declares and nothing else. That is complete only while the
    standard declares no subclass of iirds:Package.

    Asked of the directories on disk rather than of VERSIONS: a version with
    no directory is served the newest one, so looping over VERSIONS asks the
    same graph five times while its failure message names five different
    releases. The versions not shipped here cannot be checked offline at
    all, and the test below is what keeps that from being forgotten."""
    from iirds_validate import ontology as ontology_mod
    from iirds_validate import terms as T

    shipped = vendored_ontologies()
    assert shipped, "no ontology is vendored; this would otherwise pass by having nothing to check"
    for version in shipped:
        loaded = ontology_mod.Ontology(version)
        assert set(loaded.subclasses_of(T.Package)) == {T.Package}, (
            "the vendored iiRDS %s declares a subclass of iirds:Package; "
            "version detection runs before an ontology is loaded and would "
            "not see it" % version)


def test_only_the_newest_ontology_is_vendored():
    """What makes the test above honest about its own reach. Every other
    version is served the newest ontology, so nothing here has ever been
    checked against 1.0's own vocabulary. The day a second one is vendored
    this turns red, and the check above has to grow to cover it."""
    from iirds_validate import ontology as ontology_mod
    from iirds_validate.model import LATEST_VERSION, VERSIONS

    own = {version for version in VERSIONS
           if ontology_mod.load(version).substituted is None}
    assert own == {LATEST_VERSION}, (
        "these versions load an ontology of their own: %s -- the subclass "
        "check above reads directories, and now has more to read" % sorted(own))
    assert vendored_ontologies() == [LATEST_VERSION]


#: A grandchild, its parent, and a grandparent this document does not carry.
#: Nothing here is a container package, so nesting cannot pick the answer --
#: but the grandchild is two levels down and the middle package is one, and
#: only one of them is the root of what is present.
NESTED_CHAIN = MINIMAL_RDF.replace(
    '  <iirds:Package rdf:about="urn:test:package">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:title>Test package</iirds:title>\n'
    '  </iirds:Package>\n',
    '  <iirds:Package rdf:about="urn:test:aaa-grandchild">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:formatRestriction>H</iirds:formatRestriction>\n'
    '    <iirds:is-part-of-package rdf:resource="urn:test:zzz-middle"/>\n'
    '  </iirds:Package>\n'
    '  <iirds:Package rdf:about="urn:test:zzz-middle">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:is-part-of-package rdf:resource="urn:test:absent"/>\n'
    '  </iirds:Package>\n')


def test_a_grandchild_does_not_set_the_profile_of_what_contains_it(make_package):
    """The grandchild is inside a package this document carries, so it is not
    the container. The middle one names a parent that is not here, so it is.
    Before the filter read the predicate this way the grandchild could win on
    an alphabetical tie-break and switch seventeen handover MUSTs on against
    a package that never claimed one -- the false-reject direction."""
    report = runner.run(make_package(metadata=NESTED_CHAIN), runner.ALL_KINDS)

    assert report.variant == "unrestricted", (
        "the profile came off a package nested inside another package that "
        "is itself present")
    assert "M15.11a" not in _ids(report)


@pytest.mark.parametrize("declared,expected", [
    (["1.0", "1.3"], "1.3"),
    (["1.3", "1.0"], "1.3"),
    (["1.1", "1.10"], "1.10"),          # text order would answer 1.1
    (["1.2", "1.10", "1.3"], "1.10"),
    (["1.3", "9.9.9"], "9.9.9"),
    (["1.3", "not-a-version"], "not-a-version"),
])
def test_the_newest_declared_version_is_found_by_number(declared, expected):
    """The ordering detection uses, on its own. Every version the standard
    has published sorts the same as text and as numbers, so nothing in the
    corpus can exercise this -- and that is exactly why it is here rather
    than left to a fixture. A value that is not a version sorts last: it
    falls back to the newest and is reported, where sorting it away would
    leave the typo unmentioned."""
    from iirds_validate.context import _version_key

    assert sorted(declared, key=_version_key)[-1] == expected


#: Two packages each declared part of the other. Neither is a container and
#: neither is a root of what is present, so nothing is left to choose from --
#: the shape that reaches the last fallback now that a self-loop does not.
MUTUAL_NESTING = MINIMAL_RDF.replace(
    '  <iirds:Package rdf:about="urn:test:package">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:title>Test package</iirds:title>\n'
    '  </iirds:Package>\n',
    '  <iirds:Package rdf:about="urn:test:aaa">\n'
    '    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n'
    '    <iirds:is-part-of-package rdf:resource="urn:test:bbb"/>\n'
    '  </iirds:Package>\n'
    '  <iirds:Package rdf:about="urn:test:bbb">\n'
    '    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n'
    '    <iirds:is-part-of-package rdf:resource="urn:test:aaa"/>\n'
    '  </iirds:Package>\n')


def test_two_packages_nested_inside_each_other_still_declare_themselves(make_package):
    """The last fallback, and the only graph that reaches it: each package is
    part of the other and both are here, so neither represents this container
    while there are still declarations that have to be read.

    The version alone did not say which route produced it -- ("1.0",
    "unrestricted") is what the primary reading would answer too, so the test
    passed whichever ran and pinned only that the fallback existed. The
    precondition is what pins the route."""
    from iirds_validate.context import container_packages, package_nodes

    package = make_package(metadata=MUTUAL_NESTING)
    ctx = runner.load(package)

    assert container_packages(ctx.graph) == [], (
        "nothing represents this container, which is what sends the answer to "
        "the fallback")
    assert len(package_nodes(ctx.graph)) == 2, (
        "and there are still packages to read, or the fallback would answer "
        "nothing either")

    report = runner.run(package, runner.ALL_KINDS)
    assert (report.version, report.variant) == ("1.0", "unrestricted")
    assert "M3" not in _ids(report), (
        "M3 asks about container packages and there are none; that silence is "
        "the fallback's premise rather than an oversight")


def test_a_self_loop_does_not_push_a_package_below_the_root(make_package):
    """The same predicate, read the same way in one place. A package that
    names itself and a parent this document does not carry is not below
    anything: it is the container. There used to be a second reading of the
    predicate fourteen lines down, for "the roots of what is present"; under
    this reading its answer became identical, so it could never contribute
    and it is gone. One predicate, one place, and now literally one
    function."""
    both = MINIMAL_RDF.replace(
        '  <iirds:Package rdf:about="urn:test:package">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:title>Test package</iirds:title>\n'
        '  </iirds:Package>\n',
        '  <iirds:Package rdf:about="urn:test:zzz-root">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:zzz-root"/>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:absent"/>\n'
        '  </iirds:Package>\n'
        '  <iirds:Package rdf:about="urn:test:aaa-child">\n'
        '    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:zzz-root"/>\n'
        '  </iirds:Package>\n')
    report = runner.run(make_package(metadata=both), runner.ALL_KINDS)

    assert report.version == "1.3", (
        "the root of what is present declares 1.3; the package inside it "
        "declares 1.0 and does not get to answer")


#: Two packages representing this container, the newer one breaking a MUST
#: that only exists from 1.1. M3 reports the pair; the question is which
#: declaration the rest of the run is judged against.
TIED_CONTAINERS = MINIMAL_RDF.replace(
    '  <iirds:Package rdf:about="urn:test:package">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:title>Test package</iirds:title>\n'
    '  </iirds:Package>\n',
    '  <iirds:Package rdf:about="urn:test:aaa-old">\n'
    '    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n'
    '  </iirds:Package>\n'
    '  <iirds:Package rdf:about="urn:test:zzz-new">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:has-rendition rdf:resource="urn:test:r"/>\n'
    '  </iirds:Package>\n')

#: The same, with the older package declaring nothing at all.
UNDECLARED_BESIDE_OLD = TIED_CONTAINERS.replace(
    "  <iirds:Package rdf:about=\"urn:test:aaa-old\">\n"
    "    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n"
    "  </iirds:Package>\n",
    "  <iirds:Package rdf:about=\"urn:test:aaa-old\"/>\n").replace(
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
    "    <iirds:has-rendition", "    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n"
    "    <iirds:has-rendition")


def test_where_two_packages_claim_the_container_the_newer_one_answers(make_package):
    """M3 reports the pair, so the package does not pass either way -- what is
    at stake is whether the *other* defects in it are looked for. Picking by
    IRI let a package declaring 1.0 win an alphabetical tie-break and switch
    every 1.1+ rule off, so a plain §6.3 violation beside it went unreported.
    The same reasoning as two versions on one package, and as no version at
    all: nothing passes by silence."""
    report = runner.run(make_package(metadata=TIED_CONTAINERS), runner.ALL_KINDS)

    assert report.version == "1.3"
    assert "M3" in _ids(report), "two packages represent this container"
    assert "M8" in _ids(report), (
        "the package that renders is judged, rather than standing down "
        "because an alphabetically earlier one declared an older version")


def test_a_package_declaring_no_version_ranks_as_the_newest(make_package):
    """"No declaration" already means "judged against the newest" eight lines
    down in load_context, so it has to mean the same thing when the question
    is which package answers. Ranking it lowest would have made a declared
    1.0 beat it and switched rules off that a missing version leaves on."""
    report = runner.run(make_package(metadata=UNDECLARED_BESIDE_OLD), runner.ALL_KINDS)

    assert report.version is None
    assert report.effective_version == "1.3"
    assert "M8" in _ids(report)


def _two_containers(decoy_iri, decoy_version):
    """A decoy package beside one declaring 1.3 and the handover profile."""
    declared = ("    <iirds:iiRDSVersion>%s</iirds:iiRDSVersion>\n" % decoy_version
                if decoy_version else "")
    return MINIMAL_RDF.replace(
        '  <iirds:Package rdf:about="urn:test:package">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:title>Test package</iirds:title>\n'
        '  </iirds:Package>\n',
        '  <iirds:Package rdf:about="%s">\n%s  </iirds:Package>\n'
        '  <iirds:Package rdf:about="urn:test:real">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:formatRestriction>H</iirds:formatRestriction>\n'
        '  </iirds:Package>\n' % (decoy_iri, declared))


@pytest.mark.parametrize("decoy_iri,decoy_version", [
    ("urn:test:zzz", "banana"),
    ("urn:test:zzz", "9.9"),
    ("urn:test:aaa", "banana"),
    ("urn:test:aaa", None),
    ("urn:test:zzz", None),
], ids=["unreadable-after", "unpublished-after", "unreadable-before",
        "silent-before", "silent-after"])
def test_a_package_saying_less_does_not_speak_for_the_container(
        make_package, decoy_iri, decoy_version):
    """Ranking by the raw declaration handed the container to whichever
    package said the strangest thing: an unreadable version sorts after every
    number, so `banana` beat 1.3; an unpublished 9.9 did too. And a package
    declaring nothing ranks as the newest -- correctly -- which ties it with
    a real 1.3 package and hands the decision back to IRI order, the very
    tie-break this was meant to replace.

    The profile rides on the same choice, so all of it came out as
    `unrestricted` and seventeen handover MUSTs stood down. Rank by the
    version the run will actually be judged against, and prefer the package
    that says which profile it is: more is looked for, not less."""
    report = runner.run(make_package(metadata=_two_containers(decoy_iri, decoy_version)),
                        runner.ALL_KINDS)

    assert report.effective_version == "1.3"
    assert report.variant == "H", (
        "the package declaring a profile lost to one that declares less")
    assert "M3" in _ids(report), "two packages represent this container"


def test_a_profile_with_no_name_is_no_profile(make_package):
    """A profile is a name. A blank node names nothing, and its label is
    minted per parse -- so letting one through put a fresh identifier in the
    report every run and called it the package's profile. The value is still
    wrong and S5 still says so; what it is not is the answer to "which
    profile is this package"."""
    blank = MINIMAL_RDF.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        "    <iirds:formatRestriction><rdf:Description/></iirds:formatRestriction>\n")
    report = runner.run(make_package(metadata=blank), runner.ALL_KINDS)

    assert report.variant == "unrestricted", (
        "a node with no name was reported as the profile: %r" % report.variant)
    assert not report.variant.startswith("N"), report.variant
