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


def test_the_published_versions_sort_as_numbers_under_a_plain_sort():
    """Detection picks between several declared versions with sorted(), and
    this pins the assumption that lets it: over the versions the standard
    has actually published, text order and number order agree. A 1.10 would
    break that -- text puts it between 1.1 and 1.2 -- and this turns red on
    the day one appears rather than the day a package declares two."""
    from conftest import version_tuple
    from iirds_validate.model import VERSIONS

    assert sorted(VERSIONS) == sorted(VERSIONS, key=version_tuple), (
        "iiRDS %s no longer sorts the same as text and as numbers" % (VERSIONS,))


def test_a_child_whose_parent_is_absent_still_declares_itself(make_package):
    """The nesting filter leaves nothing here. Falling back to every package
    keeps the declaration that is three lines away; refusing to would
    validate a 1.0 document against 1.3 in silence."""
    report = runner.run(make_package(metadata=ORPHAN_CHILD), runner.ALL_KINDS)

    assert (report.version, report.variant) == ("1.0", "A")


def test_a_package_that_is_part_of_itself_still_declares_itself(make_package):
    """Why the filter needs no special case for the self-loop: the fallback
    already answers it. The corpus carries exactly one such package."""
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
    """The nesting filter closes the ordinary contamination and the fallback
    behind it re-opened this one: with no container package present, every
    package went back in the pool and the grandchild won on an alphabetical
    tie-break that means nothing. Its handover profile then switched on
    seventeen MUSTs against a package that never claimed one -- the same
    defect the filter exists to prevent, one level further down."""
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
