"""The claim this project rests on, as an executable test.

The same iiRDS package, written three legal ways, must produce the same result.
If any of these ever diverge, the tool has regressed into the tree-walking
behaviour it exists to replace.
"""
from __future__ import annotations

from conftest import DESCRIPTION_STYLE_RDF, MINIMAL_JSONLD, MINIMAL_RDF
from iirds_validate import runner


def _summary(report):
    return sorted((f.rule.id, f.violation.message) for f in report.findings)


def test_element_style_and_description_style_agree(make_package):
    """<iirds:Topic> and <rdf:Description><rdf:type> are the same graph.

    They are also where a DOM-based validator quietly stops working: a CSS
    selector for `Topic` cannot match an rdf:Description element, so every rule
    about information units silently checks nothing.
    """
    a = runner.check(make_package(name="a.iirds", metadata=MINIMAL_RDF))
    b = runner.check(make_package(name="b.iirds", metadata=DESCRIPTION_STYLE_RDF))

    assert _summary(a) == _summary(b)
    assert a.checked == b.checked
    assert a.checked > 40, "rules must actually have run"


def test_prefix_does_not_matter(make_package):
    """The second fixture uses `ii:` instead of `iirds:`. Both are valid XML."""
    report = runner.check(make_package(metadata=DESCRIPTION_STYLE_RDF))
    assert report.ok, [f.violation.message for f in report.findings]


def test_jsonld_is_validated_like_rdfxml(make_package):
    """iiRDS 1.3 allows metadata.jsonld. It must get the same rules, not fewer."""
    xml = runner.check(make_package(name="x.iirds", metadata=MINIMAL_RDF))
    js = runner.check(make_package(name="j.iirds", metadata=None, jsonld=MINIMAL_JSONLD))

    assert js.checked == xml.checked
    assert "META-INF/metadata.jsonld" in " ".join(js.notes)
    # Same graph, so the only difference should be the missing metadata.rdf.
    ids = {f.rule.id for f in js.findings} - {f.rule.id for f in xml.findings}
    assert ids <= {"C8"}, ids


def test_jsonld_rules_actually_bite(make_package):
    """A defect expressed in JSON-LD must be caught, not skipped."""
    broken = MINIMAL_JSONLD.replace('"format": "application/xhtml+xml", ', "")
    assert "application/xhtml+xml" not in broken, "the fixture must actually be broken"
    report = runner.check(make_package(metadata=None, jsonld=broken))
    assert "M11" in {f.rule.id for f in report.findings}
