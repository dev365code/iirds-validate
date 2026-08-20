"""Appendix B — the content itself, which nothing else checks.

Twenty-five absolute requirements govern iiRDS XHTML5 and neither this project
nor the reference tool looked at a single content file until now. Every rule
here therefore has no second implementation to be compared against, which is
the situation that produced the worst bugs in this project's history. So each
one gets a case that must fire and a case that must not, and the clean case is
taken from the shape tekom's own sample packages use.
"""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import runner

CLEAN = ('<?xml version="1.0" encoding="UTF-8"?>'
         '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">'
         '<head><link rel="stylesheet" type="text/css" href="../a.css"/>'
         '<title>General safety instructions</title></head>'
         '<body id="c_1"><div class="body">'
         '<div data-role="warning" class="note">'
         '<div data-role="signalword-panel"><p data-role="signalword">Warning:</p></div>'
         '<div data-role="message-panel"><ul><li>Risk of electrical shock</li></ul></div>'
         '<div data-role="symbol-panel"><img src="../f.png" width="76"/></div>'
         '</div></div></body></html>')


def package(make_package, xhtml, name="c.iirds",
            source="content/topic1.xhtml", fmt="application/xhtml+xml"):
    metadata = (MINIMAL_RDF
                .replace("<iirds:format>application/xhtml+xml</iirds:format>",
                         "<iirds:format>%s</iirds:format>" % fmt)
                .replace("<iirds:source>content/topic1.xhtml</iirds:source>",
                         "<iirds:source>%s</iirds:source>" % source))
    return make_package(name=name, metadata=metadata, content=(), extra=((source, xhtml),))


def ids(make_package, xhtml, **kw):
    report = runner.check(package(make_package, xhtml, **kw))
    return {f.rule.id for f in report.findings if f.rule.id.startswith("B")}


def test_content_shaped_like_tekoms_own_samples_is_clean(make_package):
    """The clean case is the hazard-statement markup from sample 1, including
    the `type` attribute on `<link>` that appears in neither the global
    attribute list nor any element-specific table. A strict attribute
    whitelist would fail the standard's own examples, so there isn't one."""
    assert not ids(make_package, CLEAN)


@pytest.mark.parametrize("rule_id,fragment", [
    ("B2", "<script>alert(1)</script>"),
    ("B2", "<form><input/></form>"),
    ("B2", "<iframe src='x'></iframe>"),
    ("B2", "<svg></svg>"),
    ("B3", "<marquee>x</marquee>"),
    ("B4", '<p onclick="go()">x</p>'),
    ("B7", '<div data-role="banana">x</div>'),
    ("B7", '<p data-role="symbol-panel">wrong element</p>'),
])
def test_each_prohibition_fires(make_package, rule_id, fragment):
    broken = CLEAN.replace("<ul><li>Risk of electrical shock</li></ul>", fragment)
    assert rule_id in ids(make_package, broken, name="%s.iirds" % abs(hash(fragment)))


def test_content_that_is_not_well_formed_xml(make_package):
    assert "B1" in ids(make_package, "<html><p>unclosed")


def test_link_may_only_be_a_stylesheet(make_package):
    """Every other relation "MUST be expressed by means of RDF in iiRDS", so a
    <link rel="next"> is metadata smuggled past the metadata."""
    broken = CLEAN.replace('<title>', '<link rel="next" href="b.xhtml"/><title>')
    assert "B5" in ids(make_package, broken)


def test_the_file_extension_must_be_xhtml(make_package):
    assert "B6" in ids(make_package, CLEAN, source="content/topic1.html")


def test_a_safety_alert_symbol_belongs_in_the_signal_word_panel(make_package):
    misplaced = CLEAN.replace('<div data-role="symbol-panel"><img src="../f.png" width="76"/></div>',
                              '<div data-role="symbol-panel">'
                              '<img data-role="safety-alert-symbol" src="../f.png"/></div>')
    assert "B8" in ids(make_package, misplaced)

    correct = CLEAN.replace('<p data-role="signalword">Warning:</p>',
                            '<p data-role="signalword">Warning:</p>'
                            '<img data-role="safety-alert-symbol" src="../f.png"/>')
    assert "B8" not in ids(make_package, correct, name="ok8.iirds")


def test_only_one_safety_alert_symbol(make_package):
    two = CLEAN.replace('<p data-role="signalword">Warning:</p>',
                        '<p data-role="signalword">W</p>'
                        '<img data-role="safety-alert-symbol" src="../a.png"/>'
                        '<img data-role="safety-alert-symbol" src="../b.png"/>')
    assert "B8" in ids(make_package, two)


def test_only_files_the_package_calls_xhtml_are_checked(make_package):
    """A PDF rendition is not iiRDS XHTML5 and must not be parsed as if it
    were. The metadata decides, not the file extension."""
    assert not ids(make_package, "<script>this is not xhtml</script>",
                   source="content/manual.pdf", fmt="application/pdf")
