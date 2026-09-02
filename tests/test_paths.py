"""Pointing at a path and getting an answer.

Three shapes matter. The `.iirds` file is the delivery. The unpacked directory
is what the package is while you are building it, and checking it there is the
difference between finding a defect in the thing you just made and finding it
in the artefact. A directory of packages is what a build output looks like.
"""
from __future__ import annotations

import shutil
import zipfile

import pytest

from iirds_validate import runner
from iirds_validate.cli import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, main
from iirds_validate.package import DirectoryPackage, PackageError, discover, open_package


@pytest.fixture
def unpacked(make_package, tmp_path):
    """The same package, extracted — what a build has before it zips."""
    archive = make_package(name="src.iirds")
    out = tmp_path / "unpacked"
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(out)
    return archive, out


def test_an_unpacked_container_gives_the_same_answer(unpacked):
    """If the two disagreed, checking early would be worse than not checking."""
    archive, directory = unpacked
    from_archive = runner.run(archive, runner.ALL_KINDS)
    from_directory = runner.run(directory, runner.ALL_KINDS)

    archive_only = {"C1", "C3", "C6", "S7", "S8", "S10"}
    assert ({f.rule.id for f in from_directory.findings} - archive_only
            == {f.rule.id for f in from_archive.findings} - archive_only)


def test_the_rules_that_cannot_apply_say_so(unpacked):
    """A directory has no entry order, no compression mode and no encryption
    flag. Passing those requirements in silence would be a lie."""
    _archive, directory = unpacked
    report = runner.check(directory)
    assert any("unpacked container" in note for note in report.notes)
    assert "C6" not in {f.rule.id for f in report.findings}


def test_a_broken_unpacked_container_is_still_caught(unpacked):
    _archive, directory = unpacked
    (directory / "META-INF" / "metadata.rdf").write_text("<rdf:RDF><unclosed>")
    assert not runner.check(directory).ok


def test_a_directory_that_is_not_a_container_is_refused(tmp_path):
    (tmp_path / "random.txt").write_text("hello")
    with pytest.raises(PackageError):
        open_package(tmp_path)


# --- discovery -------------------------------------------------------------

def test_discover_finds_packages_under_a_directory(make_package, tmp_path):
    make_package(name="one.iirds")
    make_package(name="two.iirds")
    nested = tmp_path / "nested"
    nested.mkdir()
    shutil.copy(tmp_path / "one.iirds", nested / "three.iirds")

    found = discover(tmp_path)
    # Sorted by full path, so a nested directory sorts before its siblings.
    # Deterministic is what matters: the same directory always reports in the
    # same order, which is what makes two runs diffable.
    assert [p.name for p in found] == ["three.iirds", "one.iirds", "two.iirds"]


def test_discover_returns_an_unpacked_container_as_itself(unpacked):
    _archive, directory = unpacked
    assert discover(directory) == [directory]


def test_discover_finds_unpacked_containers_side_by_side(unpacked, tmp_path):
    _archive, directory = unpacked
    shutil.copytree(directory, tmp_path / "unpacked2")
    (tmp_path / "src.iirds").unlink()
    assert len(discover(tmp_path)) == 2


# --- the command line ------------------------------------------------------

def test_a_path_with_no_subcommand_means_all(make_package, capsys):
    """Typing the verb is friction, and "check it" is what anybody pointing at
    a package wants."""
    assert main([str(make_package())]) == EXIT_OK
    out = capsys.readouterr().out
    assert "PASS" in out


def test_pointing_at_a_directory_checks_everything_under_it(make_package, tmp_path, capsys):
    make_package(name="a.iirds")
    make_package(name="b.iirds", metadata="<rdf:RDF><unclosed>")
    assert main([str(tmp_path)]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "2 packages: 1 passed, 1 failed" in out


def test_a_directory_with_nothing_in_it_is_an_operator_error(tmp_path, capsys):
    """Silently reporting success for a path that holds no packages is how a
    build gate stops being one."""
    assert main([str(tmp_path)]) == EXIT_ERROR
    assert "no iiRDS package found" in capsys.readouterr().err


def test_directory_package_reports_its_files(unpacked):
    _archive, directory = unpacked
    package = DirectoryPackage(directory)
    assert "META-INF/metadata.rdf" in package.names
    assert package.is_archive is False
    assert package.read("mimetype") == b"application/iirds+zip"
