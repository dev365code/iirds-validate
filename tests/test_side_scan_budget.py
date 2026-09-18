"""The ceiling on the search for a package's own ontology under META-INF.

Two properties, and the shipped code has neither. The budget is tested at the
head of an iteration and the read that follows is bounded by the per-entry
limit rather than by what is left of it, so one file goes over by up to that
limit -- measured, a 13,198-byte archive carrying one 12,583,089-byte entry
against an 8 MiB ceiling drew a peak of 41,774,599 bytes. And because the cut
is recorded only when the *next* iteration starts, a scan whose last file is
the large one stops with nothing said: S12 exists precisely so that a scan
which gave up and a scan which finished empty do not look alike, and in that
order they do.
"""
from __future__ import annotations

import zipfile

from conftest import MIMETYPE, MINIMAL_RDF
from iirds_validate import package as package_module
from iirds_validate import runner
from iirds_validate.rules import requirements as requirements_module


def _with_side_files(tmp_path, entries, name="side.iirds"):
    """A container carrying `entries` (name, size) under META-INF."""
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        first = zipfile.ZipInfo("mimetype")
        first.compress_type = zipfile.ZIP_STORED
        archive.writestr(first, MIMETYPE)
        archive.writestr("META-INF/metadata.rdf", MINIMAL_RDF)
        archive.writestr("content/topic1.xhtml", b"<html/>")
        for entry, size in entries:
            body = ('<?xml version="1.0"?><rdf:RDF '
                    'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
                    'xmlns:x="urn:x:"><rdf:Description rdf:about="urn:s">'
                    '<x:p>%s</x:p></rdf:Description></rdf:RDF>' % ("a" * size)).encode()
            archive.writestr("META-INF/" + entry, body)
    return path


def _read(tmp_path, entries, limit, monkeypatch):
    # The rule module imports the name by value, so the ceiling it reads is
    # its own. Patching the package's copy changes nothing it sees.
    monkeypatch.setattr(requirements_module, "MAX_SIDE_BYTES", limit)
    package = _with_side_files(tmp_path, entries)
    report = runner.run(package, runner.ALL_KINDS)
    return report


def test_one_side_file_cannot_take_the_scan_far_past_its_ceiling(tmp_path, monkeypatch):
    """The ceiling is on what the scan reads, and a read decides its own size.

    The check sits before the read and the read is bounded by the per-entry
    limit, so the first file over the ceiling is read whole however large it
    is. What the ceiling has to mean is the same thing the content budget
    means after 0.6.2: one read may cross it, bounded by the per-file limit,
    and none after.
    """
    read = []
    real = package_module.Package.read_bounded

    def counting(self, name, limit):
        raw, over = real(self, name, limit)
        if name.startswith("META-INF/") and name != "META-INF/metadata.rdf":
            read.append(len(raw))
        return raw, over

    monkeypatch.setattr(package_module.Package, "read_bounded", counting)
    limit = 64 * 1024
    _read(tmp_path, [("vendor.rdf", 8 * limit)], limit, monkeypatch)
    assert read, "no side file was read; the test is measuring nothing"
    assert sum(read) <= limit * 2, (
        "the scan read %d bytes against a ceiling of %d" % (sum(read), limit))


def test_a_scan_cut_short_by_its_last_file_still_says_so(tmp_path, monkeypatch):
    """S12 is the difference between giving up and finding nothing.

    The cut is recorded at the head of the next iteration, so when the file
    that crosses the ceiling is the last one the loop ends and nothing is
    said. Reproduced by the plan review with two files and then one.
    """
    limit = 64 * 1024
    report = _read(tmp_path, [("vendor.rdf", 8 * limit)], limit, monkeypatch)
    assert any(f.rule.id == "S12" for f in report.findings), (
        "the scan stopped at its ceiling on the last file and said nothing: %s"
        % sorted({f.rule.id for f in report.findings}))


def test_a_scan_that_fits_says_nothing(tmp_path, monkeypatch):
    """The control: a package inside the ceiling must not draw S12."""
    limit = 1024 * 1024
    report = _read(tmp_path, [("vendor.rdf", 1024)], limit, monkeypatch)
    assert not any(f.rule.id == "S12" for f in report.findings)


#: An extension that attaches to iiRDS -- one class of the package's own said
#: to be a kind of `iirds:Topic` -- padded to whatever length is asked for.
#: This is the shape R18 exists to report, and the shape a sender who wants it
#: unreported has an interest in making large.
def _attaching(pad):
    return ('<?xml version="1.0"?><rdf:RDF '
            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            'xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">'
            '<rdfs:Class rdf:about="urn:mine:Special">'
            '<rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Topic"/>'
            '</rdfs:Class>'
            '<rdf:Description rdf:about="urn:mine:pad"><rdfs:comment>%s'
            '</rdfs:comment></rdf:Description></rdf:RDF>' % ("a" * pad)).encode()


def _with_bodies(tmp_path, entries, name):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        first = zipfile.ZipInfo("mimetype")
        first.compress_type = zipfile.ZIP_STORED
        archive.writestr(first, MIMETYPE)
        archive.writestr("META-INF/metadata.rdf", MINIMAL_RDF)
        archive.writestr("content/topic1.xhtml", b"<html/>")
        for entry, body in entries:
            archive.writestr("META-INF/" + entry, body)
    return path


def _run(tmp_path, entries, limit, monkeypatch, name="attach.iirds"):
    monkeypatch.setattr(requirements_module, "MAX_SIDE_BYTES", limit)
    return runner.run(_with_bodies(tmp_path, entries, name), runner.ALL_KINDS)


def test_a_side_file_that_attaches_is_reported_when_it_fits(tmp_path, monkeypatch):
    """The control, and the reason the next test is not theatre.

    If this fixture did not actually attach to iiRDS, "R18 is silent" below
    would be true of any file at all and would be measuring nothing.
    """
    report = _run(tmp_path, [("vendor.rdf", _attaching(16))], 64 * 1024, monkeypatch,
                  "fits.iirds")
    assert "META-INF/vendor.rdf" in {f.violation.subject for f in report.findings
                                     if f.rule.id == "R18"}


def test_a_side_file_too_large_to_read_is_reported_as_unexamined(tmp_path, monkeypatch):
    """Past the ceiling R18 cannot answer, and the report has to say so.

    The file is never parsed, so the question R18 asks of it -- does this
    attach anything to iiRDS -- has no answer, and the honest report is that
    nobody looked. What must not happen is the two silences being the same
    one: a package whose extension is merely large would otherwise read
    exactly like a package that has none.
    """
    limit = 64 * 1024
    report = _run(tmp_path, [("vendor.rdf", _attaching(8 * limit))], limit, monkeypatch,
                  "toobig.iirds")
    ids = {f.rule.id for f in report.findings}
    assert "R18" not in ids, "the file was not read, so R18 cannot have an opinion"
    cut = [f for f in report.findings if f.rule.id == "S12"]
    assert cut, "the file that stopped the scan was passed over in silence: %s" % sorted(ids)
    assert cut[0].violation.subject == "META-INF/vendor.rdf", cut[0].violation.subject
    text = "%s %s" % (cut[0].violation.message, cut[0].violation.detail or "")
    assert "unanswered" in text, text
