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

from .. import terms as T
from ..context import container_packages, package_nodes
from ..model import METADATA_RDF, MIMETYPE_FILE, Violation, is_named
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
        "a conformant package's own instance is not a member of another package, so "
        "the only evidence that this container is the nested one is the breach being "
        "looked for. Deciding it from the metadata alone means assuming what is to "
        "be shown; the archive can weigh against the parent reading without "
        "settling it, which is a different question from checking this sentence. "
        "The neighbouring sentence, which needs no such decision, is R6.",
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
          "zip -Xr ../out.iirds .`; `iirdsv pack mypackage` does it correctly.")
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
          "which a package's own instance must not carry.")
def r6_the_content_of_a_nested_package_is_not_described_here(ctx):
    """"An iiRDS package that contains a nested iiRDS package MUST NOT contain
    metadata about the content of the nested iiRDS package." (section 5.3)

    The neighbouring sentence -- a nested package must not carry metadata
    about the outer one -- cannot be checked from a single container and is
    recorded as such. Its antecedent is "a nested iiRDS package", and section
    6.2 says a conformant child's own instance carries no
    iirds:is-part-of-package at all, so the only evidence that this document
    is the child is the very relation under dispute. Deciding it would mean
    assuming what is to be shown.

    This sentence needs no such decision, because both readings of the
    ambiguous document are prohibited. If this is the parent's metadata, the
    unit is content of the nested package and section 5.3 is broken. If it is
    the child's own metadata, then the child's iirds:Package is a member of
    another package and section 6.2 is broken. The finding is compelled
    either way, which is what makes it reportable without a heuristic about
    which container is in hand.

    The relation is split with R5 by the subject: R5 answers for package
    subjects, this one for everything else. Non-package rather than
    information-unit on purpose -- section 6.2 gives the relation to
    information units, so a subject that carries it and is not a package is
    one whatever else the document does or does not say about its class, and
    an untyped subject is not a way out.

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
