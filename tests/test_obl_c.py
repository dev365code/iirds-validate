"""Family C: iiRDS/A's content formats, and the sentences in section 8.2.1
that bind every file of a kind -- not only the renditions the metadata
declares as that kind.

A rule reading "the renditions declared as PDF" misses a PDF the metadata
calls something else, and a PDF a page links to that no rendition names. The
sentence binds both. Each case below quotes the requirement it holds, breaks
it in a package the declared-type reading passes, and asserts that a rule
claiming the id reports it; each has a sibling that keeps the sentence and
draws nothing.
"""
from __future__ import annotations

from iirds_validate import runner
from make_fixture_package import MINIMAL_RDF

A_PROFILE = MINIMAL_RDF.replace(
    "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
    "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
    "    <iirds:formatRestriction>A</iirds:formatRestriction>")

PAGE = ('<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title></head>'
        '<body><p>{}</p></body></html>\n')

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _declared(make_package, source, body, media_type, name):
    """The fixture's one rendition, pointed at `source` and declared as `media_type`."""
    metadata = (A_PROFILE
                .replace("<iirds:format>application/xhtml+xml</iirds:format>",
                         "<iirds:format>%s</iirds:format>" % media_type)
                .replace("<iirds:source>content/topic1.xhtml</iirds:source>",
                         "<iirds:source>%s</iirds:source>" % source))
    return runner.check(make_package(name=name, metadata=metadata, content=(),
                                     extra=((source, body),)))


def _linked(make_package, markup, files, name):
    """The fixture's page, carrying `markup`, and the files it points at."""
    return runner.check(make_package(name=name, metadata=A_PROFILE, content=(),
                                     extra=(("content/topic1.xhtml", PAGE.format(markup)),)
                                     + tuple(files)))


def _subjects(report, rule_id):
    return sorted(f.violation.subject for f in report.findings if f.rule.id == rule_id)


# ---------------------------------------------------------------------------
# x8-2-1-1-text-formats#5: "The file extension MUST be .pdf."
# ---------------------------------------------------------------------------

def test_a_pdf_the_metadata_calls_something_else_is_named_pdf(make_package):
    report = _declared(make_package, "content/manual.bin", PDF, "application/octet-stream", "c1.iirds")
    assert _subjects(report, "R41") == ["content/manual.bin"], sorted(f.rule.id for f in report.findings)


def test_a_pdf_a_page_links_to_is_named_pdf(make_package):
    report = _linked(make_package, '<a href="manual.bin">manual</a>',
                     (("content/manual.bin", PDF),), "linked-pdf.iirds")
    assert _subjects(report, "R41") == ["content/manual.bin"], sorted(f.rule.id for f in report.findings)


def test_a_pdf2_file_outside_the_declared_rendition_is_refused(make_package):
    """Section 8.2.1.1's extension requirement binds an unreferenced PDF too.

    The declared XHTML rendition is valid; adding only this PDF 2.0 .bin
    takes the package from clean to one R41 error.
    """
    assert runner.check(make_package(metadata=A_PROFILE)).ok
    report = runner.check(make_package(metadata=A_PROFILE,
                                      extra=(("content/manual.bin", b"%PDF-2.0\n%%EOF\n"),)))
    assert not report.ok
    assert [(f.rule.id, f.severity.value, f.violation.subject) for f in report.findings] == [
        ("R41", "error", "content/manual.bin")]


def test_a_pdf_named_pdf_draws_nothing_however_it_is_reached(make_package):
    assert not _subjects(_declared(make_package, "content/manual.pdf", PDF,
                                   "application/octet-stream", "c3.iirds"), "R41")
    assert not _subjects(_linked(make_package, '<a href="manual.pdf">manual</a>',
                                 (("content/manual.pdf", PDF),), "c4.iirds"), "R41")


# ---------------------------------------------------------------------------
# x8-2-1-2-graphics-formats#3: "The file extension MUST be .svg for
# non-compressed files and .svgz for gzip-compressed files."
# ---------------------------------------------------------------------------

import gzip  # noqa: E402

SVG = (b'<?xml version="1.0"?>\n<!-- a figure -->\n<svg xmlns="http://www.w3.org/2000/svg" '
       b'width="1" height="1"/>\n')
SVGZ = gzip.compress(SVG, mtime=0)


def test_an_svg_a_page_shows_under_another_name_is_refused(make_package):
    report = _linked(make_package, '<img src="figure.xml" alt=""/>',
                     (("content/figure.xml", SVG),), "s1.iirds")
    assert _subjects(report, "R42") == ["content/figure.xml"], sorted(f.rule.id for f in report.findings)


def test_a_compressed_svg_a_page_calls_svg_is_refused(make_package):
    report = _linked(make_package, '<img src="figure.svg" alt=""/>',
                     (("content/figure.svg", SVGZ),), "s2.iirds")
    assert _subjects(report, "R42") == ["content/figure.svg"], sorted(f.rule.id for f in report.findings)


def test_an_svg_the_metadata_calls_something_else_is_named_for_its_bytes(make_package):
    report = _declared(make_package, "content/figure.bin", SVG, "application/octet-stream", "s3.iirds")
    assert _subjects(report, "R42") == ["content/figure.bin"], sorted(f.rule.id for f in report.findings)


def test_an_svg_named_for_whether_it_is_compressed_draws_nothing(make_package):
    report = _linked(make_package, '<img src="a.svg" alt=""/><img src="b.svgz" alt=""/>',
                     (("content/a.svg", SVG), ("content/b.svgz", SVGZ)), "s4.iirds")
    assert not _subjects(report, "R42")


def test_a_file_that_is_not_an_svg_is_not_held_to_svg_names(make_package):
    """An XML file whose root is not SVG, and a gzip stream that is not one,
    are not what the sentence is about."""
    other = b'<?xml version="1.0"?>\n<note xmlns="urn:x"/>\n'
    report = _linked(make_package, '<a href="n.xml">n</a><a href="n.gz">z</a>',
                     (("content/n.xml", other), ("content/n.gz", gzip.compress(other, mtime=0))), "s5.iirds")
    assert not _subjects(report, "R42")


# ---------------------------------------------------------------------------
# x8-2-1-1-text-formats#2: "The file extension MUST be .xhtml."
# ---------------------------------------------------------------------------

def test_an_xhtml_page_a_page_links_to_is_named_xhtml(make_package):
    report = _linked(make_package, '<a href="other.html">next</a>',
                     (("content/other.html", PAGE.format("more").encode()),), "x1.iirds")
    assert _subjects(report, "B6") == ["content/other.html"], sorted(f.rule.id for f in report.findings)


def test_xhtml_the_metadata_calls_html_is_named_xhtml(make_package):
    report = _declared(make_package, "content/topic1.html", PAGE.format("t").encode(), "text/html", "x2.iirds")
    assert _subjects(report, "B6") == ["content/topic1.html"], sorted(f.rule.id for f in report.findings)


def test_xhtml_named_xhtml_and_html_that_is_not_xhtml_draw_nothing(make_package):
    html = b"<!DOCTYPE html>\n<html><head><title>T</title></head><body><p>x</p></body></html>\n"
    report = _linked(make_package, '<a href="other.xhtml">x</a><a href="plain.html">h</a>',
                     (("content/other.xhtml", PAGE.format("more").encode()),
                      ("content/plain.html", html)), "x3.iirds")
    assert not _subjects(report, "B6")


def test_outside_iirds_a_a_linked_page_is_not_held_to_the_iirds_a_sentence(make_package):
    report = runner.check(make_package(name="x4.iirds", metadata=MINIMAL_RDF, content=(),
                                       extra=(("content/topic1.xhtml", PAGE.format('<a href="o.html">o</a>')),
                                              ("content/o.html", PAGE.format("o").encode()))))
    assert report.variant != "A"
    assert not _subjects(report, "B6")


# ---------------------------------------------------------------------------
# x8-2-1-3-video-formats#2: "The file extension MUST be .mp4."
# x8-2-1-4-audio-formats#2: "The file extension MUST be .mp3."
#
# Read further than before -- what a page plays, MPEG-4 and MP3 by their
# bytes -- and still not claimed: a video or audio file in a format with no
# signature here, declared as something else and played by no page, is not
# recognised. These cases hold what the rules do read.
# ---------------------------------------------------------------------------

MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 16
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 16
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x64" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 16


def test_a_video_a_page_plays_is_named_mp4(make_package):
    report = _linked(make_package, '<video src="clip.webm"></video>'
                                   '<video><source src="take2.mov"/></video>',
                     (("content/clip.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 16),
                      ("content/take2.mov", MP4)), "v1.iirds")
    assert _subjects(report, "R44") == ["content/clip.webm", "content/take2.mov"], \
        sorted(f.rule.id for f in report.findings)


def test_an_mp4_the_metadata_calls_something_else_is_named_mp4(make_package):
    report = _declared(make_package, "content/clip.bin", MP4, "application/octet-stream", "v2.iirds")
    assert _subjects(report, "R44") == ["content/clip.bin"], sorted(f.rule.id for f in report.findings)


def test_a_poster_and_a_still_image_are_not_video(make_package):
    """A `poster` is the picture shown before a video plays, and an HEIC
    image is an ISO base media file too; neither is video content."""
    report = _linked(make_package, '<video src="clip.mp4" poster="still.jpg"></video>'
                                   '<img src="photo.heic" alt=""/>',
                     (("content/clip.mp4", MP4), ("content/still.jpg", JPEG),
                      ("content/photo.heic", HEIC)), "v3.iirds")
    assert not _subjects(report, "R44")


def test_audio_a_page_plays_is_named_mp3(make_package):
    report = _linked(make_package, '<audio src="tone.wav"></audio>'
                                   '<audio><source src="tone2.ogg"/></audio>',
                     (("content/tone.wav", b"RIFF\x00\x00\x00\x00WAVEfmt "),
                      ("content/tone2.ogg", b"OggS" + b"\x00" * 16)), "a1.iirds")
    assert _subjects(report, "R45") == ["content/tone.wav", "content/tone2.ogg"], \
        sorted(f.rule.id for f in report.findings)


def test_an_mp3_the_metadata_calls_something_else_is_named_mp3(make_package):
    report = _declared(make_package, "content/tone.bin", MP3, "application/octet-stream", "a2.iirds")
    assert _subjects(report, "R45") == ["content/tone.bin"], sorted(f.rule.id for f in report.findings)


def test_audio_named_mp3_draws_nothing(make_package):
    report = _linked(make_package, '<audio src="tone.mp3"></audio>',
                     (("content/tone.mp3", MP3),), "a3.iirds")
    assert not _subjects(report, "R45")


def test_an_svg_a_stylesheet_uses_is_named_for_its_bytes(make_package):
    """A page reaches some files through its stylesheet -- an icon in `url()`
    -- and the sentences bind those as they bind the rest: every file in the
    package is read for what it is, not only the ones a page names itself."""
    report = _linked(make_package, '<span>x</span>',
                     (("content/style.css", b"span { background: url(icon.xml); }"),
                      ("content/icon.xml", SVG)), "c5.iirds")
    assert _subjects(report, "R42") == ["content/icon.xml"], sorted(f.rule.id for f in report.findings)


def test_a_reference_to_another_host_is_not_a_file_in_the_package(make_package):
    """`//cdn/clip.webm` is a network-path reference: a file on another host,
    whatever the package happens to hold at `cdn/clip.webm`."""
    report = _linked(make_package, '<video src="//cdn/clip.webm"></video>',
                     (("content/cdn/clip.webm", b"\x00" * 32), ("cdn/clip.webm", b"\x00" * 32)), "v4.iirds")
    assert not _subjects(report, "R44"), sorted(f.rule.id for f in report.findings)


def test_an_svg_whose_namespace_is_an_entity_is_an_svg(make_package):
    """Older Illustrator writes the namespace through an entity its document
    type declaration defines -- `xmlns="&ns_svg;"` -- and the file is an SVG
    all the same."""
    illustrator = (b'<?xml version="1.0" encoding="utf-8"?>\n'
                   b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
                   b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd" [\n'
                   b'\t<!ENTITY ns_svg "http://www.w3.org/2000/svg">\n'
                   b'\t<!ENTITY ns_xlink "http://www.w3.org/1999/xlink">\n]>\n'
                   b'<svg version="1.1" xmlns="&ns_svg;" xmlns:xlink="&ns_xlink;" width="1" height="1"/>\n')
    report = _linked(make_package, '<img src="figure.xml" alt=""/>',
                     (("content/figure.xml", illustrator),), "s6.iirds")
    assert _subjects(report, "R42") == ["content/figure.xml"], sorted(f.rule.id for f in report.findings)


def _with_media(make_package, media_type, source, body, markup, name, *extra):
    """The fixture's page carrying `markup`, and one more rendition: `source`,
    declared as `media_type`."""
    metadata = A_PROFILE.replace(
        "</rdf:RDF>",
        '  <iirds:Topic rdf:about="urn:test:t1"><iirds:title>t</iirds:title><iirds:has-rendition>'
        '<iirds:Rendition><iirds:format>%s</iirds:format><iirds:source>%s</iirds:source>'
        '</iirds:Rendition></iirds:has-rendition></iirds:Topic>\n</rdf:RDF>' % (media_type, source))
    return runner.check(make_package(name=name, metadata=metadata, content=(),
                                     extra=(("content/topic1.xhtml", PAGE.format(markup)),
                                            (source, body)) + tuple(extra)))


def test_audio_a_page_presents_through_video_is_audio(make_package):
    """`<video src="narration.mp3">` with a caption track is how a page shows
    captioned audio. The file is declared as audio and is MP3: the page's
    element does not make it a video that failed to be an MP4."""
    report = _with_media(make_package, "audio/mpeg", "content/narration.mp3", MP3,
                         '<video src="narration.mp3"><track kind="captions" src="n.vtt"/></video>',
                         "a4.iirds", ("content/n.vtt", b"WEBVTT\n"))
    assert not _subjects(report, "R44") and not _subjects(report, "R45"), \
        sorted(f.rule.id for f in report.findings)
    video = _with_media(make_package, "video/mp4", "content/clip.mp4", MP4,
                        '<audio src="clip.mp4"></audio>', "a5.iirds")
    assert not _subjects(video, "R44") and not _subjects(video, "R45"), \
        sorted(f.rule.id for f in video.findings)


def test_a_document_type_declaration_left_open_is_read_in_bounded_time():
    """A file opening `<!DOCTYPE [][][]...` with its internal subset never closed
    made the sniff backtrack exponentially: some ninety bytes held a whole run."""
    import time

    from iirds_validate.rules.content import SNIFF, _first_element

    started = time.perf_counter()
    _first_element((b"<!DOCTYPE " + b"[]" * SNIFF)[:SNIFF])
    _first_element(b"<!DOCTYPE " + b"[]" * 28)
    assert time.perf_counter() - started < 1.0


import pytest  # noqa: E402


@pytest.mark.parametrize("case,rule,name,body,expected", [
    ("utf16-svg", "R42", "figure.bin", SVG.decode().encode("utf-16"), True),
    ("long-comment-xhtml", "B6", "page.html",
     b"<!--" + b"a" * 5000 + b"-->" + PAGE.format("x").split("?>", 1)[1].encode(), True),
    ("namespace-charref", "R42", "figure.bin", SVG.replace(b"www.w3.org", b"www.w3.or&#103;"), True),
    ("quoted-close", "R42", "figure.bin", b'<svg width=">" xmlns="http://www.w3.org/2000/svg"/>', True),
    ("long-svgz", "R42", "figure.bin",
     gzip.compress(b"<!--" + b"a" * 5000 + b'--><svg xmlns="http://www.w3.org/2000/svg"/>', mtime=0), True),
    ("false-svg-namespace", "R42", "figure.bin", b'<svg note=" xmlns=\'http://www.w3.org/2000/svg\' "/>', False),
    ("false-xhtml-namespace", "B6", "page.html", b'<html note=" xmlns=\'http://www.w3.org/1999/xhtml\' "/>', False),
])
def test_extension_identification_tokenizes_the_xml_prefix(make_package, case, rule, name, body,
                                                          expected):
    """iiRDS 1.3 §8.2.1.1/§8.2.1.2: extensions are checked for identified
    XHTML/SVG. XML 1.0 §2.3/§3.1 tokens, encodings and quoted values decide
    the root namespace, rather than a substring inside another attribute.
    """
    package = make_package(name=case + ".iirds", metadata=A_PROFILE,
                           extra=(("content/" + name, body),))
    report = runner.check(package)
    assert bool(_subjects(report, rule)) is expected, [(f.rule.id, f.violation) for f in report.findings]


@pytest.mark.parametrize("delta,expected", [(-1, True), (0, True), (1, False)])
def test_xml_identification_window_has_a_byte_boundary(make_package, delta, expected):
    """iiRDS §8.2.1.2 identification is bounded; XML 1.0 §3.1 needs
    the complete start tag before its namespace can be identified.
    """
    from iirds_validate.rules.content import MAX_XML_IDENTIFICATION_BYTES

    root = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    padding = MAX_XML_IDENTIFICATION_BYTES + delta - len(root) - 7
    body = b"<!--" + b"a" * padding + b"-->" + root
    report = runner.check(make_package(metadata=A_PROFILE,
                                      extra=(("content/boundary.bin", body),)))
    assert bool(_subjects(report, "R42")) is expected


@pytest.mark.parametrize("compressed", [False, True])
def test_identification_charges_unreferenced_bytes_and_gzip_output(make_package, monkeypatch,
                                                                  compressed):
    """iiRDS 1.3 §8.2.1.2 binds every SVG, including referenced content.
    The run ceiling applies to every identification read, including
    unreferenced files and bytes inflated from a gzip SVG prefix.
    """
    from iirds_validate import package as package_module

    monkeypatch.setattr(package_module, "MAX_CONTENT_TOTAL_BYTES", 512)
    body = b"<!--" + b"a" * 5000 + b'--><svg xmlns="http://www.w3.org/2000/svg"/>'
    body = gzip.compress(body, mtime=0) if compressed else body
    report = runner.check(make_package(metadata=A_PROFILE,
                                      extra=(("content/unreferenced.bin", body),)))
    assert _subjects(report, "S9"), [(f.rule.id, f.violation.detail) for f in report.findings]
    assert not report.ok
    assert not _subjects(report, "S3")


@pytest.mark.parametrize("version", [b"1.0", b"2.0"])
def test_pdf_version_extremes_have_the_pdf_extension(make_package, version):
    """iiRDS 1.3 §8.2.1.1: "The file extension MUST be .pdf."
    The PDF signature applies across versions, including PDF 2.0.
    """
    body = b"%PDF-" + version + b"\n%%EOF\n"
    report = runner.check(make_package(metadata=A_PROFILE,
                                      extra=(("content/document.bin", body),)))
    assert _subjects(report, "R41") == ["content/document.bin"]
    assert not report.ok


def test_xml_identification_refuses_an_uppercase_hex_reference(make_package):
    """XML 1.0 §4.1 [66] uses lowercase x in a hexadecimal CharRef."""
    body = b'<svg xmlns="http://www.w3.or&#X67;/2000/svg"/>'
    report = runner.check(make_package(metadata=A_PROFILE,
                                      extra=(("content/figure.bin", body),)))
    assert not _subjects(report, "R42")


@pytest.mark.parametrize("name,body,rule_id", [
    ("clip.mov", MP4, "R44"),
    ("tone.audio", MP3, "R45"),
    ("tone.m4a", MP4.replace(b"isom", b"M4A ", 1), "R45"),
])
def test_undeclared_media_is_named_for_its_bytes(make_package, name, body, rule_id):
    """x8-2-1-3-video-formats#2: "The file extension MUST be .mp4."
    x8-2-1-4-audio-formats#2: "The file extension MUST be .mp3."
    No rendition declares these files and no page plays them.
    """
    report = runner.check(make_package(metadata=A_PROFILE,
                                      extra=(("content/" + name, body),)))
    assert _subjects(report, rule_id) == ["content/" + name]


@pytest.mark.parametrize("media_type,body,rule_id", [
    ("audio/mpeg", MP4, "R44"),
    ("video/mp4", MP3, "R45"),
])
def test_a_conflicting_media_declaration_does_not_erase_the_bytes(
        make_package, media_type, body, rule_id):
    """x8-2-1-3-video-formats#2: "The file extension MUST be .mp4."
    x8-2-1-4-audio-formats#2: "The file extension MUST be .mp3."
    A rendition's declaration cannot remove an identified file from its family.
    """
    report = _declared(make_package, "content/media.bin", body, media_type, "conflicting-media.iirds")
    assert _subjects(report, rule_id) == ["content/media.bin"]
    assert [(f.rule.id, f.violation.subject) for f in report.findings
            if f.rule.id in ("R44", "R45")] == [(rule_id, "content/media.bin")]


@pytest.mark.parametrize("media_type", ["audio/mpeg", "video/mp4", None])
@pytest.mark.parametrize("body,rule_id,extension", [
    (MP3, "R45", ".mp3"), (MP4, "R44", ".mp4"),
    (MP4.replace(b"isom", b"M4A ", 1), "R45", ".mp3"),
])
@pytest.mark.parametrize("suffix", [".bin", ".mp3", ".mp4"])
def test_media_bytes_choose_one_family_despite_the_declaration(
        make_package, media_type, body, rule_id, extension, suffix):
    """x8-2-1-3-video-formats#2: "The file extension MUST be .mp4."
    x8-2-1-4-audio-formats#2: "The file extension MUST be .mp3."
    Each recognised byte family owns the file regardless of its declaration.
    """
    source = "content/media" + suffix
    report = (_declared(make_package, source, body, media_type, "declared-media.iirds")
              if media_type else runner.check(make_package(
                  metadata=A_PROFILE, extra=((source, body),))))
    findings = [f for f in report.findings if f.rule.id in ("R44", "R45")]
    expected = [] if suffix == extension else [(rule_id, source)]
    assert [(f.rule.id, f.violation.subject) for f in findings] == expected
    if findings and media_type:
        assert "declared " + media_type in findings[0].violation.detail
    for finding in findings:
        if finding.rule.id == "R44":
            assert finding.rule.fix == (
                "Check the media content and its iirds:format declaration. "
                "Correct a conflicting declaration, or convert the content to the intended format. "
                "Save iiRDS/A video in the required MP4 encoding with a .mp4 filename "
                "and update every reference, including iirds:source.")
        else:
            assert finding.rule.fix == (
                "Check the media content and its iirds:format declaration. "
                "Correct a conflicting declaration, or convert the content to MP3 for iiRDS/A audio. "
                "Save the MP3 file with a .mp3 filename and update every reference, "
                "including iirds:source.")


@pytest.mark.parametrize("element,body,rule_id", [
    ("audio", MP4, "R44"), ("video", MP3, "R45"),
])
def test_media_bytes_choose_one_family_despite_the_playback_element(
        make_package, element, body, rule_id):
    """x8-2-1-3-video-formats#2: "The file extension MUST be .mp4."
    x8-2-1-4-audio-formats#2: "The file extension MUST be .mp3."
    """
    report = _linked(make_package, '<%s src="media.bin"/>' % element,
                     (("content/media.bin", body),), "played-media.iirds")
    assert [(f.rule.id, f.violation.subject) for f in report.findings
            if f.rule.id in ("R44", "R45")] == [(rule_id, "content/media.bin")]


def test_media_extensions_alone_make_no_format_claim(make_package):
    """x8-2-1-3-video-formats#2: "The file extension MUST be .mp4."
    x8-2-1-4-audio-formats#2: "The file extension MUST be .mp3."
    Identified files with the required names pass; names alone identify nothing.
    """
    report = runner.check(make_package(metadata=A_PROFILE, extra=(
        ("content/clip.mp4", MP4), ("content/tone.mp3", MP3),
        ("content/ordinary.mp4", b"ordinary text"),
        ("content/ordinary.mp3", b"ordinary text"))))
    assert not _subjects(report, "R44") and not _subjects(report, "R45")


@pytest.mark.parametrize("body", [
    b"RIFF\x00\x00\x00\x00WEBP", HEIC, b"unidentified graphic", b"",
])
def test_an_image_used_by_xhtml_must_have_allowed_graphic_bytes(make_package, body):
    """x8-2-1-2-graphics-formats#1: "Raster graphics MUST be encoded as"
    The following list in the anchor allows PNG 1.2 or higher and JPEG or higher.
    Calling a file .png cannot make it one of those formats.
    """
    report = _linked(make_package, '<img src="figure.png" alt=""/>',
                     (("content/figure.png", body),), "linked-graphic.iirds")
    assert _subjects(report, "R43") == ["content/figure.png"]


def test_a_declared_image_in_an_unknown_format_is_reported(make_package):
    """x8-2-1-2-graphics-formats#1: "Raster graphics MUST be encoded as"""
    report = _declared(make_package, "content/photo.heic", HEIC, "image/heic", "declared-heic.iirds")
    assert _subjects(report, "R43") == ["content/photo.heic"]
    assert "could not be identified as JPEG or PNG" in next(
        f.violation.message for f in report.findings if f.rule.id == "R43")


@pytest.mark.parametrize("name,body", [
    ("photo.bin", JPEG), ("figure.png", b"\x89PNG\r\n\x1a\n"),
    ("figure.svg", SVG), ("figure.svgz", SVGZ),
])
def test_allowed_graphics_are_decided_by_bytes(make_package, name, body):
    """x8-2-1-2-graphics-formats#1: "Raster graphics MUST be encoded as"
    SVG is governed by the vector sentence, not this raster restriction.
    """
    report = _linked(make_package, '<img src="%s" alt=""/>' % name,
                     (("content/" + name, body),), "supported-graphic.iirds")
    assert not _subjects(report, "R43")


def test_unused_names_do_not_identify_graphics_but_known_rasters_still_report(make_package):
    """x8-2-1-2-graphics-formats#1: "Raster graphics MUST be encoded as"
    Keep the existing all-file GIF check; an unused .gif name proves nothing.
    """
    report = runner.check(make_package(metadata=A_PROFILE, extra=(
        ("content/unused.gif", b"ordinary text"),
        ("content/identified.bin", b"GIF89a"))))
    assert _subjects(report, "R43") == ["content/identified.bin"]


@pytest.mark.parametrize("name,body,format_name", [
    ("style.xml", b'<?xml version="1.0"?><style/>', "XML or HTML document"),
    ("style.css", b" \n<html><head/></html>", "XML or HTML document"),
    ("style.doctype", b"<!dOcTyPe html><html/>", "XML or HTML document"),
    ("style.svg", b"<svg/>", "XML or HTML document"),
    ("style.rdf", b"<rdf:RDF/>", "XML or HTML document"),
    ("style.pdf", PDF, "PDF file"), ("style.zip", b"PK\x03\x04", "ZIP file"),
    ("style.png", b"\x89PNG\r\n\x1a\n", "PNG file"),
    ("style.jpg", JPEG, "JPEG file"), ("style.gif", bytes.fromhex(
        "47494638396101000100800000000000ffffff2c00000000010001000002024401003b"),
     "GIF file"),
    ("style.gz", b"\x1f\x8b", "gzip file"),
    ("style.wide-xml", b"\xff\xfe" + '<?xml version="1.0"?><style/>'.encode("utf-16-le"),
     "XML or HTML document"),
    ("style.bom", b"\xef\xbb\xbf<html/>", "XML or HTML document"),
])
def test_a_stylesheet_in_another_identifiable_format_is_reported(make_package, name, body, format_name):
    """dfn-iirds-xhtml5#2: "iiRDS XHTML5 stylesheets MUST be in CSS format."""
    report = _linked(make_package, '<link rel="stylesheet" href="%s"/>' % name,
                     (("content/" + name, body),), "non-css-stylesheet.iirds")
    assert _subjects(report, "R74") == ["content/" + name]
    finding = next(f for f in report.findings if f.rule.id == "R74")
    assert finding.violation.message == "the linked stylesheet is a%s %s, not CSS" % (
        "n" if format_name == "XML or HTML document" else "", format_name)
    assert finding.rule.fix == (
        "Replace a file identified as another format with a CSS stylesheet. "
        "If the stylesheet is missing, include it at the linked path or correct the link. "
        "Update references when its path changes.")


@pytest.mark.parametrize("name,body", [
    ("style.wide", b"\xff\xfe" + "p { color: red; }".encode("utf-16-le")),
    ("style.big-endian", b"\xfe\xff" + "p { color: red; }".encode("utf-16-be")),
    ("style.latin", b'@charset "iso-8859-1"; p { content: "caf\xe9"; }'),
    ("style.cdo", b"<!--\np { color: red; }\n-->"),
    ("style.import", b'\xef\xbb\xbf@import "other.css";'),
    ("style.empty", b""),
    ("style.less-than", b'p::after { content: "<"; }'),
    ("style.bin", b"p { color: red; }\xff"),
    ("style.late", b"p { color: red; }" + b" " * 5000 + b"\xff"),
])
def test_a_stylesheets_encoding_does_not_identify_another_format(make_package, name, body):
    """dfn-iirds-xhtml5#2: "iiRDS XHTML5 stylesheets MUST be in CSS format."""
    report = _linked(make_package, '<link rel="stylesheet" href="%s"/>' % name,
                     (("content/" + name, body),), "encoded-stylesheet.iirds")
    assert not _subjects(report, "R74")


def test_leading_cdo_tokens_do_not_hide_an_xml_stylesheet(make_package):
    """dfn-iirds-xhtml5#2: "iiRDS XHTML5 stylesheets MUST be in CSS format."""
    body = b' \n<!-- \t<!--\n<?xml version="1.0"?><style/>'
    report = _linked(make_package, '<link rel="stylesheet" href="style.css"/>',
                     (("content/style.css", body),), "wrapped-xml-stylesheet.iirds")
    assert _subjects(report, "R74") == ["content/style.css"]


@pytest.mark.parametrize("href", ["../style%20sheet.css?x=1#part", "/style%20sheet.css"])
def test_a_utf8_stylesheet_resolves_like_other_content_references(make_package, href):
    """dfn-iirds-xhtml5#2: "iiRDS XHTML5 stylesheets MUST be in CSS format."""
    report = _linked(make_package, '<link rel="STYLESHEET" href="%s"/>' % href,
                     (("style sheet.css", b"p { color: red; } /* caf\xc3\xa9 */"),),
                     "relative-stylesheet.iirds")
    assert not _subjects(report, "R74")


def test_a_missing_local_stylesheet_is_reported_once(make_package):
    """dfn-iirds-xhtml5#2: "iiRDS XHTML5 stylesheets MUST be in CSS format."
    No existing B rule reports a missing link target.
    """
    report = _linked(make_package, '<link rel="stylesheet" href="missing.css"/>', (),
                     "missing-stylesheet.iirds")
    assert _subjects(report, "R74") == ["content/missing.css"]
    assert next(f.violation.message for f in report.findings if f.rule.id == "R74") == (
        "the linked stylesheet is not in the package")


def test_a_remote_stylesheet_is_outside_the_local_byte_check(make_package):
    """dfn-iirds-xhtml5#2: "iiRDS XHTML5 stylesheets MUST be in CSS format."""
    report = _linked(make_package, '<link rel="stylesheet" href="//cdn/style.css"/>',
                     (("content/cdn/style.css", b"<html/>"),), "remote-stylesheet.iirds")
    assert not _subjects(report, "R74")


@pytest.mark.parametrize("element,rel", [
    (element, rel) for element in ("a", "area")
    for rel in ("alternate", "author", "help", "license", "next", "prefetch", "prev", "search")
] + [("link", "next"), ("a", "NEXT"), ("area", "nofollow\tPREV next")])
def test_shared_document_relations_are_reported_without_claiming_the_whole_sentence(
        make_package, element, rel):
    """b-5-2-document-metadata#3: "Relations usually represented by the element <link> in HTML MUST be expressed by means of RDF in iiRDS."""
    markup = '<%s rel="%s" href="next.xhtml"/>' % (element, rel)
    report = _linked(make_package, markup, (),
                     "document-relation.iirds")
    findings = [f for f in report.findings if f.rule.id == "B5"]
    assert len(findings) == 1
    assert "b-5-2-document-metadata#3" not in findings[0].rule.covers
    if element != "link":
        assert "<%s rel=" % element in findings[0].violation.message
        assert "metadata graph" in findings[0].violation.message
    sibling = _linked(make_package, '<link rel="stylesheet" href="style.css"/>',
                      (("content/style.css", b"p { color: red; }"),), "stylesheet-relation.iirds")
    assert not _subjects(sibling, "B5")


@pytest.mark.parametrize("element", ["a", "area"])
@pytest.mark.parametrize("rel", [None, "bookmark", "nofollow", "noreferrer", "tag",
                                "icon", "stylesheet", "nofollow noreferrer"])
def test_relations_outside_the_shared_document_types_are_not_reported(
        make_package, element, rel):
    """b-5-2-document-metadata#3: "Relations usually represented by the element <link> in HTML MUST be expressed by means of RDF in iiRDS."""
    attribute = '' if rel is None else ' rel="%s"' % rel
    report = _linked(make_package, '<%s%s href="next.xhtml"/>' % (element, attribute), (),
                     "ordinary-hyperlink.iirds")
    assert not _subjects(report, "B5")


@pytest.mark.parametrize("brand", [b"M4A ", b"M4B ", b"M4P "])
def test_audio_brand_identification_does_not_claim_to_read_tracks_or_codecs(make_package, brand):
    """x8-2-1-4-audio-formats#1: "Audio content MUST be encoded as MP3 (ISO/IEC 11172-3, ISO/IEC 13818-3)."
    A registered audio brand alone cannot establish the required MP3 encoding.
    """
    from pathlib import Path

    from iirds_validate.rules import content

    phrase = "MPEG-4 files whose brand is registered for audio"
    assert frozenset((b"M4A ", b"M4B ", b"M4P ")) == content._AUDIO_BRANDS
    report = runner.check(make_package(metadata=A_PROFILE, extra=(
        ("content/branded.bin", MP4.replace(b"isom", brand, 1)),)))
    finding = next(f for f in report.findings if f.rule.id == "R45")
    assert phrase in finding.rule.title
    assert phrase in " ".join(content.r45_audio_extension.__doc__.split())
    assert "tracks and codecs are not inspected" in content._is_mp4_audio.__doc__
    source = Path(content.__file__).read_text()
    assert "audio-only" not in source.lower()
    unreleased = Path("CHANGELOG.md").read_text().split("## 0.9.0", 1)[0]
    assert phrase in " ".join(unreleased.split())
    assert "audio-only" not in unreleased.lower()


def test_stylesheet_limitations_and_media_remedies_are_stated_in_public_prose():
    """B.1 requires CSS format; bytes identify other formats, not all CSS syntax."""
    from pathlib import Path

    expected = (
        "R74 examines linked local files for identifiable non-CSS content and missing files. "
        "It does not parse all CSS syntax or fetch external stylesheets, so it leaves "
        "B.1's stylesheet obligation unclaimed.")
    divergence = Path("docs/divergences.md").read_text()
    assert expected in divergence
    assert "The referring document's environment encoding is not implemented" in divergence
    assert "Python's codec labels are not the Encoding Standard's label mappings" in divergence
    from iirds_validate.rules import content

    decoding = " ".join(content._stylesheet_text.__doc__.split())
    assert "environment encoding is not implemented" in decoding
    assert "UTF-8 is used instead" in decoding
    paragraph = " ".join(Path("CHANGELOG.md").read_text().split("## 0.9.0", 1)[0].split())
    assert "invalid UTF-8" not in paragraph
    assert "rename the file" not in paragraph
    for statement in (
            "bytes determine the media family", "once under that byte family",
            "declaration in the finding", "convert the content",
            "PDF, ZIP, images, gzip, XML or HTML", "missing from the package",
            "a stylesheet's encoding is taken from its BOM or `@charset`",
            "and otherwise assumed to be UTF-8; it is not itself a finding",
            "errors in iiRDS/A", "warnings in other readings"):
        assert statement in paragraph


def test_an_unread_graphic_is_not_classified_after_the_budget_is_spent(make_package, monkeypatch):
    """Raster bytes that were not read cannot establish a format violation."""
    from iirds_validate import package as package_module

    monkeypatch.setattr(package_module, "MAX_CONTENT_TOTAL_BYTES", 512)
    report = _linked(make_package, '<img src="figure.bin" alt=""/>',
                     (("content/figure.bin", b"unidentified graphic" + b" " * 5000),),
                     "unread-graphic.iirds")
    assert _subjects(report, "S9") == ["content/figure.bin"]
    assert not _subjects(report, "R43")
    assert not _subjects(report, "S3")
    assert not report.ok


@pytest.mark.parametrize("refusal", ["budget", "per-file"])
def test_an_unread_stylesheet_is_not_classified_as_another_format(
        make_package, monkeypatch, refusal):
    """dfn-iirds-xhtml5#2: "iiRDS XHTML5 stylesheets MUST be in CSS format."
    S9/S16 report refused reads; R74 cannot treat unread bytes as a format.
    """
    from iirds_validate import package as package_module
    from iirds_validate.rules import content

    if refusal == "budget":
        monkeypatch.setattr(package_module, "MAX_CONTENT_TOTAL_BYTES", 512)
    else:
        monkeypatch.setattr(content, "MAX_CONTENT_BYTES", 512)
    body = b"\x89PNG\r\n\x1a\n" + b" " * 5000
    report = _linked(make_package, '<link rel="stylesheet" href="style.bin"/>',
                     (("content/style.bin", body),), "unread-stylesheet.iirds")
    assert _subjects(report, "S9" if refusal == "budget" else "S16") == ["content/style.bin"]
    assert not _subjects(report, "R74")
    assert not _subjects(report, "S3")
    assert not report.ok


@pytest.mark.parametrize("raw,expected", [
    (b'@charset "iso-8859-1";\xe9', '@charset "iso-8859-1";\u00e9'),
    (b'@charset "not-an-encoding";\xff', '@charset "not-an-encoding";\ufffd'),
    (b'@charset "\x00";p{}', '@charset "\x00";p{}'),
    (b'@charset "utf-16";p{}', '@charset "utf-16";p{}'),
    (b'@charset "utf-16le";p{}', '@charset "utf-16le";p{}'),
    (b'@charset "utf-16be";p{}', '@charset "utf-16be";p{}'),
    (b'@charset "rot13";p{}', '@charset "rot13";p{}'),
    (b'\xef\xbb\xbf@charset "iso-8859-1";\xc3\xa9', '@charset "iso-8859-1";\u00e9'),
    (b'\xff\xfe' + '<?xml?>'.encode('utf-16-le'), '<?xml?>'),
    (b'\xfe\xff' + '<?xml?>'.encode('utf-16-be'), '<?xml?>'),
    (b' @charset "iso-8859-1";\xe9', ' @charset "iso-8859-1";\ufffd'),
    (b"@charset 'iso-8859-1';\xe9", "@charset 'iso-8859-1';\ufffd"),
    (b'@charset "' + b' ' * 1010 + b'iso-8859-1";\xe9',
     '@charset "' + ' ' * 1010 + 'iso-8859-1";\ufffd'),
])
def test_stylesheet_decoding_respects_bom_and_the_exact_charset_prefix(raw, expected):
    """CSS Syntax 3 §3.2 restricts the prefix to the first 1024 bytes."""
    from iirds_validate.rules.content import _stylesheet_text

    assert _stylesheet_text(raw) == expected


@pytest.mark.parametrize("label", [b"unknown-encoding", b"bad\x00label"])
def test_unknown_stylesheet_charset_labels_do_not_crash_or_identify_another_format(
        make_package, label):
    """dfn-iirds-xhtml5#2: "iiRDS XHTML5 stylesheets MUST be in CSS format."""
    body = b'@charset "' + label + b'"; p { color: red; }'
    report = _linked(make_package, '<link rel="stylesheet" href="style.css"/>',
                     (("content/style.css", body),), "unknown-charset-stylesheet.iirds")
    assert not _subjects(report, "R74")
    assert not _subjects(report, "S3")


@pytest.mark.parametrize("body", [
    b"GIF89a { color: red; }\np { color: blue; }",
    b"p { color: blue; }",
    b"GIF89a",
    b"GIF89a\x00",
    b"GIF89a { color: red; }\x00",
])
def test_a_gif_identifier_does_not_identify_a_stylesheet_as_an_image(make_package, body):
    """dfn-iirds-xhtml5#2: "iiRDS XHTML5 stylesheets MUST be in CSS format."
    A GIF prefix can be a CSS type selector; a partial header proves no image.
    """
    report = _linked(make_package, '<link rel="stylesheet" href="style.css"/>',
                     (("content/style.css", body),), "gif-selector-stylesheet.iirds")
    assert not _subjects(report, "R74")

@pytest.mark.parametrize("element", ["a", "area"])
def test_extended_document_relations_leave_the_whole_sentence_unclaimed(make_package, element):
    """b-5-2-document-metadata#3: "Relations usually represented by the element <link> in HTML MUST be expressed by means of RDF in iiRDS."
    HTML5 permits an open registry of relation types, including last.
    """
    from iirds_validate.registry import all_rules

    report = _linked(make_package, '<%s rel="last" href="last.xhtml"/>' % element,
                     (("content/last.xhtml", PAGE.format("last").encode()),),
                     "extended-document-relation.iirds")
    assert not _subjects(report, "B5")
    assert all("b-5-2-document-metadata#3" not in rule.covers for rule in all_rules())


@pytest.mark.parametrize("brand", [b"F4A ", b"F4B "])
def test_unconfirmed_audio_brands_are_outside_the_registered_audio_set(make_package, brand):
    """x8-2-1-4-audio-formats#1: "Audio content MUST be encoded as MP3 (ISO/IEC 11172-3, ISO/IEC 13818-3)."
    A brand without a confirmed audio registration does not prove audio tracks.
    """
    from iirds_validate.rules import content

    body = MP4.replace(b"isom", brand, 1)
    assert not content._is_mp4_audio(body)
    report = runner.check(make_package(metadata=A_PROFILE, extra=(
        ("content/unconfirmed.bin", body),)))
    assert _subjects(report, "R44") == ["content/unconfirmed.bin"]
    assert not _subjects(report, "R45")
