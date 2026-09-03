"""Rules for specification requirements the reference catalogue has no id for.

Everything in `schema.py`, `container.py` and `system.py` implements a rule
plusmeta catalogued. That catalogue is one reader's enumeration of the standard
and, like any enumeration, it has holes -- which nobody could see until
`docs/requirements.json` enumerated the standard independently and the two
could be compared.

The first comparison found two. Appendix A states `IRI: REQUIRED` for 56
classes; 54 of them have a rule and two do not. Neither omission is
interesting in itself. What is interesting is that they were invisible for as
long as coverage was measured against the catalogue instead of against the
specification, and that finding them cost one diff once the index existed.

Rules here carry `covers=`, naming the requirement ids they implement. That is
the map, kept in the rules rather than in a document beside them, because a
document beside them drifts.

Identifiers are `R*` and cannot collide with the catalogue's: a stored report
naming R1 means this rule and will not come to mean something else if plusmeta
adds an id.
"""
from __future__ import annotations

import posixpath

from rdflib import URIRef
from rdflib.namespace import RDFS

from .. import terms as T
from ..context import container_packages, package_nodes
from ..model import METADATA_RDF, MIMETYPE_FILE, Violation, is_named
from ..package import nested_containers
from ..registry import rule

#: Obligations the standard states that no validator can check on a package,
#: because they are addressed to somebody else.
#:
#: Without this, they sit in the unmapped column for ever and the coverage
#: figure never reaches its ceiling however much work is done -- which would
#: eventually make the number meaningless in the other direction. Every entry
#: needs a reason, and the reason has to be that the obligation is not about
#: the artefact. "Hard to check" is not a reason and belongs in the gaps.
NOT_ABOUT_THE_PACKAGE = {
    "x5-1-2-content-location#4":
        "\"iiRDS Consumers MUST ignore these files\" — an obligation on the reading "
        "application. A package cannot satisfy or breach it.",
    "dfn-iirds-zip-archive#1":
        "\"All processing applications MUST support this implementation\" — the same, "
        "about tools rather than about containers.",
}

#: Obligations that are squarely about the package and that a validator holding
#: one container cannot decide, because deciding them means knowing something
#: the container does not carry. Kept apart from NOT_ABOUT_THE_PACKAGE, which
#: excuses a different thing -- obligations addressed to reading applications --
#: so that "hard to check" cannot hide inside "not about the package".
NOT_DECIDABLE_ALONE = {
    "x5-3-nested-iirds-packages#2":
        "\"A nested iiRDS package MUST NOT contain metadata about the outer iiRDS "
        "package.\" The antecedent is \"a nested iiRDS package\", and section 6.2 says "
        "a conformant package's own instance is not a member of another package, so a "
        "document declaring itself nested is either the child breaching that sentence "
        "or a parent describing its child, and the metadata does not distinguish "
        "them. Deciding it from the metadata alone means assuming what is to be "
        "shown. Other sentences weigh without settling it -- section 6.3 says the "
        "enclosing package is the subject of no rendition, which is M8 -- and so does "
        "the archive, which is a different question from checking this sentence. The "
        "neighbouring sentence, which needs no such decision, is R6.",
}

HANDOVER = "http://iirds.tekom.de/iirds/domain/handover#"
IIRDS = "http://iirds.tekom.de/iirds#"

#: (id, class, requirement covered, the sentence, versions)
#:
#: Read off Appendix A rather than paraphrased: the specification's own tables
#: say `IRI: REQUIRED` against each of these, and the requirement id points at
#: the row it was read from.
NEEDS_AN_IRI = (
    ("R1", URIRef(IIRDS + "ClassificationType"), "iirds:ClassificationType",
     "rdfclasses_core_ClassificationType#1", ("1.2", "1.3")),
    ("R2", URIRef(HANDOVER + "DocumentCategory"), "iirdsHov:DocumentCategory",
     "rdfclasses_handover_DocumentCategory#1", ("1.3",)),
)

FIX = ('Give the <%(name)s> element an rdf:about with an IRI. Without one the '
       'element is anonymous, so nothing else in the package can refer to it and '
       'a consumer merging this package with another cannot tell two of them apart.')


def _must_have_iri(cls: URIRef, name: str):
    def check(ctx):
        # Same population as the generated table's sixty-one; these two are
        # the rest of the sixty-three, and they name concrete classes.
        for subject in ctx.typed_as(cls):
            if not is_named(subject):
                yield Violation("%s must have an IRI" % name, subject=ctx.ref(subject))
    return check


for _id, _cls, _name, _requirement, _versions in NEEDS_AN_IRI:
    _fn = _must_have_iri(_cls, _name)
    _fn.__name__ = "%s_%s_must_have_iri" % (_id.lower(), _name.split(":")[-1].lower())
    rule(_id, kind="schema", prio="MUST", versions=_versions, variants=(),
         title="instances of %s must have an IRI" % _name,
         spec="https://www.iirds.org/fileadmin/iiRDS_specification/"
              "20251103-1.3-release/index.html#a-1-1-class-definitions",
         covers=(_requirement,), fix=FIX % {"name": _name})(_fn)


@rule("R3", kind="container", prio="MUST", versions=(), variants=(),
      title="the container must be at the root of the archive, not inside a folder in it",
      spec="https://www.iirds.org/fileadmin/iiRDS_specification/"
           "20251103-1.3-release/index.html#dfn-iirds-container",
      covers=("dfn-iirds-container#1",), diagnosis="cause",
      fix="Rebuild the archive from inside the package directory rather than from its "
          "parent, so that mimetype and META-INF are at the top level of the ZIP. With "
          "the zip command that is `cd mypackage && zip -X0 ../out.iirds mimetype && "
          "zip -Xr ../out.iirds .`; `iirds pack mypackage` does it correctly.")
def r3_container_is_at_the_archive_root(ctx):
    """"An iiRDS container MUST have a single root directory." (section 5.1)

    Which for a ZIP means the archive root itself, since section 5.2 puts
    mimetype and META-INF there. The way that requirement gets broken is
    zipping the package *folder* instead of its contents -- far and away the
    most common packaging mistake, and one every archive tool invites.

    Without this the report is four errors telling the author to add a mimetype
    file, create a META-INF directory and add a metadata.rdf, all of which they
    already have, one level down. Nothing says what happened. Nothing is wrong
    with the package at all except where it sits.
    """
    if not ctx.package.is_archive:
        return

    names = [n for n in ctx.package.names if n.strip("/")]
    if any("/" not in n.strip("/") for n in names):
        return                      # something is at the root; not this defect

    roots = {n.strip("/").split("/")[0] for n in names}
    if len(roots) != 1:
        return                      # several top-level folders is a different mess

    folder = roots.pop()
    inside = {posixpath.relpath(n, folder) for n in names}
    if not ({MIMETYPE_FILE, METADATA_RDF} & inside):
        return                      # the folder holds no container either

    yield Violation("the whole package sits inside a directory in the archive, so nothing "
                    "a consumer looks for is where it looks",
                    subject=folder + "/",
                    detail="found %s -- the other container findings all follow from this one"
                           % ", ".join(sorted("%s/%s" % (folder, n) for n in
                                              sorted({MIMETYPE_FILE, METADATA_RDF} & inside))))


@rule("R5", kind="schema", prio="MUST", versions=("1.3",), variants=(),
      title="a package named as a parent must not itself be inside another package",
      spec="https://www.iirds.org/fileadmin/iiRDS_specification/"
           "20251103-1.3-release/index.html#metadata-of-nested-iirds-packages",
      covers=("x6-3-3-metadata-of-nested-iirds-packages#4",), diagnosis="cause",
      fix="Remove the iirds:is-part-of-package relation from the package this one names "
          "as its parent, or point this one at that package's own parent instead. "
          "Nesting in the parent container's metadata is one level deep: the package a "
          "child names is the container it sits in, and that container is not itself "
          "sitting in a third one described here.")
def r5_a_named_parent_is_not_itself_nested(ctx):
    """"In the metadata.rdf file of the parent iiRDS container, the referenced
    parent iiRDS container MUST NOT have any outgoing iirds:is-part-of-package
    relations." (section 6.3.3)

    One sentence, and it rules out three shapes at once: a package part of
    itself, a chain of three, and two packages each inside the other. All
    three used to be read as ordinary nesting, and the first of them was
    reported here as a deliberate silence -- the container reading stopped it
    buying an exemption, and stopped short of saying it was wrong. This says
    it, under the id of the sentence that says it.

    Version-gated to 1.3 because that is the only edition in the cached
    specification that carries section 6.3.3; 1.0 has no nesting chapter at
    all, and 1.1 and 1.2 are not on hand to check.
    """
    packages = set(package_nodes(ctx.graph))
    for pkg in package_nodes(ctx.graph):
        for parent in sorted(ctx.graph.objects(pkg, T.is_part_of_package), key=ctx.ref):
            if parent in packages and any(ctx.graph.objects(parent, T.is_part_of_package)):
                yield Violation("this package names a parent that is itself inside "
                                "another package",
                                subject=ctx.ref(pkg), detail="parent %s" % ctx.ref(parent))


@rule("R6", kind="schema", prio="MUST NOT", versions=("1.3",), variants=(),
      title="a document that declares a nested package must not describe that "
            "package's content",
      spec="https://www.iirds.org/fileadmin/iiRDS_specification/"
           "20251103-1.3-release/index.html#nested-iirds-packages",
      covers=("x5-3-nested-iirds-packages#3",), diagnosis="cause",
      fix="Point the information unit at the package this container itself is about, "
          "or remove it from this metadata and leave it to the nested container's own "
          "metadata.rdf. If this file is the nested container's own metadata rather "
          "than its parent's, the repair is the other one: drop the "
          "iirds:is-part-of-package relation from this document's own iirds:Package, "
          "which must not name another package as the one it is inside.")
def r6_the_content_of_a_nested_package_is_not_described_here(ctx):
    """"An iiRDS package that contains a nested iiRDS package MUST NOT contain
    metadata about the content of the nested iiRDS package." (section 5.3)

    The neighbouring sentence -- a nested package must not carry metadata
    about the outer one -- cannot be checked from a single container and is
    recorded as such. Its antecedent is "a nested iiRDS package", and section
    6.2 says a conformant package's own instance is not a member of another
    package, so a document declaring itself nested is either the child
    breaching that sentence or a parent describing its child. Deciding which
    would mean assuming what is to be shown.

    This sentence needs no such decision, because every reading of the
    ambiguous document is prohibited.

    If this is the parent's metadata, the unit is content of the nested
    package and section 5.3 is broken. If it is the nested child's own
    metadata, then its iirds:Package names another package as the one it is
    inside, and section 6.2 is broken. And if neither package is this
    container's -- a document describing a pair held somewhere else -- then
    section 5.1.1 is: "An iiRDS container MUST have a directory META-INF. The
    directory is exclusively used for metadata on the iiRDS package and its
    contents." A package this container neither is nor contains is neither.
    Section 6.2's other sentence closes the same door from the other side:
    "Each iiRDS package MUST have exactly one corresponding iirds:Package
    instance in the metadata."

    The third branch is the one the first version of this reasoning missed,
    and it is the reason the two named sections are cited rather than assumed.
    None of the three is decided here; the finding is compelled under all of
    them, which is what makes it reportable without a heuristic about which
    container is in hand.

    The relation is split with R5 by the subject: R5 answers for package
    subjects, this one for everything else. Not because a package is not an
    information unit -- section 6.2 lists iirds:Package among the subclasses
    of iirds:InformationUnit, so a package nested inside a nested package is
    its content -- but because R5 already reports that shape under section
    6.3.3, and one graph should not draw two findings under two requirement
    ids for one triple. Non-package rather than information-unit on the other
    side, so that an untyped subject is not a way out.

    What this sees is one triple pattern, and section 5.3's sentence is wider
    than that. A parent that copies the child's units into its own metadata
    and simply omits the iirds:is-part-of-package relations describes the
    child's content and is not reported. That is a gap, not a reading:
    "metadata about the content" has no other form this could key on without
    guessing which units belong to whom.

    Version-gated to 1.3 for the reason R5 is: the 1.0 release on hand has no
    nesting chapter at all, and 1.1 and 1.2 are not here to check.
    """
    # container_packages as it stands, deliberately: this reads the metadata
    # and nothing else. A pool widened by anything outside the graph would
    # start reporting the container's own units as somebody else's content.
    packages = set(package_nodes(ctx.graph))
    nested = packages.difference(container_packages(ctx.graph))
    # No de-duplication: a graph is a set of triples, so one subject reaches
    # one package once however many times the document spells the relation.
    for unit, pkg in sorted(
            ((s, o) for s, o in ctx.graph.subject_objects(T.is_part_of_package)
             if s not in packages and o in nested),
            key=lambda pair: (ctx.ref(pair[0]), ctx.ref(pair[1]))):
        yield Violation("this metadata describes something inside a package it says is "
                        "nested here",
                        subject=ctx.ref(unit),
                        detail="belongs to %s, which this document declares nested"
                               % ctx.ref(pkg))


@rule("R7", kind="schema", prio="MUST NOT", versions=(), variants=(),
      title="the package that represents this container must not name a parent package",
      spec="https://www.iirds.org/fileadmin/iiRDS_specification/"
           "20251103-1.3-release/index.html#information-units",
      covers=("x6-2-information-units#7",), diagnosis="cause",
      fix="Remove the iirds:is-part-of-package relation from this container's own "
          "iirds:Package. A package's own instance does not record which package it "
          "was packed inside; that relation belongs in the parent container's "
          "metadata, on the iirds:Package the parent declares for this child. If this "
          "file is meant to be the parent's, then the package it names as a parent is "
          "missing from this metadata, and the repair is to describe it here.")
def r7_the_container_package_is_not_inside_another(ctx):
    """"The corresponding iirds:Package instance of an iiRDS package MUST NOT
    be a member of another iiRDS package expressed by the property
    iirds:is-part-of-package." (section 6.2, and unchanged since 1.0)

    The realistic spelling of the nesting defect, and nothing reported it. A
    child container handed over on its own, whose metadata still names the
    parent it was packed inside, passed with no findings at all: R6 keys on
    units pointing at a package *this document declares nested*, and a lone
    child declares nothing nested.

    "The corresponding instance" is the package that represents this
    container, which is what container_packages answers -- a package naming a
    parent this document also describes as a package is a nested child
    declared the way section 6.3.3 asks, not the corresponding instance, and
    is excluded there. What is left is a package this container is about, with
    an outgoing relation the sentence forbids it.

    Self-loops are not reported: "another iiRDS package" is not itself, and
    section 6.3.3 is the sentence that names that shape -- R5 reports it.

    Not version-gated. The sentence stands word for word in the 1.0 release as
    well as in 1.3, which is the difference between this and R5 and R6.
    """
    for pkg in container_packages(ctx.graph):
        for parent in sorted(ctx.graph.objects(pkg, T.is_part_of_package), key=ctx.ref):
            if parent == pkg:
                continue
            yield Violation("the package this container is about says it is inside "
                            "another package",
                            subject=ctx.ref(pkg),
                            detail="names %s as the package it is part of" % ctx.ref(parent))


@rule("R8", kind="container", prio="MUST", versions=("1.3",), variants=(),
      title="a nested package this metadata declares must be in the archive",
      spec="https://www.iirds.org/fileadmin/iiRDS_specification/"
           "20251103-1.3-release/index.html#metadata-of-nested-iirds-packages",
      covers=("x6-3-3-metadata-of-nested-iirds-packages#2",), diagnosis="cause",
      fix="Add the nested container to this archive, beside the content, as a file "
          "whose name ends .iirds and whose own root holds an uncompressed first "
          "entry named mimetype containing application/iirds+zip. If instead this "
          "file is the nested container's own metadata rather than its parent's, the "
          "repair is the other one: drop the description of the outer package and the "
          "iirds:is-part-of-package relation that names it.")
def r8_a_declared_nested_package_is_in_the_archive(ctx):
    """"All nested iiRDS containers MUST be included side by side in the iiRDS
    ZIP archive of the highest level iiRDS package." (section 6.3.3)

    The one question about nesting that the metadata cannot answer and the
    archive can. A document declaring a nested package and a document that
    *is* the nested package are the same graph -- section 6.2 makes them so --
    and this does not decide between them, because it does not have to: if
    the declaration is true the container owes a nested archive and has not
    got one, and if it is false the document is the child breaching section
    5.3, which forbids it metadata about the outer package. Neither reading is
    clean, so the finding stands without choosing.

    The name is not the test. A file called content/nested.iirds holding
    sixteen bytes of anything would otherwise answer this, and answering it
    falsely is worse than leaving the sentence unchecked -- it would read as
    evidence. package.nested_containers reads section 5.2's own description of
    an iiRDS ZIP archive out of the first local header.

    The cost, named: "side by side in the archive of the highest level
    package" can be read as flattening, and under that reading a middle
    container in a chain three deep legitimately carries no nested archive of
    its own and is reported here. Section 8.3.1.2's "by nesting iiRDS ZIP
    archives in each other" reads the other way, and this takes that one. No
    fixture, sample or example in reach has three levels; docs/divergences.md
    carries the trade.

    Version-gated to 1.3 for the reason R5 and R6 are: the 1.0 release on hand
    has no nesting chapter at all.
    """
    declared = set(package_nodes(ctx.graph)).difference(container_packages(ctx.graph))
    if not declared or nested_containers(ctx.package):
        return
    for pkg in sorted(declared, key=ctx.ref):
        yield Violation("this metadata declares a nested iiRDS package and the archive "
                        "carries no nested iiRDS container",
                        subject=ctx.ref(pkg),
                        detail="no entry named *.iirds opens the way section 5.2 says "
                               "an iiRDS ZIP archive opens")


@rule("R9", kind="container", prio="MUST NOT", versions=("1.3",), variants=("H",),
      title="a handover package must not nest another package",
      spec="https://www.iirds.org/fileadmin/iiRDS_specification/"
           "20251103-1.3-release/index.html#nesting-of-packages",
      covers=("x8-3-1-2-nesting-of-packages#2",
              "x6-7-3-packages-related-to-component-trees#5"),
      diagnosis="cause",
      fix="Remove the nested container from the archive and the iirds:Package that "
          "declares it, and model the hierarchy with a component tree instead: relate "
          "the information units to iirds:Component instances and link those with "
          "iirds:relates-to-component, which is what the handover profile uses to say "
          "what is inside what. If nesting is really needed, the package is not an "
          "iiRDS/H package and must not declare that restriction.")
def r9_a_handover_package_does_not_nest(ctx):
    """"an iiRDS/H package MUST NOT contain another iiRDS ZIP archive"
    (section 8.3.1.2), and "iiRDS/H packages MUST use this variant of
    hierarchy formation and MUST NOT contain nested packages" (section 6.7.3).

    Two sentences saying one thing from the two sides this validator can see,
    so both are reported here and both branches run: the archive may carry no
    nested container, and the metadata may declare none. A package can breach
    either alone -- an archive with a nested container whose metadata says
    nothing, or metadata declaring a child that was never packed -- so neither
    branch stands in for the other.

    Section 6.7.3's sentence has two limbs and this reports one of them, which
    is the shape a coverage claim has to answer for. The positive limb, "MUST
    use this variant of hierarchy formation", carries no content the negative
    limb does not: "this variant" is section 6.7.3's component trees, offered
    in the three sentences above it and every one of them a MAY, and the
    paragraph's whole point is *component trees rather than nesting*. A
    handover package that models no hierarchy at all has used no other variant
    to be told off for. Read that way the sentence has one violation and this
    reports it -- and the reading is written here rather than left implicit,
    because the reading is what the claim covers.

    The opening clause of section 8.3.1.2 is why this is variant-gated rather
    than general: "While unrestricted iiRDS packages MAY be nested by nesting
    iiRDS ZIP archives in each other for compatibility reasons". Nesting is
    permitted by name outside the handover profile.

    Version-gated to 1.3 because the cached 1.0 release has no handover
    profile at all -- the string iiRDS/H does not occur in it.

    What this does not reach: a container whose own package does not declare
    the restriction is not read as a handover package, so a document that
    hides its profile on a package it also says is nested is judged
    unrestricted and this stands down. That is the container reading, and it
    is answered by R8 rather than here.
    """
    for name in nested_containers(ctx.package):
        yield Violation("a handover package must not contain another iiRDS ZIP archive",
                        subject=name,
                        detail="section 8.3.1.2; use a component tree for the hierarchy")
    declared = set(package_nodes(ctx.graph)).difference(container_packages(ctx.graph))
    for pkg in sorted(declared, key=ctx.ref):
        yield Violation("a handover package must not declare a nested package",
                        subject=ctx.ref(pkg),
                        detail="section 6.7.3; the handover profile forms hierarchies "
                               "with component trees instead")


@rule("R11", kind="schema", prio="MUST", versions=("1.3",), variants=(),
      title="a proprietary extension must be in metadata.rdf, not only in metadata.jsonld",
      spec="https://www.iirds.org/fileadmin/iiRDS_specification/"
           "20251103-1.3-release/index.html#iirds-extension-scenarios",
      covers=("x7-1-iirds-extension-scenarios#4",
              "x6-7-4-product-variants#1",
              "x6-7-1-component-trees-in-the-package#2"),
      fix="Add the statement to META-INF/metadata.rdf as well. A consumer that reads only "
          "metadata.rdf — which the standard permits, and which is the file every consumer "
          "must support — will not see your extension at all, and the classes and instances "
          "the rest of your metadata refers to will resolve to nothing.")
def r11_extensions_live_in_metadata_rdf(ctx):
    """Three sentences, one shape, and merged graphs are what hide it.

    "All proprietary extensions that are used in a package MUST be contained
    in the file metadata.rdf" (7.1); "As product variants are a proprietary
    iiRDS extension, they MUST be present in the metadata.rdf" (6.7.4); "The
    component tree is a proprietary iiRDS extension, it MUST be stored in the
    metadata.rdf" (6.7.1). The general sentence and two of its instances.

    Every rule but L9 reads the two serialisations merged, which is right for
    every other question and is exactly what makes this invisible: a product
    variant stated only in metadata.jsonld is in the graph the rules see and
    in none of the files these sentences name. L9 reports that the two
    disagree, which is a different sentence, and cannot be substituted -- a
    package can satisfy L9 by omitting the extension from both files, and
    breach these by carrying it in one.

    A package with no metadata.jsonld cannot breach this: whatever is in the
    graph came from metadata.rdf. A package with no metadata.rdf is C8's
    finding, not this one -- reporting every extension as misplaced when the
    file they belong in is absent buries the absence.
    """
    if METADATA_RDF not in ctx.per_source or len(ctx.per_source) < 2:
        return
    inside = ctx.per_source[METADATA_RDF]
    for label, cls in (("iirds:ProductVariant", T.ProductVariant),
                       ("iirds:Component", T.Component)):
        for subject in sorted(ctx.instances_of(cls), key=ctx.ref):
            if (subject, None, None) not in inside:
                yield Violation("%s is a proprietary iiRDS extension and is stated outside "
                                "metadata.rdf" % label,
                                subject=ctx.ref(subject), detail=_only_in(ctx, subject))
    for subject, parent in sorted(ctx.graph.subject_objects(RDFS.subClassOf), key=str):
        if ctx.ontology.is_iirds_term(subject) or not ctx.ontology.is_iirds_term(parent):
            continue
        if (subject, RDFS.subClassOf, parent) not in inside:
            yield Violation("a proprietary class of the iiRDS vocabulary is declared outside "
                            "metadata.rdf",
                            subject=ctx.ref(subject), detail=_only_in(ctx, subject))


def _only_in(ctx, subject) -> str:
    """Which files do describe it — so the remedy names the file to copy from."""
    names = sorted(name.rpartition("/")[2] for name, graph in ctx.per_source.items()
                   if (subject, None, None) in graph)
    return "stated in %s" % " and ".join(names) if names else None
