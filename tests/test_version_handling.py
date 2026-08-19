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
