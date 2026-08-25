"""L11 — content the package hides from its own content rules.

The B rules only look at files the package declares to be iiRDS XHTML5, which
is correct: running XHTML5 checks over a PDF would be nonsense. But the
selector is exact, so a rendition that declares any other media type receives
no content checking whatever, and says nothing about it.

That is the failure this project exists to eliminate, one level in. A file
called topic1.xhtml carrying a <script>, a <blink> and a <link rel="next">
comes back clean if the metadata says text/html -- the same package, the same
defects, one word changed in a file nobody reads twice.

The answer is not to check it anyway. It is to say that nothing checked it.
"""
from __future__ import annotations

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

#: Three defects, one per B rule, so silence is unmistakable.
DEFECTIVE = ('<?xml version="1.0" encoding="utf-8"?>'
             '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title>'
             '<link rel="next" href="topic2.xhtml"/></head>'
             '<body><script>alert(1)</script><blink>no</blink></body></html>')


def _package(tmp_path, name, declared, source="content/topic1.xhtml"):
    metadata = MINIMAL_RDF.replace("<iirds:format>application/xhtml+xml</iirds:format>",
                                   "<iirds:format>%s</iirds:format>" % declared)
    metadata = metadata.replace("<iirds:source>content/topic1.xhtml</iirds:source>",
                                "<iirds:source>%s</iirds:source>" % source)
    return build_package(tmp_path, name, metadata=metadata, content=(),
                         extra=((source, DEFECTIVE),))


def _ids(path):
    return {f.rule.id for f in runner.run(path, runner.ALL_KINDS).findings}


def test_the_baseline_is_that_these_defects_are_caught(tmp_path):
    """The control. Declared correctly, all three defects are reported --
    so any silence below is the declaration's doing and not the fixture's."""
    found = _ids(_package(tmp_path, "declared.iirds", "application/xhtml+xml"))
    assert {"B2", "B3", "B5"} <= found


def test_a_dot_xhtml_file_declared_as_something_else_is_reported(tmp_path):
    """The defect. `text/html` on a file named .xhtml silences all ten B
    rules, and the report was empty and green.

    B6 already checks the converse -- content declared as iiRDS XHTML5 that
    does not use the extension. This is the same disagreement seen from the
    other side, and it is the side where the consequence is silence rather
    than a finding.
    """
    found = _ids(_package(tmp_path, "mislabelled.iirds", "text/html"))
    assert "L11" in found


def test_the_finding_says_that_nothing_checked_the_file(tmp_path):
    """A mismatch is not the point; the lost checking is. Somebody reading
    this report needs to know their content went unexamined, not that two
    fields disagree.
    """
    report = runner.run(_package(tmp_path, "wording.iirds", "text/html"), runner.ALL_KINDS)
    finding = next(f for f in report.findings if f.rule.id == "L11")
    assert "content/topic1.xhtml" in (finding.violation.subject or "")
    assert "text/html" in (finding.violation.detail or "")


def test_a_correctly_declared_package_does_not_trip_it(tmp_path):
    assert "L11" not in _ids(_package(tmp_path, "fine.iirds", "application/xhtml+xml"))


def test_a_media_type_parameter_is_not_a_mismatch(tmp_path):
    """`application/xhtml+xml; charset=utf-8` is that media type. The content
    rules already know this; the new rule must not disagree with them."""
    assert "L11" not in _ids(_package(tmp_path, "param.iirds",
                                      "application/xhtml+xml; charset=utf-8"))


def test_a_rendition_that_is_genuinely_something_else_is_left_alone(tmp_path):
    """A PDF rendition declared as a PDF is exactly right, and must not be
    nagged at. The rule keys on the extension, not on the media type alone --
    otherwise it would fire on every non-XHTML5 rendition in every package.
    """
    assert "L11" not in _ids(_package(tmp_path, "pdf.iirds", "application/pdf",
                                      source="content/topic1.pdf"))


def test_a_rendition_with_no_format_at_all_is_m11s_business(tmp_path):
    """Not this rule's. M11 already reports a Rendition without exactly one
    iirds:format, and two findings for one defect help nobody.
    """
    metadata = MINIMAL_RDF.replace(
        "        <iirds:format>application/xhtml+xml</iirds:format>\n", "")
    package = build_package(tmp_path, "noformat.iirds", metadata=metadata, content=(),
                            extra=(("content/topic1.xhtml", DEFECTIVE),))
    found = _ids(package)
    assert "M11" in found
    assert "L11" not in found
