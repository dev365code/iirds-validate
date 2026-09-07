"""The one file in a handover package the metadata must not mention.

Section 8.3.1.1 requires an iiRDS/H package to carry a content list as an HTML
file named `index.html` in the root — C11.2 asks for it — and then says of it:

    It is not an information unit and MUST NOT be referenced in the metadata
    file.

That is the other half of a sentence this suite already relies on. R37 reports
a content file no `iirds:Rendition` names, and excludes `index.html` from that
population; the exclusion is not a convenience, it is this sentence. Written
without it, R37 reports every conformant handover package, because every one of
them contains exactly one file that nothing may point at.

So the pair is: nobody has to name it, and nobody may. Only the first half was
checked.
"""
from __future__ import annotations

import pytest

from conftest import build_package
from iirds_validate import runner
from iirds_validate.model import Severity

HEAD = """<?xml version="1.0" encoding="utf-8"?>
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
%s</rdf:RDF>
"""

CONTENT = ("content/a.pdf", "index.html")


def fired(tmp_path, extra="", name="h.iirds"):
    package = build_package(tmp_path, name, metadata=HEAD % extra, content=CONTENT)
    return {f.rule.id for f in runner.check(package).findings}


def test_a_conformant_handover_package_is_not_reported(tmp_path):
    """`index.html` is present and named by nothing, which is the shape the
    section requires."""
    assert "R40" not in fired(tmp_path)


#: Every way the metadata can come to name the file, because "referenced" is
#: about the reference and not about the property that carries it. A rendition
#: source is the one a producer reaches for; the others are what a producer
#: reaches for when the first one is reported.
REFERENCES = {
    "a rendition source": """  <iirds:Document rdf:about="urn:test:d2">
    <iirds:title>Listing</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>text/html</iirds:format>
        <iirds:source>index.html</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Document>
""",
    "a leading slash": """  <iirds:Document rdf:about="urn:test:d2">
    <iirds:title>Listing</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>text/html</iirds:format>
        <iirds:source>/index.html</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Document>
""",
    "a dot-slash path": """  <iirds:Document rdf:about="urn:test:d2">
    <iirds:title>Listing</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>text/html</iirds:format>
        <iirds:source>./index.html</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Document>
""",
    "a percent-escaped path": """  <iirds:Document rdf:about="urn:test:d2">
    <iirds:title>Listing</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>text/html</iirds:format>
        <iirds:source>inde%78.html</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Document>
""",
}


@pytest.mark.parametrize("label", sorted(REFERENCES))
def test_the_metadata_naming_the_content_list_is_reported(tmp_path, label):
    """One spelling is what a producer writes; the rest are what the same
    producer writes next. A rule keyed on the literal string would report the
    first and pass the other three, and the file it is about is the same file
    in all four."""
    assert "R40" in fired(tmp_path, REFERENCES[label]), label


def test_a_reference_to_another_html_file_is_not_reported(tmp_path):
    """The sentence is about the content list, not about HTML. A handover
    package may not have other HTML renditions under section 8.3.3, but that
    is a different sentence with a different rule."""
    other = """  <iirds:Document rdf:about="urn:test:d2">
    <iirds:title>Other</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>text/html</iirds:format>
        <iirds:source>content/other.html</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Document>
"""
    package = build_package(tmp_path, "other.iirds", metadata=HEAD % other,
                            content=("content/a.pdf", "content/other.html", "index.html"))
    assert "R40" not in {f.rule.id for f in runner.check(package).findings}


def test_it_says_nothing_outside_the_handover_profile(tmp_path):
    """`index.html` is only the content list where the profile requires one.
    An unrestricted package may carry a file of that name and point at it."""
    unrestricted = HEAD.replace(
        "    <iirds:formatRestriction>H</iirds:formatRestriction>\n", "")
    package = build_package(tmp_path, "plain.iirds",
                            metadata=unrestricted % REFERENCES["a rendition source"],
                            content=CONTENT)
    assert "R40" not in {f.rule.id for f in runner.check(package).findings}


def test_the_two_halves_of_the_sentence_do_not_contradict_each_other(tmp_path):
    """R37 excludes `index.html` from the files it asks to be referenced, and
    this rule forbids referencing it. Neither may report the package the other
    calls conformant, which is what the exclusion was for."""
    both = fired(tmp_path)
    assert "R37" not in both and "R40" not in both


def test_the_rule_claims_the_sentence():
    from iirds_validate.registry import all_rules
    rule = {r.id: r for r in all_rules()}["R40"]
    assert "x8-3-1-1-mandatory-content-list#3" in (rule.covers or ())
    assert rule.severity is Severity.ERROR
    assert rule.variants == ("H",)


def test_a_source_that_is_not_on_a_typed_rendition_is_still_a_source(tmp_path):
    """Written after a version keyed on `iirds:Rendition` passed every case
    above: each of them hangs the source on a typed rendition, so the narrower
    reading and the wider one gave the same answers and nothing chose between
    them.

    A rendition written as an untyped node is ordinary RDF/XML -- the property
    says what it is and the type is left implicit -- and the sentence is about
    the reference, not about the shape of the node carrying it.
    """
    untyped = """  <iirds:Document rdf:about="urn:test:d2">
    <iirds:title>Listing</iirds:title>
    <iirds:has-rendition>
      <rdf:Description>
        <iirds:format>text/html</iirds:format>
        <iirds:source>index.html</iirds:source>
      </rdf:Description>
    </iirds:has-rendition>
  </iirds:Document>
"""
    assert "R40" in fired(tmp_path, untyped, "untyped.iirds")
