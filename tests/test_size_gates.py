"""The size gates, observed firing — in both package forms.

MAX_METADATA_BYTES and MAX_CONTENT_BYTES had no test anywhere in this
suite: neither gate had ever been seen to fire, and a gate that has never
caught anything is a gate nobody has tested. Observing them caught a real
hole: `DirectoryPackage.info()` answered None, so both gates were silently
disabled for the unpacked form — the same oversized document an archive
refuses was read and parsed whole when checked before zipping, which is
precisely when people check big work-in-progress packages.
"""
from __future__ import annotations

from pathlib import Path

from conftest import MIMETYPE, MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.context import MAX_METADATA_BYTES
from iirds_validate.rules.content import MAX_CONTENT_BYTES

OVER_METADATA = MINIMAL_RDF.encode("utf-8") + b" " * MAX_METADATA_BYTES
OVER_CONTENT = (b'<?xml version="1.0" encoding="utf-8"?>'
                b'<html xmlns="http://www.w3.org/1999/xhtml"><head>'
                b"<title>t</title></head><body><p>big</p></body></html>"
                + b" " * MAX_CONTENT_BYTES)


def _unpacked(tmp_path, metadata: bytes, content: bytes) -> Path:
    root = tmp_path / "unpacked"
    (root / "META-INF").mkdir(parents=True)
    (root / "content").mkdir()
    (root / "mimetype").write_bytes(MIMETYPE)
    (root / "META-INF" / "metadata.rdf").write_bytes(metadata)
    (root / "content" / "topic1.xhtml").write_bytes(content)
    return root


def _findings(path):
    return runner.check(path).findings


def test_oversized_metadata_is_refused_in_an_archive(tmp_path):
    package = build_package(tmp_path, metadata=OVER_METADATA)
    hits = [f for f in _findings(package) if f.rule.id == "C16.1"]
    assert hits and "byte limit" in hits[0].violation.detail


def test_oversized_metadata_is_refused_in_a_directory_too(tmp_path):
    """Same document, unpacked form, same refusal — or the advertised
    check-before-you-zip workflow is the one place the gate is off."""
    root = _unpacked(tmp_path, OVER_METADATA, b"<html/>")
    hits = [f for f in _findings(root) if f.rule.id == "C16.1"]
    assert hits and "byte limit" in hits[0].violation.detail


def test_oversized_content_is_refused_in_an_archive(tmp_path):
    package = build_package(tmp_path, content=(),
                            extra=(("content/topic1.xhtml", OVER_CONTENT),))
    hits = [f for f in _findings(package)
            if f.rule.id == "B1" and "refused" in f.violation.message]
    assert hits and "byte limit" in hits[0].violation.detail


def test_oversized_content_is_refused_in_a_directory_too(tmp_path):
    root = _unpacked(tmp_path, MINIMAL_RDF.encode("utf-8"), OVER_CONTENT)
    hits = [f for f in _findings(root)
            if f.rule.id == "B1" and "refused" in f.violation.message]
    assert hits and "byte limit" in hits[0].violation.detail
