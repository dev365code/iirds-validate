"""The metadata an .iirds file carries is untrusted input.

A package arrives from a supplier. The validator refuses hostile
serialisations before its parser sees them; an SDK whose open() happily
parses the same bytes hands every downstream tool the problem the
validator exists to stop. These tests hold the SDK to the validator's
refusals -- same guards, same error strings, because the two projects
answer to one another.
"""
import re
import zipfile

import pytest

import iirds
import iirds._metadata

MINIMAL_JSONLD = (b'{"@context": {"iirds": "http://iirds.tekom.de/iirds#"},'
                  b' "@id": "urn:test:package", "@type": "iirds:Package"}')

RDF_XML = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
  </iirds:Package>
</rdf:RDF>
"""

#: A perfectly tame declaration -- one entity, used once. The gate has to
#: fire on the declaration itself, not on whether the expansion happens to
#: be affordable, because "affordable" is what the geometric case fakes.
ENTITY_RDF = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE rdf:RDF [<!ENTITY v "1.3">]>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>&v;</iirds:iiRDSVersion>
  </iirds:Package>
</rdf:RDF>
"""


def package_with(tmp_path, rdf=None, jsonld=None):
    path = tmp_path / "pkg.iirds"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", b"application/iirds+zip")
        if rdf is not None:
            archive.writestr("META-INF/metadata.rdf", rdf)
        if jsonld is not None:
            archive.writestr("META-INF/metadata.jsonld", jsonld)
    return path


# --- the 0.1.0 defect: hostile metadata sailed straight through -------------

def test_xml_entity_declarations_are_refused(tmp_path):
    packed = package_with(tmp_path, ENTITY_RDF.encode("utf-8"))
    with iirds.open(packed) as pkg, pytest.raises(iirds.IirdsError) as caught:
        _ = pkg.graph                    # opening itself stayed lazy and cheap
    message = str(caught.value)
    assert "META-INF/metadata.rdf" in message
    assert "XML entities" in message


def test_oversized_metadata_is_refused_unread(tmp_path):
    padded = RDF_XML.encode("utf-8") + b" " * (64 * 1024 * 1024)
    packed = package_with(tmp_path, padded)
    with iirds.open(packed) as pkg, pytest.raises(iirds.IirdsError) as caught:
        _ = pkg.graph
    assert "byte limit" in str(caught.value)


def test_a_bom_marked_utf16_document_parses(tmp_path):
    """XML says the byte order mark decides the encoding; rdflib decodes
    UTF-8 unconditionally. The validator honours the BOM, so the SDK must,
    or the same conformant package opens in one tool and not the other."""
    utf16 = RDF_XML.replace('encoding="utf-8"', 'encoding="utf-16"')
    packed = package_with(tmp_path, b"\xff\xfe" + utf16.encode("utf-16-le"))
    with iirds.open(packed) as pkg:
        assert pkg.version == "1.3"


# --- metadata.jsonld: the second serialisation iiRDS names ------------------

JSONLD = """{
  "@context": {"iirds": "http://iirds.tekom.de/iirds#"},
  "@id": "urn:test:package",
  "@type": "iirds:Package",
  "iirds:title": "from the json-ld side"
}"""


def test_jsonld_beside_rdf_is_read_and_merged(tmp_path):
    packed = package_with(tmp_path, RDF_XML.encode("utf-8"), JSONLD.encode("utf-8"))
    with iirds.open(packed) as pkg:
        assert pkg.version == "1.3"                       # from the RDF/XML side
        assert pkg.label_of(next(iter(pkg.instances_of(iirds.IIRDS["Package"])))) \
            == "from the json-ld side"                    # from the JSON-LD side
        assert pkg.metadata_sources == [iirds.METADATA_RDF, iirds.METADATA_JSONLD]
        assert pkg.parse_errors == []


def test_isomorphic_serialisations_merge_as_one(tmp_path):
    """Blank nodes cannot be co-identified across documents, so naively
    unioning two serialisations of one graph doubles every blank-node-rooted
    structure. One anonymous Component, shipped in both files, must still
    count as one Component -- the validator's merge rule, shared."""
    rdf = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
  </iirds:Package>
  <iirds:Component/>
</rdf:RDF>
"""
    jsonld = """{
  "@context": {"iirds": "http://iirds.tekom.de/iirds#"},
  "@graph": [
    {"@id": "urn:test:package", "@type": "iirds:Package", "iirds:iiRDSVersion": "1.3"},
    {"@type": "iirds:Component"}
  ]
}"""
    packed = package_with(tmp_path, rdf.encode("utf-8"), jsonld.encode("utf-8"))
    with iirds.open(packed) as pkg:
        assert pkg.metadata_sources == [iirds.METADATA_RDF, iirds.METADATA_JSONLD]
        assert len(pkg.instances_of(iirds.IIRDS["Component"])) == 1
        assert len(pkg.graph) == 3


def test_divergent_sources_still_union(tmp_path):
    """Two sources that genuinely disagree both stay in the graph: their
    disagreement is the validator's finding to report, and hiding either
    side would hide the evidence."""
    other = JSONLD.replace('"iirds:title": "from the json-ld side"',
                           '"iirds:iiRDSVersion": "1.2"')
    packed = package_with(tmp_path, RDF_XML.encode("utf-8"), other.encode("utf-8"))
    with iirds.open(packed) as pkg:
        versions = {str(o) for o in pkg.graph.objects(
            None, iirds.IIRDS["iiRDSVersion"])}
        assert versions == {"1.3", "1.2"}


def test_a_broken_jsonld_degrades_softly(tmp_path):
    """metadata.rdf parsed, so the graph works; the broken sibling is
    reported, not fatal, and not silently dropped either."""
    packed = package_with(tmp_path, RDF_XML.encode("utf-8"), b"{ not json")
    with iirds.open(packed) as pkg:
        assert pkg.version == "1.3"
        assert pkg.metadata_sources == [iirds.METADATA_RDF]
        assert len(pkg.parse_errors) == 1
        assert pkg.parse_errors[0].startswith("META-INF/metadata.jsonld: ")


def test_a_remote_jsonld_context_is_refused(tmp_path):
    """A @context URL is a network fetch the sender chose. Reading a
    package must not touch the network, so the document is refused."""
    remote = JSONLD.replace('{"iirds": "http://iirds.tekom.de/iirds#"}',
                            '"https://iirds.example/context.jsonld"')
    packed = package_with(tmp_path, RDF_XML.encode("utf-8"), remote.encode("utf-8"))
    with iirds.open(packed) as pkg:
        assert pkg.metadata_sources == [iirds.METADATA_RDF]
        assert "@context must be inline" in pkg.parse_errors[0]


def test_jsonld_alone_is_still_not_a_package(tmp_path):
    """iiRDS requires metadata.rdf; metadata.jsonld is 'additionally
    allowed'. The 0.1.0 contract stands: no metadata.rdf, no package."""
    packed = package_with(tmp_path, None, JSONLD.encode("utf-8"))
    with pytest.raises(iirds.IirdsError):
        iirds.open(packed)


def test_metadata_graphs_are_per_source(tmp_path):
    packed = package_with(tmp_path, RDF_XML.encode("utf-8"), JSONLD.encode("utf-8"))
    with iirds.open(packed) as pkg:
        graphs = pkg.metadata_graphs
        assert set(graphs) == {iirds.METADATA_RDF, iirds.METADATA_JSONLD}
        assert len(graphs[iirds.METADATA_JSONLD]) == 2   # @type + title


# --- parse_metadata and merge_sources stand alone ---------------------------

def test_parse_metadata_is_a_pure_function():
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF, RDF_XML.encode("utf-8"),
                                        base=iirds.PACKAGE_BASE)
    assert error is None and len(graph) == 2
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF, b"<rdf:RDF",
                                        base=iirds.PACKAGE_BASE)
    assert graph is None
    name, sep, detail = error.partition(": ")
    assert (name, sep) == (iirds.METADATA_RDF, ": ") and detail


@pytest.mark.parametrize("bom,codec", [
    (b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"),
    (b"\xef\xbb\xbf", "utf-8"),
])
def test_every_byte_order_mark_is_honoured(bom, codec):
    raw = bom + RDF_XML.encode(codec)
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF, raw, base=iirds.PACKAGE_BASE)
    assert error is None and len(graph) == 2


#: The same five, minus utf-8: dropping one byte from an ASCII utf-8 payload
#: leaves a document that still decodes. For every multi-byte encoding it
#: leaves half a code unit, which is what a transfer cut short looks like.
TRUNCATABLE = [
    (b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"),
]


#: Every encoding the reader might meet, written *without* a byte order mark.
#: XML says a UTF-16 document must carry one, and expat reads it anyway.
ENCODINGS = ["utf-8", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"]


#: A document may open with `Misc*` before its root element and may have no
#: XML declaration at all, so "starts with `<`" is not a property of XML --
#: it was a property of the fixtures. Every lead here is legal and expat
#: autodetects all of them.
LEADS = {"declaration": "", "newline": "\n", "space": "  ", "tab": "\t",
         "comment": "<!-- c -->\n", "instruction": "<?pi x?>\n"}


@pytest.mark.parametrize("lead", LEADS.values(), ids=LEADS)
@pytest.mark.parametrize("codec", ENCODINGS)
def test_the_entity_refusal_sees_what_the_parser_sees(codec, lead):
    """The guard and the parser have to be reading the same document.

    The refusal was a *byte* pattern over the raw bytes, and a byte pattern
    finds `<!ENTITY` in utf-8 and in nothing else. Without a byte order mark
    nothing decoded first, so a utf-16 document sailed past the guard and
    expat -- which sniffs the first bytes rather than insisting on the mark
    XML requires -- parsed it and expanded the entity.

    Stated as a property rather than a list, so the two cannot drift: if the
    parser can read a clean document in this encoding, then a document with
    an entity declaration in the same encoding must be refused *by the
    guard*, naming entities. Where the parser cannot read the encoding at
    all there is nothing to smuggle, and the refusal may come from either.
    A parser that grows an encoding turns this red until the guard follows.
    """
    def encode(document):
        # An XML declaration must come first if it is there at all, so a lead
        # replaces it rather than following it -- which is the shape that
        # matters, because a document with no declaration is legal XML and is
        # exactly what a sniff keyed on "starts with `<`" cannot see.
        if not lead:
            return document.encode(codec)
        return (lead + re.sub(r"^<\?xml[^>]*\?>\s*", "", document)).encode(codec)

    readable = iirds.parse_metadata(iirds.METADATA_RDF, encode(RDF_XML),
                                    base=iirds.PACKAGE_BASE)[1] is None
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF, encode(ENTITY_RDF),
                                        base=iirds.PACKAGE_BASE)
    assert graph is None, "a document declaring XML entities was parsed"
    if readable:
        assert "XML entities" in error, error


@pytest.mark.parametrize("bom,codec", TRUNCATABLE)
def test_a_truncated_encoding_is_an_error_and_not_an_exception(bom, codec):
    """Every other way this function fails hands back a string.

    The byte order mark says which codec to use and the bytes then have to
    survive it. They do not always: a supplier saves as utf-16 and the
    transfer is cut short, and there is nothing hostile about it. The decode
    was the one step outside a try, so it raised through a function whose
    whole contract is (graph, None) or (None, error) -- and through
    Package.parse_errors, which documents that reading it never raises.
    """
    raw = (bom + RDF_XML.encode(codec))[:-1]
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF, raw, base=iirds.PACKAGE_BASE)
    assert graph is None
    name, sep, detail = error.partition(": ")
    assert (name, sep) == (iirds.METADATA_RDF, ": ") and detail


def _damaged_deflate(tmp_path, payload: bytes):
    """A container whose metadata entry decompresses to nothing usable.

    Not hostile -- a byte flipped in transit is enough, and it is the same
    scenario as a truncated encoding, one layer lower: the failure is in
    the ZIP member rather than in what it decodes to.
    """
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/iirds+zip")
        archive.writestr(iirds.METADATA_RDF, payload)
    raw = bytearray(buf.getvalue())
    at = raw.find(iirds.METADATA_RDF.encode(), raw.find(b"PK\x03\x04", 40))
    raw[at + 26:at + 30] = b"\xde\xad\xbe\xef"
    path = tmp_path / "damaged.iirds"
    path.write_bytes(bytes(raw))
    return path


def test_a_damaged_metadata_entry_reaches_parse_errors_rather_than_the_caller(tmp_path):
    """`parse_errors` says reading it never raises. The reader was repaired
    and its caller was not: `_load` decompresses the ZIP member before the
    guarded parse ever sees it, so a damaged member raised straight through
    the same contract, one layer lower down."""
    packed = _damaged_deflate(tmp_path, RDF_XML.encode("utf-8"))
    with iirds.open(packed) as pkg:
        errors = pkg.parse_errors
        assert any(e.startswith(iirds.METADATA_RDF + ": ") for e in errors), errors
        with pytest.raises(iirds.IirdsError):
            _ = pkg.graph


def test_no_document_makes_the_reader_raise_through_its_own_contract(monkeypatch):
    """The contract is (graph, None) or (None, error) for *every* input.

    The context walker runs over a document a supplier wrote and sat outside
    the try that covers every other failure here -- with a comment claiming
    otherwise, which is worse than the gap. Forced rather than crafted: the
    reachable inputs all fail in json.loads first, so the guard's own failure
    mode is only observable this way, and the contract is what is being
    pinned, not the walker."""
    def explode(*args, **kwargs):
        raise RuntimeError("the walker met something it did not expect")
    monkeypatch.setattr(iirds._metadata, "_remote_contexts", explode)
    graph, error = iirds.parse_metadata(iirds.METADATA_JSONLD, MINIMAL_JSONLD,
                                        base=iirds.PACKAGE_BASE)
    assert graph is None
    assert error.startswith(iirds.METADATA_JSONLD + ": RuntimeError: "), error


def test_a_truncated_encoding_reaches_parse_errors_rather_than_the_caller(tmp_path):
    """The contract Package documents, held at the level a consumer sees.

    `parse_errors` says "Reading this never raises; touching `graph` does
    when nothing parsed at all." Both halves are asserted here, because a
    tool that catches IirdsError around `graph` and reports `parse_errors`
    was still dying on the second line.
    """
    truncated = (b"\xff\xfe" + RDF_XML.encode("utf-16-le"))[:-1]
    packed = package_with(tmp_path, truncated)
    with iirds.open(packed) as pkg:
        errors = pkg.parse_errors
        assert any(e.startswith("META-INF/metadata.rdf: ") for e in errors), errors
        with pytest.raises(iirds.IirdsError):
            _ = pkg.graph


#: Every construct rdflib dereferences, one per id. A string in *context
#: position* is a reference; a string under a term key inside a context object
#: is that term's IRI mapping and is inline data. Getting that distinction
#: backwards refuses every conformant package, so INLINE below is the other
#: half of each case and is as load-bearing as this list.
DEREFERENCING = {
    "import": '{"@context": {"@version": 1.1, "@import": "https://evil.example/c.jsonld"}, "@id": "urn:p"}',
    "relative": '{"@context": "secret-ctx.jsonld", "@id": "urn:p"}',
    "term-scoped": '{"@context": {"@version": 1.1, "t": {"@id": "http://e/#t",'
                   ' "@context": "secret-ctx.jsonld"}}, "@id": "urn:p"}',
    "nested-node": '{"@context": {"p": {"@id": "http://e/#p", "@type": "@id"}},'
                   ' "@id": "urn:p", "p": {"@context": "secret-ctx.jsonld", "@id": "urn:q"}}',
    "in-graph": '{"@graph": [{"@context": "secret-ctx.jsonld", "@id": "urn:q"}]}',
    "wrapped": '{"@context": {"@context": "secret-ctx.jsonld"}, "@id": "urn:p"}',
    "scheme-relative": '{"@context": "//evil.example/c.jsonld", "@id": "urn:p"}',
    "traversing": '{"@context": "../../../../../../etc/hosts", "@id": "urn:p"}',
}

#: The other half. Every one of these is a context that names nothing to fetch,
#: and a guard that refuses any of them is worse than the hole it closes.
INLINE = {
    "prefixes": '{"@context": {"iirds": "http://iirds.tekom.de/iirds#"}, "@id": "urn:p"}',
    "term-definition": '{"@context": {"has-rendition": {"@id": "http://e/#r", "@type": "@id"}},'
                       ' "@id": "urn:p"}',
    "base": '{"@context": {"@base": "https://example.invalid/"}, "@id": "urn:p"}',
    "vocab": '{"@context": {"@vocab": "https://example.invalid/v#"}, "@id": "urn:p"}',
    "null": '{"@context": null, "@id": "urn:p"}',
    "inline-scoped": '{"@context": {"@version": 1.1, "T": {"@id": "http://e/#T",'
                     ' "@context": {"z": "http://e/#z"}}}, "@id": "urn:p"}',
    "import-shaped-data": '{"@context": {"iirds": "http://iirds.tekom.de/iirds#"},'
                          ' "@id": "urn:p", "iirds:title": "@import x"}',
}


@pytest.mark.parametrize("document", DEREFERENCING.values(), ids=DEREFERENCING)
def test_every_context_reference_is_refused(document):
    """A reference is a reference whether or not it carries a scheme.

    The guard tested for one, so a scheme-less name fell through -- and a
    scheme-less name is the worse case: rdflib resolves it against the
    process's working directory and reads it off the operator's disk, with
    no socket involved, which is why sealing the network never saw it.
    `@import` fell through for the other reason: JSON-LD 1.1 added a second
    keyword that fetches, and the walker only knew the first.
    """
    graph, error = iirds.parse_metadata(iirds.METADATA_JSONLD, document.encode("utf-8"),
                                        base=iirds.PACKAGE_BASE)
    assert graph is None, "the document was parsed rather than refused"
    name, sep, detail = error.partition(": ")
    assert (name, sep) == (iirds.METADATA_JSONLD, ": ")
    assert "inline" in detail, detail


@pytest.mark.parametrize("document", INLINE.values(), ids=INLINE)
def test_an_inline_context_is_not_a_reference(document):
    """The half that decides whether the guard is usable at all."""
    graph, error = iirds.parse_metadata(iirds.METADATA_JSONLD, document.encode("utf-8"),
                                        base=iirds.PACKAGE_BASE)
    assert error is None, error


def test_nested_remote_contexts_are_found_too():
    document = """{
  "@context": {"iirds": "http://iirds.tekom.de/iirds#"},
  "@graph": [{"@context": ["https://late.example/ctx", {"x": "urn:x:"}],
              "@id": "urn:test:package"}]
}"""
    graph, error = iirds.parse_metadata(iirds.METADATA_JSONLD, document.encode("utf-8"),
                                        base=iirds.PACKAGE_BASE)
    assert graph is None and "https://late.example/ctx" in error


def test_merge_sources_is_usable_on_its_own():
    from rdflib import Graph
    one = Graph()
    one.parse(data=RDF_XML, format="xml", publicID=iirds.PACKAGE_BASE)
    two = Graph()
    two.parse(data=RDF_XML, format="xml", publicID=iirds.PACKAGE_BASE)
    assert len(iirds.merge_sources({"a": one, "b": two})) == len(one)


#: The same token, in the one place the grammar treats it as characters.
DESCRIBING_RDF = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
  <rdf:Description rdf:about="urn:test:note">
    <rdfs:comment><![CDATA[%s name "value"> declares an entity]]></rdfs:comment>
  </rdf:Description>
</rdf:RDF>
""" % ("<!" + "ENTITY")


@pytest.mark.parametrize("codec", ENCODINGS)
def test_a_document_that_describes_a_declaration_is_not_refused(codec):
    """The mirror of the test above, and the half a byte pattern gets wrong.

    A declaration is legal in one place only: inside a doctype's internal
    subset. The token elsewhere -- in a CDATA section, in a comment -- is
    characters, and iiRDS metadata may well describe the vocabulary it is
    written in. Searching the whole document read the description as the
    thing described and refused a document that declares nothing.

    Where the parser cannot read the encoding there is nothing to describe
    either, so the assertion is conditioned the same way its mirror is.
    """
    # Measured on this document's own clean twin, not on another fixture: a
    # gate that asks whether some *other* shape parses can be answered no for
    # an unrelated reason, and then this test asserts nothing at all.
    twin = DESCRIBING_RDF.replace("<!" + "ENTITY", "an entity")
    readable = iirds.parse_metadata(iirds.METADATA_RDF, twin.encode(codec),
                                    base=iirds.PACKAGE_BASE)[1] is None
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF, DESCRIBING_RDF.encode(codec),
                                        base=iirds.PACKAGE_BASE)
    if readable:
        assert error is None or "XML entities" not in error, error
        assert graph is not None, error


@pytest.mark.parametrize("codec", ["utf-8", "utf-16-le", "utf-16-be", "utf-16", "utf-8-sig"])
def test_the_graph_says_what_the_file_says(codec):
    """Reading is meant to be faithful, and one substitution was not.

    A decoded document had its encoding declaration removed, because after a
    decode the declaration contradicts the bytes. The pattern was not anchored
    to the front, so where the real declaration named no encoding the first
    match was somewhere in the body -- and a passage quoting a declaration
    came back into the graph with a piece missing. The file said one thing and
    the graph said another, which is the one thing a reader must not do.
    """
    inner = '<?xml version="1.0" encoding="utf-8"?>'
    document = ('<?xml version="1.0"?>'
                '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
                ' xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">'
                '<rdf:Description rdf:about="urn:test:note">'
                '<rdfs:comment><![CDATA[' + inner + ']]></rdfs:comment>'
                '</rdf:Description></rdf:RDF>')
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF, document.encode(codec),
                                        base=iirds.PACKAGE_BASE)
    assert error is None, error
    said = [str(o) for _s, p, o in graph if str(p).endswith("comment")]
    assert said == [inner], said


#: The five marks the reader honours, each with the codec that writes the text
#: behind it. Separate from ENCODINGS on purpose: those documents carry no
#: mark, and a mark is exactly what came apart -- a codec that hands the mark
#: back leaves U+FEFF at the front, and everything that must be the first
#: thing in the document no longer is.
MARKED = [(b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
          (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"),
          (b"\xef\xbb\xbf", "utf-8")]
MARKED_IDS = ["utf-32-le", "utf-32-be", "utf-16-le", "utf-16-be", "utf-8"]


@pytest.mark.parametrize("bom,codec", MARKED, ids=MARKED_IDS)
def test_a_decode_leaves_the_document_beginning_where_it_began(bom, codec):
    """The cause, pinned where the cause is.

    A declaration may only be the first thing in a document, so the rewrite
    that removes it after a decode may only match the first thing. Both stop
    being true if the decode hands back the byte order mark: the text then
    begins with U+FEFF, the rewrite does not fire, and the bytes go on saying
    UTF-8 while the declaration still says UTF-16. Pinned here rather than
    only through its consequence, so that the next codec added to the table
    has to be one that consumes the mark.
    """
    decoded = iirds._metadata._decode(bom + RDF_XML.encode(codec))
    assert decoded.startswith(b"<?xml"), decoded[:12]


@pytest.mark.parametrize("bom,codec", MARKED, ids=MARKED_IDS)
def test_a_marked_document_declaring_entities_is_refused(bom, codec):
    """The consequence, and the half a mark-less test cannot see.

    With the mark left in place the refusal answered "declares nothing" about
    a document it had not been able to read, and the parser underneath the
    graph -- which is not the one the guard asks -- read it and expanded what
    it declared. Small declarations reached megabytes; the shape scales.
    """
    # The declaration names the encoding the document is actually written in,
    # which is what a producer emitting UTF-16 writes -- and what makes the
    # bytes and the declaration disagree once a mark is left in place and the
    # rewrite stops firing. A fixture declaring utf-8 in a UTF-16 file is
    # still readable after the broken decode, so it passes either way and
    # proves nothing.
    named = re.sub(r'encoding="[^"]*"', 'encoding="%s"' % codec, ENTITY_RDF, count=1)
    graph, error = iirds.parse_metadata(iirds.METADATA_RDF, bom + named.encode(codec),
                                        base=iirds.PACKAGE_BASE)
    assert graph is None, "a document declaring XML entities was parsed"
    assert "XML entities" in error, error


def _forge_declared_size(path, real: int, claimed: int) -> None:
    """Rewrite the uncompressed-size fields the sender writes."""
    import struct

    raw = bytearray(path.read_bytes())
    path.write_bytes(bytes(raw.replace(struct.pack("<I", real),
                                       struct.pack("<I", claimed))))


def test_a_declared_size_does_not_become_a_size_this_never_read(tmp_path):
    """The gate has to be on what is read, not on what is claimed. The
    uncompressed size in a ZIP's central directory is written by whoever
    built the archive, so reading it made this announce a gigabyte about a
    document of a few hundred bytes -- a sentence with no measurement behind
    it, and the wrong diagnosis for what is actually wrong with the file.

    The archive is malformed either way and this still refuses it. What it
    says now is what happened."""
    body = RDF_XML.encode("utf-8")
    packed = package_with(tmp_path, body)
    _forge_declared_size(packed, len(body), 1 << 30)

    with iirds.open(packed) as pkg, pytest.raises(iirds.IirdsError) as caught:
        _ = pkg.graph
    said = str(caught.value)
    assert "byte limit" not in said, (
        "a few hundred bytes were reported as over a limit nobody measured: %s" % said)
    assert "does not describe its contents" in said, said


def test_a_document_that_really_is_oversized_is_still_refused(tmp_path):
    """The other direction, which the gate exists for and must keep."""
    padded = RDF_XML.encode("utf-8") + b" " * (64 * 1024 * 1024)
    packed = package_with(tmp_path, padded)
    with iirds.open(packed) as pkg, pytest.raises(iirds.IirdsError) as caught:
        _ = pkg.graph
    assert "byte limit" in str(caught.value)
