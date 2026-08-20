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
import zipfile

import pytest

from iirds_validate import runner
from iirds_validate.cli import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, main
from iirds_validate.model import MIMETYPE_VALUE
from iirds_validate.packer import PackError, pack

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
