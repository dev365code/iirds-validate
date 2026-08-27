"""What checking a package's renditions costs, and where that stops.

A rendition is read out of the archive by the rules that look inside it.
Measured, one rendition was decompressed four times in a run: B1 read it to
refuse or accept it and read it again to parse it, and the tree cache that
B2 draws from did the same pair over again, because the bytes were never kept
after the first look. Forty renditions of one megabyte each, in an archive
that compresses to nothing, made the run read a hundred and sixty.

Two things are pinned here. Each rendition is decompressed once, and the sum
of what a run decompresses has a ceiling it states rather than a limit it
discovers by running out of memory.
"""
from __future__ import annotations

import collections
import os

from conftest import MINIMAL_RDF, build_package
from iirds_validate import package as package_module
from iirds_validate import runner

BLOB = b"<html xmlns='http://www.w3.org/1999/xhtml'><body>x</body></html>"


def _package_with_renditions(directory, count, blob=BLOB):
    units = "".join(
        '  <iirds:Topic rdf:about="urn:t:%d"><iirds:title>t%d</iirds:title>'
        '<iirds:has-rendition><iirds:Rendition>'
        '<iirds:format>application/xhtml+xml</iirds:format>'
        '<iirds:source>content/r%d.xhtml</iirds:source>'
        '</iirds:Rendition></iirds:has-rendition></iirds:Topic>\n' % (i, i, i)
        for i in range(count))
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", units + "</rdf:RDF>")
    extra = tuple(("content/r%d.xhtml" % i, blob) for i in range(count))
    return build_package(directory, "renditions.iirds", metadata=metadata, extra=extra)


def _reads_by_name(monkeypatch, package):
    """How many times each content entry was decompressed during one run,
    counted at the one method every read goes through."""
    counts = collections.Counter()
    original = package_module.Package.read_bounded

    def counting(self, name, limit):
        if name.startswith("content/"):
            counts[name] += 1
        return original(self, name, limit)

    monkeypatch.setattr(package_module.Package, "read_bounded", counting)
    report = runner.run(str(package), runner.ALL_KINDS)
    return counts, report


def test_each_rendition_is_decompressed_once_per_run(tmp_path, monkeypatch):
    """Four reads of the same bytes was the measured shape: a refusal check,
    a parse, and the same pair again from a second rule. The bytes are kept
    after the first look now, so every later question is answered from
    memory that was already paid for."""
    package = _package_with_renditions(tmp_path, 3)
    counts, _ = _reads_by_name(monkeypatch, package)
    assert counts, "no rendition was read at all; the fixture is wrong"
    worst = max(counts.values())
    assert worst == 1, {k: v for k, v in counts.items() if v > 1}


def test_a_run_states_a_ceiling_on_what_it_will_decompress(tmp_path, monkeypatch):
    """Per-entry limits bound each rendition and nothing bounds their sum, so
    an archive that compresses to nothing can make a run decompress as much
    as it declares. The ceiling is a number the package can read in the
    report, not a memory error."""
    monkeypatch.setattr(package_module, "MAX_CONTENT_TOTAL_BYTES", 8 * len(BLOB))
    package = _package_with_renditions(tmp_path, 12)
    _, report = _reads_by_name(monkeypatch, package)
    # By rule id, not by wording. The first version of this matched the word
    # "budget" in any finding and was green on a parse-error rule whose
    # message happened to carry it, while S9 had fired zero times.
    said = [f for f in report.findings if f.rule.id == "S9"]
    assert len(said) == 1, sorted({f.rule.id for f in report.findings})
    assert str(8 * len(BLOB)) in (said[0].violation.detail or ""), said[0].violation.detail
    assert said[0].violation.subject.startswith("content/r"), said[0].violation.subject


def test_the_ceiling_is_the_one_the_environment_names(monkeypatch):
    """S9's remedy tells the reader to raise IIRDS_CONTENT_BUDGET, so the
    variable has to exist and to be the number that is used -- a remedy that
    names a knob the code does not read is worse than no remedy."""
    import importlib
    import subprocess
    import sys as _sys

    probe = ("import iirds_validate.package as p; print(p.MAX_CONTENT_TOTAL_BYTES)")
    env = dict(os.environ, IIRDS_CONTENT_BUDGET="12345")
    env["PYTHONPATH"] = os.pathsep.join(
        os.path.abspath(e) for e in _sys.path if e and os.path.isdir(e))
    out = subprocess.run([_sys.executable, "-c", probe], capture_output=True,
                         text=True, env=env, check=True).stdout.strip()
    assert out == "12345", out
    del importlib
