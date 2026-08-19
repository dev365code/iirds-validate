"""System rules (S*) and the container rules that finish category C."""
from __future__ import annotations

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
    """C8 asks whether the file is there; C9 asks whether it is RDF at all."""
    report = runner.check(make_package(
        metadata='<?xml version="1.0"?><notrdf xmlns="urn:x"/>'))
    assert "C9" in ids(report)


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
