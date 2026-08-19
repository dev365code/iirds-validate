"""Container rules — the ZIP itself."""
from __future__ import annotations

from iirds_validate import runner


def ids(report):
    return {f.rule.id for f in report.findings}


def test_clean_package_passes(make_package):
    report = runner.check(make_package())
    assert report.ok, [f.violation.message for f in report.findings]


def test_wrong_extension(make_package):
    assert "C3" in ids(runner.check(make_package(name="test.zip")))


def test_missing_mimetype(make_package):
    assert "C4" in ids(runner.check(make_package(mimetype=None)))


def test_mimetype_with_trailing_newline(make_package):
    assert "C5" in ids(runner.check(make_package(mimetype=b"application/iirds+zip\n")))


def test_mimetype_must_be_first_and_stored(make_package):
    assert "C6" in ids(runner.check(make_package(mimetype_first=False)))
    assert "C6" in ids(runner.check(make_package(mimetype_stored=False)))


def test_missing_metadata(make_package):
    assert "C8" in ids(runner.check(make_package(metadata=None)))


def test_content_in_root_is_rejected(make_package):
    """C11.1 owns the root; C12 owns META-INF. .xhtml counts as content even
    though the reference tool's pattern misses it — see container.py."""
    report = runner.check(make_package(content=("stray.xhtml",)))
    assert "C11.1" in ids(report)


def test_broken_xml_is_reported_not_crashed(make_package):
    report = runner.check(make_package(metadata="<rdf:RDF><unclosed>"))
    assert "C16.1" in ids(report)
    assert not report.ok


def test_not_a_zip(tmp_path):
    path = tmp_path / "broken.iirds"
    path.write_bytes(b"this is not a zip file")
    report = runner.check(path)
    assert "C1" in ids(report)
    assert not report.ok
