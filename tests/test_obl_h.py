"""Profiles, nesting and iiRDS/H: five sentences no rule answered for.

Each is quoted from docs/requirements.json, id first, above the package that
breaks it. That package is the evidence `test_covers_is_earned.NAMED_CASES`
points at: it breaks the sentence, and the rule claiming the sentence has to
report it. Where a sentence carries a condition, a package beside it meets
the condition's other side and has to be left alone -- a check can report
more than its sentence without anybody noticing, and a sibling is how that
gets noticed.
"""
from __future__ import annotations

import pytest
from rdflib import Graph

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from test_handover_rules_fire import HANDOVER


def findings(package, rule_id):
    return [f for f in runner.check(package).findings if f.rule.id == rule_id]


def as_jsonld(metadata: str) -> str:
    return Graph().parse(data=metadata, format="xml").serialize(format="json-ld")


def handover(tmp_path, name, metadata=HANDOVER, extra=()):
    """The conformant iiRDS/H fixture, its metadata.jsonld generated from its
    metadata.rdf the way its own module does it, plus `extra`."""
    return build_package(tmp_path, name, metadata=metadata, jsonld=as_jsonld(metadata),
                         content=(), extra=(("content/doc1.pdf", b"%PDF-1.4"),
                                            ("index.html", "<html/>")) + tuple(extra))


# ---------------------------------------------------------------------------
# x5-1-1-metadata-location-and-rdf-serializations#3
#   "If metadata is provided in the JSON-LD 1.1 syntax, the META-INF directory
#    MUST contain the file metadata.jsonld (see [json-ld11])."
# ---------------------------------------------------------------------------

#: The minimal package's metadata in the other serialisation.
JSONLD = as_jsonld(MINIMAL_RDF)


@pytest.mark.parametrize("where", [
    "META-INF/metadata.json",           # the other extension JSON-LD is written with
    "META-INF/Metadata.jsonld",         # the name in another case; a ZIP name is exact
    "metadata.jsonld",                  # the name, in the root
    "META-INF/jsonld/metadata.jsonld",  # the name, one directory down
    "content/metadata.txt",             # a name that says nothing; the bytes are JSON-LD
])
def test_json_ld_metadata_anywhere_but_meta_inf_metadata_jsonld_is_reported(tmp_path, where):
    package = build_package(tmp_path, "misplaced.iirds", extra=((where, JSONLD),))
    assert [f.violation.subject for f in findings(package, "C16.2")] == [where]


def test_json_ld_metadata_in_its_place_is_not_reported_for_a_copy_elsewhere(tmp_path):
    """The sentence asks for the file to be there, and it is. What else the
    package carries is not this sentence's question."""
    package = build_package(tmp_path, "placed.iirds", jsonld=JSONLD,
                            extra=(("META-INF/metadata.json", JSONLD),))
    assert findings(package, "C16.2") == []


def test_json_ld_that_is_not_iirds_metadata_is_not_reported(tmp_path):
    """The condition is that *metadata* is provided in JSON-LD. A document
    saying nothing in an iiRDS vocabulary is content that happens to be
    JSON-LD, and a package may carry any content it likes."""
    data = '{"@context": {"@vocab": "http://schema.org/"}, "@id": "urn:x:pump", "name": "Pump"}'
    package = build_package(tmp_path, "data.iirds", extra=(("content/data.jsonld", data),))
    assert findings(package, "C16.2") == []


def test_json_ld_is_not_asked_of_an_edition_that_does_not_name_it(tmp_path):
    """iiRDS 1.2 names one serialisation, RDF/XML; the words JSON-LD and
    metadata.jsonld do not occur in it."""
    older = MINIMAL_RDF.replace("<iirds:iiRDSVersion>1.3<", "<iirds:iiRDSVersion>1.2<")
    package = build_package(tmp_path, "older.iirds", metadata=older,
                            extra=(("META-INF/metadata.json", as_jsonld(older)),))
    assert findings(package, "C16.2") == []


def test_a_handover_package_with_its_json_ld_elsewhere_is_reported_once(tmp_path):
    """The handover profile makes the file mandatory, and the branch saying so
    already reports this package. It breaks both sentences and one remedy
    answers both, so it is reported once."""
    package = build_package(
        tmp_path, "h.iirds", metadata=HANDOVER, content=(),
        extra=(("content/doc1.pdf", b"%PDF-1.4"), ("index.html", "<html/>"),
               ("META-INF/metadata.json", as_jsonld(HANDOVER))))
    assert [f.violation.message for f in findings(package, "C16.2")] == [
        "iiRDS/H packages must contain META-INF/metadata.jsonld"]


# ---------------------------------------------------------------------------
# x6-3-3-metadata-of-nested-iirds-packages#1
#   "For each nested child iiRDS container, an iirds:Package MUST be present in
#    the metadata of the parent iiRDS container."
# x6-3-3-metadata-of-nested-iirds-packages#3
#   "In the metadata.rdf file of the parent iiRDS container, the iirds:Package
#    of the nested child iiRDS container MUST reference exactly one
#    iirds:Package by iirds:is-part-of-package."
#
# Which iirds:Package is a child's, the standard shows rather than says:
# Example 16 prints the parent's metadata.rdf and the child's, and the nested
# package carries one IRI in both. Until 1.2 the parent's package named the
# child's archive by iirds:has-rendition instead, and 1.3 recommends omitting
# that without forbidding it, so a rendition naming the archive is the other
# way a parent points at its child.
# ---------------------------------------------------------------------------

HEAD = MINIMAL_RDF.replace("</rdf:RDF>\n", "")


def parent(body: str) -> str:
    return HEAD + body + "</rdf:RDF>\n"


def child(tmp_path, iri="urn:test:child", metadata=None) -> bytes:
    """A nested container whose own package is `iri`."""
    where = tmp_path / ("child-%d" % len(list(tmp_path.iterdir())))
    where.mkdir()
    rdf = metadata if metadata is not None else MINIMAL_RDF.replace("urn:test:package", iri)
    return build_package(where, "child.iirds", metadata=rdf).read_bytes()


def declared(iri="urn:test:child", parents=("urn:test:package",), rendition=None) -> str:
    """The parent's iirds:Package for a child, the way Example 16 writes it."""
    lines = ['  <iirds:Package rdf:about="%s">' % iri,
             "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>"]
    lines += ['    <iirds:is-part-of-package rdf:resource="%s"/>' % p for p in parents]
    if rendition is not None:
        lines += ["    <iirds:has-rendition>",
                  "      <iirds:Rendition>",
                  "        <iirds:format>application/iirds+zip</iirds:format>",
                  "        <iirds:source>%s</iirds:source>" % rendition,
                  "      </iirds:Rendition>",
                  "    </iirds:has-rendition>"]
    return "\n".join(lines + ["  </iirds:Package>"]) + "\n"


def nesting(tmp_path, body, entries, name="parent.iirds", jsonld=None):
    return build_package(tmp_path, name, metadata=parent(body), jsonld=jsonld,
                         extra=tuple(entries))


def test_a_nested_container_the_parent_does_not_declare_is_reported(tmp_path):
    package = nesting(tmp_path, "", [("content/child.iirds", child(tmp_path))])
    got = findings(package, "R60")
    assert [f.violation.subject for f in got] == ["content/child.iirds"]
    assert "urn:test:child" in got[0].violation.detail


def test_a_nested_container_declared_under_another_iri_is_reported(tmp_path):
    """A package is declared, and it is not the child's: the child says it is
    urn:test:child, and nothing in the parent describes that package."""
    package = nesting(tmp_path, declared("urn:test:someone-else"),
                      [("content/child.iirds", child(tmp_path))])
    assert [f.violation.subject for f in findings(package, "R60")] == ["content/child.iirds"]


def test_a_nested_container_the_parent_declares_is_not_reported(tmp_path):
    package = nesting(tmp_path, declared(), [("content/child.iirds", child(tmp_path))])
    assert findings(package, "R60") == []


def test_a_nested_container_named_by_a_rendition_is_declared(tmp_path):
    """The 1.2 way of pointing at a child, which 1.3 recommends omitting and
    does not forbid."""
    package = nesting(tmp_path, declared("urn:test:other", rendition="content/child.iirds"),
                      [("content/child.iirds", child(tmp_path))])
    assert findings(package, "R60") == []


def test_a_child_whose_own_package_cannot_be_read_is_still_owed_one(tmp_path):
    """The child's metadata does not parse, so which package is its own cannot
    be read off it. The parent still owes it one, and declares none."""
    broken = child(tmp_path, metadata="<rdf:RDF")
    package = nesting(tmp_path, "", [("content/child.iirds", broken)])
    assert [f.violation.subject for f in findings(package, "R60")] == ["content/child.iirds"]


def test_a_child_whose_own_package_cannot_be_read_is_left_alone_once_one_is_declared(tmp_path):
    """Which declared package is that child's cannot be told, and one is
    there; saying more would be a guess."""
    broken = child(tmp_path, metadata="<rdf:RDF")
    package = nesting(tmp_path, declared("urn:test:whichever"),
                      [("content/child.iirds", broken)])
    assert findings(package, "R60") == []


def test_a_declared_child_package_that_is_part_of_no_package_is_reported(tmp_path):
    package = nesting(tmp_path, declared(parents=()),
                      [("content/child.iirds", child(tmp_path))])
    got = findings(package, "R60")
    assert [f.violation.subject for f in got] == ["urn:test:child"]
    assert "none" in got[0].violation.message


def test_a_declared_child_package_that_is_part_of_two_packages_is_reported(tmp_path):
    other = ('  <iirds:Package rdf:about="urn:test:other">\n'
             "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
             "  </iirds:Package>\n")
    package = nesting(tmp_path, other + declared(parents=("urn:test:package", "urn:test:other")),
                      [("content/child.iirds", child(tmp_path))])
    assert [f.violation.subject for f in findings(package, "R60")] == ["urn:test:child"]


def test_a_declared_child_package_part_of_something_that_is_not_a_package_is_reported(tmp_path):
    """"reference exactly one iirds:Package": a Topic is referenced, and no
    package is."""
    package = nesting(tmp_path, declared(parents=("urn:test:topic1",)),
                      [("content/child.iirds", child(tmp_path))])
    assert [f.violation.subject for f in findings(package, "R60")] == ["urn:test:child"]


def test_the_one_reference_is_asked_of_metadata_rdf(tmp_path):
    """"In the metadata.rdf file of the parent iiRDS container": the reference
    stated in metadata.jsonld alone is not in the file the sentence names."""
    package = nesting(tmp_path, declared(parents=()),
                      [("content/child.iirds", child(tmp_path))],
                      jsonld=as_jsonld(parent(declared())))
    assert [f.violation.subject for f in findings(package, "R60")] == ["urn:test:child"]


# ---------------------------------------------------------------------------
# x6-7-3-packages-related-to-component-trees#4
#   "iiRDS/H packages MUST use this variant of hierarchy formation and MUST NOT
#    contain nested packages."   (the first limb; the second is #5)
# x8-3-1-2-nesting-of-packages#3
#   "Instead, components trees MUST be used to represent hierarchical
#    dependencies, see Packages related to component trees."
#
# Read as R9's docstring reads the first: "this variant" is the component
# trees section 6.7.3 offers, and "instead" in section 8.3.1.2 is instead of
# nesting ZIP archives. Those are the two ways of forming a hierarchy of
# packages the standard names, and a handover package takes the other one by
# nesting; one that models no hierarchy at all has used no other variant to
# be told off for. A relation from outside iiRDS -- dcterms:hasPart, say -- is
# not a variant the standard names, and being nested in another package is
# section 8.1.1's matter, not something this package contains. So the package
# breaking both sentences is the one that nests, and R9 reports both of its
# shapes. The sibling is the variant itself: a component tree and nothing
# nested, which has to cost the package nothing.
# ---------------------------------------------------------------------------

A_NESTED_PACKAGE = ('  <iirds:Package rdf:about="urn:test:nested">\n'
                    "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
                    '    <iirds:is-part-of-package rdf:resource="urn:test:package"/>\n'
                    "  </iirds:Package>\n")

COMPONENT_TREE = ('  <iirds:Component rdf:about="urn:test:pump">\n'
                  '    <rdfs:label xml:lang="en">Pump</rdfs:label>\n'
                  '    <iirds:has-component rdf:resource="urn:test:motor"/>\n'
                  "  </iirds:Component>\n"
                  '  <iirds:Component rdf:about="urn:test:motor">\n'
                  '    <rdfs:label xml:lang="en">Motor</rdfs:label>\n'
                  "  </iirds:Component>\n")


@pytest.mark.parametrize("shape", ["a nested archive", "a nested package declared"])
def test_a_handover_package_that_nests_forms_its_hierarchy_the_other_way(tmp_path, shape):
    if shape == "a nested archive":
        package = handover(tmp_path, "nests.iirds",
                           extra=(("content/inner.iirds", child(tmp_path)),))
    else:
        package = handover(tmp_path, "declares.iirds",
                           metadata=HANDOVER.replace("</rdf:RDF>", A_NESTED_PACKAGE + "</rdf:RDF>"))
    assert findings(package, "R9")


def test_a_handover_package_with_a_component_tree_and_nothing_nested_costs_nothing(tmp_path):
    with_tree = HANDOVER.replace("</rdf:RDF>", COMPONENT_TREE + "</rdf:RDF>").replace(
        '    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n',
        '    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n'
        '    <iirds:relates-to-component rdf:resource="urn:test:pump"/>\n')
    assert with_tree != HANDOVER and "relates-to-component" in with_tree

    def said(package):
        return sorted((f.rule.id, f.violation.subject, f.violation.message)
                      for f in runner.check(package).findings)

    (tmp_path / "tree").mkdir()
    (tmp_path / "plain").mkdir()
    assert said(handover(tmp_path / "tree", "tree.iirds", metadata=with_tree)) == \
        said(handover(tmp_path / "plain", "plain.iirds"))


def test_a_json_ld_file_the_metadata_names_as_a_rendition_is_content(tmp_path):
    """The package says what the file is: the content of a topic."""
    topic = ('  <iirds:Topic rdf:about="urn:test:t2"><iirds:title>t</iirds:title>'
             "<iirds:has-rendition><iirds:Rendition>"
             "<iirds:format>application/ld+json</iirds:format>"
             "<iirds:source>content/data.jsonld</iirds:source>"
             "</iirds:Rendition></iirds:has-rendition></iirds:Topic>\n")
    package = build_package(tmp_path, "rendered.iirds",
                            metadata=MINIMAL_RDF.replace("</rdf:RDF>", topic + "</rdf:RDF>"),
                            extra=(("content/data.jsonld", JSONLD),))
    assert findings(package, "C16.2") == []


# ---------------------------------------------------------------------------
# The edges of each reading: what is read, what is left alone, and what a
# bounded read does when it stops.
# ---------------------------------------------------------------------------

def test_plain_json_is_not_json_ld(tmp_path):
    """No key is a keyword or an IRI, so the document says nothing in RDF --
    an iiRDS IRI among its values is data, not a statement."""
    data = '{"title": "Package overview", "see": "http://iirds.tekom.de/iirds#Package"}'
    package = build_package(tmp_path, "plain.iirds", extra=(("content/search.json", data),))
    assert findings(package, "C16.2") == []


def test_a_file_that_opens_like_json_and_is_not_is_not_metadata(tmp_path):
    package = build_package(tmp_path, "notjson.iirds",
                            extra=(("content/notes.json", "{ a Package, and not JSON"),))
    assert findings(package, "C16.2") == []


def test_a_json_ld_document_past_the_metadata_limit_is_not_read(tmp_path, monkeypatch):
    """Bounded as metadata.jsonld itself is: a document the reader would
    refuse at the right path is not read at a wrong one either."""
    from iirds_validate.rules import container

    monkeypatch.setattr(container, "MAX_METADATA_BYTES", 200)
    package = build_package(tmp_path, "big.iirds", extra=(("META-INF/metadata.json", JSONLD),))
    assert len(JSONLD) > 200
    assert findings(package, "C16.2") == []


def a_child_archive(tmp_path, entries, metadata_method=None):
    """A nested container written by hand: mimetype first and stored, then
    `entries`, with metadata.rdf in `metadata_method` where one is given."""
    import zipfile

    where = tmp_path / ("hand-%d.iirds" % len(list(tmp_path.iterdir())))
    with zipfile.ZipFile(where, "w", zipfile.ZIP_DEFLATED) as archive:
        first = zipfile.ZipInfo("mimetype", date_time=(1980, 1, 1, 0, 0, 0))
        archive.writestr(first, b"application/iirds+zip")
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = (metadata_method if metadata_method and name.endswith(".rdf")
                                  else zipfile.ZIP_DEFLATED)
            archive.writestr(info, data)
    return where.read_bytes()


CHILD_RDF = MINIMAL_RDF.replace("urn:test:package", "urn:test:child")


@pytest.mark.parametrize("why", [
    "the archive is past the metadata limit",
    "its metadata.rdf is in a method the reader refuses",
    "its metadata.rdf is past the metadata limit",
    "it has no metadata.rdf",
])
def test_a_child_whose_own_package_cannot_be_read_off_it_is_owed_one_all_the_same(
        tmp_path, monkeypatch, why):
    import zipfile

    from iirds_validate.rules import container

    if why == "the archive is past the metadata limit":
        monkeypatch.setattr(container, "MAX_METADATA_BYTES", 300)
        raw = child(tmp_path)
        assert len(raw) > 300
    elif why == "its metadata.rdf is in a method the reader refuses":
        raw = a_child_archive(tmp_path, [("META-INF/metadata.rdf", CHILD_RDF),
                                         ("content/topic1.xhtml", "<html/>")],
                              metadata_method=zipfile.ZIP_BZIP2)
    elif why == "its metadata.rdf is past the metadata limit":
        padded = CHILD_RDF.replace("<rdf:RDF ", "<!--%s--><rdf:RDF " % (" " * 20000), 1)
        raw = a_child_archive(tmp_path, [("META-INF/metadata.rdf", padded),
                                         ("content/topic1.xhtml", "<html/>")])
        monkeypatch.setattr(container, "MAX_METADATA_BYTES", 5000)
        assert len(raw) < 5000 < len(padded)
    else:
        raw = a_child_archive(tmp_path, [("content/topic1.xhtml", "<html/>")])
    package = nesting(tmp_path, "", [("content/child.iirds", raw)])
    assert [f.violation.subject for f in findings(package, "R60")] == ["content/child.iirds"]


@pytest.mark.parametrize("metadata", [None, "<rdf:RDF"], ids=["absent", "unreadable"])
def test_the_one_reference_is_asked_of_metadata_rdf_even_when_it_cannot_be_read(
        tmp_path, metadata):
    """The child is declared in metadata.jsonld, which is the parent's metadata
    too, so the first sentence holds. The second names metadata.rdf, and a
    file that is not there, or does not read, describes no package at all."""
    package = build_package(tmp_path, "nordf.iirds", metadata=metadata,
                            jsonld=as_jsonld(parent(declared())),
                            extra=(("content/child.iirds", child(tmp_path)),))
    assert [f.violation.subject for f in findings(package, "R60")] == ["urn:test:child"]


@pytest.mark.parametrize("other", [
    '<iirds:is-part-of-package rdf:resource="urn:test:topic1"/>',       # a Topic
    '<iirds:is-part-of-package rdf:resource="urn:test:nothing"/>',      # described nowhere
], ids=["and a topic", "and an IRI nothing describes"])
def test_a_second_reference_of_any_kind_is_one_too_many(tmp_path, other):
    """"exactly one iirds:Package by iirds:is-part-of-package": the property's
    range is iirds:Package, so whatever a second reference names, the child's
    package references more than one."""
    body = declared().replace("  </iirds:Package>", "    %s\n  </iirds:Package>" % other)
    package = nesting(tmp_path, body, [("content/child.iirds", child(tmp_path))])
    assert [f.violation.subject for f in findings(package, "R60")] == ["urn:test:child"]


def test_a_second_parent_typed_only_in_metadata_jsonld_is_counted(tmp_path):
    q = ('  <iirds:Package rdf:about="urn:test:q">\n'
         "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n  </iirds:Package>\n")
    body = declared(parents=("urn:test:package", "urn:test:q"))
    package = nesting(tmp_path, body, [("content/child.iirds", child(tmp_path))],
                      jsonld=as_jsonld(parent(body + q)))
    assert [f.violation.subject for f in findings(package, "R60")] == ["urn:test:child"]


@pytest.mark.parametrize("spare", [
    "only in metadata.jsonld",
    "part of two packages",
])
def test_an_unreadable_child_is_owed_a_package_that_keeps_both_sentences(tmp_path, spare):
    """Which declared package is the unreadable child's cannot be told. If it
    is the spare, the spare breaks the second sentence; if it is not, the
    child has none and breaks the first. Either way the package breaks one."""
    broken = child(tmp_path, metadata="<rdf:RDF")
    if spare == "only in metadata.jsonld":
        package = nesting(tmp_path, "", [("content/child.iirds", broken)],
                          jsonld=as_jsonld(parent(declared("urn:test:x"))))
    else:
        q = ('  <iirds:Package rdf:about="urn:test:q">\n'
             "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n  </iirds:Package>\n")
        package = nesting(tmp_path, q + declared("urn:test:x",
                                                 parents=("urn:test:package", "urn:test:q")),
                          [("content/child.iirds", broken)])
    assert [f.violation.subject for f in findings(package, "R60")] == ["content/child.iirds"]


def test_a_child_carrying_the_parent_s_iri_is_found_by_the_rendition_that_names_it(tmp_path):
    """Generated from one template, the child's own package has the parent's
    IRI. The parent declares it the 1.2 way, by a rendition naming the
    archive, and that declaration is the child's -- not the parent's own
    package, which only happens to share the IRI."""
    raw = child(tmp_path, iri="urn:test:package")
    package = nesting(tmp_path, declared("urn:test:child-decl", rendition="content/child.iirds"),
                      [("content/child.iirds", raw)])
    assert findings(package, "R60") == []


def test_grandchildren_side_by_side_are_declared_by_their_own_parent(tmp_path):
    """Section 6.3.3: "All nested iiRDS containers MUST be included side by
    side in the iiRDS ZIP archive of the highest level iiRDS package." So a
    grandchild sits beside its parent in the top archive, and its parent's
    metadata -- not the top one's -- is where its package is declared."""
    middle = MINIMAL_RDF.replace("urn:test:package", "urn:test:middle").replace(
        "</rdf:RDF>", declared("urn:test:grandchild", parents=("urn:test:middle",))
        + "</rdf:RDF>")
    package = nesting(tmp_path, declared("urn:test:middle"),
                      [("content/middle.iirds", child(tmp_path, metadata=middle)),
                       ("content/grandchild.iirds", child(tmp_path, iri="urn:test:grandchild"))])
    assert findings(package, "R60") == []


def test_a_grandchild_s_declaration_is_held_to_the_second_sentence_where_it_is(tmp_path):
    middle = MINIMAL_RDF.replace("urn:test:package", "urn:test:middle").replace(
        "</rdf:RDF>", declared("urn:test:grandchild", parents=()) + "</rdf:RDF>")
    package = nesting(tmp_path, declared("urn:test:middle"),
                      [("content/middle.iirds", child(tmp_path, metadata=middle)),
                       ("content/grandchild.iirds", child(tmp_path, iri="urn:test:grandchild"))])
    got = findings(package, "R60")
    assert [f.violation.subject for f in got] == ["urn:test:grandchild"]
    assert "content/middle.iirds" in got[0].violation.detail


def test_example_16_as_printed_is_declared(tmp_path):
    """The child's rdf:about in the standard's Example 16 opens with a space,
    which no IRI can contain; the space is not a different package."""
    printed = MINIMAL_RDF.replace('rdf:about="urn:test:package"', 'rdf:about=" urn:test:child"')
    package = nesting(tmp_path, declared(), [("content/child.iirds", child(tmp_path, metadata=printed))])
    assert findings(package, "R60") == []


def test_two_archives_under_one_declaration_are_told_once(tmp_path):
    package = nesting(tmp_path, declared(parents=()),
                      [("content/a.iirds", child(tmp_path)), ("content/b.iirds", child(tmp_path))])
    got = findings(package, "R60")
    assert [f.violation.subject for f in got] == ["urn:test:child"]
    assert "content/a.iirds" in got[0].violation.detail and "content/b.iirds" in got[0].violation.detail


def test_in_a_handover_package_the_remedy_is_to_take_the_child_out(tmp_path):
    """R9 says an iiRDS/H package must not nest at all. Declaring the child
    would answer this rule and break more of R9, so here the remedy is R9's."""
    package = handover(tmp_path, "h-nests.iirds", extra=(("content/inner.iirds", child(tmp_path)),))
    got = findings(package, "R60")
    assert got and all("R9" in (f.violation.fix or "") for f in got)


# ---------------------------------------------------------------------------
# x5-1-1#3 again: what "metadata" is, and the JSON-LD a reader of it meets.
# The package's metadata is the document that describes the package -- the
# iirds:Package every metadata graph has (M3) -- which is what separates it
# from a label table, structured data about a product, or a side file in
# META-INF that a consumer is advised to ignore.
# ---------------------------------------------------------------------------

PKG = "http://iirds.tekom.de/iirds#Package"


@pytest.fixture
def no_network(monkeypatch):
    """test_offline.py's: a connection attempt is an error, not a wait."""
    import socket

    def refuse(*args, **kwargs):
        raise AssertionError("the validator attempted a network connection")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.mark.parametrize("text", [
    '{"@context": "https://example.com/ctx.jsonld", "@id": "urn:test:package", "@type": "%s"}' % PKG,
    '{"@context": {"@import": "https://example.com/ctx.jsonld", "ii": "http://iirds.tekom.de/iirds#"},'
    ' "@id": "urn:test:package", "@type": "ii:Package"}',
    '{"@context": "context.jsonld", "@id": "urn:test:package", "@type": "%s"}' % PKG,
    '{"@id": "urn:test:graph", "@graph": [{"@id": "urn:test:package", "@type": "%s"}]}' % PKG,
    "\n" * 100 + JSONLD,
    '{"@context": {"@vocab": "http://iirds.tekom.de/iirds#Pack"}, "@id": "urn:test:package",'
    ' "@type": "age"}',
    '[{"@context": ["https://example.com/ctx.jsonld", {"ii": "http://iirds.tekom.de/iirds#"}],'
    ' "@id": "urn:test:package", "@type": "ii:Package"}]',
], ids=["a context to fetch", "an @import", "a context file", "a named graph",
        "whitespace first", "the name split across a vocabulary", "an array of nodes"])
def test_json_ld_metadata_is_found_whatever_else_it_asks_a_reader_for(tmp_path, no_network, text):
    """An offline reader fetches no context, so what a document defines in
    place is what it says here; a context it names elsewhere is left out
    rather than the document with it -- and nothing is fetched."""
    package = build_package(tmp_path, "shapes.iirds", extra=(("META-INF/metadata.json", text),))
    assert [f.violation.subject for f in findings(package, "C16.2")] == ["META-INF/metadata.json"]


def test_json_ld_written_into_metadata_rdf_is_json_ld_metadata(tmp_path):
    package = build_package(tmp_path, "inrdf.iirds", metadata=JSONLD)
    assert "META-INF/metadata.rdf" in [f.violation.subject for f in findings(package, "C16.2")]


def test_an_empty_metadata_jsonld_does_not_hold_the_metadata_kept_elsewhere(tmp_path):
    package = build_package(tmp_path, "decoy.iirds", jsonld="{}",
                            extra=(("META-INF/metadata.json", JSONLD),))
    assert [f.violation.subject for f in findings(package, "C16.2")] == ["META-INF/metadata.json"]


@pytest.mark.parametrize("where,text", [
    ("content/viewer/de.json",
     '{"http://iirds.tekom.de/iirds#Topic": "Thema", "http://iirds.tekom.de/iirds#Document": "Dokument"}'),
    ("content/product.jsonld",
     '{"@context": "https://schema.org", "@id": "urn:x:pump", "@type": "http://iirds.tekom.de/iirds#Topic"}'),
    ("META-INF/extension.jsonld",
     '{"@id": "http://my.co/ns#Leaflet", "@type": "http://www.w3.org/2000/01/rdf-schema#Class",'
     ' "http://www.w3.org/2000/01/rdf-schema#subClassOf": {"@id": "http://iirds.tekom.de/iirds#Topic"}}'),
], ids=["a label table keyed by iiRDS IRIs", "structured data typed with an iiRDS class",
        "a side file describing an extension"])
def test_json_that_does_not_describe_the_package_is_not_its_metadata(tmp_path, where, text):
    package = build_package(tmp_path, "notmeta.iirds", extra=((where, text),))
    assert findings(package, "C16.2") == []


def test_json_that_is_not_valid_json_ld_is_not_metadata(tmp_path):
    """A context is an object, a string or an array; a number is none of them.
    The reader refuses the document, and a document it refuses provides
    nothing."""
    text = '{"@context": 5, "@id": "urn:test:package", "@type": "%s"}' % PKG
    package = build_package(tmp_path, "badld.iirds", extra=(("META-INF/metadata.json", text),))
    assert findings(package, "C16.2") == []
