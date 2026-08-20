"""The claim this project rests on, as an executable test.

The same iiRDS package, written three legal ways, must produce the same result.
If any of these ever diverge, the tool has regressed into the tree-walking
behaviour it exists to replace.
"""
from __future__ import annotations

from conftest import ATTRIBUTE_STYLE_RDF, DESCRIPTION_STYLE_RDF, MINIMAL_JSONLD, MINIMAL_RDF
from iirds_validate import runner


def _summary(report):
    return sorted((f.rule.id, f.violation.message) for f in report.findings)


def test_the_same_graph_written_two_ways_gives_the_same_report(make_package):
    """MINIMAL_RDF and ATTRIBUTE_STYLE_RDF are the same nine triples.

    They share almost no XML structure: one nests a typed element, the other
    uses rdf:Description with an explicit rdf:type, literals as attributes and
    rdf:parseType="Resource". A DOM-based validator has to be written three
    times to read both, and is written once.

    Both packages are *defective* — the rendition has no iirds:format. Comparing
    two clean packages compares two empty lists, which is what this test used to
    do: it would have passed had the tool reported nothing for either file, or
    for any file. A comparison only says something when there is something to
    compare.
    """
    drop = "        <iirds:format>application/xhtml+xml</iirds:format>\n"
    a = runner.check(make_package(name="a.iirds", metadata=MINIMAL_RDF.replace(drop, "")))
    b = runner.check(make_package(name="b.iirds", metadata=ATTRIBUTE_STYLE_RDF.replace(
        "      <x:format>application/xhtml+xml</x:format>\n", "")))

    assert _summary(a), "the fixture must actually be defective, or this proves nothing"
    assert _summary(a) == _summary(b)
    assert a.checked == b.checked
    assert a.checked > 40, "rules must actually have run"


def test_description_style_is_read_as_the_topic_it_describes(make_package):
    """<rdf:Description><rdf:type> is where a DOM-based validator quietly stops
    working: a CSS selector for `Topic` cannot match an rdf:Description element,
    so every rule about information units silently checks nothing.

    Not the same graph as MINIMAL_RDF — this fixture gives the rendition an IRI
    where the other leaves it anonymous, a difference `test_dual_serialisation`
    relies on. What must carry across is that the rules still see a Topic, and
    still object when its rendition has no format.
    """
    report = runner.check(make_package(name="d.iirds", metadata=DESCRIPTION_STYLE_RDF.replace(
        "    <ii:format>application/xhtml+xml</ii:format>\n", "")))

    assert [f.rule.id for f in report.findings] == ["M11"]
    assert report.checked > 40


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
