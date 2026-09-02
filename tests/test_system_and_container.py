"""System rules (S*) and the container rules that finish category C."""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import runner
from iirds_validate.registry import CATALOG, implemented_ids

H_RDF = MINIMAL_RDF.replace(
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
    "    <iirds:formatRestriction>H</iirds:formatRestriction>\n")

INDEX_HTML = "<html><body><h1>Contents</h1></body></html>"


def ids(report):
    return {f.rule.id for f in report.findings}


# --- system ---------------------------------------------------------------

def test_the_system_rules_are_registered_not_fabricated():
    """They were synthesised inside the runner, so coverage reported 0/3 for
    behaviour that already existed and their titles lived in two places."""
    assert {"S1", "S2", "S3"} <= implemented_ids()
    for rid in ("S1", "S2", "S3"):
        assert CATALOG[rid]["kind"] == "system"


def test_s1_when_the_file_is_not_a_zip(tmp_path):
    path = tmp_path / "broken.iirds"
    path.write_bytes(b"definitely not a zip")
    report = runner.check(path)
    assert "C1" in ids(report) and not report.ok


def test_s2_when_nothing_parses(make_package):
    report = runner.lint(make_package(metadata="<rdf:RDF><unclosed>"))
    assert not report.ok


# --- container ------------------------------------------------------------

def test_c9_metadata_that_is_not_an_rdf_document(make_package):
    """C8 asks whether the file is there; C9 asks whether it is RDF/XML at all.

    A document element with no namespace is not a node element -- its name
    is not an IRI -- so this is not RDF/XML by the grammar. (An earlier
    version of this test used `<notrdf xmlns="urn:x"/>`, which *is* a node
    element: a typed node in the `urn:x` namespace. The grammar says so and
    rdflib reads it so; the test was pinning the rule's overreach.)
    """
    report = runner.check(make_package(
        metadata='<?xml version="1.0"?><manual><title>hello</title></manual>'))
    assert "C9" in ids(report)


#: One top-level node element, no rdf:RDF around it: the form RDF/XML §2.6
#: permits -- "When there is only one top-level node element inside rdf:RDF,
#: the rdf:RDF can be omitted although any XML namespaces must still be
#: declared." The package sits inside the topic by is-part-of-package so that
#: one element holds everything MINIMAL_RDF says.
ROOTLESS = """<?xml version="1.0" encoding="utf-8"?>
<iirds:Topic xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
             xmlns:iirds="http://iirds.tekom.de/iirds#" rdf:about="urn:test:topic1">
  <iirds:title>A topic</iirds:title>
  <iirds:is-part-of-package>
    <iirds:Package rdf:about="urn:test:package">
      <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
      <iirds:title>Test package</iirds:title>
    </iirds:Package>
  </iirds:is-part-of-package>
  <iirds:has-rendition>
    <iirds:Rendition>
      <iirds:format>application/xhtml+xml</iirds:format>
      <iirds:source>content/topic1.xhtml</iirds:source>
    </iirds:Rendition>
  </iirds:has-rendition>
</iirds:Topic>
"""
WRAPPED = ROOTLESS.replace(
    '<iirds:Topic xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
    '             xmlns:iirds="http://iirds.tekom.de/iirds#" rdf:about="urn:test:topic1">',
    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
    '         xmlns:iirds="http://iirds.tekom.de/iirds#">\n'
    '<iirds:Topic rdf:about="urn:test:topic1">').replace("</iirds:Topic>\n", "</iirds:Topic>\n</rdf:RDF>\n")


def test_c9_accepts_the_rootless_form_the_grammar_permits(make_package):
    """The obligation C9 covers asks for RDF 1.1 XML syntax and cites the
    grammar; the grammar's §2.6 lets the rdf:RDF element go when one node
    element is all there is. rdflib reads that form into the same graph as
    the wrapped one; the rule reported it as not RDF, with a remedy claiming
    no parser would read a statement from it."""
    from rdflib.compare import isomorphic

    from iirds_validate.context import load_context
    from iirds_validate.package import open_package

    assert "</rdf:RDF>" in WRAPPED and "</rdf:RDF>" not in ROOTLESS
    rootless, wrapped = make_package(metadata=ROOTLESS), make_package(metadata=WRAPPED)
    with open_package(rootless) as a, open_package(wrapped) as b:
        assert isomorphic(load_context(a).graph, load_context(b).graph)
    plain, framed = runner.check(rootless), runner.check(wrapped)
    assert "C9" not in ids(plain)
    assert plain.ok and framed.ok
    assert ids(plain) == ids(framed)


def test_c9_accepts_rdf_description_as_the_document_element(make_package):
    metadata = ROOTLESS.replace("<iirds:Topic ", "<rdf:Description ").replace("</iirds:Topic>", "</rdf:Description>") \
        .replace('rdf:about="urn:test:topic1">', 'rdf:about="urn:test:topic1"><rdf:type rdf:resource="http://iirds.tekom.de/iirds#Topic"/>')
    assert "C9" not in ids(runner.check(make_package(metadata=metadata)))


def test_c9_accepts_an_empty_rdf_root(make_package):
    """`<rdf:RDF/>` is RDF/XML that says nothing; the graph rules, not this
    one, say what is missing."""
    report = runner.check(make_package(
        metadata='<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>'))
    assert "C9" not in ids(report)
    assert "M3" in ids(report)


def test_c9_leaves_a_namespaced_document_to_the_graph_rules(make_package):
    """An XHTML file named metadata.rdf is, to the grammar, one typed node
    element of the XHTML vocabulary: RDF/XML that is not about iiRDS. Not
    C9's finding -- the graph rules say there is no package, and lint says
    the classes are nobody's."""
    xhtml = ('<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
             '<head><title>t</title></head><body><p>x</p></body></html>')
    package = make_package(metadata=xhtml)
    report = runner.check(package)
    assert "C9" not in ids(report)
    assert "M3" in ids(report)
    assert "L5" in ids(runner.lint(package))


def test_c9_is_silent_when_the_reader_refused_the_document(make_package):
    """A document element the grammar reserves (`rdf:li` here) is not a node
    element, and rdflib refuses it before this rule looks: C16.1 owns it."""
    report = runner.check(make_package(
        metadata='<?xml version="1.0"?><rdf:li xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>'))
    assert "C16.1" in ids(report)
    assert "C9" not in ids(report)


@pytest.mark.parametrize("tag,verdict", [
    ("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF", True),          # doc
    ("{http://iirds.tekom.de/iirds#}Package", True),                      # a node element
    ("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description", True),   # the untyped node element
    ("{urn:x}notrdf", True),                                              # a node element in any vocabulary
    ("{http://www.w3.org/1999/xhtml}html", True),
    ("manual", False),                                                    # no namespace: not an IRI
    ("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li", False),           # reserved by §7.2.5
    ("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", False),
    ("{foo}bar", False),                                                  # `foobar` is no absolute IRI
])
def test_the_rdfxml_criterion_is_the_grammars(tag, verdict):
    """§7.2.1: a standalone document starts with production doc *or*
    nodeElement; §7.2.5: a node element's name is any absolute IRI except
    the core syntax terms, rdf:li and the old terms."""
    from iirds_validate.context import is_rdfxml_document_element

    assert is_rdfxml_document_element(tag) is verdict


def test_c9_accepts_an_unusual_prefix(make_package):
    """`<r:RDF xmlns:r="...">` is the same document. Matching on the literal
    string "<rdf:RDF" would reject it."""
    metadata = (MINIMAL_RDF
                .replace("rdf:RDF", "r:RDF")
                .replace("xmlns:rdf=", "xmlns:r=")
                .replace("rdf:about", "r:about"))
    assert "C9" not in ids(runner.check(make_package(metadata=metadata)))


def test_c11_1_content_file_in_the_root(make_package):
    report = runner.check(make_package(extra=(("stray.pdf", "x"),)))
    assert "C11.1" in ids(report)


def test_c11_1_ignores_files_that_are_not_content(make_package):
    """A stray readme is untidy, not a conformance failure."""
    report = runner.check(make_package(extra=(("readme.txt", "x"),)))
    assert "C11.1" not in ids(report)


def test_c11_1h_allows_index_html_in_the_root_of_a_handover_package(make_package):
    """iiRDS/H *requires* index.html in the root, so the ordinary rule against
    HTML in the root cannot apply to it."""
    plain = runner.check(make_package(name="plain.iirds", extra=(("index.html", INDEX_HTML),)))
    assert "C11.1" in ids(plain)

    handover = runner.check(make_package(name="h.iirds", metadata=H_RDF,
                                         jsonld="{}", extra=(("index.html", INDEX_HTML),)))
    assert "C11.1" not in ids(handover)
    assert "C11.1H" not in ids(handover)
    assert "C11.2" not in ids(handover)


def test_c11_2_handover_package_without_a_content_list(make_package):
    report = runner.check(make_package(metadata=H_RDF, jsonld="{}"))
    assert "C11.2" in ids(report)


def test_c11_2_content_list_must_actually_be_html(make_package):
    report = runner.check(make_package(metadata=H_RDF, jsonld="{}",
                                       extra=(("index.html", "not html at all"),)))
    assert "C11.2" in ids(report)


def test_c12_content_file_in_meta_inf(make_package):
    report = runner.check(make_package(extra=(("META-INF/leaflet.pdf", "x"),)))
    assert "C12" in ids(report)


def test_container_category_is_complete():
    container = {rid for rid, m in CATALOG.items() if m["kind"] == "container"}
    assert container <= implemented_ids(), sorted(container - implemented_ids())


# --- what follows from "not RDF/XML" is not the package's own -------------------

NOT_RDFXML = '<?xml version="1.0"?><manual><title>hello</title></manual>'


def test_a_document_that_is_not_rdfxml_yields_no_graph_findings(make_package):
    """rdflib reads `<manual>` as a class named manual, and the graph rules
    used to run on that: "declares no iirds:Package", "proprietary class
    `manual` not linked" -- every finding true, every one a consequence of
    C9. A graph read from a document that is not RDF/XML is not the
    package's metadata and is not admitted as such; S2 says why nothing
    could be checked."""
    report = runner.run(make_package(metadata=NOT_RDFXML), runner.ALL_KINDS)
    found = ids(report)
    assert "C9" in found and "S2" in found
    assert "M3" not in found and "L5" not in found
    s2 = [f for f in report.findings if f.rule.id == "S2"][0]
    assert "not an RDF/XML document (document element is manual)" in (s2.violation.detail or "")
    assert any("the graph rules had nothing to check" in n for n in report.notes)
    assert not report.ok


def test_the_json_report_says_which_finding_follows(make_package):
    report = runner.check(make_package(metadata=NOT_RDFXML))
    assert [f.rule.id for f in report.findings] == ["C9", "S2"]
    listed = report.as_dict()["findings"]
    assert listed[0]["diagnosis"] is None
    assert listed[-1]["diagnosis"] == "consequence"


def test_a_json_ld_twin_keeps_the_graph_rules_running(make_package):
    """metadata.jsonld beside a metadata.rdf that is not RDF/XML: the graph
    comes from the JSON-LD, C9 is reported, and nothing else follows."""
    from conftest import MINIMAL_JSONLD

    report = runner.check(make_package(metadata=NOT_RDFXML, jsonld=MINIMAL_JSONLD))
    assert "C9" in ids(report)
    assert "S2" not in ids(report) and "M3" not in ids(report)
    assert any("metadata read from META-INF/metadata.jsonld" in n for n in report.notes)


def test_unparseable_metadata_no_longer_reports_the_absence_of_a_package_on_top(make_package):
    """The note said the graph rules could not run; M3 fired anyway, on an
    empty graph. One absence, said once, by S2."""
    report = runner.check(make_package(metadata=MINIMAL_RDF.replace("</rdf:RDF>", "")))
    assert "C16.1" in ids(report) and "S2" in ids(report)
    assert "M3" not in ids(report)
