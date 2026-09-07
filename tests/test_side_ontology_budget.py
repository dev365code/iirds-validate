"""The files a run reads to decide it did not need them.

Section 7 lets a package put its own ontology beside the metadata, and R18
finds them: every entry under `META-INF/` that is not one of the files the
standard names is read, parsed as RDF, and kept only if it attaches something
to iiRDS. A signature, a manifest, a readme is none of this rule's business --
which is decided *after* the file has been read and parsed.

So the work a package can ask for had no ceiling. Each entry is read to the
per-entry limit and handed to the RDF parser, and the entry count is whatever
the archive says. The content budget does not cover it: `Package.charge` is
documented as the ceiling on content, and only content pays into it, because a
first version charged metadata too and a run died reading `metadata.rdf` with
the death surfacing as a parse error rather than as the budget it was.

Measured before this existed: an archive of a tenth of a megabyte, holding
small RDF files under `META-INF/` that attach nothing, kept a run reading for
longer than any package in the vendored corpus and finished with an empty
report. Small input, large work, clean answer -- and the clean answer is the
part that matters, because the run had stopped being an examination of the
package and nothing said so.
"""
from __future__ import annotations

import zipfile
import zlib

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.package import MAX_SIDE_BYTES

#: One side file, big enough that a handful of them pass the ceiling. The
#: content is RDF that parses and attaches nothing -- the shape R18 reads and
#: discards, which is the shape with no cost to the sender.
FILLER = ('<?xml version="1.0"?><rdf:RDF '
          'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
          + '<rdf:Description rdf:about="urn:x:pad"/>' * 400
          + '</rdf:RDF>')


def side_files(count):
    return tuple(("META-INF/side%04d.rdf" % i, FILLER) for i in range(count))


def report(tmp_path, count, name="side.iirds"):
    package = build_package(tmp_path, name, metadata=MINIMAL_RDF,
                            content=("content/topic1.xhtml",), extra=side_files(count))
    return runner.check(package)


def test_a_package_within_the_ceiling_is_examined_and_says_nothing(tmp_path):
    assert "S12" not in {f.rule.id for f in report(tmp_path, 2).findings}


def test_the_scan_stops_at_its_ceiling_and_says_so(tmp_path):
    """The finding is the point. A scan that gives up and reports nothing is
    indistinguishable from a scan that finished and found nothing, and the
    second is what a reader takes an empty report to mean."""
    enough = MAX_SIDE_BYTES // len(FILLER.encode("utf-8")) + 4
    findings = [f for f in report(tmp_path, enough).findings if f.rule.id == "S12"]
    assert findings, "the scan ran past its ceiling and did not say so"
    assert len(findings) == 1


def test_the_finding_says_where_it_stopped(tmp_path):
    enough = MAX_SIDE_BYTES // len(FILLER.encode("utf-8")) + 4
    hit = [f for f in report(tmp_path, enough).findings if f.rule.id == "S12"][0]
    text = "%s %s" % (hit.violation.message, hit.violation.detail or "")
    assert str(MAX_SIDE_BYTES) in text or "ceiling" in text, text
    assert "not examined" in text or "stopped" in text, text


def test_the_work_is_bounded_rather_than_merely_reported(tmp_path):
    """The counter has to stop the loop, not annotate it.

    A version that recorded the overrun and went on reading would satisfy a
    test that only looks for the finding, and would leave the cost exactly
    where it was. The finding states how much the scan read, which is its own
    account of the work it did; one file is the most it may exceed the ceiling
    by, because the decision is taken after a read rather than before.
    """
    enough = MAX_SIDE_BYTES // len(FILLER.encode("utf-8")) + 40
    hit = [f for f in report(tmp_path, enough, "many.iirds").findings
           if f.rule.id == "S12"]
    assert hit, "no cut reported on a package far past the ceiling"
    import re
    numbers = [int(n) for n in re.findall(r"\d+", hit[0].violation.detail or "")]
    assert numbers, hit[0].violation.detail
    read = numbers[0]
    assert read <= MAX_SIDE_BYTES + len(FILLER.encode("utf-8")), (read, MAX_SIDE_BYTES)


def test_a_real_side_ontology_is_still_found(tmp_path):
    """The ceiling must not become a way of not looking. One package ontology
    under META-INF is read, attaches, and draws no cut."""
    attaching = ('<?xml version="1.0"?><rdf:RDF '
                 'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
                 'xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">'
                 '<rdfs:Class rdf:about="urn:mine:Special">'
                 '<rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Topic"/>'
                 '</rdfs:Class></rdf:RDF>')
    package = build_package(tmp_path, "one.iirds", metadata=MINIMAL_RDF,
                            content=("content/topic1.xhtml",),
                            extra=(("META-INF/mine.rdf", attaching),))
    assert "S12" not in {f.rule.id for f in runner.check(package).findings}


def test_the_rule_is_a_system_rule():
    """As S9 is, and for the same reason: the subject is the run, not the
    package, and every kind of run can be cut short this way."""
    from iirds_validate.registry import all_rules
    rule = {r.id: r for r in all_rules()}["S12"]
    assert rule.kind == "system"
    assert rule.versions == () and rule.variants == ()


#: An extension that attaches, so R18 reports the file by name. Used as the
#: witness that the scan went on past a neighbour it could not read.
ATTACHING = ('<?xml version="1.0"?><rdf:RDF '
             'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
             'xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">'
             '<rdfs:Class rdf:about="urn:mine:Late">'
             '<rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Topic"/>'
             '</rdfs:Class></rdf:RDF>')


def corrupt_entry(path, name):
    """Break one entry's stream so that reading it raises.

    A flipped byte inside the deflate stream, located through the local
    header rather than by searching for the payload, because a compressed
    payload is not in the file to be searched for. What comes out is a zlib
    error or a CRC mismatch depending on where the flip lands; the rule may
    not care which, so neither does this.
    """
    with zipfile.ZipFile(path) as zf:
        offset = zf.getinfo(name).header_offset
    raw = bytearray(path.read_bytes())
    name_len = int.from_bytes(raw[offset + 26:offset + 28], "little")
    extra_len = int.from_bytes(raw[offset + 28:offset + 30], "little")
    raw[offset + 30 + name_len + extra_len] ^= 0xFF
    path.write_bytes(bytes(raw))
    return path


def test_the_fixture_is_actually_unreadable(tmp_path):
    """Stated first, because the two tests below pass without it whether or
    not the entry is broken, and a fixture that quietly repaired itself would
    make them say nothing."""
    package = build_package(tmp_path, "corrupt.iirds", metadata=MINIMAL_RDF,
                            content=("content/topic1.xhtml",),
                            extra=(("META-INF/broken.rdf", FILLER),))
    corrupt_entry(package, "META-INF/broken.rdf")
    with zipfile.ZipFile(package) as zf, pytest.raises((zipfile.BadZipFile, zlib.error)):
        zf.read("META-INF/broken.rdf")


def test_an_unreadable_side_file_does_not_end_the_run(tmp_path):
    package = build_package(tmp_path, "survives.iirds", metadata=MINIMAL_RDF,
                            content=("content/topic1.xhtml",),
                            extra=(("META-INF/broken.rdf", FILLER),))
    corrupt_entry(package, "META-INF/broken.rdf")
    report = runner.check(package)          # must not raise
    named_as_an_extension = {f.violation.subject for f in report.findings
                             if f.rule.id == "R18"}
    assert "META-INF/broken.rdf" not in named_as_an_extension, sorted(named_as_an_extension)
    # C1 does name it, and that is where a reader is told: the entry is
    # damaged, not a proprietary extension that section 5.1.1 talks about.
    assert "META-INF/broken.rdf" in {f.violation.subject for f in report.findings
                                     if f.rule.id == "C1"}


def test_an_unreadable_side_file_does_not_end_the_scan(tmp_path):
    """`continue`, not `return`. The entry that cannot be read is one entry's
    worth of ignorance; a version that gave up on the rest would look the same
    on a package holding nothing else, and stop finding extensions on the
    packages this rule exists for."""
    package = build_package(tmp_path, "after.iirds", metadata=MINIMAL_RDF,
                            content=("content/topic1.xhtml",),
                            extra=(("META-INF/broken.rdf", FILLER),
                                   ("META-INF/zz-late.rdf", ATTACHING)))
    corrupt_entry(package, "META-INF/broken.rdf")
    subjects = {f.violation.subject for f in runner.check(package).findings}
    assert "META-INF/zz-late.rdf" in subjects, sorted(subjects)
