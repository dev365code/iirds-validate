"""Container rules that no test had ever made fire.

Each needs an archive shaped a particular way, which is why they were skipped:
`conftest`'s builder produces well-formed packages, and these want malformed
ones. That is not a reason to leave a rule unobserved -- C15 and S8 both show
what an unexercised container rule can be doing instead of its job.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import runner
from iirds_validate.rules.container import MAX_NAME, MAX_PATH

BASE = (("mimetype", b"application/iirds+zip"),
        ("META-INF/metadata.rdf", MINIMAL_RDF),
        ("content/topic1.xhtml", "<html/>"))


def archive(tmp_path, name, entries, mimetype_stored=True):
    """Written entry by entry, because every rule here is about the ZIP itself
    rather than about anything a graph could express."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for entry, data in entries:
            info = zipfile.ZipInfo(entry)
            if entry == "mimetype" and mimetype_stored:
                info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, data)
    path = tmp_path / name
    path.write_bytes(buf.getvalue())
    return path


def ids(path, version=None):
    return {f.rule.id for f in runner.run(path, runner.ALL_KINDS, version=version).findings}


def test_c2_an_archive_with_no_entries(tmp_path):
    assert "C2" in ids(archive(tmp_path, "empty.iirds", ()))


def test_c10_a_name_using_a_forbidden_character(tmp_path):
    """The characters are unusable or reserved on at least one platform a
    package has to survive, so the archive would not extract intact."""
    found = ids(archive(tmp_path, "chars.iirds", (*BASE, ("content/a<b>.xhtml", "<html/>"))))
    assert "C10" in found


def test_c13_a_path_longer_than_the_limit(tmp_path):
    deep = "content/" + "/".join("d" * 20 for _ in range(MAX_PATH // 20)) + "/t.xhtml"
    assert len(deep) > MAX_PATH
    assert "C13" in ids(archive(tmp_path, "deep.iirds", (*BASE, (deep, "<html/>"))))


def test_c14_a_file_name_longer_than_the_limit(tmp_path):
    long_name = "content/%s.xhtml" % ("n" * (MAX_NAME + 10))
    assert "C14" in ids(archive(tmp_path, "long.iirds", (*BASE, (long_name, "<html/>"))))


def test_c15_the_same_path_stored_twice(tmp_path):
    """A ZIP can hold one path more than once; which copy a consumer gets
    depends on the unzip implementation."""
    twice = (*BASE, ("content/topic1.xhtml", "<html>second</html>"))
    assert "C15" in ids(archive(tmp_path, "dupe.iirds", twice))


def test_l12_two_paths_differing_only_in_case(tmp_path):
    """The collision C15 does not catch, and the one that actually happens.

    Both are valid, distinct entries under the specification's "file names are
    case-sensitive", and the same file on Windows and macOS. The archive
    validated; the directory that came out of it is missing a file.
    """
    colliding = (*BASE, ("content/Fig1.png", b"a"), ("content/fig1.png", b"b"))
    found = ids(archive(tmp_path, "case.iirds", colliding))
    assert "L12" in found
    assert "C15" not in found, "these are genuinely distinct entries, so C15 is right to pass"


def test_l12_is_quiet_when_names_differ_by_more_than_case(tmp_path):
    assert "L12" not in ids(archive(tmp_path, "fine.iirds",
                                    (*BASE, ("content/fig1.png", b"a"),
                                     ("content/fig2.png", b"b"))))


def test_c11_1h_a_stray_file_in_the_root_of_a_handover_package(tmp_path):
    """iiRDS/H allows mimetype, META-INF and index.html in the root, and
    nothing else: a handover package is meant to be openable by a person with
    a browser, and a cluttered root defeats that.
    """
    metadata = MINIMAL_RDF.replace(
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>"
        "<iirds:formatRestriction>H</iirds:formatRestriction>")
    entries = (("mimetype", b"application/iirds+zip"),
               ("META-INF/metadata.rdf", metadata),
               ("index.html", "<html/>"),
               ("datasheet.pdf", b"%PDF-1.4 stray"),
               ("content/topic1.xhtml", "<html/>"))
    assert "C11.1H" in ids(archive(tmp_path, "handover.iirds", entries))


def test_c1_a_file_that_is_not_a_zip_at_all(tmp_path):
    """C1 and S1 are different answers and the runner used to give C1 to both,
    which left S1 unable to fire while its docstring said this was where it
    came from."""
    broken = tmp_path / "not-a-zip.iirds"
    broken.write_bytes(b"this is not a ZIP archive at all")
    report = runner.run(broken, runner.ALL_KINDS)
    assert "C1" in {f.rule.id for f in report.findings}, \
        "something was read; it is simply not a usable ZIP"
    assert not report.ok


def test_s1_a_path_nothing_can_be_read_from(tmp_path):
    """Absent, or not permitted: a mistake in the command rather than a defect
    in a package somebody sent."""
    report = runner.run(tmp_path / "absent.iirds", runner.ALL_KINDS)
    assert "S1" in {f.rule.id for f in report.findings}
    assert "C1" not in {f.rule.id for f in report.findings}


@pytest.mark.parametrize("rule_id", ["C1", "C2", "C10", "C13", "C14", "C15", "L12", "S1"])
def test_none_of_these_fire_on_a_well_formed_package(rule_id, tmp_path):
    """The half that says each is looking at the right thing."""
    assert rule_id not in ids(archive(tmp_path, "good.iirds", BASE))
