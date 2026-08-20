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

from rdflib import URIRef

from ..model import Violation, is_named
from ..registry import rule

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
