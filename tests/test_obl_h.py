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


# Section 8.3.1.1 specifies column data, not header spelling or order.
# The identifiers here are RDF IRIs, not names inferred from the ZIP entries.
LIST_COLUMNS = ("Document", "Languages", "Product", "Category", "Reference")


def list_rows(count=3):
    return [("Operating instructions %d" % n, "en", "urn:test:variant",
             "http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions",
             ("urn:test:package" if n == 1 else "urn:test:doc%d" % n))
            for n in range(1, count + 1)]


def content_list(rows, headers=LIST_COLUMNS, extra=""):
    from html import escape

    head = ("<thead><tr>" + "".join("<th>%s</th>" % escape(h) for h in headers)
            + "</tr></thead>") if headers else ""
    body = "".join("<tr>" + "".join("<td>%s</td>" % escape(c) for c in row)
                   + "</tr>" for row in rows)
    return ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Documents</title>'
            '</head><body><table>' + head + '<tbody>' + body + '</tbody></table>'
            + extra + '</body></html>')


def listed_handover(tmp_path, name, rows=None, body=None, metadata=None):
    """Three information units: the package and two delivered documents."""
    if metadata is None:
        start = HANDOVER.index('  <iirds:Document rdf:about="urn:test:doc1">')
        end = HANDOVER.index('  </iirds:Document>', start) + len('  </iirds:Document>')
        block = HANDOVER[start:end]
        documents = "\n".join(block.replace('urn:test:doc1', 'urn:test:doc%d' % n)
                              .replace('Operating instructions</iirds:title>',
                                       'Operating instructions %d</iirds:title>' % n)
                              for n in range(2, 4))
        metadata = (HANDOVER[:start] + documents + HANDOVER[end:]).replace(
            "<iirds:title>Handover</iirds:title>",
            "<iirds:title>Operating instructions 1</iirds:title>"
            "<iirds:language>en</iirds:language>"
            '<hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/'
            'handover#OperatingInstructions"/>')
    if body is None:
        body = content_list(list_rows() if rows is None else rows)
    return build_package(tmp_path, name, metadata=metadata, jsonld=as_jsonld(metadata),
                         content=(), extra=(("content/doc1.pdf", b"%PDF-1.4"),
                                            ("index.html", body)))


@pytest.mark.parametrize("element", ["video", "audio", "p", "div", "ins", "custom"])
def test_content_list_elements_outside_its_allowed_sections_are_reported(tmp_path, element):
    """Only the element restriction is checked; the full XHTML claim is withdrawn."""
    body = content_list(list_rows(), extra="<%s/>" % element)
    package = listed_handover(tmp_path, "element.iirds", body=body)
    got = findings(package, "R67")
    assert got and {f.violation.subject for f in got} == {"index.html"}


def test_content_list_with_only_allowed_elements_passes(tmp_path):
    body = content_list(list_rows(), extra="<section><h2>Summary</h2><span>Ready</span></section>")
    package = listed_handover(tmp_path, "allowed.iirds", body=body)
    assert findings(package, "R67") == []


@pytest.mark.parametrize("body", ["<html><body>", '<html xmlns="urn:foreign"/>'])
def test_content_list_that_cannot_be_iirds_xhtml_is_reported(tmp_path, body):
    assert findings(listed_handover(tmp_path, "invalid-list.iirds", body=body), "R67")


def test_content_list_missing_a_unit_row_is_reported(tmp_path):
    """x8-3-1-1-mandatory-content-list#5\n
    The content list MUST contain tabular data according to section Tabular Data with one row per information unit and MUST at least contain columns providing the following data (see Metadata Requirements):"""
    package = listed_handover(tmp_path, "missing-row.iirds", rows=list_rows()[:2])
    assert findings(package, "R68")


@pytest.mark.parametrize("rows", [
    list_rows()[:2] + [list_rows()[0]],
    list_rows()[:2] + [list_rows()[2][:-1] + ("urn:test:unknown",)],
    list_rows() + [list_rows()[1]],
])
def test_content_list_rows_must_refer_to_each_unit_once(tmp_path, rows):
    assert findings(listed_handover(tmp_path, "wrong-rows.iirds", rows=rows), "R68")


def test_content_list_with_one_row_per_unit_passes(tmp_path):
    assert findings(listed_handover(tmp_path, "three-rows.iirds"), "R68") == []


def test_content_list_without_tabular_data_is_reported(tmp_path):
    package = listed_handover(tmp_path, "no-table.iirds", body="<html><body/></html>")
    assert findings(package, "R68")
    assert findings(package, "R69") == []


@pytest.mark.parametrize("column", range(5), ids=LIST_COLUMNS)
def test_content_list_missing_a_data_cell_is_reported(tmp_path, column):
    """Five nonempty cells are checked; the full data-role claim is withdrawn."""
    rows = [r[:column] + r[column + 1:] for r in list_rows()]
    headers = LIST_COLUMNS[:column] + LIST_COLUMNS[column + 1:]
    package = listed_handover(tmp_path, "missing-column.iirds", body=content_list(rows, headers))
    assert bool(findings(package, "R69")) == (column != 4)


@pytest.mark.parametrize("column", range(5), ids=LIST_COLUMNS)
def test_content_list_header_cannot_replace_missing_column_data(tmp_path, column):
    rows = list_rows()
    rows[1] = rows[1][:column] + ("",) + rows[1][column + 1:]
    package = listed_handover(tmp_path, "empty-cell.iirds", rows=rows)
    assert bool(findings(package, "R69")) == (column != 4)


def test_content_list_required_columns_and_additional_data_pass(tmp_path):
    # The standard specifies data, not English captions, or a fixed order.
    rows = [tuple(reversed(r)) + ("Delivered",) for r in list_rows()]
    body = content_list(rows, ("Verweis", "Kategorie", "Produkt", "Sprache", "Titel", "Status"))
    assert findings(listed_handover(tmp_path, "all-columns.iirds", body=body), "R69") == []


def test_content_list_columns_do_not_require_a_header_spelling(tmp_path):
    package = listed_handover(tmp_path, "no-captions.iirds", body=content_list(list_rows(), headers=()))
    assert findings(package, "R69") == []


@pytest.mark.parametrize("profile", ["A", "unrestricted"])
def test_content_list_obligations_are_only_asked_in_h_reading(tmp_path, profile):
    metadata = HANDOVER.replace("<iirds:formatRestriction>H</iirds:formatRestriction>",
                                "<iirds:formatRestriction>%s</iirds:formatRestriction>" % profile)
    package = listed_handover(tmp_path, "other-profile.iirds", body="<html><video/></html>",
                              metadata=metadata)
    assert not {"R67", "R68", "R69"} & {f.rule.id for f in runner.check(package).findings}


@pytest.mark.parametrize("extra", [
    '<span onclick="alert(1)">Title</span>',
    '<a href="javascript:alert(1)">Title</a>',
    '<link rel="next" href="content/doc1.pdf"/>',
    '<span data-role="invented">Title</span>',
])
def test_content_list_xhtml_attribute_requirements_are_reported(tmp_path, extra):
    package = listed_handover(tmp_path, "attributes.iirds",
                              body=content_list(list_rows(), extra=extra))
    assert findings(package, "R67") == []
    assert {f.rule.id for f in runner.check(package).findings} & {"B4", "B5", "B7", "B11"}


def test_the_package_information_unit_does_not_need_a_list_row(tmp_path):
    rows = list_rows()[1:]
    assert findings(listed_handover(tmp_path, "package-row.iirds", rows=rows), "R68") == []


def test_missing_content_list_is_reported_by_the_shared_claimant(tmp_path):
    from iirds_validate.registry import all_rules

    package = build_package(tmp_path, "missing-list.iirds", metadata=HANDOVER,
                            jsonld=as_jsonld(HANDOVER), content=(),
                            extra=(("content/doc1.pdf", b"%PDF-1.4"),))
    fired = {f.rule.id for f in runner.check(package).findings}
    for suffix in ("#1", "#2"):
        claim = "x8-3-1-1-mandatory-content-list" + suffix
        assert fired & {r.id for r in all_rules() if claim in r.covers}
    assert {"R67", "R68", "R69"}.isdisjoint(fired)


def test_a_pdf_hyperlink_can_identify_a_document_row(tmp_path):
    # The package row uses its IRI. The two documents share a PDF, and their
    # title and language data distinguish the two links as 6.10.1 permits.
    body = content_list(list_rows()).replace(
        "<td>urn:test:doc2</td>", '<td><a href="./content/doc1.pdf">Open</a></td>').replace(
        "<td>urn:test:doc3</td>", '<td><a href="content/doc1.pdf">Open</a></td>')
    package = listed_handover(tmp_path, "linked.iirds", body=body)
    assert findings(package, "R68") == []
    assert findings(package, "R69") == []


def test_a_complex_identity_can_identify_a_document_row(tmp_path):
    metadata = HANDOVER.replace('</rdf:RDF>', """
      <rdf:Description rdf:about="urn:test:doc1">
        <iirds:has-identity><iirds:Identity>
          <iirds:identifier>DOC-1</iirds:identifier>
          <iirds:has-identity-domain rdf:resource="urn:test:document-domain"/>
        </iirds:Identity></iirds:has-identity>
      </rdf:Description>
      <iirds:IdentityDomain rdf:about="urn:test:document-domain"/>
    </rdf:RDF>""")
    rows = [("Handover", "en", "urn:test:variant", LIST_COLUMNS[3], "urn:test:package"),
            ("Operating instructions", "en", "urn:test:variant", LIST_COLUMNS[3], "urn:test:doc1")]
    body = content_list(rows).replace("<td>urn:test:doc1</td>",
                                      "<td><span>DOC-1</span><br/>"
                                      "<span>urn:test:document-domain</span></td>")
    assert findings(listed_handover(tmp_path, "identity.iirds", body=body, metadata=metadata), "R68") == []
    body = body.replace("<span>urn:test:document-domain</span>", "")
    assert findings(listed_handover(tmp_path, "bare-identifier.iirds", body=body, metadata=metadata), "R68")


def test_content_list_new_findings_keep_the_h_content_warning_policy(tmp_path):
    from iirds_validate.cli import main

    package = listed_handover(tmp_path, "policy.iirds",
                              body=content_list(list_rows(), extra="<video/>"))
    got = runner.check(package)
    assert findings(package, "R67")
    assert not [f for f in got.findings if str(f.severity) == "error"]
    assert main(["check", str(package)]) == 0
    assert main(["check", "-W", str(package)]) == 1


def test_foreign_table_names_do_not_supply_xhtml_tabular_data(tmp_path):
    body = content_list(list_rows()).replace('xmlns="http://www.w3.org/1999/xhtml"',
                                             'xmlns="urn:foreign"')
    package = listed_handover(tmp_path, "foreign-table.iirds", body=body)
    assert findings(package, "R68")
    assert findings(package, "R69") == []


# Content list inputs rebuilt by the fixture writer.
H2B_REVIEW_METADATA = '<?xml version="1.0" encoding="utf-8"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n         xmlns:vcard="http://www.w3.org/2006/vcard/ns#"\n         xmlns:hov="http://iirds.tekom.de/iirds/domain/handover#"\n         xmlns:iirds="http://iirds.tekom.de/iirds#">\n  <iirds:Package rdf:about="urn:test:package">\n    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n    <iirds:formatRestriction>H</iirds:formatRestriction>\n    <iirds:title>Operating instructions 1</iirds:title><iirds:language>en</iirds:language><hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <!-- Section 8.3.2 states its product-variant requirements twice, once for\n         the Package and once for the Document, word for word. This fixture was\n         asserted conformant for weeks while carrying only the second: the\n         Package named no variant, and no rule read that list. R13 to R16 read\n         it now. Both may name the same variant, and the simplest conformant\n         package does. -->\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:Package>\n\n  <iirds:Document rdf:about="urn:test:doc2">\n    <iirds:title>Operating instructions 2</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n  <iirds:Document rdf:about="urn:test:doc3">\n    <iirds:title>Operating instructions 3</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n\n  <!-- Section 8.3.2 puts the creator of an information object on the identity\n       domain, not on the object: what is attributed is the scheme the content\n       is known by. The domain carries no iirds:has-identity-type, which is\n       what the reference\'s own passing fixture does; the type is required of\n       a product variant\'s domains (M15.7b, M15.7d), not of this one. -->\n  <iirds:InformationObject rdf:about="urn:test:io1">\n    <iirds:title>Operating instructions</iirds:title>\n    <iirds:has-identity rdf:resource="urn:test:identity-object"/>\n  </iirds:InformationObject>\n\n  <iirds:Identity rdf:about="urn:test:identity-object">\n    <iirds:identifier>OI-2026</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-object"/>\n  </iirds:Identity>\n\n  <iirds:IdentityDomain rdf:about="urn:test:domain-object">\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:IdentityDomain>\n\n  <iirds:ProductVariant rdf:about="urn:test:variant">\n    <rdfs:label xml:lang="en">Rotor 3000</rdfs:label>\n    <iirds:has-identity rdf:resource="urn:test:identity-instance"/>\n    <iirds:has-identity rdf:resource="urn:test:identity-type"/>\n  </iirds:ProductVariant>\n\n  <iirds:Identity rdf:about="urn:test:identity-instance">\n    <iirds:identifier>SN-00417</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-instance"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-instance">\n    <rdfs:label xml:lang="en">Serial numbers</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#SerialNumber"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <iirds:Identity rdf:about="urn:test:identity-type">\n    <iirds:identifier>ROT-3000</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-type"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-type">\n    <rdfs:label xml:lang="en">Product types</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#ProductType"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <!-- One organisation in three roles, which is ordinary for a handover: the\n       manufacturer wrote the documentation and shipped the package. The rules\n       ask for a different role in each place. Author on the Document, Creator\n       on the Package and InformationObject, Manufacturer on the identity\n       domains.\n\n       Three Party instances rather than one carrying three roles, because the\n       ontology states "Cardinality: iirds:Party [0..1]" for has-party-role and\n       the prose makes it mandatory, so a Party holds exactly one. Saying an\n       organisation acts in several roles means several Party nodes pointing at\n       the same vcard, and getting that wrong here was how this fixture first\n       failed M22.1. -->\n  <iirds:Party rdf:about="urn:test:party-manufacturer">\n    <rdfs:label xml:lang="en">Rotor Works, as manufacturer</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-author">\n    <rdfs:label xml:lang="en">Rotor Works, as author</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Author"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-creator">\n    <rdfs:label xml:lang="en">Rotor Works, as creator</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Creator"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <vcard:Organization rdf:about="urn:test:supplier-card">\n    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>\n  </vcard:Organization>\n</rdf:RDF>\n'
H2B_REVIEW_LISTS = {
    'baseline': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'package_row_missing': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 2</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
}

def h2b_review_package(tmp_path, case, body=None, metadata=None):
    return listed_handover(tmp_path, case + ".iirds",
                           body=H2B_REVIEW_LISTS[case] if body is None else body,
                           metadata=H2B_REVIEW_METADATA if metadata is None else metadata)


def test_h2b_population_does_not_require_a_package_row(tmp_path):
    package = h2b_review_package(tmp_path, "package_row_missing")
    assert findings(package, "R68") == []


@pytest.mark.parametrize("kind", ["Topic", "Fragment"])
def test_h2b_population_leaves_forbidden_units_to_the_h_metadata_rule(tmp_path, kind):
    metadata = H2B_REVIEW_METADATA.replace("</rdf:RDF>",
                '<iirds:%s rdf:about="urn:test:other"/></rdf:RDF>' % kind)
    package = h2b_review_package(tmp_path, "baseline", metadata=metadata)
    assert findings(package, "R68") == []
    assert findings(package, "M15.11a")


H2B_IDENTITY = '<rdf:Description rdf:about="urn:test:doc2"><iirds:has-identity><iirds:Identity><iirds:identifier>DOC-1</iirds:identifier><iirds:has-identity-domain rdf:resource="urn:test:document-domain"/></iirds:Identity></iirds:has-identity></rdf:Description><iirds:IdentityDomain rdf:about="urn:test:document-domain"/>'


@pytest.mark.parametrize("reference", [
    '<td>DOC-1 (urn:test:document-domain)</td>',
    '<td>DOC-1</td><td>urn:test:document-domain</td>',
    '<td>Reference: urn:test:doc2 (delivered)</td>',
    '<td><span>urn:test:</span><span>doc2</span></td>',
])
def test_h2b_identification_uses_whole_row_text(tmp_path, reference):
    metadata = H2B_REVIEW_METADATA.replace('</rdf:RDF>', H2B_IDENTITY + '</rdf:RDF>')
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('<td>urn:test:doc2</td>', reference)
    assert findings(h2b_review_package(tmp_path, 'baseline', body, metadata), 'R68') == []


@pytest.mark.parametrize("reference", ['DOC-1', 'xurn:test:doc2x'])
def test_h2b_identification_needs_domain_and_text_boundaries(tmp_path, reference):
    metadata = H2B_REVIEW_METADATA.replace('</rdf:RDF>', H2B_IDENTITY + '</rdf:RDF>')
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('urn:test:doc2</td>', reference + '</td>')
    assert findings(h2b_review_package(tmp_path, 'baseline', body, metadata), 'R68')


def test_h2b_identification_combines_iri_and_identity_alternatives(tmp_path):
    metadata = H2B_REVIEW_METADATA.replace('</rdf:RDF>', H2B_IDENTITY.replace('urn:test:doc2', 'urn:test:doc3') + '</rdf:RDF>')
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('urn:test:doc2</td>', 'urn:test:doc2 DOC-1 (urn:test:document-domain)</td>')
    got = findings(h2b_review_package(tmp_path, 'baseline', body, metadata), 'R68')
    assert any(f.violation.message == 'a row refers to more than one document' for f in got)
    assert any('row 1' in (f.violation.detail or '') for f in got)


def test_h2b_identification_shared_pdf_uses_title_with_suffix_and_not_language_spelling(tmp_path):
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('>en<', '>English<')
    for n in (2, 3):
        body = body.replace('Operating instructions %d</td>' % n, 'Operating instructions %d (revision 2)</td>' % n)
        body = body.replace('urn:test:doc%d</td>' % n, '<a href="/content/doc1.pdf#page=%d">Open</a></td>' % n)
    assert findings(h2b_review_package(tmp_path, 'baseline', body), 'R68') == []


def test_h2b_identification_ambiguous_shared_pdf_does_not_identify_a_document(tmp_path):
    body = content_list([('Summary', '<a href="content/doc1.pdf">Open</a>')], headers=()).replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    got = findings(h2b_review_package(tmp_path, 'baseline', body), 'R68')
    assert len(got) == 2
    assert all('has no row identifying document' in f.violation.message for f in got)


H2B_REVIEW_LISTS.update({
    'tfoot_total': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody><tfoot><tr><td colspan="5">Total: 3 information units</td></tr></tfoot></table></body></html>',
    'all_th_data_rows': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><th scope="row">Operating instructions 1</th><th scope="row">en</th><th scope="row">urn:test:variant</th><th scope="row">http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</th><th scope="row">urn:test:package</th></tr><tr><th scope="row">Operating instructions 2</th><th scope="row">en</th><th scope="row">urn:test:variant</th><th scope="row">http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</th><th scope="row">urn:test:doc2</th></tr><tr><th scope="row">Operating instructions 3</th><th scope="row">en</th><th scope="row">urn:test:variant</th><th scope="row">http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</th><th scope="row">urn:test:doc3</th></tr></tbody></table></body></html>',
    'rowspan_product': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td rowspan="3">urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>en</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'colspan_optional_note': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><tbody><tr><td colspan="2">Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>Delivered</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>Delivered</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'nested_table': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><tbody><tr><td><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></td></tr></tbody></table></body></html>',
})

@pytest.mark.parametrize("case", ["tfoot_total", "all_th_data_rows", "rowspan_product", "colspan_optional_note", "nested_table"])
def test_h2b_table_semantics_accept_headers_footers_and_spans(tmp_path, case):
    package = h2b_review_package(tmp_path, case)
    assert findings(package, "R68") == []
    assert findings(package, "R69") == []


def test_h2b_table_semantics_nested_cells_belong_only_to_the_inner_table(tmp_path):
    body = content_list([("Outer",)], headers=()).replace('<td>Outer</td>', '<td>Outer<table><tbody><tr><td>urn:test:doc2</td></tr><tr><td>urn:test:doc3</td></tr></tbody></table></td>')
    assert findings(h2b_review_package(tmp_path, 'baseline', body), 'R68') == []


H2B_REVIEW_LISTS.update({
    'split_row_column_witness': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>urn:test:package</td></tr><tr><td>urn:test:doc2</td></tr><tr><td>urn:test:doc3</td></tr></tbody></table><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr></tbody></table></body></html>',
    'language_english': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>English</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>English</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>English</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'title_suffix': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1 (rev. 2)</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2 (rev. 2)</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3 (rev. 2)</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
})

def test_h2b_cells_are_checked_for_every_document_across_tables(tmp_path):
    from iirds_validate.cli import main

    package = h2b_review_package(tmp_path, 'split_row_column_witness')
    assert findings(package, 'R68') == []
    got = findings(package, 'R69')
    assert {f.violation.message for f in got} == {
        'the row for document urn:test:doc2 provides fewer than five data cells',
        'the row for document urn:test:doc3 provides fewer than five data cells'}
    assert main(['check', '-W', str(package)]) == 1


@pytest.mark.parametrize('case', ['language_english', 'title_suffix'])
def test_h2b_cells_accept_human_readable_data(tmp_path, case):
    assert findings(h2b_review_package(tmp_path, case), 'R69') == []


def test_h2b_cells_example_62_shape_needs_no_package_data(tmp_path):
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('>en<', '>English<').replace('http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td>', 'iirdsHov:Operation</td>')
    metadata = H2B_REVIEW_METADATA.replace('<iirds:title>Operating instructions 1</iirds:title>', '').replace('<iirds:language>en</iirds:language>', '', 1).replace('<hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>', '', 1)
    package = h2b_review_package(tmp_path, 'baseline', body, metadata)
    assert not {f.rule.id for f in runner.check(package).findings} & {'R67', 'R68', 'R69'}


def test_h2b_cells_a_document_row_in_another_table_also_needs_five_cells(tmp_path):
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('</body>', '<table><tbody><tr><td>urn:test:doc2</td></tr></tbody></table></body>')
    got = findings(h2b_review_package(tmp_path, 'baseline', body), 'R69')
    assert len(got) == 1
    assert 'urn:test:doc2' in got[0].violation.message


def test_h2b_cells_empty_grid_positions_do_not_provide_data(tmp_path):
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('>en<', '><')
    assert len(findings(h2b_review_package(tmp_path, 'baseline', body), 'R69')) == 2


def test_h2b_elements_leave_onclick_to_one_b4_finding(tmp_path):
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('<td>en</td>', '<td onclick="alert(1)">en</td>', 1)
    package = h2b_review_package(tmp_path, 'baseline', body)
    assert len(findings(package, 'B4')) == 1
    assert findings(package, 'R67') == []


def test_h2b_elements_do_not_claim_the_unchecked_attribute_whitelist(tmp_path):
    from iirds_validate.registry import all_rules

    body = H2B_REVIEW_LISTS['package_row_missing'].replace('<td>en</td>', '<td invented="value">en</td>', 1)
    package = h2b_review_package(tmp_path, 'baseline', body)
    assert findings(package, 'R67') == []
    claim = 'x8-3-1-1-mandatory-content-list#4'
    assert not any(claim in rule.covers for rule in all_rules())


def test_h2b_elements_report_a_non_html_root(tmp_path):
    package = h2b_review_package(tmp_path, 'baseline', '<body/>')
    assert any('html document element' in f.violation.message for f in findings(package, 'R67'))


def test_h2b_public_descriptions_match_the_checked_scope(tmp_path, capsys):
    from iirds_validate.cli import main

    for rule, title, remedy in [
        ('R67', 'the content list follows the XHTML element restrictions', 'Replace the element named in this finding.'),
        ('R68', 'the content list identifies each delivered document in a table row', 'Add a row for the named document, or correct its reference.'),
        ('R69', 'the content list gives each document row five data cells', 'Provide document-title, language, product-reference, category or classification, and unit-reference data for the named document.'),
    ]:
        assert main(['rules', rule, '-v']) == 0
        output = capsys.readouterr().out
        assert title in output
        assert remedy in output
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('</body>', '<video/></body>')
    got = findings(h2b_review_package(tmp_path, 'baseline', body), 'R67')
    assert got[0].violation.message == 'index.html contains <video>, which section 8.3.1.1 excludes.'


def test_h2b_branches_record_no_new_silent_paths():
    import json

    from conftest import ROOT

    assert json.loads((ROOT / 'docs/silent-paths.json').read_text())['counts']['silent'] == 26


@pytest.mark.parametrize('body', [
    '<html><body><table/></body></html>',
    '<html xmlns:f="urn:foreign"><body><table><tbody><f:tr><f:td>urn:test:doc2</f:td></f:tr></tbody></table></body></html>',
])
def test_h2b_branches_empty_and_foreign_rows_do_not_identify_documents(tmp_path, body):
    package = h2b_review_package(tmp_path, 'baseline', body)
    assert len(findings(package, 'R68')) == 2
    assert findings(package, 'R69') == []


@pytest.mark.parametrize('span', ['0', 'invalid'])
def test_h2b_branches_rowspan_to_end_and_invalid_span_fallback(tmp_path, span):
    body = H2B_REVIEW_LISTS['rowspan_product'].replace('rowspan="3"', 'rowspan="%s"' % span)
    package = h2b_review_package(tmp_path, 'baseline', body)
    assert findings(package, 'R68') == []
    assert bool(findings(package, 'R69')) == (span == 'invalid')


def test_h2b_branches_shared_pdf_with_two_matching_titles_identifies_neither(tmp_path):
    body = '<html><body><table><tbody><tr><td>Operating instructions 2; Operating instructions 3 <a href="content/doc1.pdf">Open</a></td></tr></tbody></table></body></html>'
    got = findings(h2b_review_package(tmp_path, 'baseline', body), 'R68')
    assert len(got) == 2
    assert all('has no row identifying document' in f.violation.message for f in got)


H2B_REVIEW_LISTS.update({
    'header_first_table': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Summary</th></tr></thead></table><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'language_name_and_code': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>English (en)</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>English (en)</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>English (en)</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'title_suffix_wrapped': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td><span>Operating instructions 1</span> (rev. 2)</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td><span>Operating instructions 2</span> (rev. 2)</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td><span>Operating instructions 3</span> (rev. 2)</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'th_row_header_corrected': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><th scope="row">Operating instructions 1</th><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><th scope="row">Operating instructions 2</th><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><th scope="row">Operating instructions 3</th><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'topic_row_missing': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'topic_row_present': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr><tr><td>Supplement</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:extra</td></tr></tbody></table></body></html>',
    'fragment_row_missing': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
    'fragment_row_present': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><thead><tr><th>Title</th><th>Language</th><th>Product</th><th>Category</th><th>Reference</th></tr></thead><tbody><tr><td>Operating instructions 1</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td>Operating instructions 2</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td>Operating instructions 3</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr><tr><td>Supplement</td><td>en</td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:extra</td></tr></tbody></table></body></html>',
    'title_language_one_cell': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Delivered documents</title></head><body><table><tbody><tr><td><span>Operating instructions 1</span><br/><span>en</span></td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:package</td></tr><tr><td><span>Operating instructions 2</span><br/><span>en</span></td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc2</td></tr><tr><td><span>Operating instructions 3</span><br/><span>en</span></td><td>urn:test:variant</td><td>http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td><td>urn:test:doc3</td></tr></tbody></table></body></html>',
})

H2B_REVIEW_METADATA_BY_CASE = {
    'topic_row_missing': '<?xml version="1.0" encoding="utf-8"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n         xmlns:vcard="http://www.w3.org/2006/vcard/ns#"\n         xmlns:hov="http://iirds.tekom.de/iirds/domain/handover#"\n         xmlns:iirds="http://iirds.tekom.de/iirds#">\n  <iirds:Package rdf:about="urn:test:package">\n    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n    <iirds:formatRestriction>H</iirds:formatRestriction>\n    <iirds:title>Operating instructions 1</iirds:title><iirds:language>en</iirds:language><hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <!-- Section 8.3.2 states its product-variant requirements twice, once for\n         the Package and once for the Document, word for word. This fixture was\n         asserted conformant for weeks while carrying only the second: the\n         Package named no variant, and no rule read that list. R13 to R16 read\n         it now. Both may name the same variant, and the simplest conformant\n         package does. -->\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:Package>\n\n  <iirds:Document rdf:about="urn:test:doc2">\n    <iirds:title>Operating instructions 2</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n  <iirds:Document rdf:about="urn:test:doc3">\n    <iirds:title>Operating instructions 3</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n\n  <!-- Section 8.3.2 puts the creator of an information object on the identity\n       domain, not on the object: what is attributed is the scheme the content\n       is known by. The domain carries no iirds:has-identity-type, which is\n       what the reference\'s own passing fixture does; the type is required of\n       a product variant\'s domains (M15.7b, M15.7d), not of this one. -->\n  <iirds:InformationObject rdf:about="urn:test:io1">\n    <iirds:title>Operating instructions</iirds:title>\n    <iirds:has-identity rdf:resource="urn:test:identity-object"/>\n  </iirds:InformationObject>\n\n  <iirds:Identity rdf:about="urn:test:identity-object">\n    <iirds:identifier>OI-2026</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-object"/>\n  </iirds:Identity>\n\n  <iirds:IdentityDomain rdf:about="urn:test:domain-object">\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:IdentityDomain>\n\n  <iirds:ProductVariant rdf:about="urn:test:variant">\n    <rdfs:label xml:lang="en">Rotor 3000</rdfs:label>\n    <iirds:has-identity rdf:resource="urn:test:identity-instance"/>\n    <iirds:has-identity rdf:resource="urn:test:identity-type"/>\n  </iirds:ProductVariant>\n\n  <iirds:Identity rdf:about="urn:test:identity-instance">\n    <iirds:identifier>SN-00417</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-instance"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-instance">\n    <rdfs:label xml:lang="en">Serial numbers</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#SerialNumber"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <iirds:Identity rdf:about="urn:test:identity-type">\n    <iirds:identifier>ROT-3000</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-type"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-type">\n    <rdfs:label xml:lang="en">Product types</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#ProductType"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <!-- One organisation in three roles, which is ordinary for a handover: the\n       manufacturer wrote the documentation and shipped the package. The rules\n       ask for a different role in each place. Author on the Document, Creator\n       on the Package and InformationObject, Manufacturer on the identity\n       domains.\n\n       Three Party instances rather than one carrying three roles, because the\n       ontology states "Cardinality: iirds:Party [0..1]" for has-party-role and\n       the prose makes it mandatory, so a Party holds exactly one. Saying an\n       organisation acts in several roles means several Party nodes pointing at\n       the same vcard, and getting that wrong here was how this fixture first\n       failed M22.1. -->\n  <iirds:Party rdf:about="urn:test:party-manufacturer">\n    <rdfs:label xml:lang="en">Rotor Works, as manufacturer</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-author">\n    <rdfs:label xml:lang="en">Rotor Works, as author</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Author"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-creator">\n    <rdfs:label xml:lang="en">Rotor Works, as creator</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Creator"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <vcard:Organization rdf:about="urn:test:supplier-card">\n    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>\n  </vcard:Organization>\n<iirds:Topic rdf:about="urn:test:extra"><iirds:title>Supplement</iirds:title><iirds:language>en</iirds:language><iirds:relates-to-product-variant rdf:resource="urn:test:variant"/><hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/></iirds:Topic></rdf:RDF>\n',
    'topic_row_present': '<?xml version="1.0" encoding="utf-8"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n         xmlns:vcard="http://www.w3.org/2006/vcard/ns#"\n         xmlns:hov="http://iirds.tekom.de/iirds/domain/handover#"\n         xmlns:iirds="http://iirds.tekom.de/iirds#">\n  <iirds:Package rdf:about="urn:test:package">\n    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n    <iirds:formatRestriction>H</iirds:formatRestriction>\n    <iirds:title>Operating instructions 1</iirds:title><iirds:language>en</iirds:language><hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <!-- Section 8.3.2 states its product-variant requirements twice, once for\n         the Package and once for the Document, word for word. This fixture was\n         asserted conformant for weeks while carrying only the second: the\n         Package named no variant, and no rule read that list. R13 to R16 read\n         it now. Both may name the same variant, and the simplest conformant\n         package does. -->\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:Package>\n\n  <iirds:Document rdf:about="urn:test:doc2">\n    <iirds:title>Operating instructions 2</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n  <iirds:Document rdf:about="urn:test:doc3">\n    <iirds:title>Operating instructions 3</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n\n  <!-- Section 8.3.2 puts the creator of an information object on the identity\n       domain, not on the object: what is attributed is the scheme the content\n       is known by. The domain carries no iirds:has-identity-type, which is\n       what the reference\'s own passing fixture does; the type is required of\n       a product variant\'s domains (M15.7b, M15.7d), not of this one. -->\n  <iirds:InformationObject rdf:about="urn:test:io1">\n    <iirds:title>Operating instructions</iirds:title>\n    <iirds:has-identity rdf:resource="urn:test:identity-object"/>\n  </iirds:InformationObject>\n\n  <iirds:Identity rdf:about="urn:test:identity-object">\n    <iirds:identifier>OI-2026</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-object"/>\n  </iirds:Identity>\n\n  <iirds:IdentityDomain rdf:about="urn:test:domain-object">\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:IdentityDomain>\n\n  <iirds:ProductVariant rdf:about="urn:test:variant">\n    <rdfs:label xml:lang="en">Rotor 3000</rdfs:label>\n    <iirds:has-identity rdf:resource="urn:test:identity-instance"/>\n    <iirds:has-identity rdf:resource="urn:test:identity-type"/>\n  </iirds:ProductVariant>\n\n  <iirds:Identity rdf:about="urn:test:identity-instance">\n    <iirds:identifier>SN-00417</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-instance"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-instance">\n    <rdfs:label xml:lang="en">Serial numbers</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#SerialNumber"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <iirds:Identity rdf:about="urn:test:identity-type">\n    <iirds:identifier>ROT-3000</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-type"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-type">\n    <rdfs:label xml:lang="en">Product types</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#ProductType"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <!-- One organisation in three roles, which is ordinary for a handover: the\n       manufacturer wrote the documentation and shipped the package. The rules\n       ask for a different role in each place. Author on the Document, Creator\n       on the Package and InformationObject, Manufacturer on the identity\n       domains.\n\n       Three Party instances rather than one carrying three roles, because the\n       ontology states "Cardinality: iirds:Party [0..1]" for has-party-role and\n       the prose makes it mandatory, so a Party holds exactly one. Saying an\n       organisation acts in several roles means several Party nodes pointing at\n       the same vcard, and getting that wrong here was how this fixture first\n       failed M22.1. -->\n  <iirds:Party rdf:about="urn:test:party-manufacturer">\n    <rdfs:label xml:lang="en">Rotor Works, as manufacturer</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-author">\n    <rdfs:label xml:lang="en">Rotor Works, as author</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Author"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-creator">\n    <rdfs:label xml:lang="en">Rotor Works, as creator</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Creator"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <vcard:Organization rdf:about="urn:test:supplier-card">\n    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>\n  </vcard:Organization>\n<iirds:Topic rdf:about="urn:test:extra"><iirds:title>Supplement</iirds:title><iirds:language>en</iirds:language><iirds:relates-to-product-variant rdf:resource="urn:test:variant"/><hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/></iirds:Topic></rdf:RDF>\n',
    'fragment_row_missing': '<?xml version="1.0" encoding="utf-8"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n         xmlns:vcard="http://www.w3.org/2006/vcard/ns#"\n         xmlns:hov="http://iirds.tekom.de/iirds/domain/handover#"\n         xmlns:iirds="http://iirds.tekom.de/iirds#">\n  <iirds:Package rdf:about="urn:test:package">\n    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n    <iirds:formatRestriction>H</iirds:formatRestriction>\n    <iirds:title>Operating instructions 1</iirds:title><iirds:language>en</iirds:language><hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <!-- Section 8.3.2 states its product-variant requirements twice, once for\n         the Package and once for the Document, word for word. This fixture was\n         asserted conformant for weeks while carrying only the second: the\n         Package named no variant, and no rule read that list. R13 to R16 read\n         it now. Both may name the same variant, and the simplest conformant\n         package does. -->\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:Package>\n\n  <iirds:Document rdf:about="urn:test:doc2">\n    <iirds:title>Operating instructions 2</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n  <iirds:Document rdf:about="urn:test:doc3">\n    <iirds:title>Operating instructions 3</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n\n  <!-- Section 8.3.2 puts the creator of an information object on the identity\n       domain, not on the object: what is attributed is the scheme the content\n       is known by. The domain carries no iirds:has-identity-type, which is\n       what the reference\'s own passing fixture does; the type is required of\n       a product variant\'s domains (M15.7b, M15.7d), not of this one. -->\n  <iirds:InformationObject rdf:about="urn:test:io1">\n    <iirds:title>Operating instructions</iirds:title>\n    <iirds:has-identity rdf:resource="urn:test:identity-object"/>\n  </iirds:InformationObject>\n\n  <iirds:Identity rdf:about="urn:test:identity-object">\n    <iirds:identifier>OI-2026</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-object"/>\n  </iirds:Identity>\n\n  <iirds:IdentityDomain rdf:about="urn:test:domain-object">\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:IdentityDomain>\n\n  <iirds:ProductVariant rdf:about="urn:test:variant">\n    <rdfs:label xml:lang="en">Rotor 3000</rdfs:label>\n    <iirds:has-identity rdf:resource="urn:test:identity-instance"/>\n    <iirds:has-identity rdf:resource="urn:test:identity-type"/>\n  </iirds:ProductVariant>\n\n  <iirds:Identity rdf:about="urn:test:identity-instance">\n    <iirds:identifier>SN-00417</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-instance"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-instance">\n    <rdfs:label xml:lang="en">Serial numbers</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#SerialNumber"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <iirds:Identity rdf:about="urn:test:identity-type">\n    <iirds:identifier>ROT-3000</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-type"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-type">\n    <rdfs:label xml:lang="en">Product types</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#ProductType"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <!-- One organisation in three roles, which is ordinary for a handover: the\n       manufacturer wrote the documentation and shipped the package. The rules\n       ask for a different role in each place. Author on the Document, Creator\n       on the Package and InformationObject, Manufacturer on the identity\n       domains.\n\n       Three Party instances rather than one carrying three roles, because the\n       ontology states "Cardinality: iirds:Party [0..1]" for has-party-role and\n       the prose makes it mandatory, so a Party holds exactly one. Saying an\n       organisation acts in several roles means several Party nodes pointing at\n       the same vcard, and getting that wrong here was how this fixture first\n       failed M22.1. -->\n  <iirds:Party rdf:about="urn:test:party-manufacturer">\n    <rdfs:label xml:lang="en">Rotor Works, as manufacturer</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-author">\n    <rdfs:label xml:lang="en">Rotor Works, as author</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Author"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-creator">\n    <rdfs:label xml:lang="en">Rotor Works, as creator</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Creator"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <vcard:Organization rdf:about="urn:test:supplier-card">\n    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>\n  </vcard:Organization>\n<iirds:Fragment rdf:about="urn:test:extra"><iirds:title>Supplement</iirds:title><iirds:language>en</iirds:language><iirds:relates-to-product-variant rdf:resource="urn:test:variant"/><hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/></iirds:Fragment></rdf:RDF>\n',
    'fragment_row_present': '<?xml version="1.0" encoding="utf-8"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n         xmlns:vcard="http://www.w3.org/2006/vcard/ns#"\n         xmlns:hov="http://iirds.tekom.de/iirds/domain/handover#"\n         xmlns:iirds="http://iirds.tekom.de/iirds#">\n  <iirds:Package rdf:about="urn:test:package">\n    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n    <iirds:formatRestriction>H</iirds:formatRestriction>\n    <iirds:title>Operating instructions 1</iirds:title><iirds:language>en</iirds:language><hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <!-- Section 8.3.2 states its product-variant requirements twice, once for\n         the Package and once for the Document, word for word. This fixture was\n         asserted conformant for weeks while carrying only the second: the\n         Package named no variant, and no rule read that list. R13 to R16 read\n         it now. Both may name the same variant, and the simplest conformant\n         package does. -->\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:Package>\n\n  <iirds:Document rdf:about="urn:test:doc2">\n    <iirds:title>Operating instructions 2</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n  <iirds:Document rdf:about="urn:test:doc3">\n    <iirds:title>Operating instructions 3</iirds:title>\n    <iirds:language>en</iirds:language>\n    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n    <hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/>\n    <iirds:is-version-of rdf:resource="urn:test:io1"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-author"/>\n    <iirds:relates-to-product-variant rdf:resource="urn:test:variant"/>\n    <iirds:has-rendition>\n      <iirds:Rendition>\n        <iirds:format>application/pdf</iirds:format>\n        <iirds:source>content/doc1.pdf</iirds:source>\n      </iirds:Rendition>\n    </iirds:has-rendition>\n  </iirds:Document>\n\n  <!-- Section 8.3.2 puts the creator of an information object on the identity\n       domain, not on the object: what is attributed is the scheme the content\n       is known by. The domain carries no iirds:has-identity-type, which is\n       what the reference\'s own passing fixture does; the type is required of\n       a product variant\'s domains (M15.7b, M15.7d), not of this one. -->\n  <iirds:InformationObject rdf:about="urn:test:io1">\n    <iirds:title>Operating instructions</iirds:title>\n    <iirds:has-identity rdf:resource="urn:test:identity-object"/>\n  </iirds:InformationObject>\n\n  <iirds:Identity rdf:about="urn:test:identity-object">\n    <iirds:identifier>OI-2026</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-object"/>\n  </iirds:Identity>\n\n  <iirds:IdentityDomain rdf:about="urn:test:domain-object">\n    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>\n  </iirds:IdentityDomain>\n\n  <iirds:ProductVariant rdf:about="urn:test:variant">\n    <rdfs:label xml:lang="en">Rotor 3000</rdfs:label>\n    <iirds:has-identity rdf:resource="urn:test:identity-instance"/>\n    <iirds:has-identity rdf:resource="urn:test:identity-type"/>\n  </iirds:ProductVariant>\n\n  <iirds:Identity rdf:about="urn:test:identity-instance">\n    <iirds:identifier>SN-00417</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-instance"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-instance">\n    <rdfs:label xml:lang="en">Serial numbers</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#SerialNumber"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <iirds:Identity rdf:about="urn:test:identity-type">\n    <iirds:identifier>ROT-3000</iirds:identifier>\n    <iirds:has-identity-domain rdf:resource="urn:test:domain-type"/>\n  </iirds:Identity>\n  <iirds:IdentityDomain rdf:about="urn:test:domain-type">\n    <rdfs:label xml:lang="en">Product types</rdfs:label>\n    <iirds:has-identity-type rdf:resource="http://iirds.tekom.de/iirds#ProductType"/>\n    <iirds:relates-to-party rdf:resource="urn:test:party-manufacturer"/>\n  </iirds:IdentityDomain>\n\n  <!-- One organisation in three roles, which is ordinary for a handover: the\n       manufacturer wrote the documentation and shipped the package. The rules\n       ask for a different role in each place. Author on the Document, Creator\n       on the Package and InformationObject, Manufacturer on the identity\n       domains.\n\n       Three Party instances rather than one carrying three roles, because the\n       ontology states "Cardinality: iirds:Party [0..1]" for has-party-role and\n       the prose makes it mandatory, so a Party holds exactly one. Saying an\n       organisation acts in several roles means several Party nodes pointing at\n       the same vcard, and getting that wrong here was how this fixture first\n       failed M22.1. -->\n  <iirds:Party rdf:about="urn:test:party-manufacturer">\n    <rdfs:label xml:lang="en">Rotor Works, as manufacturer</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-author">\n    <rdfs:label xml:lang="en">Rotor Works, as author</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Author"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <iirds:Party rdf:about="urn:test:party-creator">\n    <rdfs:label xml:lang="en">Rotor Works, as creator</rdfs:label>\n    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Creator"/>\n    <iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n  </iirds:Party>\n  <vcard:Organization rdf:about="urn:test:supplier-card">\n    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>\n  </vcard:Organization>\n<iirds:Fragment rdf:about="urn:test:extra"><iirds:title>Supplement</iirds:title><iirds:language>en</iirds:language><iirds:relates-to-product-variant rdf:resource="urn:test:variant"/><hov:has-document-category rdf:resource="http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions"/></iirds:Fragment></rdf:RDF>\n',
}


@pytest.mark.parametrize('case', sorted(H2B_REVIEW_LISTS))
def test_h2b_regression_frozen_content_lists(tmp_path, case):
    metadata = H2B_REVIEW_METADATA_BY_CASE.get(case, H2B_REVIEW_METADATA)
    package = h2b_review_package(tmp_path, case, metadata=metadata)
    report = runner.check(package)
    list_findings = {f.rule.id for f in report.findings} & {'R67', 'R68', 'R69'}
    expected = {'R69'} if case in ('split_row_column_witness', 'title_language_one_cell') else set()
    assert list_findings == expected
    if case.startswith(('topic_', 'fragment_')):
        assert findings(package, 'M15.11a')
    if case == 'split_row_column_witness':
        from iirds_validate.cli import main
        assert main(['check', str(package)]) == 0
        assert main(['check', '-W', str(package)]) == 1


def test_h2b_regression_document_rows_can_be_in_different_tables(tmp_path):
    rows = list_rows()[1:]
    body = content_list(rows[:1], extra=content_list(rows[1:]).split('<body>')[1].split('</body>')[0])
    package = h2b_review_package(tmp_path, 'baseline', body)
    assert findings(package, 'R68') == []
    assert findings(package, 'R69') == []


def test_h2b_regression_missing_duplicate_and_multiple_references_name_the_document(tmp_path):
    missing = content_list(list_rows()[1:2])
    got = findings(h2b_review_package(tmp_path, 'baseline', missing), 'R68')
    assert [f.violation.message for f in got] == ['index.html has no row identifying document urn:test:doc3']
    duplicate = content_list(list_rows()[1:] + [list_rows()[1]])
    got = findings(h2b_review_package(tmp_path, 'baseline', duplicate), 'R68')
    assert [f.violation.message for f in got] == ['index.html lists document urn:test:doc2 more than once']
    assert got[0].violation.detail == 'rows 1, 3'
    multiple = content_list(list_rows()[1:]).replace('urn:test:doc2</td>', 'urn:test:doc2; urn:test:doc3</td>')
    got = findings(h2b_review_package(tmp_path, 'baseline', multiple), 'R68')
    assert any(f.violation.message == 'a row refers to more than one document' and f.violation.detail == 'row 1' for f in got)


def test_h2b_regression_example_62_shape_has_no_findings(tmp_path):
    from iirds_validate.cli import main

    body = H2B_REVIEW_LISTS['package_row_missing'].replace('>en<', '>English<').replace('http://iirds.tekom.de/iirds/domain/handover#OperatingInstructions</td>', 'iirdsHov:Operation</td>')
    package = h2b_review_package(tmp_path, 'baseline', body)
    assert runner.check(package).findings == []
    assert main(['check', '-W', str(package)]) == 0


def test_h2b_regression_iri_identity_value_and_domain_can_share_one_text_node(tmp_path):
    metadata = H2B_REVIEW_METADATA.replace('</rdf:RDF>', H2B_IDENTITY + '</rdf:RDF>')
    body = H2B_REVIEW_LISTS['package_row_missing'].replace('urn:test:doc2</td>', 'DOC-1 (urn:test:document-domain)</td>')
    package = h2b_review_package(tmp_path, 'baseline', body, metadata)
    assert findings(package, 'R68') == []
    assert findings(package, 'R69') == []


@pytest.mark.parametrize('table', [False, True])
def test_h2b_regression_tabular_data_is_required_even_without_documents(tmp_path, table):
    """#5 still requires tabular data when the delivered-document population is empty."""
    start = HANDOVER.index('  <iirds:Document rdf:about="urn:test:doc1">')
    end = HANDOVER.index('  </iirds:Document>', start) + len('  </iirds:Document>')
    metadata = HANDOVER[:start] + HANDOVER[end:]
    body = '<html><body>%s</body></html>' % ('<table/>' if table else '')
    package = build_package(tmp_path, 'no-documents.iirds', metadata=metadata,
                            jsonld=as_jsonld(metadata), content=(), extra=(('index.html', body),))
    got = findings(package, 'R68')
    assert bool(got) == (not table)
    assert findings(package, 'R69') == []


def test_data_roles_are_not_verified(tmp_path):
    """x8-3-1-1-mandatory-content-list#5 / #6
    The content list MUST contain tabular data according to section Tabular Data with one row per information unit and MUST at least contain columns providing the following data (see Metadata Requirements):
    The row identifies the document but supplies none of the other data roles.
    """
    body = content_list([('urn:test:doc1', 'approved', 'page 1', 'note A', 'note B')])
    package = listed_handover(tmp_path, 'unverified-data.iirds', body=body, metadata=HANDOVER)
    assert findings(package, 'R68') == []
    assert findings(package, 'R69') == []
    assert findings(package, 'C11.2') == []


def test_content_list_partial_checks_do_not_claim_the_data_sentence():
    from iirds_validate.registry import all_rules
    from test_covers_is_earned import NAMED_CASES

    claim = 'x8-3-1-1-mandatory-content-list#5'
    rules = {rule.id: rule for rule in all_rules()}
    assert rules['R68'].covers == ()
    assert claim not in rules['C11.2'].covers
    assert claim not in NAMED_CASES
    assert not any(claim in rule.covers for rule in rules.values())


def test_content_list_claim_totals_exclude_unverified_data():
    from test_covers_is_earned import CLAIMED, UNAUDITED, held
    from test_requirement_coverage import CLAIMED as rule_claims

    assert len(CLAIMED) == 184
    assert len(held()) == 149
    assert len(UNAUDITED) == 35
    assert sum(len(ids) for ids in rule_claims.values()) == 211
