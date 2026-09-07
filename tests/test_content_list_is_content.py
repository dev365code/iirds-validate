"""The one file in a handover package no content rule was looking at.

Appendix B's rules read "every declared XHTML file": the population is what
the metadata names as an `iirds:Rendition` with an XHTML media type. Section
8.3.1.1 says the content list is not an information unit and MUST NOT be
referenced in the metadata file -- R40 reports a package that references it --
and it also says the content list MUST be based on iiRDS XHTML 5.

Both are true at once, and together they made a hole. The file the standard
requires to obey appendix B is the one file the standard forbids declaring,
and the rules that enforce appendix B only look at what is declared. So a
handover package could carry a content list built from scripts, forms and
iframes -- three things appendix B says MUST NOT be used -- and every content
rule stayed silent, on a file a person opens in a browser.

Measured before the repair: `<script>`, `<form>` and `<iframe>` together in
`index.html` drew C16.2, M15.2, M15.3, M15.5, M15.7a, M15.8, M15.9 and R13,
and not one finding from a B rule.

The prohibition is what made the blind spot. That is the shape worth keeping
in mind: a rule that makes a package conformant can be the reason a checker
stops looking at part of it.
"""
from __future__ import annotations

from conftest import build_package
from iirds_validate import runner

HANDOVER = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:formatRestriction>H</iirds:formatRestriction>
    <iirds:title>T</iirds:title>
  </iirds:Package>
  <iirds:Document rdf:about="urn:test:d1">
    <iirds:title>D</iirds:title>
    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>application/pdf</iirds:format>
        <iirds:source>content/a.pdf</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Document>
</rdf:RDF>
"""

CLEAN_LIST = ("<html><head><title>Content list</title></head><body>"
              "<table><tr><th>Title</th></tr><tr><td>D</td></tr></table>"
              "</body></html>")


def report(tmp_path, body, name="h.iirds", metadata=HANDOVER):
    package = build_package(tmp_path, name, metadata=metadata,
                            content=("content/a.pdf",), extra=(("index.html", body),))
    return runner.run(package, runner.ALL_KINDS)


def fired(tmp_path, body, name="h.iirds", metadata=HANDOVER):
    return {f.rule.id for f in report(tmp_path, body, name, metadata).findings}


def test_a_conformant_content_list_draws_no_content_finding(tmp_path):
    """First, so that the three below are not satisfied by a rule that reports
    every content list there is."""
    assert not [r for r in fired(tmp_path, CLEAN_LIST) if r.startswith("B")]


def test_a_script_in_the_content_list_is_reported(tmp_path):
    body = CLEAN_LIST.replace("</body>", "<script>alert(1)</script></body>")
    assert "B2" in fired(tmp_path, body, "script.iirds")


def test_a_form_in_the_content_list_is_reported(tmp_path):
    body = CLEAN_LIST.replace("</body>", '<form><input name="x"/></form></body>')
    assert "B2" in fired(tmp_path, body, "form.iirds")


def test_an_iframe_in_the_content_list_is_reported(tmp_path):
    body = CLEAN_LIST.replace("</body>", '<iframe src="x"></iframe></body>')
    assert "B2" in fired(tmp_path, body, "iframe.iirds")


def test_the_finding_names_the_content_list(tmp_path):
    """A reader with three files and one finding needs to know which file."""
    body = CLEAN_LIST.replace("</body>", "<script>alert(1)</script></body>")
    hits = [f for f in report(tmp_path, body, "named.iirds").findings if f.rule.id == "B2"]
    assert hits
    assert any("index.html" in (f.violation.subject or "") for f in hits), \
        [f.violation.subject for f in hits]


def test_an_unrestricted_package_keeps_its_index_html_to_itself(tmp_path):
    """`index.html` is the content list where a profile requires one. In an
    unrestricted package it is an ordinary file, and an ordinary file is
    content when the metadata says it is -- which is the rule that was already
    there, and this must not quietly widen it."""
    unrestricted = HANDOVER.replace(
        "    <iirds:formatRestriction>H</iirds:formatRestriction>\n", "")
    body = CLEAN_LIST.replace("</body>", "<script>alert(1)</script></body>")
    assert "B2" not in fired(tmp_path, body, "plain.iirds", unrestricted)
