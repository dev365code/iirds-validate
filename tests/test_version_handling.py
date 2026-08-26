"""Version detection must never turn into a silent pass."""
from __future__ import annotations

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


def test_a_package_declaring_two_versions_is_judged_against_the_lower(make_package):
    """M4 reports the pair, so no choice makes this package pass. The lower
    version is the one that cannot hold it to rules it may never have been
    subject to."""
    report = runner.run(make_package(metadata=TWO_VERSIONS), runner.ALL_KINDS)

    assert report.version == "1.0"
    assert report.effective_version == "1.0"
    assert "M4" in _ids(report)


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


def test_detection_needs_no_ontology_because_package_has_no_subclass():
    """The premise the design rests on. Detection runs before the ontology
    is chosen -- it cannot consult one -- so it closes over the subclasses
    the *package* declares and nothing else. That is complete only while the
    standard itself declares no subclass of iirds:Package. If it ever does,
    this turns red and the design has to be revisited."""
    from iirds_validate import ontology as ontology_mod
    from iirds_validate import terms as T
    from iirds_validate.model import VERSIONS

    for version in VERSIONS:
        loaded = ontology_mod.load(version)
        assert set(loaded.subclasses_of(T.Package)) == {T.Package}, (
            "iiRDS %s declares a subclass of iirds:Package; version detection "
            "runs before an ontology is loaded and would not see it" % version)
