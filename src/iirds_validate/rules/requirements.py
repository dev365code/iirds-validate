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
        for subject in ctx.typed_exactly(cls):
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
