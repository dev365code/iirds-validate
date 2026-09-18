"""The B rules against documents that are hostile, unusual, or merely legal.

Every case here passed silently before it was written, and each one passed for
a different reason. Together they are the argument for why a content rule needs
its own entry gate: the rule can be right and still never see the document.
"""
from __future__ import annotations

import os
import time

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

XHTML = "http://www.w3.org/1999/xhtml"


def _b_rules(path):
    return sorted({f.rule.id for f in runner.check(path).findings if f.rule.id.startswith("B")})


def _document(body: str, *, xmlns: bool = True, doctype: str = "",
              head: str = "", encoding: str = "utf-8") -> str:
    ns = ' xmlns="%s"' % XHTML if xmlns else ""
    declared = "utf-16" if encoding.startswith("utf-16") else "utf-8"
    return ('<?xml version="1.0" encoding="%s"?>%s<html%s><head><title>t</title>%s'
            "</head><body>%s</body></html>" % (declared, doctype, ns, head, body))


#: What the parser reads when nothing tells it the encoding -- measured,
#: not assumed. A byte order mark is honoured; without one it autodetects
#: UTF-16 in both byte orders and refuses UTF-32 in both, so nothing can
#: be smuggled in UTF-32. A guard that matches bytes matches the first of
#: these and none of the rest.
XML_ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be")

#: The outermost entity the declarations below define. Named once: a
#: fixture that declares five and references a sixth is refused for being
#: undefined, which looks exactly like the guard working and is not.
_TOP = 4


def _small_bomb(encoding: str) -> bytes:
    """The billion-laughs shape, sized so that a parser which does expand
    it finishes rather than taking the suite with it. What is under test is
    the refusal of the declaration, which does not depend on the size."""
    entities = "".join('<!ENTITY e%d "%s">' % (i, ("&e%d;" % (i - 1)) * 4 if i else "x" * 16)
                       for i in range(_TOP + 1))
    return _document("<p>&e%d;</p>" % _TOP, encoding=encoding,
                     doctype="<!DOCTYPE html [%s]>" % entities).encode(encoding)


@pytest.mark.parametrize("encoding", XML_ENCODINGS)
def test_a_content_file_is_read_whatever_encoding_it_arrives_in(tmp_path, encoding):
    """The premise the refusal below rests on. Without it, refusing a bomb
    in an encoding would prove nothing: the parser might simply not read
    that encoding, and the refusal would be taking credit for a limit that
    is not its own. B5 firing is the proof the document was parsed."""
    document = _document("", head='<link rel="next" href="topic2.xhtml"/>',
                         encoding=encoding).encode(encoding)
    package = build_package(tmp_path, "clean-%s.iirds" % encoding, content=(),
                            extra=(("content/topic1.xhtml", document),))
    assert "B5" in _b_rules(package)


@pytest.mark.parametrize("encoding", XML_ENCODINGS)
def test_entity_expansion_is_refused_whatever_encoding_it_arrives_in(tmp_path, encoding):
    """The refusal matched bytes, and a byte pattern finds `<!ENTITY` in
    UTF-8 and nowhere else -- so the same declaration, written UTF-16,
    walked past it and the parser expanded what it declared. The gate is a
    property, not a list of encodings to keep up to date: wherever a clean
    document is read, one declaring entities is refused."""
    package = build_package(tmp_path, "bomb-%s.iirds" % encoding, content=(),
                            extra=(("content/topic1.xhtml", _small_bomb(encoding)),))
    report = runner.check(package)
    assert "B1" in {f.rule.id for f in report.findings}


def test_entity_expansion_is_refused_rather_than_expanded(tmp_path):
    """A 400-byte file that expands to gigabytes must not be parsed.

    The billion-laughs shape. Nothing about it is invalid iiRDS, so no rule was
    ever going to reject it on its merits — the parser had to die first, and it
    died holding the whole run. Refusing to parse it is the safe answer; what
    severity the refusal carries depends on the profile, and this test pins
    both sides of that line.
    """
    entities = "".join('<!ENTITY e%d "%s">' % (i, ("&e%d;" % (i - 1)) * 10 if i else "x" * 64)
                       for i in range(9))
    bomb = _document("<p>&e8;</p>", doctype="<!DOCTYPE html [%s]>" % entities)
    package = build_package(tmp_path, "bomb.iirds", content=(),
                            extra=(("content/topic1.xhtml", bomb),))

    start = time.monotonic()
    report = runner.check(package)
    elapsed = time.monotonic() - start

    assert elapsed < 5, "took %.1fs; the expansion was attempted" % elapsed
    b1 = next(f for f in report.findings if f.rule.id == "B1")

    # Calibrated, not absolute. An unrestricted package may carry any content,
    # so a file this validator refuses to read is a warning there — the
    # refusal itself is this tool's safety guard, not a conformance fact — and
    # `-W` exists for gates that want it fatal. Under iiRDS/A the profile
    # restricts content to iiRDS XHTML5, so the same finding is an error.
    assert str(b1.severity) == "warning"
    assert report.ok

    restricted = MINIMAL_RDF.replace(
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
        "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>"
        "<iirds:formatRestriction>A</iirds:formatRestriction>")
    package_a = build_package(tmp_path, "bomb-a.iirds", metadata=restricted, content=(),
                              extra=(("content/topic1.xhtml", bomb),))
    report_a = runner.check(package_a)
    assert not report_a.ok, "under iiRDS/A the same document fails the build"
    assert str(next(f for f in report_a.findings if f.rule.id == "B1").severity) == "error"


def test_media_type_parameters_do_not_disable_the_content_rules(tmp_path):
    """`application/xhtml+xml; charset=utf-8` is that media type, with a parameter.

    RFC 2045 says so and nothing in iiRDS says otherwise, so a package declaring
    the charset — which is good practice — silently skipped all ten B rules.
    The most conscientious authors got the least checking.
    """
    body = '<script>alert(1)</script><link rel="next" href="x"/>'
    reported = {}
    for label, declared in (("plain", "application/xhtml+xml"),
                            ("parameterised", "application/xhtml+xml; charset=utf-8")):
        metadata = MINIMAL_RDF.replace("<iirds:format>application/xhtml+xml</iirds:format>",
                                       "<iirds:format>%s</iirds:format>" % declared)
        package = build_package(tmp_path, "%s.iirds" % label, metadata=metadata, content=(),
                                extra=(("content/topic1.xhtml", _document(body)),))
        reported[label] = _b_rules(package)

    assert reported["parameterised"] == reported["plain"] != []


def test_elements_are_matched_by_local_name_not_by_namespace(tmp_path):
    """A document with no `xmlns` still has a `<link>` in it.

    Matching on the fully-qualified name is correct XML and the wrong check for
    this job: the documents most likely to be malformed are the ones missing the
    namespace declaration, and those were the ones no rule could see. Matching
    on the local name means the sloppier the document, the more it gets told.
    """
    body = ""
    head_link = '<link rel="next" href="topic2.xhtml"/>'
    document = ('<?xml version="1.0"?><html><head><title>t</title>%s</head>'
                "<body>%s</body></html>" % (head_link, body))
    package = build_package(tmp_path, "nons.iirds", content=(),
                            extra=(("content/topic1.xhtml", document),))

    assert "B5" in _b_rules(package)


def test_hazard_symbols_are_counted_per_statement_not_per_file(tmp_path):
    """Two correct warnings in one file are two correct warnings.

    Counting symbols across the whole document meant the second correct hazard
    statement made the first one look wrong — the rule got worse as the document
    got more careful, which is the wrong direction for a safety check.
    """
    def panel(role: str, word: str, symbol: bool) -> str:
        image = '<img data-role="safety-alert-symbol" src="%s.png"/>' % word if symbol else ""
        return ('<div data-role="%s"><div data-role="signalword-panel">'
                '<p data-role="signalword">%s</p>%s</div></div>' % (role, word, image))

    good = build_package(tmp_path, "two-good.iirds", content=(),
                         extra=(("content/topic1.xhtml",
                                 _document(panel("warning", "WARNING", True)
                                           + panel("danger", "DANGER", True))),))
    assert "B8" not in _b_rules(good)

    # The negative controls, so that counting per panel is not just a way of
    # switching the rule off. B8 asks two things — where the symbol sits, and
    # that a panel carries no more than one — and both must still be asked.
    stray = _document(panel("warning", "WARNING", False)
                      + '<img data-role="safety-alert-symbol" src="loose.png"/>')
    assert "B8" in _b_rules(build_package(tmp_path, "stray.iirds", content=(),
                                          extra=(("content/topic1.xhtml", stray),)))

    doubled = _document(
        '<div data-role="warning"><div data-role="signalword-panel">'
        '<p data-role="signalword">WARNING</p>'
        '<img data-role="safety-alert-symbol" src="a.png"/>'
        '<img data-role="safety-alert-symbol" src="b.png"/></div></div>')
    assert "B8" in _b_rules(build_package(tmp_path, "doubled.iirds", content=(),
                                          extra=(("content/topic1.xhtml", doubled),)))


#: A passage *about* a declaration, in each of the places the grammar allows
#: text to sit. None of these declares anything: the token is characters.
DESCRIBING = {
    "cdata": lambda d: _document("<p><![CDATA[%s e0 \"x\"> declares an entity]]></p>" % d),
    "prolog-comment": lambda d: _document("<p>see above</p>",
                                          doctype="<!-- %s is a declaration -->" % d),
    "doctype-and-cdata": lambda d: _document("<p><![CDATA[%s e0 \"x\">]]></p>" % d,
                                             doctype="<!DOCTYPE html>"),
}


@pytest.mark.parametrize("shape", sorted(DESCRIBING), ids=sorted(DESCRIBING))
@pytest.mark.parametrize("encoding", XML_ENCODINGS)
def test_a_document_that_describes_a_declaration_is_not_refused(tmp_path, encoding, shape):
    """iiRDS is a documentation standard, so a topic about XML syntax is an
    ordinary file rather than a contrived one.

    The refusal searched the whole document for the token. The grammar allows
    a declaration in one place only -- inside a doctype's internal subset --
    so a passage quoting it in a CDATA section, or a comment before the
    doctype, was read as the thing itself. Under iiRDS/A that is an error, and
    a package fails on a topic documenting the standard it ships with.

    The third shape is the one a check keyed on "is there a doctype" still
    gets wrong, which is why it is here: the question is not whether the
    document has a doctype but whether it declares anything.
    """
    document = DESCRIBING[shape]("<!" + "ENTITY").encode(encoding)
    package = build_package(tmp_path, "describes-%s-%s.iirds" % (shape, encoding),
                            content=(), extra=(("content/topic1.xhtml", document),))
    report = runner.check(package)
    refusals = [f for f in report.findings
                if f.rule.id == "B1" and "entit" in (f.violation.detail or "")]
    assert refusals == [], refusals[0].violation.detail


@pytest.mark.parametrize("encoding", XML_ENCODINGS)
def test_an_external_dtd_is_not_refused_for_declaring_nothing(tmp_path, encoding):
    """A doctype naming an external DTD declares nothing this parser will
    read: it does not fetch, so nothing can expand. Refusing it would report
    a document for something that cannot happen, and if a parser ever did
    fetch, that is the offline promise's business and has its own rule."""
    document = _document("<p>hi</p>",
                         doctype='<!DOCTYPE html SYSTEM "entities.dtd">').encode(encoding)
    package = build_package(tmp_path, "external-%s.iirds" % encoding, content=(),
                            extra=(("content/topic1.xhtml", document),))
    refusals = [f for f in runner.check(package).findings
                if f.rule.id == "B1" and "entit" in (f.violation.detail or "")]
    assert refusals == [], refusals[0].violation.detail


def _many_renditions(tmp_path, count, size):
    """A container of almost no size on disk that declares `count` renditions.

    The shape the budget exists for. Each rendition is one byte repeated, so
    it compresses to nothing and decompresses to `size`; the archive is a few
    tens of kilobytes and what reading it costs is `count * size`.
    """
    topics = "".join("""  <iirds:Topic rdf:about="urn:test:t%d">
    <iirds:title>T%d</iirds:title>
    <iirds:has-rendition><iirds:Rendition>
      <iirds:format>application/xhtml+xml</iirds:format>
      <iirds:source>content/r%d.xhtml</iirds:source>
    </iirds:Rendition></iirds:has-rendition>
  </iirds:Topic>\n""" % (i, i, i) for i in range(count))
    body = ("<html xmlns='%s'><body><p>%s</p></body></html>" % (XHTML, "a" * size)).encode()
    return build_package(
        tmp_path,
        metadata=MINIMAL_RDF.replace("</rdf:RDF>", topics + "</rdf:RDF>"),
        extra=[("content/r%d.xhtml" % i, body) for i in range(count)],
    )


def test_the_content_budget_bounds_what_a_run_reads(tmp_path, monkeypatch):
    """The ceiling is on what a run reads, and it did not hold.

    `MAX_CONTENT_TOTAL_BYTES` exists so that an archive of no size cannot make
    a run decompress without bound, and `charge` raises past it. But the read
    came first and the charge second, and the refusal that followed was kept
    per file rather than for the run -- so every later rendition was read in
    full before being charged for and refused. Measured on a 49,510 byte
    archive declaring forty renditions of a megabyte each, against a two
    megabyte ceiling: 41,945,847 bytes came out, twenty times the ceiling.

    What the ceiling bounds is reading, and this measures reading. A run that
    crossed it never held the bytes -- the crossing read is discarded -- so a
    gate on peak memory passes against the defect and says nothing.

    One read may still cross it. A size is not knowable without reading, and
    that read is bounded by the per-file limit. What must not happen is the
    read after it.

    Both ceilings are moved together, and they have to be: at their shipped
    sizes the sum this asserts is 64 MiB, which a package small enough to
    build in a test is under however many times it is read. The first version
    of this test moved only the budget and passed against the defect.
    """
    from iirds_validate import package as package_module
    from iirds_validate.rules import content as content_module

    package = _many_renditions(tmp_path, count=8, size=64 * 1024)
    budget, per_file = 96 * 1024, 128 * 1024
    monkeypatch.setattr(package_module, "MAX_CONTENT_TOTAL_BYTES", budget)
    monkeypatch.setattr(content_module, "MAX_CONTENT_BYTES", per_file)

    held = []
    real = package_module.Package.read_bounded

    def counting(self, name, limit):
        raw, oversize = real(self, name, limit)
        if name.startswith("content/"):
            held.append(len(raw))
        return raw, oversize

    monkeypatch.setattr(package_module.Package, "read_bounded", counting)
    runner.run(package, runner.ALL_KINDS)

    assert held, "no content entry was read; the test is measuring nothing"
    assert sum(held) <= budget + per_file, (
        "a run read %d bytes of content against a ceiling of %d; the ceiling "
        "allows one read to cross it and none after" % (sum(held), budget))


def test_the_damage_check_asks_for_bounded_reads(tmp_path, monkeypatch):
    """C1 opens every entry, and no ceiling in this project bounds that pass.

    Asking whether an archive is damaged means decompressing all of it: there
    is no cheaper way to find the entry that will not come back out, and no
    size the archive declares can be trusted to answer it. So the pass is
    outside the content budget on purpose, and the one thing that keeps it
    from being a whole archive in memory at once is that it asks for a
    bounded slice at a time and keeps none of what comes back.

    This measures the asking, which is all this pass controls. What CPython
    hands back for a given request is not the same question and is not
    asserted here.

    Two mutations that leave this pass useless and were not caught by the
    first version of this test, which is why it is written this way:

    * `Package.testzip` gutted to `return None`. Every read the test saw came
      from the content rules, which chunk their own reads, so the gate was
      green with the damage check doing nothing. The pass is now identified
      by its call site rather than by the shape of its reads.
    * `_INTEGRITY_CHUNK` raised to a gigabyte. The old bound was
      `max(_INTEGRITY_CHUNK, ...)` -- the constant under test -- so raising
      it moved the assertion with it and a whole entry came back in one
      block. The bound here is a number written here.
    """
    import zipfile

    from iirds_validate import package as package_module

    #: Larger than any request this pass should make and far smaller than an
    #: entry. Written here rather than read from the code being tested.
    SLICE = 1024 * 1024

    package = _many_renditions(tmp_path, count=3, size=4 * 1024 * 1024)

    ran, inside, asked = [], [], []
    real_testzip = package_module.Package.testzip
    real_read = zipfile.ZipExtFile.read

    def watched(self):
        ran.append(True)
        inside.append(True)
        try:
            return real_testzip(self)
        finally:
            inside.pop()

    def measured(self, n=-1):
        # Only what this pass asks for. A flag that stayed set after the pass
        # returned would collect the content rules' own chunked reads, and a
        # damage check that read nothing would look like one that behaved.
        if inside:
            asked.append(n)
        return real_read(self, n)

    monkeypatch.setattr(package_module.Package, "testzip", watched)
    monkeypatch.setattr(zipfile.ZipExtFile, "read", measured)
    runner.run(package, runner.ALL_KINDS)

    assert ran, ("the damage check never ran, so this test measured nothing -- "
                 "C1 is what calls it, and it is archive-only")
    assert asked, "the damage check ran and read nothing"
    assert all(n is not None and 0 < n <= SLICE for n in asked), (
        "the damage check asked for %r; a request for a whole entry -- "
        "`read()` with no argument -- is one archive in memory at once"
        % sorted({n for n in asked if n is None or n <= 0 or n > SLICE}))


def _renditions_with_one_damaged(tmp_path, count=3, damaged=1, name="test.iirds"):
    """A container whose renditions are sound but for corrupt streams.

    Each document violates several appendix B rules, so a rule that examines
    it has something to say and a rule that never sees it stays silent -- the
    difference this test is about.

    `damaged` is one index or several. A damaged deflate stream is the one
    fault that reads the same on every platform this runs on, which is why the
    tests about more than one unreadable file are built here rather than out
    of file permissions: `chmod(0o000)` leaves a file readable on Windows.
    """
    import struct
    import zipfile

    topics = "".join("""  <iirds:Topic rdf:about="urn:t:%d"><iirds:title>t%d</iirds:title>
    <iirds:has-rendition><iirds:Rendition>
      <iirds:format>application/xhtml+xml</iirds:format>
      <iirds:source>content/topic%03d.xhtml</iirds:source>
    </iirds:Rendition></iirds:has-rendition></iirds:Topic>\n""" % (i, i, i)
        for i in range(count))
    body = ("<html xmlns='%s'><body><script>x</script><form></form>"
            "<p data-role='nonsense'>t</p></body></html>" % XHTML).encode()
    package = build_package(
        tmp_path, name,
        metadata=MINIMAL_RDF.replace("</rdf:RDF>", topics + "</rdf:RDF>"),
        extra=[("content/topic%03d.xhtml" % i, body) for i in range(count)])

    raw = bytearray(package.read_bytes())
    wanted = (damaged,) if isinstance(damaged, int) else tuple(damaged)
    with zipfile.ZipFile(package) as archive:
        offsets = [archive.getinfo("content/topic%03d.xhtml" % i).header_offset
                   for i in wanted]
    for offset in offsets:
        name_len, extra_len = struct.unpack("<HH", raw[offset + 26:offset + 30])
        start = offset + 30 + name_len + extra_len
        for at in range(start + 4, start + 12):      # inside the deflate stream
            raw[at] ^= 0xFF
    package.write_bytes(bytes(raw))
    return package


def test_one_unreadable_stream_does_not_decide_what_the_other_rules_examine(tmp_path):
    """A rendition nobody can decompress must cost that rendition, not the rest.

    `_bytes_of` caught two kinds of refusal -- an unreadable compression
    method and the run's ceiling -- and a corrupt deflate stream is neither.
    It came out of `read_bounded` as `zlib.error`, killed the rule that asked,
    and left `_walk`'s cache installed and half filled, because the dict was
    put on the context before the loop that filled it -- it is built into a
    local and installed complete now. Every later content rule
    then iterated a truncated file set and was recorded as having answered.

    Measured on this package before the repair: B1 and B2 raised, and B3
    reported only `content/topic000.xhtml` -- `topic002` is intact, breaks the
    same rules, and nobody opened it. The report said B3 ran.
    """
    package = _renditions_with_one_damaged(tmp_path)
    report = runner.run(package, runner.ALL_KINDS)
    seen = {}
    for finding in report.findings:
        if finding.rule.id.startswith("B"):
            seen.setdefault(finding.rule.id, set()).add(finding.violation.subject)

    assert not report.not_applicable.get("raised"), (
        "a rule raised rather than reporting the file it could not read: %s"
        % report.not_applicable.get("raised"))
    assert seen.get("B2") == {"content/topic000.xhtml", "content/topic002.xhtml"}, (
        "the rules that examine content saw %r; the sound renditions are "
        "topic000 and topic002" % (sorted(seen.get("B2", ())),))
    refused = [f for f in report.findings
               if f.rule.id == "B1" and f.violation.subject == "content/topic001.xhtml"]
    assert refused, "the damaged rendition is not reported as refused"
    # And the package fails on that account alone. B1 is a content rule and
    # demotes to a warning outside iiRDS/A, so the finding above does not
    # decide anything; S16 is what says a file nobody read is not a file that
    # passed. Asserting only the first left the verdict untested.
    assert {f.rule.id for f in report.findings
            if f.violation.subject == "content/topic001.xhtml"} >= {"B1", "S16"}
    assert not report.ok


def test_a_sound_package_is_unchanged_by_that_handling(tmp_path):
    """The control. Nothing about an archive that reads must move."""
    package = _renditions_with_one_damaged(tmp_path, count=3, damaged=None) \
        if False else build_package(
            tmp_path, name="sound.iirds",
            metadata=MINIMAL_RDF.replace("</rdf:RDF>", """  <iirds:Topic rdf:about="urn:t:0">
    <iirds:title>t0</iirds:title><iirds:has-rendition><iirds:Rendition>
      <iirds:format>application/xhtml+xml</iirds:format>
      <iirds:source>content/topic000.xhtml</iirds:source>
    </iirds:Rendition></iirds:has-rendition></iirds:Topic>\n</rdf:RDF>"""),
            extra=[("content/topic000.xhtml",
                    ("<html xmlns='%s'><body><script>x</script></body></html>" % XHTML).encode())])
    report = runner.run(package, runner.ALL_KINDS)
    assert not report.not_applicable.get("raised"), report.not_applicable.get("raised")
    assert any(f.rule.id == "B2" and f.violation.subject == "content/topic000.xhtml"
               for f in report.findings)


def _one_rendition(tmp_path, name, count=1):
    """A package whose single rendition is sound, so any finding about it is
    about the reading and not about the markup."""
    import zipfile  # noqa: F401  (imported by the callers for extraction)

    sources = ["content/r.xhtml"] if count == 1 else \
        ["content/r%d.xhtml" % i for i in range(count)]
    topics = "".join("""  <iirds:Topic rdf:about="urn:t:r%d">
    <iirds:title>r%d</iirds:title>
    <iirds:has-rendition><iirds:Rendition>
      <iirds:format>application/xhtml+xml</iirds:format>
      <iirds:source>%s</iirds:source>
    </iirds:Rendition></iirds:has-rendition></iirds:Topic>\n""" % (i, i, source)
        for i, source in enumerate(sources))
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", topics + "</rdf:RDF>")
    body = ("<html xmlns='%s'><body><p>r</p></body></html>" % XHTML).encode()
    return build_package(tmp_path, name, metadata=metadata,
                         extra=[(source, body) for source in sources])


@pytest.mark.skipif(os.name == "nt", reason="chmod(0o000) leaves a file readable on "
                                            "Windows, so the fault this builds is not one "
                                            "there; the zipped case above covers S16 on "
                                            "every platform")
def test_a_rendition_nobody_can_read_still_fails_the_package(tmp_path):
    """Reporting the file instead of raising must not turn a fail into a pass.

    Before, an unreadable rendition killed the rule and the run recorded
    `S3 rule B1 raised` -- a system finding, an error in every profile. Now
    the file is reported by B1, which is a content rule, and content rules
    demote to warnings outside iiRDS/A because whether a file is "iiRDS XHTML5
    content" is this project's reading (runner.severity_override). Whether the
    container will hand the file over is not a reading of anything, so the
    demotion must not carry it: measured on the unpacked form, where no C1
    holds the verdict, the package came back `ok` with exit 0.

    The unpacked form is where it shows, and it is the shape a build checks.
    The archive form of the same fault -- a stream that will not decompress --
    fails too, but only because C1 opens every entry and reports the damage;
    that is the rule the unpacked form suspends, which is why the verdict
    there rested on nothing. `test_one_unreadable_stream_...` above holds the
    zipped side, S16 included.
    """
    import zipfile

    package = _one_rendition(tmp_path, "unreadable.iirds")
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(unpacked)
    (unpacked / "content" / "r.xhtml").chmod(0o000)
    try:
        report = runner.run(unpacked, runner.ALL_KINDS)
        ids = sorted({f.rule.id for f in report.findings})
        assert not report.ok, (
            "a package holding a file nothing could read came back clean: %s" % ids)
    finally:
        (unpacked / "content" / "r.xhtml").chmod(0o644)


def test_the_same_package_read_whole_is_clean(tmp_path):
    """The control: the permission is the only fault, so with it back nothing
    is said about the file at all.

    Written as `assert report.ok` first, which is not a control: outside
    iiRDS/A every content error is a warning and `ok` reads errors only, so it
    stayed true when the fixture was replaced with markup that is not
    well-formed, with an empty file, and with a PNG. What has to be asserted
    is silence about this file, which is also what makes the test above a
    measurement -- the same fixture, read, draws nothing.
    """
    import zipfile

    package = _one_rendition(tmp_path, "readable.iirds")
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(unpacked)
    report = runner.run(unpacked, runner.ALL_KINDS)
    about_it = [(f.rule.id, f.violation.detail) for f in report.findings
                if f.violation.subject == "content/r.xhtml"]
    assert not about_it, about_it
    assert report.ok


def test_every_file_that_could_not_be_read_is_named(tmp_path):
    """One finding per file, not one per run.

    Every other fixture in this suite has exactly one unreadable file, so a
    version of S16 that stopped after the first name passed all of them -- and
    "which files went unexamined" is the whole of what the rule adds over the
    rules that say what the run did.

    Two damaged streams rather than two unreadable files on disk: a mode bit
    is not a fault on every platform this suite runs on, and the property
    being checked here has nothing to do with which platform it is.
    """
    package = _renditions_with_one_damaged(tmp_path, count=3, damaged=(0, 2),
                                           name="two-damaged.iirds")
    report = runner.run(package, runner.ALL_KINDS)
    assert sorted(f.violation.subject for f in report.findings
                  if f.rule.id == "S16") == ["content/topic000.xhtml",
                                             "content/topic002.xhtml"]


def test_a_command_that_reads_no_content_does_not_claim_to_have_asked(tmp_path):
    """`iirds lint` selects ("lint", "system") and opens no rendition, so S16
    has nothing to look at -- and `kind="system"` puts it in every kind set,
    so the report listed it among the rules the run had checked. A question
    nobody asked, counted as answered, is what `ARCHIVE_ONLY` exists for one
    layer out.

    Built from a damaged stream rather than a mode bit: which container form
    this is does not matter to the question, and a mode bit is not a fault on
    every platform this suite runs on.
    """
    package = _renditions_with_one_damaged(tmp_path, count=1, damaged=0,
                                           name="lint.iirds")
    assert [f for f in runner.run(package, runner.ALL_KINDS).findings
            if f.rule.id == "S16"], "the rule does not fire where content is read"
    lint = runner.lint(package)
    assert "S16" in lint.not_applicable.get("unasked", []), (
        "lint counted a rule it cannot run among the rules it checked")


def test_a_rendition_larger_than_the_per_file_ceiling_is_not_this_rules_business(tmp_path):
    """The line S16 draws, held here because it is a line and not an omission.

    `MAX_CONTENT_BYTES` is a number this project chose; a rendition past it is
    a legal file the container hands over perfectly well, and this tool
    declines to read it. B1 says so as a warning, and outside iiRDS/A the
    package passes -- which is a hole, and closing it turns a legal package's
    pass into a failure. That is a release of its own, not something a repair
    to the reporting may do on the way past.
    """
    from iirds_validate.rules import content as content_module

    monkey = pytest.MonkeyPatch()
    monkey.setattr(content_module, "MAX_CONTENT_BYTES", 32)
    try:
        package = _one_rendition(tmp_path, "big.iirds")
        report = runner.run(package, runner.ALL_KINDS)
        assert {f.rule.id for f in report.findings if f.violation.subject == "content/r.xhtml"} \
            == {"B1"}, sorted((f.rule.id, f.severity) for f in report.findings)
    finally:
        monkey.undo()
