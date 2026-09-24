"""Section 8.2.1: the content formats an iiRDS/A package may carry.

Section 8.2 is iiRDS/A's, so the rules here apply to a package that declares
that profile and to no other. The fixtures declare it, and each case has a
clean control beside it so a rule that fires on everything cannot pass for
one that reads the sentence.

None of these rules claims its sentence. R41, R42, R44 and R45 read what a
rendition declares, and the sentences bind a file a page points at as well;
R43 reads every file and knows four raster formats by their bytes. `B6` holds iiRDS XHTML5 renditions to
`.xhtml` the same way, and in an iiRDS/A package its finding is an error
rather than the warning it is elsewhere.
"""
from __future__ import annotations

from iirds_validate import runner
from iirds_validate.model import Severity
from make_fixture_package import MINIMAL_RDF

A_PROFILE = MINIMAL_RDF.replace(
    "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
    "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
    "    <iirds:formatRestriction>A</iirds:formatRestriction>")

XHTML = ('<?xml version="1.0" encoding="utf-8"?>\n'
         '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title></head>'
         '<body><p>Text</p></body></html>\n')


def _structured_text_named(make_package, source, metadata=A_PROFILE, name="a.iirds"):
    metadata = metadata.replace("<iirds:source>content/topic1.xhtml</iirds:source>",
                                "<iirds:source>%s</iirds:source>" % source)
    return runner.check(make_package(name=name, metadata=metadata, content=(),
                                     extra=((source, XHTML),)))


def test_the_fixture_is_an_iirds_a_package(make_package):
    assert _structured_text_named(make_package, "content/topic1.xhtml").variant == "A"


def test_structured_text_not_named_xhtml_is_refused_in_iirds_a(make_package):
    """x8-2-1-1-text-formats#2: "The file extension MUST be .xhtml.\""""
    report = _structured_text_named(make_package, "content/topic1.html")
    b6 = [f for f in report.findings if f.rule.id == "B6"]
    assert b6, "no B6 for structured text named .html: %s" % sorted(
        f.rule.id for f in report.findings)
    assert all(f.severity is Severity.ERROR for f in b6), [f.severity for f in b6]
    assert not report.ok


def test_the_same_file_named_xhtml_draws_nothing(make_package):
    report = _structured_text_named(make_package, "content/topic1.xhtml")
    assert "B6" not in {f.rule.id for f in report.findings}


def test_outside_iirds_a_the_same_file_is_a_warning(make_package):
    """The sentence is iiRDS/A's. Appendix B's copy of it still reaches an
    unrestricted package, where content rules report as warnings -- so the
    finding is there and the package is not failed for it."""
    report = _structured_text_named(make_package, "content/topic1.html",
                                    metadata=MINIMAL_RDF, name="u.iirds")
    assert report.variant != "A"
    b6 = [f for f in report.findings if f.rule.id == "B6"]
    assert b6 and all(f.severity is Severity.WARNING for f in b6), [
        (f.rule.id, f.severity) for f in report.findings]


# ---------------------------------------------------------------------------
# x8-2-1-1-text-formats#5: "The file extension MUST be .pdf."
#
# R41 reads the renditions declared as PDF and claims neither this sentence
# nor the one before it: this one binds a PDF a page points at too, and
# whether a file conforms to ISO 19005-3 is a question for a PDF/A validator.
# ---------------------------------------------------------------------------

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _pdf_named(make_package, source, metadata=A_PROFILE, name="p.iirds"):
    metadata = (metadata
                .replace("<iirds:format>application/xhtml+xml</iirds:format>",
                         "<iirds:format>application/pdf</iirds:format>")
                .replace("<iirds:source>content/topic1.xhtml</iirds:source>",
                         "<iirds:source>%s</iirds:source>" % source))
    return runner.check(make_package(name=name, metadata=metadata, content=(),
                                     extra=((source, PDF),)))


def _r41(report):
    return [f for f in report.findings if f.rule.id == "R41"]


def test_a_pdf_not_named_pdf_is_refused_in_iirds_a(make_package):
    report = _pdf_named(make_package, "content/manual.pdfa")
    found = _r41(report)
    assert found, "no R41 for a PDF named .pdfa: %s" % sorted(f.rule.id for f in report.findings)
    assert [f.violation.subject for f in found] == ["content/manual.pdfa"]
    assert all(f.severity is Severity.ERROR for f in found)


def test_a_pdf_named_pdf_draws_nothing_in_either_case(make_package):
    """Case-blind, as B6 is for .xhtml: a filesystem that shows `.PDF` is
    naming the same extension."""
    assert not _r41(_pdf_named(make_package, "content/manual.pdf", name="p1.iirds"))
    assert not _r41(_pdf_named(make_package, "content/manual.PDF", name="p2.iirds"))


def test_the_pdf_rule_is_iirds_a_s_alone(make_package):
    """Section 8.2 is iiRDS/A. An unrestricted package that names its PDF
    `.pdfa` breaks nothing this sentence says."""
    report = _pdf_named(make_package, "content/manual.pdfa", metadata=MINIMAL_RDF, name="u2.iirds")
    assert report.variant != "A"
    assert not _r41(report)


# ---------------------------------------------------------------------------
# x8-2-1-2-graphics-formats#3: "The file extension MUST be .svg for
# non-compressed files and .svgz for gzip-compressed files."
#
# The extension depends on the bytes, so the rule reads the first two of them:
# a gzip stream opens with 1f 8b. Two bytes are what it needs; the bounded read
# hands back three.
# ---------------------------------------------------------------------------

import gzip  # noqa: E402

SVG = (b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
       b'width="1" height="1"/>\n')
SVGZ = gzip.compress(SVG, mtime=0)


def _svg_named(make_package, source, body, metadata=A_PROFILE, name="s.iirds"):
    metadata = (metadata
                .replace("<iirds:format>application/xhtml+xml</iirds:format>",
                         "<iirds:format>image/svg+xml</iirds:format>")
                .replace("<iirds:source>content/topic1.xhtml</iirds:source>",
                         "<iirds:source>%s</iirds:source>" % source))
    return runner.check(make_package(name=name, metadata=metadata, content=(),
                                     extra=((source, body),)))


def _r42(report):
    return [f for f in report.findings if f.rule.id == "R42"]


def test_an_svg_is_named_for_whether_it_is_compressed(make_package):
    assert not _r42(_svg_named(make_package, "content/a.svg", SVG, name="s1.iirds"))
    assert not _r42(_svg_named(make_package, "content/a.svgz", SVGZ, name="s2.iirds"))


def test_an_uncompressed_svg_named_svgz_is_refused(make_package):
    found = _r42(_svg_named(make_package, "content/a.svgz", SVG, name="s3.iirds"))
    assert [f.violation.subject for f in found] == ["content/a.svgz"]
    assert all(f.severity is Severity.ERROR for f in found)


def test_a_compressed_svg_named_svg_is_refused(make_package):
    found = _r42(_svg_named(make_package, "content/a.svg", SVGZ, name="s4.iirds"))
    assert [f.violation.subject for f in found] == ["content/a.svg"]


def test_an_svg_named_neither_is_refused(make_package):
    assert _r42(_svg_named(make_package, "content/a.xml", SVG, name="s5.iirds"))


def test_the_svg_rule_is_iirds_a_s_alone(make_package):
    report = _svg_named(make_package, "content/a.xml", SVG, metadata=MINIMAL_RDF, name="u3.iirds")
    assert report.variant != "A"
    assert not _r42(report)


# ---------------------------------------------------------------------------
# R43: the raster formats section 8.2.1.2 leaves out, by a file's bytes.
#
# A graphic is used whether a rendition declares it or an XHTML page points
# at it, so the rule reads what each file is rather than what the metadata
# says it is: a GIF named .png is still a GIF. It recognises the raster
# formats it has a signature for, and says so; one it does not know passes.
# Neither #1 ("Raster graphics MUST be encoded as"), which would need every
# other format recognised, nor #6 ("Only JPG and PNG graphics according to
# this section MUST be used"), a restriction on the graphics an SVG uses, is
# claimed.
# ---------------------------------------------------------------------------

GIF = b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def _with_graphic(make_package, path, body, metadata=A_PROFILE, name="g.iirds"):
    return runner.check(make_package(name=name, metadata=metadata, content=(),
                                     extra=(("content/topic1.xhtml", XHTML), (path, body))))


def _r43(report):
    return [f for f in report.findings if f.rule.id == "R43"]


def test_a_gif_in_an_iirds_a_package_is_refused(make_package):
    found = _r43(_with_graphic(make_package, "content/logo.gif", GIF))
    assert [f.violation.subject for f in found] == ["content/logo.gif"]
    assert all(f.severity is Severity.ERROR for f in found)


def test_a_gif_is_a_gif_whatever_it_is_called(make_package):
    assert _r43(_with_graphic(make_package, "content/logo.png", GIF, name="g2.iirds"))


def test_png_and_jpeg_draw_nothing(make_package):
    assert not _r43(_with_graphic(make_package, "content/a.png", PNG, name="g3.iirds"))
    assert not _r43(_with_graphic(make_package, "content/a.jpg", JPEG, name="g4.iirds"))


def test_the_graphics_rule_is_iirds_a_s_alone(make_package):
    report = _with_graphic(make_package, "content/logo.gif", GIF, metadata=MINIMAL_RDF, name="u4.iirds")
    assert report.variant != "A"
    assert not _r43(report)


# ---------------------------------------------------------------------------
# x8-2-1-3-video-formats#2 and x8-2-1-4-audio-formats#2: "The file extension
# MUST be .mp4." / ".mp3."
#
# Video and audio content is what a rendition declares with a video/ or audio/
# media type, whatever the subtype: `video/webm` is video content, and is the
# case the sentence exists for. No sentence here is claimed: a video or an
# audio file a page points at is not read, the video encoding sentence is held
# in the index without the codecs that complete it, and conformance to ISO/IEC
# 11172-3 is a question for a decoder.
# ---------------------------------------------------------------------------


def _media_named(make_package, media_type, source, metadata=A_PROFILE, name="m.iirds"):
    metadata = (metadata
                .replace("<iirds:format>application/xhtml+xml</iirds:format>",
                         "<iirds:format>%s</iirds:format>" % media_type)
                .replace("<iirds:source>content/topic1.xhtml</iirds:source>",
                         "<iirds:source>%s</iirds:source>" % source))
    return runner.check(make_package(name=name, metadata=metadata, content=(),
                                     extra=((source, b"\x00" * 32),)))


def _fired(report, rule_id):
    return [f for f in report.findings if f.rule.id == rule_id]


def test_video_not_named_mp4_is_refused_whatever_its_subtype(make_package):
    for n, (media, source) in enumerate((("video/mp4", "content/clip.mov"),
                                         ("video/webm", "content/clip.webm"))):
        found = _fired(_media_named(make_package, media, source, name="v%d.iirds" % n), "R44")
        assert [f.violation.subject for f in found] == [source], (media, source)


def test_video_named_mp4_draws_nothing(make_package):
    assert not _fired(_media_named(make_package, "video/mp4", "content/clip.MP4", name="v9.iirds"), "R44")


def test_audio_not_named_mp3_is_refused_whatever_its_subtype(make_package):
    for n, (media, source) in enumerate((("audio/mpeg", "content/voice.wav"),
                                         ("audio/ogg", "content/voice.ogg"))):
        found = _fired(_media_named(make_package, media, source, name="a%d.iirds" % n), "R45")
        assert [f.violation.subject for f in found] == [source], (media, source)


def test_audio_named_mp3_draws_nothing(make_package):
    assert not _fired(_media_named(make_package, "audio/mpeg", "content/voice.mp3", name="a9.iirds"), "R45")


def test_the_media_rules_are_iirds_a_s_alone(make_package):
    video = _media_named(make_package, "video/webm", "content/c.webm", metadata=MINIMAL_RDF, name="u5.iirds")
    audio = _media_named(make_package, "audio/ogg", "content/v.ogg", metadata=MINIMAL_RDF, name="u6.iirds")
    assert video.variant != "A" and not _fired(video, "R44")
    assert audio.variant != "A" and not _fired(audio, "R45")


# ---------------------------------------------------------------------------
# The first bytes R42 and R43 read: not past a spent content budget, charged
# to it where the file is a rendition, reused where B1 already read them, and
# a file that cannot be read reported by the rule that asked. The first
# version caught every failure and went on, and a file nobody could read
# passed.
# ---------------------------------------------------------------------------

class _Package:
    """A container that hands over a GIF, or fails the way it is told to."""

    def __init__(self, fails=None):
        self.fails, self.charged, self.reads = fails, 0, 0

    def read_bounded(self, name, limit):
        self.reads += 1
        if self.fails is not None:
            raise self.fails
        return GIF[:limit + 1], len(GIF) > limit

    def charge(self, count):
        self.charged += count


class _Run:
    def __init__(self, package):
        self.package = package


def test_first_bytes_are_not_read_once_the_content_budget_is_spent():
    from iirds_validate.rules.content import _head

    run = _Run(_Package())
    run.__dict__["content_budget"] = (4096, 1024, "content/big.xhtml")
    assert _head(run, "content/logo.gif", 12, rendition=True) == (None, None)
    assert run.package.reads == 0


def test_a_rendition_s_first_bytes_are_charged_and_another_file_s_are_not():
    from iirds_validate.rules.content import _head

    rendition, other = _Run(_Package()), _Run(_Package())
    assert _head(rendition, "content/logo.gif", 12, rendition=True) == (GIF[:12], None)
    assert rendition.package.charged == 13      # the read's limit plus one, as read
    assert _head(other, "content/spare.gif", 12, rendition=False) == (GIF[:12], None)
    assert other.package.charged == 0


def test_bytes_b1_read_are_used_and_an_empty_file_is_empty():
    from iirds_validate.rules.content import _head

    run = _Run(_Package(fails=AssertionError("read twice")))
    run.__dict__["_content_bytes"] = {"content/a.svgz": (b"", None),
                                      "content/b.svgz": (b"", "not read: refused")}
    assert _head(run, "content/a.svgz", 2, rendition=True) == (b"", None)
    assert _head(run, "content/b.svgz", 2, rendition=True) == (None, None)
    assert run.package.reads == 0


def test_a_first_read_that_fails_comes_back_as_a_reason():
    from iirds_validate.rules.content import _head

    run = _Run(_Package(OSError("refused")))
    assert _head(run, "content/logo.gif", 12, rendition=False) == (None, "not read: refused")
    assert "content_unexamined" not in run.__dict__


def test_a_fault_of_this_code_reaches_the_runner():
    import pytest

    from iirds_validate.rules.content import _head

    with pytest.raises(TypeError):
        _head(_Run(_Package(TypeError("ours"))), "content/logo.gif", 12, rendition=True)


def _refusing(monkeypatch, refused):
    from iirds_validate.package import Package

    original = Package.read_bounded

    def refusing(self, name, limit):
        if name == refused:
            raise OSError("refused")
        return original(self, name, limit)

    monkeypatch.setattr(Package, "read_bounded", refusing)


def test_a_declared_svg_nobody_can_read_is_reported_rather_than_passed(make_package, monkeypatch):
    _refusing(monkeypatch, "content/figure.svgz")
    report = _svg_named(make_package, "content/figure.svgz", SVG, name="unread.iirds")
    [found] = _r42(report)
    assert found.violation.subject == "content/figure.svgz"
    assert "could not be read" in found.violation.message
    assert "S3" not in {f.rule.id for f in report.findings}


def test_a_graphic_a_page_points_at_that_cannot_be_read_is_reported(make_package, monkeypatch):
    _refusing(monkeypatch, "content/logo.gif")
    [found] = _r43(_with_graphic(make_package, "content/logo.gif", GIF, name="unread-g.iirds"))
    assert found.violation.subject == "content/logo.gif"
    assert "could not be read" in found.violation.message


def test_a_rendition_s_read_that_crosses_the_budget_is_recorded_for_s9():
    from iirds_validate.package import ContentBudgetExceeded
    from iirds_validate.rules.content import _head

    class Crossing(_Package):
        def charge(self, count):
            raise ContentBudgetExceeded(4099, 4096)

    run = _Run(Crossing())
    assert _head(run, "content/logo.gif", 12, rendition=True) == (None, None)
    assert run.__dict__["content_budget"] == (4099, 4096, "content/logo.gif")


def test_a_method_no_bounded_read_can_be_made_of_is_left_to_s14():
    from iirds import UnreadableMethod
    from iirds_validate.rules.content import _head

    run = _Run(_Package(fails=UnreadableMethod("content/logo.gif", 12)))
    assert _head(run, "content/logo.gif", 12, rendition=True) == (None, None)


TIFF_LE = b"II*\x00" + b"\x00" * 12
TIFF_BE = b"MM\x00*" + b"\x00" * 12
WEBP = b"RIFF" + b"\x00" * 4 + b"WEBPVP8 " + b"\x00" * 8
BMP = b"BM" + b"\x36\x00\x00\x00" + b"\x00\x00\x00\x00" + b"\x36" + b"\x00" * 7


def test_every_raster_format_r43_knows_is_refused(make_package):
    for number, (body, known) in enumerate(((TIFF_LE, "TIFF"), (TIFF_BE, "TIFF"),
                                            (WEBP, "WebP"), (BMP, "BMP"))):
        found = _r43(_with_graphic(make_package, "content/g%d.png" % number, body,
                                   name="raster-%d.iirds" % number))
        assert [f.violation.message for f in found] == [
            "a %s graphic, where iiRDS/A allows JPEG and PNG" % known], known


def test_two_letters_are_not_a_bmp(make_package):
    """BMP's signature is two letters; a file that opens with them and not
    with the zero bytes the format fixes after its size is not one."""
    assert not _r43(_with_graphic(make_package, "content/notes.txt", b"BMW service notes\n",
                                  name="bmw.iirds"))


def test_r43_leaves_mimetype_and_meta_inf_alone(make_package):
    report = runner.check(make_package(name="meta.iirds", metadata=A_PROFILE, content=(),
                                       extra=(("content/topic1.xhtml", XHTML),
                                              ("META-INF/logo.gif", GIF))))
    assert "META-INF/logo.gif" not in [f.violation.subject for f in _r43(report)]


def test_the_svg_extension_is_compared_without_regard_to_case(make_package):
    assert not _r42(_svg_named(make_package, "content/FIG.SVG", SVG, name="upper-s.iirds"))
    assert not _r42(_svg_named(make_package, "content/FIG.SVGZ", SVGZ, name="upper-z.iirds"))
