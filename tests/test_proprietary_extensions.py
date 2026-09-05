"""Section 7.1: an extension you use has to be in metadata.rdf.

    x7-1-iirds-extension-scenarios#4  All proprietary extensions that are used
        in a package MUST be contained in the file metadata.rdf in the iiRDS
        package.

Section 7.3 says what one is, in three kinds: a proprietary **class** (added
as a subclass or equivalent class of an iiRDS class), a proprietary
**property** (added as a subproperty of an iiRDS property), and a proprietary
**instance** (added as an instance of an iiRDS class). The sentence pairs with
the one after it — "the file metadata.rdf MUST NOT contain the iiRDS schema" —
so the pair is about where a vocabulary lives: yours in metadata.rdf, the
standard's not.

The claim on that sentence was withdrawn once, because the third kind reads as
though it covered every node in the package. Telling a company's vocabulary
term from its data is the decision this file records, and the ontology makes
it rather than a list:

    **A class is a vocabulary class when the bundled ontology supplies
    instances of it.** The standard ships the terms of its own vocabularies --
    twenty document types, eight party roles, eight identity types, five
    classification types -- and ships no documents, because documents are
    data. A company adding a term of that kind extends the vocabulary; a
    company adding a document does not.

Two consequences worth stating, because both were measured rather than
assumed. `iirds:ClassificationDomain` and `iirds:ExternalClassification` carry
no ontology instances, so they are data classes and an eCl@ss IRI is never
reported here -- which is the false positive this rule would otherwise be
full of, section 6.8.4 being entirely about pointing outside. And
`iirds:ProductVariant` and `iirds:Component` are data classes too, though the
standard calls them proprietary extensions in so many words; they keep their
own sentences and their own rule, R11.

Over the hundred and thirty metadata files this repository vendors, the type
and predicate populations are empty and the instance population is three
`rdf:resource=""` in the reference tool's own deliberate-defect fixtures.
"""
from __future__ import annotations

import json

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

IIRDS = "http://iirds.tekom.de/iirds#"
RDFS_ = "http://www.w3.org/2000/01/rdf-schema#"
MY = "http://my.co/ns#"


def package(tmp_path, name, rdf_body="", jsonld_nodes=None):
    """`rdf_body` goes into metadata.rdf; `jsonld_nodes`, when given, into a
    metadata.jsonld beside it. No jsonld at all when it is None, which is the
    shape that shows a name described in neither file."""
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", rdf_body + "</rdf:RDF>")
    jsonld = None
    if jsonld_nodes is not None:
        graph = [{"@id": "urn:test:package", "@type": "iirds:Package",
                  "iirds:iiRDSVersion": "1.3", "iirds:title": "Test package"}]
        graph.extend(jsonld_nodes)
        jsonld = json.dumps({"@context": {"iirds": IIRDS, "rdfs": RDFS_},
                             "@graph": graph})
    return build_package(tmp_path, name, metadata=metadata, jsonld=jsonld)


def fired(tmp_path, name, **kwargs):
    return {f.rule.id for f in runner.run(package(tmp_path, name, **kwargs),
                                          runner.ALL_KINDS).findings}


def under_check(tmp_path, name, **kwargs):
    """What `iirds check` reports. The three populations below were all silent
    here, and one of them was silent in every mode."""
    return {f.rule.id for f in runner.check(package(tmp_path, name, **kwargs)).findings}


# --- the three kinds, used and described nowhere ---------------------------

USES_A_CLASS = ('  <rdf:Description rdf:about="urn:test:t9">\n'
                '    <rdf:type rdf:resource="%sManual"/>\n'
                "  </rdf:Description>\n" % MY)

USES_A_PROPERTY = ('  <rdf:Description rdf:about="urn:test:topic1">\n'
                   '    <ext:partNumber xmlns:ext="%s">X-1</ext:partNumber>\n'
                   "  </rdf:Description>\n" % MY)

USES_AN_INSTANCE = ('  <rdf:Description rdf:about="urn:test:doc9">\n'
                    '    <rdf:type rdf:resource="%sDocument"/>\n'
                    '    <iirds:has-document-type rdf:resource="%sHandbook"/>\n'
                    "  </rdf:Description>\n" % (IIRDS, MY))



# --- the same three, described in metadata.jsonld only ---------------------

JSONLD_ONLY = {
    "a proprietary class": (
        USES_A_CLASS,
        {"@id": MY + "Manual", "@type": "rdfs:Class",
         "rdfs:subClassOf": {"@id": "iirds:Document"}}),
    "a proprietary property": (
        USES_A_PROPERTY,
        {"@id": MY + "partNumber",
         "@type": "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property",
         "rdfs:subPropertyOf": {"@id": "iirds:identifier"}}),
    "a proprietary vocabulary instance": (
        USES_AN_INSTANCE,
        {"@id": MY + "Handbook", "@type": "iirds:DocumentType",
         "rdfs:label": "Handbook"}),
}


@pytest.mark.parametrize("what", sorted(JSONLD_ONLY), ids=sorted(JSONLD_ONLY))
def test_an_extension_only_in_the_json_ld_is_reported(tmp_path, what):
    body, node = JSONLD_ONLY[what]
    got = fired(tmp_path, "jsonld_%d.iirds" % abs(hash(what)),
                rdf_body=body, jsonld_nodes=(node,))
    assert "R18" in got, (what, sorted(got))


@pytest.mark.parametrize("what", sorted(JSONLD_ONLY), ids=sorted(JSONLD_ONLY))
def test_the_same_extension_in_metadata_rdf_is_not_reported(tmp_path, what):
    """The control, and the only one that matters: a package that does what
    the sentence asks must be silent, or the rule is a rule about nothing."""
    body, node = JSONLD_ONLY[what]
    declaration = {
        "a proprietary class":
            '  <rdf:Description rdf:about="%sManual">\n'
            '    <rdf:type rdf:resource="%sClass"/>\n'
            '    <rdfs:subClassOf rdf:resource="%sDocument"/>\n'
            "  </rdf:Description>\n" % (MY, RDFS_, IIRDS),
        "a proprietary property":
            '  <rdf:Description rdf:about="%spartNumber">\n'
            '    <rdf:type rdf:resource="http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"/>\n'
            '    <rdfs:subPropertyOf rdf:resource="%sidentifier"/>\n'
            "  </rdf:Description>\n" % (MY, IIRDS),
        "a proprietary vocabulary instance":
            '  <rdf:Description rdf:about="%sHandbook">\n'
            '    <rdf:type rdf:resource="%sDocumentType"/>\n'
            "  </rdf:Description>\n" % (MY, IIRDS),
    }[what]
    got = fired(tmp_path, "ok_%d.iirds" % abs(hash(what)),
                rdf_body=declaration + body, jsonld_nodes=(node,))
    assert "R18" not in got, (what, sorted(got))


# --- what the rule must not reach ------------------------------------------

NOT_AN_EXTENSION = {
    "an external classification, which is meant to point outside":
        '  <iirds:ExternalClassification rdf:about="urn:test:xc">\n'
        '    <iirds:has-classification-domain rdf:resource="https://eclass.eu/0173-1"/>\n'
        "    <iirds:classificationIdentifier>27-27-40-01</iirds:classificationIdentifier>\n"
        "  </iirds:ExternalClassification>\n",
    "a rendition referred to by a relative IRI":
        '  <rdf:Description rdf:about="urn:test:topic1">\n'
        '    <iirds:has-rendition rdf:resource="content/topic1.xhtml"/>\n'
        "  </rdf:Description>\n",
    "a well-known vocabulary used as a predicate":
        '  <rdf:Description rdf:about="urn:test:topic1">\n'
        '    <dcterms:title xmlns:dcterms="http://purl.org/dc/terms/">t</dcterms:title>\n'
        "  </rdf:Description>\n",
    #: Section 7.3 says what a proprietary extension is by how it attaches to
    #: iiRDS -- a subclass of an iiRDS class, a subproperty of an iiRDS
    #: property, an instance of an iiRDS class -- and a name that attaches to
    #: none of them is not one, whatever it looks like. The first version of
    #: this rule asked instead whether a name was outside the iiRDS and
    #: well-known namespaces and stood in a vocabulary position, which is a
    #: proxy for the question and fails in both directions: it reported these
    #: four, and it reported a proprietary class defined in a side ontology
    #: while staying silent about a proprietary term defined in the same file.
    "a W3C vocabulary used as a predicate":
        '  <rdf:Description rdf:about="urn:test:topic1">\n'
        '    <prov:wasGeneratedBy xmlns:prov="http://www.w3.org/ns/prov#" '
        'rdf:resource="urn:test:run"/>\n'
        "  </rdf:Description>\n",
    "an XMP property, which every PDF pipeline emits":
        '  <rdf:Description rdf:about="urn:test:topic1">\n'
        '    <xmp:CreateDate xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
        "2026-01-01</xmp:CreateDate>\n  </rdf:Description>\n",
    "a name of the package's own used as a type and attached to nothing":
        USES_A_CLASS,
    "a name of the package's own used as a predicate and attached to nothing":
        USES_A_PROPERTY,
    #: The reading this rule settled on, kept as a case because it is the one
    #: the first version got wrong. A name referred to in a vocabulary slot and
    #: typed by nobody is a dangling reference: the package never adds the
    #: extension, so there is no extension of the package's for section 7.1 to
    #: place. L1 has that sentence, and `test_lint.py` pins in its own words
    #: that "a reference to an undescribed IRI breaks no MUST" -- reading it
    #: the other way reversed a settled decision as a side effect, and did:
    #: `iirds:relates-to-event` takes an `iirds:Event`, the ontology seeds
    #: that class with one generic term, and a reference to an event that does
    #: not exist became a MUST breach.
    "a vocabulary name referred to and typed by nobody": USES_AN_INSTANCE,
    "a document, which is data and not a vocabulary term":
        '  <rdf:Description rdf:about="urn:test:doc9">\n'
        '    <rdf:type rdf:resource="%sDocument"/>\n'
        '    <iirds:is-version-of rdf:resource="urn:test:elsewhere"/>\n'
        "  </rdf:Description>\n" % IIRDS,
}


@pytest.mark.parametrize("what", sorted(NOT_AN_EXTENSION), ids=sorted(NOT_AN_EXTENSION))
def test_what_is_not_a_proprietary_extension_is_not_reported(tmp_path, what):
    """Each of these is a name from outside the iiRDS vocabulary, used, and
    described nowhere -- and none of them is a proprietary extension. The
    first is section 6.8.4's whole purpose; the second and fourth are ordinary
    references, which L1 has its own sentence for; the third is a vocabulary
    the standard itself uses."""
    got = fired(tmp_path, "notext_%d.iirds" % abs(hash(what)),
                rdf_body=NOT_AN_EXTENSION[what])
    assert "R18" not in got, (what, sorted(got))


def test_the_vocabulary_classes_are_read_from_the_ontology_not_listed():
    """The decision this rule rests on, asserted against the ontology rather
    than against a list somebody typed. A list would be a copy of the
    vocabulary and would drift from it; the point of deriving it is that a
    class the standard starts supplying terms for becomes a vocabulary class
    without anybody noticing it has to."""
    from iirds_validate.ontology import load
    from iirds_validate.rules.requirements import vocabulary_classes

    vocab = vocabulary_classes(load())
    for name in ("DocumentType", "PartyRole", "IdentityType",
                 "ContentLifeCycleStatusValue", "ClassificationType"):
        assert IIRDS + name in {str(c) for c in vocab}, name
    for name in ("Document", "Topic", "Fragment", "Package", "Rendition",
                 "ClassificationDomain", "ExternalClassification",
                 "ProductVariant", "Component"):
        assert IIRDS + name not in {str(c) for c in vocab}, name


# --- the file section 5.1.1 tells consumers to ignore -----------------------

SIDE_ONTOLOGY = (
    '<?xml version="1.0"?>\n'
    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
    '         xmlns:rdfs="%s" xmlns:iirds="%s">\n'
    '  <rdf:Description rdf:about="%sHandbook">\n'
    '    <rdf:type rdf:resource="%sDocumentType"/>\n'
    "  </rdf:Description>\n"
    '  <rdf:Description rdf:about="%sManual">\n'
    '    <rdfs:subClassOf rdf:resource="%sDocument"/>\n'
    "  </rdf:Description>\n"
    "</rdf:RDF>\n" % (RDFS_, IIRDS, MY, IIRDS, MY, IIRDS))


def _with_side_file(path, name, body):
    import io
    import zipfile

    buf = io.BytesIO(path.read_bytes())
    with zipfile.ZipFile(buf, "a") as archive:
        archive.writestr(name, body)
    path.write_bytes(buf.getvalue())
    return path


def test_an_extension_ontology_in_meta_inf_is_reported(tmp_path):
    """The shape that keeps this claim honest, and the one the first version
    of the rule could not see.

    A package may put its extension ontology in `META-INF/extension.rdf` and
    point the rest of its metadata at it. Section 5.1.1 says it is RECOMMENDED
    for consumers to ignore any other file in META-INF, so that ontology
    reaches nobody: the names resolve to nothing and the classes carry no
    rules. That is exactly what section 7.1 forbids, and `iirds check` was
    silent about it -- nothing in this project looks at a META-INF file it did
    not ask for.
    """
    path = _with_side_file(
        build_package(tmp_path, "side.iirds",
                      metadata=MINIMAL_RDF.replace("</rdf:RDF>",
                                                   USES_A_CLASS + "</rdf:RDF>")),
        "META-INF/extension.rdf", SIDE_ONTOLOGY)
    got = {f.rule.id for f in runner.check(path).findings}
    assert "R18" in got, sorted(got)


def test_a_meta_inf_file_that_is_not_an_extension_is_not_reported(tmp_path):
    """The control. A package may carry other things there -- a signature, a
    manifest, a readme -- and this rule is about extension ontologies, not
    about tidiness."""
    for name, body in (("META-INF/signatures.xml", "<signatures/>"),
                       ("META-INF/notes.txt", "nothing to see"),
                       #: A directory entry, which a ZIP carries as a name of
                       #: its own. Reading it as a file asks the container for
                       #: bytes that are not there; the tracer found the line
                       #: that skips it had never run.
                       ("META-INF/sub/", ""),
                       ("META-INF/other.rdf",
                        '<?xml version="1.0"?><rdf:RDF '
                        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                        '<rdf:Description rdf:about="urn:x"/></rdf:RDF>')):
        path = _with_side_file(
            build_package(tmp_path, "quiet_%d.iirds" % abs(hash(name)),
                          metadata=MINIMAL_RDF),
            name, body)
        got = {f.rule.id for f in runner.check(path).findings}
        assert "R18" not in got, (name, sorted(got))


def test_every_shape_of_the_sentence_is_reported(tmp_path):
    """The case the coverage claim names: every way a package can breach
    section 7.1#4, in one place, so that adding a shape means adding it here.

    Four. Section 7.3's three kinds of extension, each attached in
    metadata.jsonld and not in metadata.rdf; and an extension ontology in a
    META-INF file, which is the shape that reaches a consumer as nothing at
    all and which nothing in this project used to look at.
    """
    for what, (body, node) in sorted(JSONLD_ONLY.items()):
        got = fired(tmp_path, "shape_%d.iirds" % abs(hash(what)),
                    rdf_body=body, jsonld_nodes=(node,))
        assert "R18" in got, (what, sorted(got))

    path = _with_side_file(
        build_package(tmp_path, "shape_side.iirds",
                      metadata=MINIMAL_RDF.replace("</rdf:RDF>",
                                                   USES_A_CLASS + "</rdf:RDF>")),
        "META-INF/extension.rdf", SIDE_ONTOLOGY)
    got = {f.rule.id for f in runner.check(path).findings}
    assert "R18" in got, sorted(got)


#: Ordinary data of an iiRDS class, in metadata.jsonld only. Every one of
#: these breaches section 5.1.1 and L9 reports it; none of them is a
#: proprietary extension, and calling one that is the reading the withdrawal
#: existed to prevent. The first repair of this rule reintroduced it by way of
#: a subclass closure: `iirds:iirdsDomainEntity` carries instances beneath it,
#: so reading "the ontology supplies instances of it" transitively put the
#: root of almost everything in the vocabulary set and made every document one.
DATA_IN_THE_JSON_LD = {
    "a document": {"@id": "urn:test:d9", "@type": "iirds:Document",
                   "iirds:title": "A document"},
    "a rendition": {"@id": "urn:test:r9", "@type": "iirds:Rendition"},
    "a topic": {"@id": "urn:test:t9", "@type": "iirds:Topic"},
    "a party": {"@id": "urn:test:p9", "@type": "iirds:Party"},
    "an identity": {"@id": "urn:test:i9", "@type": "iirds:Identity"},
}


@pytest.mark.parametrize("what", sorted(DATA_IN_THE_JSON_LD), ids=sorted(DATA_IN_THE_JSON_LD))
def test_ordinary_data_in_the_json_ld_is_not_a_proprietary_extension(tmp_path, what):
    got = fired(tmp_path, "data_%d.iirds" % abs(hash(what)),
                jsonld_nodes=(DATA_IN_THE_JSON_LD[what],))
    assert "R18" not in got, (what, sorted(got))
    assert "L9" in got, "the disagreement is still reported, under its own sentence"


def test_the_vocabulary_set_is_the_classes_the_standard_supplies_terms_for():
    """Two conditions, both from the ontology, both load-bearing.

    Directly typed, because reading it through the subclass closure put
    `iirds:iirdsDomainEntity` in the set and every document with it. And
    Appendix A's IRI column, because a class whose instances the standard says
    need not be named cannot be a vocabulary -- a term nobody can refer to is
    not a term.
    """
    from iirds_validate.ontology import load
    from iirds_validate.rules.requirements import vocabulary_classes

    names = {str(c) for c in vocabulary_classes(load())}
    for name in ("DocumentType", "PartyRole", "IdentityType", "ClassificationType"):
        assert IIRDS + name in names, name
    for name in ("Document", "Topic", "Fragment", "Package", "Rendition", "Party",
                 "Identity", "ClassificationDomain", "ExternalClassification",
                 "ProductVariant", "Component", "iirdsDomainEntity",
                 "AdministrativeMetadata", "InformationUnit",
                 "PlanningTime", "MaintenanceInterval", "WorkingTime", "DownTime"):
        assert IIRDS + name not in names, name


def test_the_equivalence_the_standard_writes_the_other_way_round_is_read(tmp_path):
    """Section 7.3.2: "Proprietary iiRDS extensions MAY add proprietary classes
    as equivalent classes. The property rdfs:subClassOf expresses equivalence
    of classes." The standard's own Example 43 writes both directions, and a
    package may write only the one whose subject is the iiRDS class.

    Reading one direction did two wrong things at once: it reported a package
    that had said, in metadata.rdf, exactly what this rule asks it to say —
    and it missed the same statement when it was in metadata.jsonld only,
    which is the breach. Both halves are here, because the fix for the first
    is what makes the second possible to get wrong silently.
    """
    equivalence = ('  <rdf:Description rdf:about="%sComponent">\n'
                   '    <rdfs:subClassOf rdf:resource="%sProductPart"/>\n'
                   "  </rdf:Description>\n" % (IIRDS, MY))
    use = ('  <rdf:Description rdf:about="urn:test:p1">\n'
           '    <rdf:type rdf:resource="%sProductPart"/>\n  </rdf:Description>\n' % MY)

    assert "R18" not in fired(tmp_path, "equiv_ok.iirds", rdf_body=equivalence + use), \
        "metadata.rdf says it, in the direction the standard permits"

    got = fired(tmp_path, "equiv_jsonld.iirds", rdf_body=use, jsonld_nodes=(
        {"@id": IIRDS + "Component", "rdfs:subClassOf": {"@id": MY + "ProductPart"}},))
    assert "R18" in got, sorted(got)


def test_a_term_typed_with_the_packages_own_subclass_is_a_term(tmp_path):
    """Section 7.3: "Proprietary instances MAY also be instances of a
    proprietary class." So a document-type term of the package's own, typed
    with the package's own subclass of `iirds:DocumentType`, is a term — and
    asking `cls in vocabulary` by set membership missed every one of them.
    That is the failure `Context.is_instance` names in its own docstring:
    "exact typing is how section 7 gets forgotten one rule at a time".
    """
    declaration = ('  <rdf:Description rdf:about="%sHouseDocType">\n'
                   '    <rdfs:subClassOf rdf:resource="%sDocumentType"/>\n'
                   "  </rdf:Description>\n" % (MY, IIRDS))
    got = fired(tmp_path, "own_subclass.iirds", rdf_body=declaration,
                jsonld_nodes=({"@id": MY + "Handbook", "@type": MY + "HouseDocType"},))
    assert "R18" in got, sorted(got)


def test_a_product_variant_stays_r11s_and_does_not_become_a_vocabulary_term(tmp_path):
    """`iirds:ProductMetadata` is the parent of `iirds:ProductVariant` and
    `iirds:Component`, and it carries instances beneath it. Reading the
    vocabulary set through the subclass closure therefore pulls both in, and
    the two rules report one defect again — the thing the split was for.

    Sections 6.7.4 and 6.7.1 are R11's; this rule leaves them alone.
    """
    got = fired(tmp_path, "variant_r11.iirds", jsonld_nodes=(
        {"@id": MY + "Rotor3000", "@type": "iirds:ProductVariant",
         "rdfs:label": "Rotor 3000"},))
    assert "R11" in got, sorted(got)
    assert "R18" not in got, ("one defect, one rule", sorted(got))
