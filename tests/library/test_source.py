"""source_of(): from a Rendition to the file it names.

The helper a naive implementation gets wrong. iirds:source values in the
wild carry leading slashes, ./ prefixes and internal ../ segments; a
resolver that compares them literally answers "no such file" about files
that are right there, and one that resolves without looking lets a
hostile path walk out of the package.

§6.3 calls the value a URL, twice, in one normative sentence, so it is
read as one: percent-decoded, fragment and query cut. Appendix A calls
the same value a relative path with range rdfs:Literal, so this is a
choice between two normative sentences and not a fact -- the checker's
docs/divergences.md carries both sides. The tests at the bottom of this
file record what the choice costs, because §5.1.3 permits `%` and `#` in
a file name and one legal spelling of a legal name goes unreachable.

The resolution here is the checker's, case for case. What differs is
what happens at the end: a reader refuses to resolve what escapes, a
validator answers None and reports it. Same reading, different layer.
"""
from __future__ import annotations

import zipfile

import pytest
from rdflib import Graph

import iirds

RDF_WITH_RENDITION = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
  </iirds:Package>
  <iirds:Rendition rdf:about="urn:test:rendition">
    <iirds:source>%s</iirds:source>
  </iirds:Rendition>
</rdf:RDF>
"""

RENDITION = iirds.IIRDS["Rendition"]


def package_with_source(tmp_path, source, entries=("content/topic1.xhtml",)):
    path = tmp_path / "pkg.iirds"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/iirds+zip")
        archive.writestr("META-INF/metadata.rdf",
                         (RDF_WITH_RENDITION % source).encode("utf-8"))
        for entry in entries:
            archive.writestr(entry, b"<html/>")
    return path


@pytest.mark.parametrize("spelling", [
    "content/topic1.xhtml",
    "/content/topic1.xhtml",
    "./content/topic1.xhtml",
    "content/extra/../topic1.xhtml",
])
def test_the_spellings_the_wild_actually_uses(tmp_path, spelling):
    with iirds.open(package_with_source(tmp_path, spelling)) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) == "content/topic1.xhtml"
        with pkg.open(rendition) as handle:
            assert handle.read() == b"<html/>"


def test_resolution_does_not_judge_existence(tmp_path):
    """source_of answers "what does this rendition name"; whether the
    entry exists is open()'s business and the validator's finding."""
    packed = package_with_source(tmp_path, "content/missing.pdf")
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) == "content/missing.pdf"
        with pytest.raises(iirds.IirdsError, match="missing.pdf"):
            pkg.open(rendition)


def test_a_path_that_escapes_the_package_is_refused(tmp_path):
    packed = package_with_source(tmp_path, "../../etc/passwd")
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        with pytest.raises(iirds.IirdsError, match="escapes"):
            pkg.source_of(rendition)


def test_a_node_without_a_source_answers_none_and_open_refuses(tmp_path):
    packed = package_with_source(tmp_path, "content/topic1.xhtml")
    with iirds.open(packed) as pkg:
        package_node = pkg.instances_of(iirds.IIRDS["Package"])[0]
        assert pkg.source_of(package_node) is None
        with pytest.raises(iirds.IirdsError, match="no iirds:source"):
            pkg.open(package_node)


def test_the_module_level_function_needs_only_a_graph():
    graph = Graph()
    graph.parse(data=RDF_WITH_RENDITION % "/content/topic1.xhtml", format="xml",
                publicID=iirds.PACKAGE_BASE)
    (rendition,) = iirds.instances_of(graph, RENDITION)
    assert iirds.source_of(graph, rendition) == "content/topic1.xhtml"


def test_a_backslash_traversal_is_refused(tmp_path):
    """The oldest zip-slip spelling: `..\\..\\etc`. posixpath does not
    touch backslashes, so the guard must fold them first (the validator
    does exactly this in system.py)."""
    packed = package_with_source(tmp_path, "..\\..\\etc\\passwd.xhtml")
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        with pytest.raises(iirds.IirdsError, match="escape"):
            pkg.source_of(rendition)


def test_an_empty_source_names_nothing(tmp_path):
    packed = package_with_source(tmp_path, "")
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) is None


def test_a_percent_encoded_name_reaches_the_file_it_names(tmp_path):
    """`iirds:source` is a URI reference, so a file whose name carries a
    space arrives percent-encoded. Comparing the encoded spelling against
    the entry list answers "no such file" about a file that is right there."""
    packed = package_with_source(tmp_path, "content/a%20b.xhtml",
                                 entries=("content/a b.xhtml",))
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) == "content/a b.xhtml"
        with pkg.open(rendition) as handle:
            assert handle.read() == b"<html/>"


def test_a_hash_in_a_name_arrives_encoded_and_a_fragment_does_not(tmp_path):
    """One consequence of reading the value as a URL: if `#` delimits a
    fragment then a `#` in a name must be written `%23`.

    Not because a rendition points into a document that way -- §6.3.1 says
    it does not, and the spec's own worked example puts the fragment in an
    iirds:FragmentSelector beside a whole-file iirds:source. Only because
    a URL's fragment is not part of its path. The cost of that is measured
    two tests below."""
    packed = package_with_source(tmp_path, "content/a%23b.xhtml",
                                 entries=("content/a#b.xhtml",))
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) == "content/a#b.xhtml"


@pytest.mark.parametrize("spelling", [
    "content/topic1.xhtml#section-2",
    "content/topic1.xhtml?revision=2",
    "content/topic1.xhtml?revision=2#section-2",
])
def test_a_fragment_or_query_is_not_part_of_the_entry_name(tmp_path, spelling):
    """A URL's fragment and query are not part of its path, so neither is
    part of the entry the value names."""
    packed = package_with_source(tmp_path, spelling)
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) == "content/topic1.xhtml"
        with pkg.open(rendition) as handle:
            assert handle.read() == b"<html/>"


def test_a_percent_encoded_traversal_is_refused(tmp_path):
    """The escape check has to run on what the value means, not on how it
    is spelled: `%2e%2e` is `..` and a guard reading raw text walks past it."""
    packed = package_with_source(tmp_path, "content/%2e%2e/%2e%2e/etc/passwd")
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        with pytest.raises(iirds.IirdsError, match="escapes"):
            pkg.source_of(rendition)


@pytest.mark.parametrize("elsewhere", [
    "http://example.com/topic1.xhtml",
    "https://example.com/topic1.xhtml",
    "file:///etc/passwd",
    "mailto:someone@example.com",
    "urn:uuid:2c2d4f2e-0000-0000-0000-000000000000",
    "data:text/plain,hello",
    "content/a%3Ab.xhtml",
])
def test_a_value_a_file_name_may_not_carry_names_no_entry(tmp_path, elsewhere):
    """§5.1.3 excludes `:` from file and directory names, so a value still
    holding one after decoding cannot be naming an entry -- whatever the
    scheme, and whether the colon was written or encoded. Normalising such
    a value as a path invents a name (`http:/example.com/...`) that nothing
    in any container will match."""
    packed = package_with_source(tmp_path, elsewhere)
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) is None


def test_open_says_which_of_the_two_silences_it_met(tmp_path):
    """A node with no source and a node whose source names nothing in this
    container both answer None, and telling a reader they declared no
    source when they declared one sends them looking for the wrong thing."""
    packed = package_with_source(tmp_path, "http://example.com/topic1.xhtml")
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        with pytest.raises(iirds.IirdsError, match="not an entry in this container"):
            pkg.open(rendition)


# ---------------------------------------------------------------------------
# What the URL reading costs
#
# §5.1.3 permits `%` and `#` in a file name. Reading iirds:source as a URL
# therefore makes one legal spelling of a legal name unreachable, and these
# record which one, so that nobody has to discover it. They are not a wish:
# they pass, and they will keep passing until the reading changes.
# ---------------------------------------------------------------------------

def test_a_file_actually_named_with_a_percent_escape_is_unreachable(tmp_path):
    """Both entries below are legal under §5.1.3 and name different files.
    Read as a URL, one value addresses the other one's file and nothing
    addresses this one."""
    packed = package_with_source(
        tmp_path, "content/a%20b.xhtml",
        entries=("content/a b.xhtml", "content/a%20b.xhtml"))
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) == "content/a b.xhtml", (
            "the file literally named content/a%20b.xhtml cannot be named "
            "by any iirds:source value under this reading")


def test_a_file_actually_named_with_a_hash_is_unreachable(tmp_path):
    """The same cost on the other character. `content/a#b.xhtml` is a legal
    entry name and every spelling of it resolves somewhere else."""
    packed = package_with_source(tmp_path, "content/a#b.xhtml",
                                 entries=("content/a#b.xhtml",))
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) == "content/a"
        with pytest.raises(iirds.IirdsError, match="no such entry"):
            pkg.open(rendition)


def test_a_directory_actually_named_with_an_escape_resolves_elsewhere(tmp_path):
    """The sharpest edge of the reading, and it does not announce itself.
    `%` is legal in a directory name, so a conformant package may hold a
    directory called `%2e%2e`. Decoding turns the value into `content/../`
    and it quietly names a different file -- one directory up, which here
    is the package root. Not a refusal a reader could act on: a wrong
    answer that looks like a right one."""
    packed = package_with_source(tmp_path, "content/%2e%2e/topic1.xhtml",
                                 entries=("content/%2e%2e/topic1.xhtml",
                                          "topic1.xhtml"))
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        assert pkg.source_of(rendition) == "topic1.xhtml"


def test_a_deeper_escape_spelled_with_escapes_is_refused(tmp_path):
    """Two levels up leaves the package, and the refusal has to see that
    through the encoding: a guard reading raw text finds no `..` here."""
    packed = package_with_source(tmp_path, "%2e%2e/%2e%2e/etc/passwd")
    with iirds.open(packed) as pkg:
        (rendition,) = pkg.instances_of(RENDITION)
        with pytest.raises(iirds.IirdsError, match="escapes"):
            pkg.source_of(rendition)


def test_open_names_the_silence_it_met(tmp_path):
    """Three values answer None and each sends a reader somewhere else."""
    cases = (("content/topic1.xhtml", "no iirds:source", True),
             # A blank-but-not-empty value is a legal file name under
             # §5.1.3, so it names an entry and misses this branch.
             ("", "empty iirds:source", False),
             ("http://example.com/x", "not an entry in this container", False))
    for source, expected, on_package in cases:
        packed = package_with_source(tmp_path, source)
        with iirds.open(packed) as pkg:
            node = (pkg.instances_of(iirds.IIRDS["Package"])[0] if on_package
                    else pkg.instances_of(RENDITION)[0])
            with pytest.raises(iirds.IirdsError, match=expected):
                pkg.open(node)
