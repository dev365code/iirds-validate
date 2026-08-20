"""The B rules against documents that are hostile, unusual, or merely legal.

Every case here passed silently before it was written, and each one passed for
a different reason. Together they are the argument for why a content rule needs
its own entry gate: the rule can be right and still never see the document.
"""
from __future__ import annotations

import time

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

XHTML = "http://www.w3.org/1999/xhtml"


def _b_rules(path):
    return sorted({f.rule.id for f in runner.check(path).findings if f.rule.id.startswith("B")})


def _document(body: str, *, xmlns: bool = True, doctype: str = "") -> str:
    ns = ' xmlns="%s"' % XHTML if xmlns else ""
    return ('<?xml version="1.0" encoding="utf-8"?>%s<html%s><head><title>t</title>'
            "</head><body>%s</body></html>" % (doctype, ns, body))


def test_entity_expansion_is_refused_rather_than_expanded(tmp_path):
    """A 400-byte file that expands to gigabytes must not be parsed.

    The billion-laughs shape. Nothing about it is invalid iiRDS, so no rule was
    ever going to reject it on its merits — the parser had to die first, and it
    died holding the whole run. Refusing to parse it is both the safe answer and
    the correct one: a document whose text nobody can compute is not a document
    a reader can read, which is exactly what the B rules are about.
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
    assert "B1" in {f.rule.id for f in report.findings}
    assert not report.ok, "a document that cannot be read must not pass"


def test_media_type_parameters_do_not_disable_the_content_rules(tmp_path):
    """`application/xhtml+xml; charset=utf-8` is that media type, with a parameter.

    RFC 2045 says so and nothing in iiRDS says otherwise, so a package declaring
    the charset — which is good practice — silently skipped all eight B rules.
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
