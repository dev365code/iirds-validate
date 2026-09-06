"""S7 and S8 — the two container requirements no test had ever reached.

Both are about properties of the ZIP that only appear at a scale the rest of
the suite never builds, so both shipped unexercised. S8 was worse than
unexercised: it was inverted, and failed exactly the archives it exists to
protect.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.rules import system

#: One past the limit the specification names. Around 9 MB and three seconds,
#: which is the price of testing a rule about large archives at all.
ENTRIES = 70_000


def _fired(report, rule_id):
    return [f for f in report.findings if f.rule.id == rule_id]


@pytest.fixture(scope="module")
def large_archive(tmp_path_factory):
    """A valid archive with more entries than ZIP32 can address.

    Python's zipfile writes the ZIP64 records itself once the count goes past
    the limit — which is the point: an ordinary, correctly built large package
    is the case S8 was rejecting.
    """
    path = tmp_path_factory.mktemp("large") / "large.iirds"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/iirds+zip")
        archive.writestr("META-INF/metadata.rdf", MINIMAL_RDF)
        archive.writestr("content/topic1.xhtml", "<html/>")
        for n in range(ENTRIES):
            archive.writestr("content/filler%06d.xhtml" % n, "<html/>")
    path.write_bytes(buf.getvalue())
    return path


def test_a_correctly_built_large_archive_does_not_fail_s8(large_archive):
    """The regression. S8 compared entry count against the limit and then
    inferred ZIP64 from per-entry offsets — but seventy thousand small files
    exceed the count limit while every offset stays well inside 4 GB, so the
    inference said "no ZIP64" for an archive that plainly had it. The rule
    could only ever fire, and only ever on archives that were correct.
    """
    assert len(zipfile.ZipFile(large_archive).infolist()) > 65_536
    assert _fired(runner.check(large_archive), "S8") == []


def test_s8_still_fires_when_the_zip64_record_is_absent(large_archive, monkeypatch):
    """The other half, which no archive Python can write will demonstrate.

    `zipfile` refuses to produce a ZIP64-less archive past the limit — pass
    `allowZip64=False` and it raises rather than emit one. The archives that do
    exist come from writers that got it wrong, so the defect is reached here by
    telling the detector it found no record. It pins the branch that matters:
    over the limit and no ZIP64 is still a violation.
    """
    monkeypatch.setattr(system, "_has_zip64_record", lambda path: False)
    findings = _fired(runner.check(large_archive), "S8")
    assert len(findings) == 1
    assert "%d entries" % (ENTRIES + 3) in findings[0].violation.detail


def test_the_entry_limit_is_the_number_the_specification_names():
    """"more than 65536 file entries" — so 65536 entries is not more than that.

    An off-by-one here is invisible in every test that does not sit exactly on
    the boundary, and reports a conformant archive as broken.
    """
    assert system.ZIP64_ENTRY_LIMIT == 65_536


def _mark_encrypted(path, target: str) -> None:
    """Set bit 0 of the general purpose flag on one entry, in the raw bytes.

    `zipfile` will not write the bit — `writestr` clears the flags it does not
    itself set — so the only way to produce the thing S7 looks for is to reach
    past the library and set it in the headers, both of them: the central
    directory is what a reader consults and the local header is what it finds
    when it seeks there, and a package with only one of them set is a different
    defect from the one under test.
    """
    data = bytearray(path.read_bytes())
    name = target.encode("utf-8")
    cursor = 0
    while True:
        cursor = data.find(b"PK\x01\x02", cursor)
        if cursor < 0:
            raise AssertionError("no central directory entry for %s" % target)
        length = int.from_bytes(data[cursor + 28:cursor + 30], "little")
        if data[cursor + 46:cursor + 46 + length] == name:
            break
        cursor += 4
    local = int.from_bytes(data[cursor + 42:cursor + 46], "little")
    assert data[local:local + 4] == b"PK\x03\x04"
    data[cursor + 8] |= 0x1        # central directory copy of the flag
    data[local + 6] |= 0x1         # local file header copy
    path.write_bytes(bytes(data))


def test_s7_reports_an_encrypted_entry(tmp_path):
    """Bit 0 of the general purpose flag, set on one entry of an otherwise
    ordinary package. An entry that claims to be encrypted is unreadable to a
    consumer that has only the package, which is every consumer.
    """
    package = build_package(tmp_path, "encrypted.iirds")
    _mark_encrypted(package, "content/topic1.xhtml")

    findings = _fired(runner.check(package), "S7")
    assert [f.violation.subject for f in findings] == ["content/topic1.xhtml"]


def test_neither_rule_is_claimed_against_a_directory(tmp_path):
    """Both are properties of the archive. On an unpacked container they must
    stand down and be reported as not assessed, never as passed.
    """
    package = build_package(tmp_path, "unpacked.iirds")
    unpacked = tmp_path / "unpacked"
    zipfile.ZipFile(package).extractall(unpacked)

    report = runner.check(unpacked)
    assert _fired(report, "S7") == _fired(report, "S8") == []
    assert report.skipped > 0


#: The requirements whose subject is the ZIP archive itself. An unpacked
#: container cannot answer them, and the runner has always said so in a note.
ARCHIVE_ONLY = ("C1", "C3", "C6", "R3", "S7", "S8", "S10")


def _unpacked(tmp_path):
    root = tmp_path / "unpacked"
    (root / "META-INF").mkdir(parents=True)
    (root / "mimetype").write_text("application/iirds+zip", "utf-8")
    (root / "META-INF" / "metadata.rdf").write_text(
        '<?xml version="1.0"?><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:iirds="http://iirds.tekom.de/iirds#">'
        '<iirds:Package rdf:about="urn:x:p">'
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion></iirds:Package></rdf:RDF>", "utf-8")
    return root


def test_the_archive_rules_are_reported_as_not_assessed_and_not_as_checked(tmp_path):
    """"Reported as not assessed, never as passed" was a note and nothing else.

    The runner counts a rule as checked before running it, and these seven return
    at their first line when the container is not an archive -- so an unpacked
    directory came back `PASS, 175 rules checked` with "the archive must not be
    encrypted" and "large archives must use ZIP64" among the hundred and
    seventy-five. The only trace was a sentence in `notes`, which no test read
    the content of and no consumer of the JSON report can act on.

    Now they are where a reader and a machine both look: out of the checked
    count and named in `not_applicable`, under a reason of their own. The note
    stays, as prose for the same fact.
    """
    report = runner.check(_unpacked(tmp_path))
    named = set(report.not_applicable.get("unpacked", ()))
    assert named == set(ARCHIVE_ONLY), sorted(named)
    for rule_id in ARCHIVE_ONLY:
        for reason, ids in report.not_applicable.items():
            if reason != "unpacked":
                assert rule_id not in ids, (rule_id, reason)


def test_the_note_and_the_report_name_the_same_rules(tmp_path):
    """The sentence was the only representation of this and said "the six
    requirements ... (C1, C3, C6, S7, S8, S10)" in free text. Changing which
    ids it named broke nothing. It is written from the list now, so the prose
    and the machine-readable half cannot disagree."""
    report = runner.check(_unpacked(tmp_path))
    note = next(n for n in report.notes if "unpacked container" in n)
    for rule_id in ARCHIVE_ONLY:
        assert rule_id in note, (rule_id, note)


def test_a_packed_container_still_checks_them(tmp_path):
    """The control: these rules are not disabled, they are inapplicable to a
    directory. A real archive answers all seven."""
    package = build_package(tmp_path, "packed.iirds")
    report = runner.check(package)
    assert report.not_applicable["unpacked"] == [], report.not_applicable
    assert all(r not in sum(report.not_applicable.values(), [])
               for r in ARCHIVE_ONLY), report.not_applicable


def test_no_rule_keeps_its_own_archive_guard():
    """One list, not a list and seven guards saying the same thing.

    Each of these rules opened with `if not ctx.package.is_archive: return`,
    and the runner counted them as checked before running them -- which is the
    defect above. With the runner deciding, the guards became seven lines no
    package can reach, and the unreached-line baseline said so: eleven to
    seventeen in one measurement.

    R3 is why this is a gate and not a deletion. It carries the same guard, is
    about the archive's own layout -- "the container must be at the root of the
    archive, not inside a folder" -- and was not in the list, so an unpacked
    container still reported it among the rules it had checked. Six were
    repaired and the seventh was found by counting dead lines. A guard added
    instead of a list entry would put the next one back.

    The first pattern here read `\\w+\\.package\\.is_archive`, and S10 -- one of
    the seven -- spells it `package.is_archive`, off a local bound a line
    earlier. Planting that rule's own guard back left this test green. A gate
    written against seven examples has to match all seven of them.
    """
    import re
    from pathlib import Path

    from iirds_validate.runner import ARCHIVE_ONLY as declared

    assert set(declared) == set(ARCHIVE_ONLY), sorted(set(declared) ^ set(ARCHIVE_ONLY))
    rules_dir = Path(runner.__file__).resolve().parent / "rules"
    guarded = sorted(path.name for path in rules_dir.glob("*.py")
                     if re.search(r"if not \w+(\.package)?\.is_archive",
                                  path.read_text("utf-8")))
    assert guarded == [], (
        "these modules still guard on is_archive; the runner decides now: %s" % guarded)


#: The English for a count, up to the largest this list could plausibly reach.
#: The release notes say "seven rules"; the number they say it about is
#: `len(ARCHIVE_ONLY)`, and one of the two is prose.
IN_WORDS = {6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def test_the_unreleased_notes_state_the_count_that_was_measured(tmp_path):
    """The release notes for this change said "six", and there are seven.

    They were right when written. R3 joined the list afterwards, and nothing
    would have said so -- which is the shape of the defect that put the front
    page on `77 of 280` for two releases: a figure in published prose with no
    gate behind it, agreeing with nothing because nothing read it.

    Only the unreleased section. Once a version ships its notes are a record of
    what the tool said at the time, and a gate that keeps rewriting them to
    today's measurement destroys the record it is meant to protect.

    The count is matched on a word boundary because the paragraph it is checked
    against says "six of those hundred and seventy-five", and `"seven" in text`
    is satisfied by `seventy-five`. Written without the boundary, this test
    passed on the prose it was written to reject.
    """
    import re
    from pathlib import Path

    report = runner.check(_unpacked(tmp_path))
    moved = len(report.not_applicable["unpacked"])
    checked = report.checked

    root = Path(runner.__file__).resolve().parents[2]
    sections = (root / "CHANGELOG.md").read_text("utf-8").split("\n## ")
    unreleased = [s for s in sections if s.splitlines()[0].endswith("unreleased")]
    assert len(unreleased) == 1, [s.splitlines()[0] for s in sections[1:]]
    entry = next(p for p in unreleased[0].split("\n\n") if "`notApplicable`" in p)

    assert re.search(r"\b%s\b" % IN_WORDS[moved], entry), (
        "the notes no longer say %r about the %d rules the runner stands down"
        % (IN_WORDS[moved], moved))
    assert "%d rules checked" % (checked + moved) in entry, (
        "the notes quote a count an unpacked container does not produce; it is "
        "%d checked plus %d not assessed" % (checked, moved))
    assert "from %d to %d" % (checked + moved, checked) in unreleased[0], (
        "the notes no longer state the move this change makes: %d to %d"
        % (checked + moved, checked))
