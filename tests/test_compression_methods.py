"""Entries this tool will not decompress, and why no ceiling covers them.

Every limit here -- 64 MiB per file, the run's content budget, the slice the
damage check asks for -- bounds what a read hands *back*. None of them bounds
what the read allocates, and for two of the methods the ZIP format allows,
those are not the same number.

CPython's `zipfile.ZipExtFile._read1` passes a length to the decompressor for
DEFLATE and for nothing else; every other method is decompressed whole and the
result sliced afterwards, so the slicing happens after the allocation. Measured
on 3.9.6, one entry declaring 64 MiB, one `read(65536)`:

    STORED     archive 67,108,970   peak         79,898
    DEFLATED   archive     65,339   peak        238,399
    BZIP2      archive        189   peak     71,530,984
    LZMA       archive      9,657   peak     79,972,634

and through the whole tool at its default 512 MiB budget, a 1,292-byte package
declaring two 64 MiB bzip2 renditions peaked at 269,480,527 bytes traced and
724,271,104 resident. Lowering the budget does not help: the overshoot is in a
single read.

So these entries are refused rather than read. Decoding them here would mean
driving the decompressors directly and reimplementing zip's framing around
them, which is a larger risk than the one it removes, and refusing is the only
bound that can be shown to hold. The refusal is a finding: the run says the
entry was not read, not parsed, and not checked for damage either -- answering
that last one would mean decompressing it.
"""
from __future__ import annotations

import tracemalloc
import zipfile

import pytest

from conftest import MIMETYPE, MINIMAL_RDF
from iirds_validate import runner

try:  # the refusal this unit adds; absent until it exists
    from iirds import UnreadableMethod as Refused
except ImportError:  # pragma: no cover - only before the rule lands
    class Refused(Exception):
        pass

#: Declared big enough that reading one entry is unmistakable in the numbers,
#: and small enough that a machine running this suite survives the failure.
DECLARED = 16 * 1024 * 1024

#: What a run may allocate with its ceilings set to 256 KiB. Far above what
#: parsing and the graph cost on a package this small, far below one entry.
SANE = 8 * 1024 * 1024

#: Room around a single bounded read for the machinery that performs it.
SLACK = 1024 * 1024

METHODS = {"stored": zipfile.ZIP_STORED, "deflate": zipfile.ZIP_DEFLATED,
           "bzip2": zipfile.ZIP_BZIP2, "lzma": zipfile.ZIP_LZMA}


def _package(tmp_path, method, name="m.iirds"):
    """A container whose one rendition uses `method`."""
    topic = """  <iirds:Topic rdf:about="urn:test:t1">
    <iirds:title>T</iirds:title>
    <iirds:has-rendition><iirds:Rendition>
      <iirds:format>application/xhtml+xml</iirds:format>
      <iirds:source>content/r.xhtml</iirds:source>
    </iirds:Rendition></iirds:has-rendition>
  </iirds:Topic>
"""
    body = ("<html xmlns='http://www.w3.org/1999/xhtml'><body><p>%s</p></body></html>"
            % ("a" * DECLARED)).encode()
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        first = zipfile.ZipInfo("mimetype")
        first.compress_type = zipfile.ZIP_STORED
        archive.writestr(first, MIMETYPE)
        archive.writestr("META-INF/metadata.rdf",
                         MINIMAL_RDF.replace("</rdf:RDF>", topic + "</rdf:RDF>"))
        archive.writestr("content/topic1.xhtml", b"<html/>")
        entry = zipfile.ZipInfo("content/r.xhtml")
        entry.compress_type = METHODS[method]
        archive.writestr(entry, body)
    return path


@pytest.mark.parametrize("method", sorted(METHODS))
def test_one_bounded_read_allocates_about_what_it_was_asked_for(tmp_path, method):
    """`read_bounded(name, limit)` is the contract every ceiling is built on.

    It is not a claim about the file being small -- a deflate entry declaring
    sixteen megabytes is read, up to the per-file limit, and costs that. It is
    a claim about the *limit* meaning something: ask for 64 KiB and the read
    costs about 64 KiB, whatever the entry declares. That is what holds for
    stored and deflate and what does not hold for the other two, and it is why
    lowering a ceiling cannot fix them.
    """
    from iirds_validate.package import open_package

    package = _package(tmp_path, method)
    limit = 64 * 1024
    readable = method in ("stored", "deflate")
    with open_package(package) as opened:
        tracemalloc.start()
        try:
            opened.read_bounded("content/r.xhtml", limit)
        except Refused:
            tracemalloc.stop()
            assert not readable, "%s is one of the two that are read, and was refused" % method
            return
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    assert readable, ("%s was read; a bounded read cannot be made of it" % method)
    assert peak <= limit + SLACK, (
        "a %d byte read of a %s entry declaring %d bytes allocated %d"
        % (limit, method, DECLARED, peak))


@pytest.mark.parametrize("method", sorted(METHODS))
def test_a_whole_run_stays_inside_the_ceilings_it_states(tmp_path, monkeypatch, method):
    """The same thing where a reader meets it: ceilings lowered so that every
    method has the same room, and only the methods whose reads obey a limit
    stay inside it."""
    from iirds_validate import package as package_module
    from iirds_validate.rules import content as content_module

    monkeypatch.setattr(package_module, "MAX_CONTENT_TOTAL_BYTES", 256 * 1024)
    monkeypatch.setattr(content_module, "MAX_CONTENT_BYTES", 256 * 1024)

    package = _package(tmp_path, method)
    tracemalloc.start()
    try:
        runner.run(package, runner.ALL_KINDS)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak <= SANE, (
        "a %d byte package declaring %d bytes as %s made the run allocate %d, "
        "against ceilings of 256 KiB" % (package.stat().st_size, DECLARED, method, peak))
@pytest.mark.parametrize("method", ["bzip2", "lzma"])
def test_an_entry_in_a_method_this_tool_will_not_read_is_reported(tmp_path, method):
    """Refused, and said so. A package that is quietly not examined passes."""
    report = runner.run(_package(tmp_path, method), runner.ALL_KINDS)
    said = [f for f in report.findings if f.rule.id == "S14"]
    assert said, ("nothing reported the entry this run would not read; the "
                  "findings were %s" % sorted({f.rule.id for f in report.findings}))
    assert any(f.violation.subject == "content/r.xhtml" for f in said), (
        "the finding names %s, not the entry" % [f.violation.subject for f in said])


@pytest.mark.parametrize("method", ["bzip2", "lzma"])
def test_a_refusal_that_has_a_rule_of_its_own_is_not_named_twice(tmp_path, method):
    """S16 names a file the run listed as content and never parsed, and stops
    where another rule already says why at the same severity: the run's total
    is S9's, and a method no bounded read can be made of is this one. Two
    errors for one file would make the report read as two faults, and the
    second would carry no remedy the first does not."""
    report = runner.run(_package(tmp_path, method), runner.ALL_KINDS)
    assert [f.rule.id for f in report.findings if f.rule.id == "S14"], \
        "the cause rule did not fire, so this proves nothing"
    twice = [f for f in report.findings
             if f.rule.id == "S16" and f.violation.subject == "content/r.xhtml"]
    assert not twice, "S14 names this entry already: %s" % [f.violation.detail for f in twice]


@pytest.mark.parametrize("method", sorted(METHODS))
def test_the_two_methods_this_tool_reads_are_read(tmp_path, method):
    """The refusal is two methods wide and no wider.

    Without this, refusing everything passes the test above, and a package
    built by any ordinary tool stops being judged at all.
    """
    report = runner.run(_package(tmp_path, method), runner.ALL_KINDS)
    refused = [f for f in report.findings if f.rule.id == "S14"]
    if method in ("stored", "deflate"):
        assert not refused, "%s was refused; it is one of the two that are read" % method
    else:
        assert refused


def _with_method(tmp_path, entries, metadata, name="m.iirds", mimetype_method=None):
    """A container where named entries carry a method of their own."""
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        first = zipfile.ZipInfo("mimetype")
        first.compress_type = mimetype_method or zipfile.ZIP_STORED
        archive.writestr(first, MIMETYPE)
        archive.writestr("META-INF/metadata.rdf", metadata)
        archive.writestr("content/topic1.xhtml", b"<html/>")
        for entry, body, method in entries:
            info = zipfile.ZipInfo(entry)
            info.compress_type = method
            archive.writestr(info, body)
    return path


def test_a_rule_that_reads_an_entry_stands_down_rather_than_raising(tmp_path):
    """C5 reads `mimetype`, and reading it now raises.

    An unhandled raise costs the whole rule: the run reported `S3 rule C5
    raised`, told the reader to open an issue about their own package, and
    answered for one rule fewer -- for a package whose fault it had already
    identified twice, in C6 and in S14. Standing down loses nothing, because
    C6 requires this entry to be stored and every method that stops the read
    is already a C6 violation.
    """
    package = _with_method(tmp_path, (), MINIMAL_RDF, mimetype_method=zipfile.ZIP_BZIP2)
    report = runner.run(package, runner.ALL_KINDS)
    ids = {f.rule.id for f in report.findings}

    assert "C5" in report.ran, "C5 did not run: %s" % sorted(ids)
    assert "S3" not in ids, "a rule raised: %s" % [
        f.violation.detail for f in report.findings if f.rule.id == "S3"]
    assert {"C6", "S14"} <= ids, sorted(ids)


def test_the_handover_content_list_is_reported_rather_than_silently_skipped(tmp_path):
    """The one file an iiRDS/H package promises a person with a browser.

    C11.2 asks whether it is an HTML document, which cannot be asked of a file
    this run will not open. Answering anyway is the defect this project keeps
    finding in itself, and saying nothing is the other one, so it says that it
    did not look.
    """
    from test_content_list_is_content import HANDOVER

    package = _with_method(
        tmp_path, (("index.html", b"<html><body>list</body></html>", zipfile.ZIP_BZIP2),),
        HANDOVER, name="h.iirds")
    report = runner.run(package, runner.ALL_KINDS)
    ids = {f.rule.id for f in report.findings}

    assert "S3" not in ids, "a rule raised: %s" % [
        f.violation.detail for f in report.findings if f.rule.id == "S3"]
    assert "S14" in ids, sorted(ids)
    said = [f for f in report.findings if f.rule.id == "C11.2"]
    assert said, "the content list was passed over in silence: %s" % sorted(ids)
    assert "was not read" in said[0].violation.message, said[0].violation.message


def test_an_unpacked_container_has_no_method_to_refuse(tmp_path):
    """A directory is not an archive, and the guards must not ask it.

    `DirectoryPackage.info` answers with the one thing a directory can say
    honestly -- a size -- and carries no compression method. The guards added
    for C5 and C11.2 asked for one anyway, so every rule that reads an entry
    raised on an unpacked container and was lost: three unrelated tests about
    directories went red with `S3 rule ... raised` and nothing else.
    """
    import zipfile as zf

    from iirds_validate import runner as r

    package = _package(tmp_path, "deflate")
    unpacked = tmp_path / "unpacked"
    zf.ZipFile(package).extractall(unpacked)

    report = r.check(unpacked)
    ids = {f.rule.id for f in report.findings}
    assert "S3" not in ids, "a rule raised on a directory: %s" % [
        f.violation.detail for f in report.findings if f.rule.id == "S3"]
    assert "S14" not in ids, "a directory has no compression method to refuse"
