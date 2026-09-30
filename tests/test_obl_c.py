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
                     (("content/manual.bin", PDF),), "c2.iirds")
    assert _subjects(report, "R41") == ["content/manual.bin"], sorted(f.rule.id for f in report.findings)


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
