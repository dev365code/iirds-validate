"""L16 — a relation whose object is a literal points at nothing.

`iirds:relates-to-party` takes a party; `iirds:is-version-of` takes an
information object. Write `<iirds:relates-to-party>party1</...>` instead of
`rdf:resource="urn:...:party1"` and the graph carries a string where a
reference belongs: the relation exists, the target does not, and a consumer
following it finds nothing. The XML looks almost identical, which is why it
happens — the reference form needs an attribute and the mistake needs one
character less.

It is a lint and claims nothing. `rdfs:range` in RDF is an inference and not a
constraint, and the specification states no general obligation that a
relation's object be an instance of its range; the one MUST about range is
section 7.3.3's, about proprietary properties complying with the iiRDS one.
What is true here is the interoperability sentence this family exists for: the
package is valid and the data is unusable.

Over the hundred and thirty vendor metadata files this repository holds, this
finds eight — four `iirds:relates-to-party` written as the string `party1` or
`party2`, and four empty strings on `iirds:is-version-of` and
`iirds:is-replacement-of`. Nothing reported any of them.
"""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner

IIRDS = "http://iirds.tekom.de/iirds#"


def fired(tmp_path, name, body, kinds=None):
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", body + "</rdf:RDF>")
    report = runner.run(build_package(tmp_path, name, metadata=metadata),
                        kinds if kinds is not None else runner.ALL_KINDS)
    return {f.rule.id for f in report.findings}


#: property -> a literal value somebody really wrote, or would. The last three
#: are the ones a range-based population misses: `relates-to-vcard`'s range is
#: `vcard:Kind`, which is a class in somebody else's namespace, and the other
#: two declare no range of their own and inherit it from the relation root.
AS_A_LITERAL = {
    "relates-to-party": "party1",
    "is-version-of": "urn:test:doc-v1",
    "relates-to-product-variant": "Rotor 3000",
    "has-rendition": "content/topic1.xhtml",
    "relates-to-vcard": "SupCo Ltd.",
    "has-abstract": "a summary",
    "has-event-type": "maintenance",
}


@pytest.mark.parametrize("prop", sorted(AS_A_LITERAL), ids=sorted(AS_A_LITERAL))
def test_a_relation_carrying_a_literal_is_reported(tmp_path, prop):
    body = ('  <rdf:Description rdf:about="urn:test:topic1">\n'
            "    <iirds:%s>%s</iirds:%s>\n"
            "  </rdf:Description>\n" % (prop, AS_A_LITERAL[prop], prop))
    assert "L16" in fired(tmp_path, "lit_%d.iirds" % abs(hash(prop)), body), prop


@pytest.mark.parametrize("prop", sorted(AS_A_LITERAL), ids=sorted(AS_A_LITERAL))
def test_the_same_relation_written_as_a_reference_is_not(tmp_path, prop):
    """The control, and the whole difference: one attribute."""
    body = ('  <rdf:Description rdf:about="urn:test:topic1">\n'
            '    <iirds:%s rdf:resource="urn:test:target"/>\n'
            "  </rdf:Description>\n" % prop)
    assert "L16" not in fired(tmp_path, "ref_%d.iirds" % abs(hash(prop)), body), prop


def test_the_population_is_the_ontologys_own_relation_concept(tmp_path):
    """Not "the property declares a class as its range" -- that is a proxy, and
    it was wrong in two directions at once.

    The ontology states the split itself: every property it declares is a
    subproperty of `iirds:iirdsRelationConcept` ("iiRDS resource's property
    that references an iiRDS resource") or of `iirds:iirdsAttribute`, the two
    sets are disjoint, and together they are all of it. Reading the range
    instead dropped `iirds:relates-to-vcard`, whose range is `vcard:Kind` and
    so failed a test for an *iiRDS* class; and `iirds:has-abstract`,
    `iirds:has-event-code` and `iirds:has-event-type`, which state no range of
    their own and inherit the root's. All four are relations by the standard's
    own word.
    """
    from rdflib import URIRef

    from iirds_validate.ontology import load
    from iirds_validate.rules.lint import relation_properties

    ontology = load()
    iirds = "http://iirds.tekom.de/iirds#"
    declared = ontology.subproperties_of(URIRef(iirds + "iirdsRelationConcept"))
    attributes = ontology.subproperties_of(URIRef(iirds + "iirdsAttribute"))
    population = relation_properties(ontology)

    assert declared & attributes == set(), "the ontology's two roots overlap"
    assert population == declared - {URIRef(iirds + "iirdsRelationConcept")}, sorted(
        str(p) for p in population ^ (declared - {URIRef(iirds + "iirdsRelationConcept")}))
    assert len(population) == 46, len(population)
    for marked in ("has-information-type", "relates-to-action",
                   "relates-to-administrative-metadata"):
        assert URIRef(iirds + marked) in population, marked
    for attribute in ("title", "revision", "identifier"):
        assert URIRef(iirds + attribute) not in population, attribute


def test_the_abstract_root_is_not_in_the_population():
    """`iirds:iirdsRelationConcept` is a subproperty of itself, and the concept
    "property that references an iiRDS resource" is not one of them. A rule
    that interrogates a term no package may write is asking about nothing.

    Excluded by identity and not by the ontology's "not intended to be used
    directly" marker, which three real relations also carry. Those stay in:
    that marker says the property is the wrong one to reach for, which is a
    different observation from this one."""
    from rdflib import URIRef

    from iirds_validate.ontology import load
    from iirds_validate.rules.lint import relation_properties

    root = URIRef("http://iirds.tekom.de/iirds#iirdsRelationConcept")
    assert root in load().subproperties_of(root), "the closure stopped including itself"
    assert root not in relation_properties(load())


def test_a_relation_a_declared_edition_does_not_have_is_left_to_l15(tmp_path):
    """`iirds:is-translation-of` arrived in 1.3. In a package declaring 1.0 it
    is not a relation of the declared vocabulary at all, so "this relation
    points at nothing" is the wrong sentence about it -- L15's "a name the
    declared edition does not have yet" is the right one, and it fires.

    Only the newest ontology ships, so the population is the same forty-six
    whatever the package declares; the edition it is read against has to come
    from the per-edition inventory, the way L15 takes it. Eight of the
    forty-six are absent in 1.0, six in 1.1, three in 1.2.
    """
    body = ('  <rdf:Description rdf:about="urn:test:topic1">\n'
            "    <iirds:is-translation-of>topic0</iirds:is-translation-of>\n"
            "  </rdf:Description>\n")

    def fired_for(version, name):
        metadata = MINIMAL_RDF.replace("1.3", version).replace("</rdf:RDF>", body + "</rdf:RDF>")
        package = build_package(tmp_path, name, metadata=metadata)
        return {f.rule.id for f in runner.run(package, runner.ALL_KINDS).findings}

    old = fired_for("1.0", "ed10.iirds")
    assert "L16" not in old, sorted(old)
    assert "L15" in old, sorted(old)
    assert "L16" in fired_for("1.3", "ed13.iirds")


def test_the_edition_filter_matches_the_inventory(tmp_path):
    """The counts the rule's reason rests on, read from the inventory rather
    than written down: a number in a docstring that nothing measures is a
    number that stops being true."""
    from iirds_validate.model import VERSIONS
    from iirds_validate.ontology import load
    from iirds_validate.resources import version_terms
    from iirds_validate.rules.lint import relation_properties

    population = {str(p) for p in relation_properties(load())}
    editions = version_terms()
    absent = {v: len(population - set(editions[v])) for v in VERSIONS}
    assert absent == {"1.0": 8, "1.0.1": 8, "1.1": 6, "1.2": 3, "1.3": 0}, absent


def test_a_property_whose_range_is_a_literal_is_left_alone(tmp_path):
    """`iirds:title` and `iirds:identifier` are declared `rdfs:range
    rdfs:Literal`; a string is what they are for. Reading "relation" as "any
    property" would report every title in every package."""
    body = ('  <rdf:Description rdf:about="urn:test:topic1">\n'
            "    <iirds:title>A topic</iirds:title>\n"
            "    <iirds:revision>3</iirds:revision>\n"
            "  </rdf:Description>\n")
    assert "L16" not in fired(tmp_path, "literal_range.iirds", body)


def findings(tmp_path, name, body):
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", body + "</rdf:RDF>")
    report = runner.run(build_package(tmp_path, name, metadata=metadata), runner.ALL_KINDS)
    return [f for f in report.findings if f.rule.id == "L16"]


def test_an_empty_relation_is_not_described_as_carrying_text(tmp_path):
    """`<iirds:is-version-of/>` carries no text, and telling its author to
    "write the target as a reference rather than as text" names a string that
    is not there.

    This is not a corner: five of the eight occurrences in the vendored corpus
    are empty or whitespace, so the rule's headline sentence described three
    of its own eight findings. Same rule -- the relation exists and points at
    nothing either way -- and a different sentence for each half.
    """
    empty = findings(tmp_path, "empty.iirds",
                     '  <rdf:Description rdf:about="urn:test:topic1">\n'
                     "    <iirds:is-version-of></iirds:is-version-of>\n"
                     "  </rdf:Description>\n")
    assert len(empty) == 1, empty
    assert "empty" in empty[0].violation.message, empty[0].violation.message
    assert "text" not in empty[0].violation.message, empty[0].violation.message
    assert "delete" in (empty[0].rule.fix or "") or "delete" in (empty[0].violation.detail or "")

    whitespace = findings(tmp_path, "ws.iirds",
                          '  <rdf:Description rdf:about="urn:test:topic1">\n'
                          "    <iirds:relates-to-party>\n\t\t</iirds:relates-to-party>\n"
                          "  </rdf:Description>\n")
    assert len(whitespace) == 1, whitespace
    assert "empty" in whitespace[0].violation.message, whitespace[0].violation.message


def test_a_literal_with_a_datatype_says_which(tmp_path):
    """`rdf:datatype="…#anyURI"` is the one literal form that does carry a
    resolvable identifier, and `rdf:parseType="Literal"` is markup rather than
    a name. Reported as `the value is the string '…'` both read as somebody
    having typed a word, which sends the reader to the wrong repair.
    """
    typed = findings(tmp_path, "typed.iirds",
                     '  <rdf:Description rdf:about="urn:test:topic1">\n'
                     '    <iirds:relates-to-party rdf:datatype='
                     '"http://www.w3.org/2001/XMLSchema#anyURI">urn:test:p'
                     "</iirds:relates-to-party>\n  </rdf:Description>\n")
    plain = findings(tmp_path, "plain.iirds",
                     '  <rdf:Description rdf:about="urn:test:topic1">\n'
                     "    <iirds:relates-to-party>urn:test:p</iirds:relates-to-party>\n"
                     "  </rdf:Description>\n")
    assert len(typed) == 1 and len(plain) == 1
    assert "xsd:anyURI" in typed[0].violation.detail, typed[0].violation.detail
    assert typed[0].violation.detail != plain[0].violation.detail

    markup = findings(tmp_path, "markup.iirds",
                      '  <rdf:Description rdf:about="urn:test:topic1">\n'
                      '    <iirds:relates-to-party rdf:parseType="Literal">'
                      "<b>x</b></iirds:relates-to-party>\n  </rdf:Description>\n")
    assert len(markup) == 1
    assert "rdf:XMLLiteral" in markup[0].violation.detail, markup[0].violation.detail

    # A datatype from neither namespace is shown whole. A prefix nobody uses
    # is less informative than the IRI, and a proprietary datatype is exactly
    # what section 7 lets a package mint.
    own = findings(tmp_path, "owndt.iirds",
                   '  <rdf:Description rdf:about="urn:test:topic1">\n'
                   '    <iirds:relates-to-party rdf:datatype="http://suppco.example/dt#PartyRef">'
                   "party1</iirds:relates-to-party>\n  </rdf:Description>\n")
    assert len(own) == 1
    assert "http://suppco.example/dt#PartyRef" in own[0].violation.detail, \
        own[0].violation.detail


def test_a_language_tagged_literal_says_which_language(tmp_path):
    tagged = findings(tmp_path, "lang.iirds",
                      '  <rdf:Description rdf:about="urn:test:topic1">\n'
                      '    <iirds:relates-to-party xml:lang="de">Firma'
                      "</iirds:relates-to-party>\n  </rdf:Description>\n")
    assert len(tagged) == 1
    assert "de" in tagged[0].violation.detail, tagged[0].violation.detail


def test_the_handover_relation_is_watched_too(tmp_path):
    """`iirdsHov:has-document-category` is the only one of the forty-six
    outside the core namespace, and every fixture in this file and in the
    parity file writes a core one. A body that skipped anything not in
    `http://iirds.tekom.de/iirds#` passed the whole suite, `emit_shacl
    --check` included -- the shipped shape went on reporting the property
    while Python stopped, and the differential gate could not see a
    divergence nothing exercises.

    The rule is not profile-gated (`variants=()`), so this is checked in a
    base package as well as an iiRDS/H one: that the property is a handover
    term does not mean only a handover package can carry it.
    """
    body = ('  <rdf:Description rdf:about="urn:test:doc1">\n'
            '    <iirdsHov:has-document-category>Manual</iirdsHov:has-document-category>\n'
            "  </rdf:Description>\n")
    metadata = MINIMAL_RDF.replace(
        "<rdf:RDF", '<rdf:RDF xmlns:iirdsHov="http://iirds.tekom.de/iirds/domain/handover#"', 1
    ).replace("</rdf:RDF>", body + "</rdf:RDF>")
    package = build_package(tmp_path, "hov.iirds", metadata=metadata)
    assert "L16" in {f.rule.id for f in runner.run(package, runner.ALL_KINDS).findings}


def test_every_violation_is_reported_and_not_only_the_first(tmp_path):
    """A body that stopped after its first finding passed every test in this
    file. Multiplicity was held only by the count case in the parity file,
    which is a statement about the two encodings agreeing -- the rule's own
    file has to say that a package with three of these gets three.
    """
    body = ('  <rdf:Description rdf:about="urn:test:topic1">\n'
            "    <iirds:relates-to-party>party1</iirds:relates-to-party>\n"
            "    <iirds:is-version-of>doc0</iirds:is-version-of>\n"
            "  </rdf:Description>\n"
            '  <rdf:Description rdf:about="urn:test:topic2">\n'
            "    <iirds:relates-to-party>party1</iirds:relates-to-party>\n"
            "  </rdf:Description>\n")
    assert len(findings(tmp_path, "many.iirds", body)) == 3


def test_it_is_a_lint_and_not_a_conformance_error(tmp_path):
    """No sentence of the standard makes this a MUST. `rdfs:range` is an
    inference in RDF, not a constraint, and the one range MUST -- section
    7.3.3's -- is about a proprietary property complying with the iiRDS one,
    which is a different claim about different terms. So this reports under
    `iirds lint` and leaves `iirds check` alone."""
    body = ('  <rdf:Description rdf:about="urn:test:topic1">\n'
            "    <iirds:relates-to-party>party1</iirds:relates-to-party>\n"
            "  </rdf:Description>\n")
    assert "L16" not in fired(tmp_path, "conf.iirds", body, runner.CONFORMANCE_KINDS)
    assert "L16" in fired(tmp_path, "lint.iirds", body)


def test_the_rule_claims_nothing():
    from iirds_validate.registry import all_rules

    rule = next(r for r in all_rules() if r.id == "L16")
    assert rule.covers == (), rule.covers
    assert rule.kind == "lint", rule.kind


#: Well-formed XML that rdflib will not read as RDF. `MANIFEST.json`'s
#: `parses` key is decided by `ElementTree.fromstring`, so "ok" there means
#: the bytes are XML and not that they are a graph. Named rather than counted
#: so that a fourth one arriving is a failure and not a smaller number.
XML_BUT_NOT_RDF = {
    "Example 46 - Tagging.rdf",                    # an <img> in no namespace
    "metadata_iirds_sample_pass-M77_false.rdf",     # a property attribute whose URI is not one
    "metadata_iirds_sample_pass-M77_true.rdf",
}


def test_the_corpus_figure_the_changelog_publishes():
    """Ten, in nine files, seven of them empty rather than misspelt. The
    release notes say so, so a gate measures it.

    Read through the corpus manifest and its namespace-wrapper recovery, the
    way `tests/test_shapes_parity.py` reads the same files. The first version
    of this gate called `Graph().parse` under a bare `except: continue`, so it
    read ninety-seven of the hundred and thirty files it said it read and could
    not tell "this corpus file is broken" from "I failed to read it".

    Both denominators are asserted, because they are different facts and the
    manifest's word for the first invites being read as the second: a hundred
    and seventeen of the hundred and thirty are well-formed XML, and a hundred
    and fourteen of those are a graph rdflib will build.

    Counted over the metadata files rather than by running packages, because
    the corpus ships loose `.rdf` files and the point of the number is how
    often the mistake occurs in metadata somebody shipped -- not how many
    packages this repository happens to have built out of them.
    """
    import json
    import pathlib
    import sys

    from rdflib import Graph, Literal

    from iirds_validate.ontology import load
    from iirds_validate.rules.lint import relation_properties

    root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    import vendor_corpus

    relations = relation_properties(load())
    manifest = json.loads((root / "tests" / "corpus" / "plusmeta"
                           / "MANIFEST.json").read_text("utf-8"))
    well_formed, refused = 0, set()
    hits, files, conforming, empty = 0, set(), 0, 0
    for name, meta in sorted(manifest["files"].items()):
        if meta["parses"] not in ("ok", "needs_namespace_wrapper"):
            continue
        well_formed += 1
        raw = (vendor_corpus.FILES / name).read_bytes()
        if meta["parses"] == "needs_namespace_wrapper":
            text = raw.decode("utf-8", "replace")
            body = text.split("?>", 1)[1] if text.lstrip().startswith("<?xml") else text
            raw = (vendor_corpus.NAMESPACE_WRAPPER % body).encode("utf-8")
        graph = Graph()
        try:
            graph.parse(data=raw, format="xml")
        except Exception:                  # noqa: BLE001 -- the point is which ones
            refused.add(name)
            continue
        for _subject, prop, obj in graph:
            if prop in relations and isinstance(obj, Literal):
                hits += 1
                files.add(name)
                conforming += 1 if "_true" in name else 0
                empty += 0 if str(obj).strip() else 1

    assert len(manifest["files"]) == 130, len(manifest["files"])
    assert well_formed == 117, well_formed
    assert refused == XML_BUT_NOT_RDF, sorted(refused ^ XML_BUT_NOT_RDF)
    assert (hits, len(files), empty) == (10, 9, 7), (hits, sorted(files), empty)
    # Not "four of them conform": the corpus's word for a file that breaks
    # nothing is `_pass`. `_true` means only that the rule the fixture is named
    # after passes in this variant, and each `_false` here is its `_true` plus
    # a duplicated element -- so the mistake this rule finds is in the base
    # sample, present in both halves of the pair, and claimed by neither name.
    assert conforming == 4, conforming


#: The relations for which a literal is already a conformance error, measured
#: rather than listed: the release notes and the rule's own docstring name
#: them, and a rule joining or leaving this set is a change to what L16 is for.
ALREADY_A_MUST = {
    "has-classification-domain": "R23",
    "has-content-lifecycle-status-value": "R10",
    "has-document-type": "R19",
    "has-end-selector": "R21",
    "has-first-child": "M26",
    "has-identity-domain": "M19.4",
    "has-party-role": "M22.2",
    "has-start-selector": "R20",
    "is-applicable-for-document-type": "R19",
    "relates-to-administrative-metadata": "M94",
    "relates-to-component": "M17",
    "relates-to-product-variant": "M18",
    "relates-to-vcard": "R12",
}


def test_the_relations_a_must_already_covers_are_the_ones_named(tmp_path):
    """"No rule read it" was the first draft's claim and it was false seven
    times over, and is now false thirteen times over. For thirteen of the
    forty-six the standard states the range obligation in a sentence of its
    own, a rule implements it as a MUST, and L16 restates it as a warning.
    That overlap is fine -- what is not fine is a docstring that says the
    opposite of it.

    Six of the thirteen arrived after this list did, when the five rules in
    `test_relation_targets.py` were written. The list moved because it is
    measured and not written down, which is the whole reason it is measured.

    Measured by running one package per relation rather than by reading the
    rules, because the question is what a package provokes and not what a
    `covers=` tuple says.
    """
    from iirds_validate.ontology import load
    from iirds_validate.rules.lint import relation_properties

    covered = {}
    for index, prop in enumerate(sorted(relation_properties(load()), key=str)):
        name = str(prop).split("#")[-1]
        body = ('  <rdf:Description rdf:about="urn:test:topic1">\n'
                "    <iirds:%s>text</iirds:%s>\n  </rdf:Description>\n" % (name, name))
        metadata = MINIMAL_RDF.replace("</rdf:RDF>", body + "</rdf:RDF>")
        package = build_package(tmp_path, "m%d.iirds" % index, metadata=metadata)
        fired = {f.rule.id for f in runner.run(package, runner.CONFORMANCE_KINDS).findings}
        if fired:
            covered[name] = sorted(fired)

    assert {k: v[0] for k, v in covered.items()} == ALREADY_A_MUST, covered
    assert all(len(v) == 1 for v in covered.values()), covered
