"""Writing a container — the half of the archive requirements a directory
cannot answer.

This is the only place the project writes rather than reads, and the trust
profile is different: a validator that is wrong reports a wrong verdict, and a
writer that is wrong produces a wrong artefact that then gets delivered. So the
central test is not "does it write a file" but "does what it writes satisfy the
rules this project would fail somebody else for breaking".
"""
from __future__ import annotations

import hashlib
import re
import zipfile

import pytest
from iirds import PackError, pack

from iirds_validate import runner
from iirds_validate.cli import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, main
from iirds_validate.model import MIMETYPE_VALUE

ARCHIVE_RULES = {"C1", "C3", "C4", "C5", "C6", "S7", "S8"}


@pytest.fixture
def unpacked(make_package, tmp_path):
    archive = make_package(name="src.iirds")
    out = tmp_path / "unpacked"
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(out)
    return out


def test_what_it_writes_satisfies_the_rules_it_would_fail_others_for(unpacked, tmp_path):
    result = pack(unpacked, tmp_path / "out.iirds")
    report = runner.run(result, runner.ALL_KINDS)
    assert not ({f.rule.id for f in report.findings} & ARCHIVE_RULES)
    assert report.ok, [f.violation.message for f in report.findings]


def test_mimetype_is_the_first_entry_and_stored(unpacked, tmp_path):
    """The requirement every other tool gets wrong. `zip` needs two invocations
    with the right flags, most graphical tools cannot express it, and
    shutil.make_archive cannot either."""
    result = pack(unpacked, tmp_path / "out.iirds")
    with zipfile.ZipFile(result) as archive:
        first = archive.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == MIMETYPE_VALUE.encode("ascii")


def test_packing_twice_gives_the_same_bytes(unpacked, tmp_path):
    """So "this archive came from that directory" is checkable with sha256
    rather than taken on trust."""
    a = pack(unpacked, tmp_path / "a.iirds")
    b = pack(unpacked, tmp_path / "b.iirds")
    assert hashlib.sha256(a.read_bytes()).hexdigest() == \
           hashlib.sha256(b.read_bytes()).hexdigest()


def test_a_missing_mimetype_is_written_rather_than_refused(unpacked, tmp_path):
    (unpacked / "mimetype").unlink()
    result = pack(unpacked, tmp_path / "out.iirds")
    assert zipfile.ZipFile(result).read("mimetype") == MIMETYPE_VALUE.encode("ascii")


def test_a_wrong_mimetype_is_refused_rather_than_overwritten(unpacked, tmp_path):
    """Silently correcting it would hide a defect in whatever produced the
    directory, which will produce it again tomorrow."""
    (unpacked / "mimetype").write_text("application/zip")
    with pytest.raises(PackError, match="does not contain"):
        pack(unpacked, tmp_path / "out.iirds")


def test_already_compressed_files_are_stored(unpacked, tmp_path):
    (unpacked / "content" / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 400)
    result = pack(unpacked, tmp_path / "out.iirds")
    with zipfile.ZipFile(result) as archive:
        png = archive.getinfo("content/figure.png")
        assert png.compress_type == zipfile.ZIP_STORED


def test_a_directory_that_is_not_a_container_is_refused(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    with pytest.raises(PackError, match="no META-INF"):
        pack(tmp_path, tmp_path / "out.iirds")


def test_an_existing_output_is_not_clobbered(unpacked, tmp_path):
    target = tmp_path / "out.iirds"
    pack(unpacked, target)
    with pytest.raises(PackError, match="exists"):
        pack(unpacked, target)
    pack(unpacked, target, overwrite=True)


def test_the_command_packs_then_validates_what_it_wrote(unpacked, tmp_path, capsys):
    """Validating the archive rather than the directory is the point: the five
    requirements a directory cannot answer are now answered, against the file
    that will actually be delivered."""
    code = main(["pack", str(unpacked), "-o", str(tmp_path / "out.iirds")])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "wrote" in out and "PASS" in out


def test_a_defect_in_the_directory_survives_packing(unpacked, tmp_path):
    """Packing must not launder a broken package into a clean verdict."""
    (unpacked / "META-INF" / "metadata.rdf").write_text("<rdf:RDF><unclosed>")
    assert main(["pack", str(unpacked), "-o", str(tmp_path / "out.iirds"), "-q"]) \
        == EXIT_FINDINGS


def test_packing_something_unpackable_is_an_operator_error(tmp_path, capsys):
    assert main(["pack", str(tmp_path / "nope"), "-q"]) == EXIT_ERROR
    assert "iirds-validate:" in capsys.readouterr().err


def test_the_exists_refusal_speaks_cli_on_the_cli(unpacked, tmp_path, capsys):
    """The library half of pack() speaks API ("overwrite=True"); a person at
    a terminal needs the flag spelling. The CLI owns its own wording, so the
    message is translated at the boundary rather than leaking either dialect
    into the other layer."""
    target = tmp_path / "out.iirds"
    pack(unpacked, target)
    code = main(["pack", str(unpacked), "-o", str(target)])
    assert code == EXIT_ERROR
    err = capsys.readouterr().err
    assert "--overwrite" in err
    assert "overwrite=True" not in err


def test_the_pyz_bundles_what_pyproject_declares():
    """The .pyz build script reads its bundle list from pyproject.toml, so
    the two cannot drift; this pins what that list currently is. A third
    dependency flows into the archive automatically -- and changes this
    test, so it happens on purpose."""
    import build_zipapp
    names = sorted(spec.split(">")[0].split("=")[0].split("<")[0]
                   for spec in build_zipapp.dependencies())
    assert names == ["iirds", "rdflib"]


# ---------------------------------------------------------------------------
# What the offline artefact carries besides code
#
# The .pyz is the copy that goes onto a locked-down machine on a USB stick,
# and it is the one copy with no index behind it to look anything up in. The
# wheel and the sdist carry this project's licence because pyproject declares
# `license-files`; the .pyz is built by a different path and declared nothing.
# ---------------------------------------------------------------------------

def declared_licence_files():
    """What `pyproject.toml` says ships beside the code."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text("utf-8")
    block = re.search(r"^license-files = \[(.*?)\]", text, re.M | re.S)
    assert block, "pyproject.toml no longer declares license-files"
    return re.findall(r'"([^"]+)"', block.group(1))


def test_the_pyz_carries_the_same_licence_files_the_wheel_does():
    """Apache-2.0 asks that a copy of the licence and the NOTICE travel with
    the work. Every dependency's terms were kept here deliberately -- the
    dist-info is preserved for exactly that reason -- and this project's own
    were the ones left behind."""
    import build_zipapp

    assert sorted(build_zipapp.REDISTRIBUTED) == sorted(declared_licence_files()), (
        "the .pyz and the wheel would carry different licence files: %s vs %s"
        % (sorted(build_zipapp.REDISTRIBUTED), sorted(declared_licence_files())))


def test_staging_puts_them_where_someone_opening_the_archive_finds_them(tmp_path):
    import build_zipapp

    build_zipapp.copy_licences(tmp_path)
    for name in build_zipapp.REDISTRIBUTED:
        carried = tmp_path / name
        assert carried.is_file(), "%s is not in the archive" % name
        assert carried.read_text("utf-8").strip(), "%s is in the archive and empty" % name


def test_the_licence_declaration_cannot_be_read_as_nothing():
    """The two checks above read `license-files` with the same expression, so
    an expression that stops matching makes them agree about an empty list and
    pass with an archive carrying no licence at all. That is the shape of
    green this project keeps finding, so the parse refuses to answer nothing
    -- here demonstrated on setuptools' own documented glob syntax, which the
    expression does not parse."""
    import build_zipapp

    globbed = 'license-files = ["LICEN[CS]E*", "NOTICE"]'
    with pytest.raises(AssertionError, match="license-files"):
        _read_licence_files_from(build_zipapp, globbed)


def _read_licence_files_from(build_zipapp, text):
    """Run the declaration reader against `text` instead of pyproject.toml."""
    from pathlib import Path
    from unittest import mock

    original = Path.read_text
    with mock.patch.object(Path, "read_text",
                           lambda self, *a, **k: text if self.name == "pyproject.toml"
                           else original(self, *a, **k)):
        return build_zipapp._licence_files()


def test_every_distribution_the_archive_bundles_has_a_row_in_third_party():
    """The table opens "everything bundled here", and pip brings a
    dependency's dependencies too: the archive carries four distributions,
    not the two this project declares. Asking the declared list would only
    confirm the names somebody had already thought of -- which is what the
    first version of this test did, while `isodate` and `pyparsing` sat in
    the archive with no row anywhere."""
    import build_zipapp

    assert build_zipapp.unattributed(BUNDLED) == []


#: What `pip install --target` actually leaves beside the code. Pinned here
#: because a test cannot run pip; `stage()` checks the real list at build time
#: and refuses to build when a row is missing.
BUNDLED = ("iirds", "isodate", "pyparsing", "rdflib")


def test_a_bundled_distribution_nobody_wrote_a_row_for_is_named():
    import build_zipapp

    assert build_zipapp.unattributed(BUNDLED + ("smuggled",)) == ["smuggled"]
