"""R3 — the package zipped one directory too high.

Every archive tool invites this: you select the package folder and compress it,
and the result holds `mypackage/mimetype` where a consumer looks for `mimetype`.
The package is entirely correct. Only its position is wrong.

Before this rule the report was four errors telling the author to add a
mimetype file, create a META-INF directory and add a metadata.rdf -- all of
which they had, one level down -- and nothing saying what happened.
"""
from __future__ import annotations

import io
import zipfile

from conftest import MINIMAL_RDF
from iirds_validate import runner


def archive(tmp_path, name, prefix="", extra=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo(prefix + "mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, b"application/iirds+zip")
        zf.writestr(prefix + "META-INF/metadata.rdf", MINIMAL_RDF)
        zf.writestr(prefix + "content/topic1.xhtml", "<html/>")
        for entry, data in extra:
            zf.writestr(entry, data)
    path = tmp_path / name
    path.write_bytes(buf.getvalue())
    return path


def ids(path):
    return {f.rule.id for f in runner.run(path, runner.ALL_KINDS).findings}


def test_a_package_zipped_from_its_parent_is_named_as_such(tmp_path):
    assert "R3" in ids(archive(tmp_path, "wrapped.iirds", prefix="mypackage/"))


def test_the_finding_says_where_the_container_actually_is(tmp_path):
    """The author has to be able to see that their package is fine and only
    misplaced, or they will start adding files they already have."""
    report = runner.run(archive(tmp_path, "w2.iirds", prefix="delivery-2026/"),
                        runner.ALL_KINDS)
    finding = next(f for f in report.findings if f.rule.id == "R3")
    assert finding.violation.subject == "delivery-2026/"
    assert "delivery-2026/META-INF/metadata.rdf" in finding.violation.detail
    assert "follow from this one" in finding.violation.detail


def test_a_correctly_rooted_package_does_not_trip_it(tmp_path):
    assert "R3" not in ids(archive(tmp_path, "fine.iirds"))


def test_a_folder_that_holds_no_container_is_not_this_defect(tmp_path):
    """An archive of ordinary files nested in a directory is broken in some
    other way, and saying "your container is one level down" about it would be
    a confident wrong answer rather than no answer."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("docs/readme.txt", "nothing to do with iiRDS")
        zf.writestr("docs/manual.pdf", b"%PDF-1.4")
    path = tmp_path / "notapackage.iirds"
    path.write_bytes(buf.getvalue())
    assert "R3" not in ids(path)


def test_two_top_level_directories_are_a_different_mess(tmp_path):
    """Two containers in one archive, or one container and something else.
    Either way "it sits inside a directory" is not the diagnosis."""
    extra = (("other/mimetype", b"application/iirds+zip"),)
    assert "R3" not in ids(archive(tmp_path, "two.iirds", prefix="one/", extra=extra))
