"""Interoperability rules (L*) — "will anyone else be able to read this?"

Conformance and usability are different questions. A package can satisfy every
MUST in the specification and still be useless to the system that receives it:
a relation that points at an IRI nobody defined, a rendition whose file was
never packed, a table of contents with nodes hanging off nothing.

These checks exist because that is exactly what goes wrong in practice, and
because no conformance checker will ever report it — there is no rule being
broken. They are warnings, not errors: the package is valid, it is just not
going to work.
"""
from __future__ import annotations

import difflib
import re

from rdflib import BNode, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from .. import terms as T
from ..model import DCTERMS, IIRDS_NAMESPACES, OWL, VCARD, VERSIONS, Violation
from ..package import ELSEWHERE, ESCAPES, NOTHING, entry_named, entry_or_reason
from ..registry import rule
from ..resources import version_terms

#: Interoperability rules are not version-specific. Take the list from model
#: rather than restating it: a private copy means that the day 1.4 is added,
#: every L rule stops applying to 1.4 packages and lint quietly reports clean.
ALL_VERSIONS = VERSIONS

LABEL_PROPERTIES = (RDFS.label, SKOS.prefLabel, SKOS.altLabel, T.title,
                    VCARD["fn"], DCTERMS.title)

#: Vocabularies the specification itself tells you to use. Not "proprietary".
WELL_KNOWN = (
    "http://www.w3.org/2006/vcard/ns#",
    "http://www.w3.org/2004/02/skos/core#",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2002/07/owl#",
    "http://www.w3.org/2001/XMLSchema#",
    "http://purl.org/dc/terms/",
    "http://purl.org/dc/elements/1.1/",
    "http://schema.org/",
    "https://schema.org/",
)


def _labelled(ctx, node) -> bool:
    """A label on the node, or on anything hanging directly off it.

    iiRDS routinely puts the human-readable string one level down — an
    iirds:Event carries no label of its own, its has-event-code does. A
    consumer can display either, so either counts.
    """
    if any(ctx.has(node, prop) for prop in LABEL_PROPERTIES):
        return True
    for _pred, obj in ctx.graph.predicate_objects(node):
        if isinstance(obj, (URIRef, BNode)) and any(ctx.has(obj, p) for p in LABEL_PROPERTIES):
            return True
    return False


def _lint(rule_id, title, prio="RECOMMENDED", conformance=False, fix=None, covers=()):
    """Register an interoperability rule.

    `conformance=True` marks the ones that implement a sentence the
    specification states as a MUST. Those also run under `check`: the catalogue
    happens to have no id for them, which is a fact about the catalogue rather
    than about whether the standard requires it.
    """
    return rule(rule_id, kind="lint", prio=prio, title=title, versions=ALL_VERSIONS,
                variants=(), spec=None, conformance=conformance, fix=fix, covers=covers)


#: Sentinel pushed onto the traversal stack to mark "finished with this node".
_CLOSE = object()


def _children(ctx, node):
    """The two edges that make up an iiRDS navigation structure.

    `has-first-child` descends a level, `has-next-sibling` continues the linked
    list on the current one. Both L3 and L4 walk exactly these.
    """
    return list(ctx.values(node, T.has_first_child)) + list(ctx.values(node, T.has_next_sibling))


def _described(ctx, node) -> bool:
    """Does the package say anything at all about this node?"""
    return (node, None, None) in ctx.graph


# --------------------------------------------------------------------------

def _undescribed_references(ctx):
    """IRIs an iiRDS relation points at that the package never describes."""
    # One finding per target, and the subject named in it is the smallest of
    # those that point at it -- not whichever the store happened to yield
    # first, which named a different real thing on the next run of the same
    # file. The targets are walked in the same order for the same reason.
    routes = {}
    for subj, pred, obj in ctx.graph:
        if not isinstance(obj, URIRef) or not ctx.ontology.is_iirds_term(pred):
            continue
        if ctx.ontology.is_iirds_term(obj) or ctx.ontology.is_defined(obj):
            continue                      # a term from the standard vocabulary
        if str(obj).startswith(WELL_KNOWN) or _described(ctx, obj):
            continue
        routes.setdefault(obj, []).append((subj, pred))
    for obj in sorted(routes, key=str):
        subj, pred = min(routes[obj], key=lambda sp: (ctx.ref(sp[0]), str(sp[1])))
        yield subj, pred, obj


@_lint("L1", "an iiRDS relation should not point at an IRI the package never describes",
       fix="Either describe the target in this package, or drop the reference. A relation pointing at an IRI nothing here mentions gives a consumer a name and no way to resolve it.")
def l1_dangling_references(ctx):
    """The failure behind 'I built a valid package and my reader lost the data'.

    RDF lets the same fact be written inline or as a reference. The reference
    form is correct — but if the target is described nowhere, a consumer
    resolves it to nothing and the information silently disappears. No
    conformance rule is broken, so no conformance checker will tell you.

    Web IRIs are handled by L8 instead: pointing at an external ontology is a
    deliberate, legitimate thing to do.
    """
    for subj, pred, obj in _undescribed_references(ctx):
        if str(obj).startswith(("http://", "https://")):
            continue
        yield Violation("relation points at an IRI that is never described in this package",
                        subject=ctx.ref(obj),
                        detail="referenced by %s via %s" % (ctx.label_of(subj), pred.split("#")[-1]))


@_lint("L8", "external references cannot be resolved by an offline consumer", prio="MAY",
       fix="Bundle the vocabulary in the package, or accept that consumers behind a firewall will not resolve it. This is a note rather than a defect: it says what an offline reader loses.")
def l8_external_references(ctx):
    """Links out to another vocabulary — fine, but worth knowing they are there.

    A consumer behind an air gap resolves these to nothing, so anything the
    package needs a reader to understand should also be described locally.
    """
    for subj, pred, obj in _undescribed_references(ctx):
        if not str(obj).startswith(("http://", "https://")):
            continue
        yield Violation("reference to an external vocabulary, not described in this package",
                        subject=ctx.ref(obj),
                        detail="referenced by %s via %s" % (ctx.label_of(subj), pred.split("#")[-1]))


@_lint("L2", "every iirds:source must resolve to a file inside the container",
       prio="MUST", conformance=True,
       fix="Add the file to the container at exactly the path iirds:source names, or correct the path. Paths are relative to the container root, case-sensitive, and use forward slashes.")
def l2_missing_content_files(ctx):
    """A rendition that points at a file nobody packed."""
    present = set(ctx.package.files)
    for rend in ctx.instances_of(T.Rendition):
        for src in ctx.values(rend, T.source):
            raw = str(src)
            candidate, reason = entry_or_reason(raw)
            if reason == ELSEWHERE:
                # Not a path that went wrong -- not a path. M9 reports that the
                # URL has to be relative to the package root, and saying it
                # again here, in the words of a different defect, helps nobody.
                continue
            if reason == ESCAPES:
                yield Violation("iirds:source escapes the package root",
                                subject=ctx.ref(rend), detail=raw)
            elif reason == NOTHING:
                yield Violation("iirds:source names no file",
                                subject=ctx.ref(rend), detail=raw)
            elif candidate not in present:
                yield Violation("iirds:source does not resolve to a file in the container",
                                subject=ctx.ref(rend), detail=raw)


@_lint("L3", "every iirds:DirectoryNode should be reachable from a root node",
       fix="Link the node in with iirds:has-first-child or iirds:has-next-sibling from a node that is itself reachable, or remove it. A node no root reaches is invisible in every viewer, whatever it contains.")
def l3_orphan_directory_nodes(ctx):
    """Nodes hanging off nothing: they exist, but no consumer will ever show them."""
    nodes = set(ctx.instances_of(T.DirectoryNode))
    if not nodes:
        return
    roots = [n for n in nodes if ctx.has(n, T.has_directory_structure_type)]
    reachable, stack = set(), list(roots)
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        stack.extend(_children(ctx, node))
    for node in sorted(nodes - reachable, key=ctx.ref):
        yield Violation("directory node is not reachable from any root node",
                        subject=ctx.ref(node), detail=ctx.label_of(node))


@_lint("L4", "the directory structure should not contain cycles", prio="MUST",
       fix="Break the loop: follow the reported nodes and remove the has-first-child or has-next-sibling that points back to an ancestor. A consumer walking this structure does not terminate.")
def l4_directory_cycles(ctx):
    """A consumer walking the table of contents would loop forever.

    Iterative on purpose. `has-next-sibling` is a linked list, so a flat table
    of contents of N entries is N deep — a thousand-entry manual is ordinary,
    and a recursive walk blows the stack and reports a valid package as broken.
    """
    state = {}                       # node -> "open" while on the current path
    reported = set()

    for start in ctx.instances_of(T.DirectoryNode):
        if state.get(start) == "done":
            continue
        # (node, trail) with an explicit close marker, so the trail unwinds
        # exactly as it would on return from a recursive call.
        stack = [(start, [])]
        while stack:
            node, trail = stack.pop()
            if node is _CLOSE:
                state[trail] = "done"
                continue
            if state.get(node) == "done":
                continue
            if state.get(node) == "open":
                if node not in reported:
                    reported.add(node)
                    loop = trail[trail.index(node):] + [node] if node in trail else [node]
                    yield Violation("cycle in the directory structure",
                                    subject=ctx.ref(node),
                                    detail=" -> ".join(ctx.ref(n).split("/")[-1] for n in loop))
                continue
            state[node] = "open"
            stack.append((_CLOSE, node))
            for child in _children(ctx, node):
                stack.append((child, trail + [node]))


@_lint("L5", "proprietary classes should be linked to the iiRDS vocabulary",
       fix="Add rdfs:subClassOf from the proprietary class to the nearest iiRDS class. Without it a consumer sees a class it has no rules for and can only ignore the instances; with it they degrade to the iiRDS meaning.")
def l5_unmapped_custom_classes(ctx):
    """Spec section 7: extensions are understood only if they hang off iiRDS.

    A class of your own that is not a subclass of anything standard is opaque —
    the receiving system can store it, but it cannot act on it.
    """
    reported = set()
    for _subj, cls in ctx.graph.subject_objects(RDF.type):
        if not isinstance(cls, URIRef) or ctx.ontology.is_iirds_term(cls) or cls in reported:
            continue
        if cls in (RDFS.Class, RDF.Property) or str(cls).startswith(WELL_KNOWN):
            continue
        parents = list(ctx.graph.objects(cls, RDFS.subClassOf))
        equivalents = list(ctx.graph.objects(cls, OWL.equivalentClass))
        if any(ctx.ontology.is_iirds_term(p) for p in parents + equivalents):
            continue
        reported.add(cls)
        yield Violation("proprietary class is not linked to any iiRDS class",
                        subject=ctx.ref(cls),
                        detail="add rdfs:subClassOf or owl:equivalentClass pointing into iiRDS")


@_lint("L6", "proprietary metadata values should carry a human-readable label",
       fix="Add an rdfs:label with an xml:lang. A consumer cannot show a bare IRI to a technician, and cannot match it against anything either.")
def l6_unlabelled_concepts(ctx):
    """Labels travel inside the package, so a consumer has something to show.

    They are also what a search over the package can match against: an IRI
    ending in `cooling-fan` will never match a query written in German or
    Korean, but an rdfs:label will. Information units are exempt — they are
    covered by L7, which asks for a title instead.
    """
    units = set(ctx.information_units())
    referenced = {obj for pred, obj in ctx.graph.predicate_objects(None)
                  if isinstance(obj, URIRef) and ctx.ontology.is_iirds_term(pred)}

    # Structural nodes are exempt: their human face lives somewhere else, so a
    # label on the node itself is dead weight, and asking for one buried every
    # correct packed package under identical warnings — thirty on a thirty-
    # topic package, one per identified Rendition. A Rendition is shown as its
    # file, a Party as its vcard (M23 insists there is one), a Selector as the
    # place it points into, a ContentLifeCycleStatus as its value, a
    # DirectoryNode as the title of the unit it references, an Identity as its
    # identifier string. What stays warned is what a consumer genuinely
    # renders or matches by label: identity domains, events, classifications,
    # proprietary subjects and the like.
    structural = set()
    for cls in (T.Rendition, T.Selector, T.Party, T.ContentLifeCycleStatus,
                T.DirectoryNode, T.Identity):
        structural.update(ctx.instances_of(cls))

    for subj in sorted(ctx.iirds_subjects(), key=ctx.ref):
        if isinstance(subj, BNode) or subj in units or subj in structural:
            continue
        if ctx.ontology.is_iirds_term(subj) or str(subj).startswith(WELL_KNOWN):
            continue
        if subj not in referenced:
            continue
        if _labelled(ctx, subj):
            continue
        types = sorted(str(ty).split("#")[-1] for ty in ctx.values(subj, RDF.type))
        yield Violation("metadata value has no label a consumer could display",
                        subject=ctx.ref(subj),
                        detail=("typed as %s" % ", ".join(types)) if types else None)


@_lint("L7", "every information unit should have a title",
       fix="Add an iirds:title. It is what appears in a table of contents and in search results, and an information unit without one arrives unnamed.")
def l7_untitled_information_units(ctx):
    """Valid without one, unusable without one."""
    for unit in ctx.information_units():
        # iirds:Package is itself a subclass of iirds:InformationUnit, but a
        # package is not a thing with a title in the same sense. Asked as a
        # closure, not as a type comparison: section 7 lets a package declare
        # its own subclass of iirds:Package, and comparing rdf:type values
        # took the exemption away from exactly the packages that used it --
        # while the shape kept it, because sh:class follows subClassOf.
        if ctx.is_instance(unit, T.Package):
            continue
        if not ctx.has(unit, T.title):
            types = sorted(str(t).split("#")[-1] for t in ctx.values(unit, RDF.type))
            yield Violation("information unit has no iirds:title",
                            subject=ctx.ref(unit), detail=", ".join(types) or None)


@_lint("L9", "the RDF/XML and JSON-LD metadata must describe the same graph",
       prio="MUST", conformance=True,
       fix="Regenerate both files from one source, or delete one of them. A consumer may read either, so two that disagree hand two readers different data with no way to tell which was meant.",
       covers=("x5-1-1-metadata-location-and-rdf-serializations#2",
               "x5-1-1-metadata-location-and-rdf-serializations#4",))
def l9_serialisations_disagree(ctx):
    """iiRDS 1.3 lets a package state its metadata twice.

    Nothing obliges a consumer to read both, so if the two disagree, two
    conformant readers get different data from the same package and neither
    has any way to notice. Every other rule here works on the merged graph,
    which is correct — and which is precisely what makes this invisible.
    """
    from rdflib.compare import graph_diff, to_isomorphic

    if len(ctx.per_source) < 2:
        return

    (name_a, graph_a), (name_b, graph_b) = sorted(ctx.per_source.items())
    iso_a, iso_b = to_isomorphic(graph_a), to_isomorphic(graph_b)
    if iso_a == iso_b:
        return

    _both, only_a, only_b = graph_diff(iso_a, iso_b)

    def sample(graph, limit=2):
        return "; ".join("%s %s %s" % tuple(str(term).split("#")[-1][:38] for term in triple)
                         for triple in sorted(graph, key=str)[:limit])

    detail = []
    if len(only_a):
        detail.append("%d statement(s) only in %s (%s)" % (len(only_a), name_a, sample(only_a)))
    if len(only_b):
        detail.append("%d statement(s) only in %s (%s)" % (len(only_b), name_b, sample(only_b)))

    yield Violation("the two metadata serialisations describe different graphs",
                    subject="META-INF", detail=" | ".join(detail))


#: iiRDS classes the ontology itself marks as groupings. Read out of the
#: bundled ontology rather than listed, so the set stays right as the standard
#: adds classes.
_ABSTRACT_MARKER = "not int"


@_lint("L10", "abstract iiRDS classes should not be used to type an instance directly",
       fix="Retype the instance as one of the subclasses. The grouping class says only that something of that family is involved, which leaves a consumer nothing to act on.")
def l10_abstract_class_used_directly(ctx):
    """Our reading of "Not intended to be used directly. Use the subclasses instead."

    This is a lint rule and not M78-M93 on purpose. The catalogue files those
    ids under that wording, but the reference tool implements all sixteen as a
    check that the element carries an rdf:about — so a package can be typed
    entirely against abstract classes and still pass every conformance rule
    that exists. The wording says otherwise and the ontology repeats it in each
    class's own description, so the observation is worth making; making it as a
    MUST would mean failing tekom's sample packages on an interpretation
    nothing else shares.

    It is genuinely useful: an instance typed `iirds:Qualification` rather than
    `iirds:Role` tells a consumer only that some qualification is involved. The
    standard subclasses are what carry meaning.
    """
    abstract = set()
    for cls, description in ctx.ontology.graph.subject_objects(T.IIRDS_DESCRIPTION):
        if _ABSTRACT_MARKER in str(description).lower():
            abstract.add(cls)

    for cls in sorted(abstract, key=str):
        for subject in ctx.graph.subjects(RDF.type, cls):
            subclasses = sorted(str(s).split("#")[-1]
                                for s in ctx.ontology.graph.subjects(RDFS.subClassOf, cls))
            yield Violation("%s is a grouping class; type the instance as one of its "
                            "subclasses" % str(cls).split("#")[-1],
                            subject=ctx.ref(subject),
                            detail=("standard subclasses: %s" % ", ".join(subclasses[:6]))
                                   if subclasses else "define a proprietary subclass")


@_lint("L11", "content named .xhtml but declared as another media type is never checked",
       fix="Either declare the rendition as application/xhtml+xml, or rename the file so it does not claim to be iiRDS XHTML5. Until the two agree, none of the content rules examine it.")
def l11_content_hidden_from_the_content_rules(ctx):
    """The B rules examine only what the package declares to be iiRDS XHTML5,
    which is right — running XHTML5 checks over a PDF would be nonsense. But
    the consequence of a wrong declaration is *silence*, and silence is the one
    outcome a validator must never produce for a file it did not look at.

    `content/topic1.xhtml` carrying a `<script>`, declared `text/html`, comes
    back clean. Same bytes, same defects, one word changed in a file nobody
    reads twice. This is the failure mode the whole project exists to
    eliminate, reappearing one level in.

    B6 is the same disagreement seen from the other side: content declared as
    iiRDS XHTML5 that does not use the `.xhtml` extension. That side produces a
    finding, so it was noticed. This side produced nothing, so it was not.

    Keyed on the extension rather than the media type alone, because "this
    rendition is not iiRDS XHTML5" describes most renditions in most packages
    and is not worth saying. `.xhtml` is the extension B6 requires of iiRDS
    XHTML5 content, so a file carrying it and declaring otherwise is one of the
    two fields being wrong — and either way nothing examined the file.
    """
    # Imported rather than restated: two media-type parsers that disagree would
    # put this rule and the B rules into a gap where a file is neither checked
    # nor reported, which is worse than the defect being fixed here.
    from .content import XHTML_FORMAT, _media_type

    for rendition in sorted(ctx.instances_of(T.Rendition), key=ctx.ref):
        declared = [_media_type(f) for f in ctx.values(rendition, T.fmt)]
        if not declared or XHTML_FORMAT in declared:
            continue          # no format at all is M11's finding, not a second one here
        for source in ctx.values(rendition, T.source):
            # entry_named, not a fourth normalisation: this rule exists to
            # catch a file that no content rule read, so resolving the value
            # differently from those rules is how it goes quiet on exactly
            # the packages it is for.
            name = entry_named(str(source))
            if name and name.lower().endswith(".xhtml") and ctx.package.has(name):
                yield Violation("this file is named .xhtml but is not declared as iiRDS "
                                "XHTML5, so none of the content rules examined it",
                                subject=name,
                                detail="declared as %s" % ", ".join(sorted(declared)))


@_lint("L12", "two entries differing only in case will not survive extraction",
       fix="Rename one of them so the two differ by more than case. The ZIP holds both, "
           "and Windows and macOS filesystems hold one, so the package a consumer unpacks "
           "is missing a file that validated perfectly.",
)
def l12_case_only_collisions(ctx):
    """C15 asks whether the same path appears twice, and it is right to: within
    the archive those really are one entry claimed twice.

    This is the other collision, and the one that actually happens. `A.xhtml`
    and `a.xhtml` are distinct paths in a ZIP, distinct under the
    specification's "file names are case-sensitive", and the same file on the
    two operating systems most consumers run. The archive validates, and the
    directory that comes out of it has one fewer file than went in — a defect
    that exists only after the package leaves the producer, which is precisely
    what an interoperability rule is for.

    Reported per colliding group rather than per entry, because renaming one
    member fixes the whole group.
    """
    groups = {}
    for name in ctx.package.names:
        groups.setdefault(name.lower(), []).append(name)

    for _folded, names in sorted(groups.items()):
        distinct = sorted(set(names))
        if len(distinct) > 1:
            yield Violation("entries differ only in case, so one is lost on a "
                            "case-insensitive filesystem",
                            subject=distinct[0], detail="also " + ", ".join(distinct[1:]))


# ---------------------------------------------------------------------------
# A name in the iiRDS namespace that the vocabulary does not define
# ---------------------------------------------------------------------------

#: How alike two normalised names have to be before one is offered as the
#: other's correction -- `difflib`'s ratio, so the threshold means the same
#: for a short name and a long one. Below it, a name of six letters or fewer
#: is still answered when exactly one defined name is a single slip away
#: (a letter dropped, added, changed, or two swapped): a ratio built for long
#: names calls a five-letter word with one slip a stranger.
NEAREST_ENOUGH = 0.82
SHORT_NAME = 6

#: What may stand in each position of a triple, by the vocabulary's own
#: typing. A predicate is answered only with a property, the object of
#: rdf:type only with a class, and any other object or a subject with an
#: instance or a class -- the nearest name by letters to `hasDocumentType`
#: is the class `DocumentType`, which a reader cannot put in a predicate.
KINDS_BY_POSITION = {"predicate": ("property",), "class": ("class",),
                     "value": ("instance", "class"), "subject": ("instance", "class")}
POSITION_ORDER = ("predicate", "class", "value", "subject")

#: The host the four iiRDS namespaces share, so that a suggestion in a
#: sibling vocabulary can be written as "X in iirds/domain/machinery#"
#: rather than as a whole IRI that the grouped report would have to cut.
IIRDS_HOST = "http://iirds.tekom.de/"

REMEDY_BY_POSITION = {
    "predicate": "Correct the spelling, or declare the property in your own namespace and "
                 "link it to the iiRDS property it specialises with rdfs:subPropertyOf "
                 "(section 7.3).",
    "class": "Correct the spelling, or declare the class in your own namespace and link it "
             "to the iiRDS class it specialises with rdfs:subClassOf (section 7.3).",
    "value": "Correct the spelling, or mint the instance in your own namespace and give it "
             "an rdf:type of the iiRDS class it belongs to (section 7.3).",
}
REMEDY_BY_POSITION["subject"] = REMEDY_BY_POSITION["value"]


def _normalised(name: str) -> str:
    """Case and separators aside: `hasDocumentType`, `has-document-type` and
    `HAS_DOCUMENT_TYPE` are one name to a person, and to this."""
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _one_slip_apart(a: str, b: str) -> bool:
    """Optimal-string-alignment distance of exactly one: a letter dropped,
    added or changed, or two neighbours swapped."""
    if abs(len(a) - len(b)) > 1:
        return False
    rows = [list(range(len(b) + 1))]
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            best = min(rows[i - 1][j] + 1, row[j - 1] + 1, rows[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                best = min(best, rows[i - 2][j - 2] + 1)
            row.append(best)
        rows.append(row)
    return rows[-1][-1] == 1


def _vocabulary(ontology):
    """The defined terms indexed for suggestion, once per vocabulary.

    Kept on the ontology object because it is the thing that does not change
    between packages; building it per finding cost half a millisecond, which
    is nothing for one typo and a second for a package with two thousand.
    """
    cache = ontology.__dict__.get("_suggestion_index")
    if cache is not None:
        return cache
    classes = ontology.classes()
    properties = ontology.properties()
    index = {}
    for position, kinds in KINDS_BY_POSITION.items():
        by_norm = {}
        for term in ontology.defined_terms():
            kind = "class" if term in classes else "property" if term in properties else "instance"
            if kind in kinds:
                by_norm.setdefault(_normalised(_local(term)), []).append(term)
        index[position] = by_norm
    ontology.__dict__["_suggestion_index"] = index
    return index


def _local(iri) -> str:
    return str(iri).rsplit("#", 1)[-1]


def _namespace(iri) -> str:
    return str(iri).rsplit("#", 1)[0] + "#"


def _pick(candidates, namespace):
    """Of several terms that spell the same, the one in the namespace the
    name was written in; `Operation` exists in core and in handover."""
    same = [c for c in candidates if _namespace(c) == namespace]
    return sorted(same or candidates, key=str)[0]


def _suggest(term, position, ontology):
    """The defined term this one was most likely meant to be, or None.

    Compared on normalised local names, within the kinds the position
    allows. Exact after normalisation wins outright (a case slip, a
    separator written the other way, a term of a sibling vocabulary named
    in core); then a clearly nearest name by ratio; then, for a short name,
    the single defined name one slip away. Two candidates as good as each
    other are no answer: a wrong suggestion costs more than none, because a
    reader acts on it.
    """
    by_norm = _vocabulary(ontology)[position]
    wanted = _normalised(_local(term))
    if not wanted:
        return None
    namespace = _namespace(term)
    if wanted in by_norm:
        return _pick(by_norm[wanted], namespace)
    close = difflib.get_close_matches(wanted, by_norm, n=2, cutoff=NEAREST_ENOUGH)
    if close:
        if len(close) == 1 or (difflib.SequenceMatcher(None, wanted, close[0]).ratio()
                               > difflib.SequenceMatcher(None, wanted, close[1]).ratio()):
            return _pick(by_norm[close[0]], namespace)
        return None
    if len(wanted) <= SHORT_NAME:
        near = [name for name in by_norm if _one_slip_apart(wanted, name)]
        if len(near) == 1:
            return _pick(by_norm[near[0]], namespace)
    return None


def _spelled(term, meant) -> str:
    """The suggestion as a reader would write it back."""
    name = _local(meant)
    if _namespace(meant) == _namespace(term):
        return name
    return "%s in %s" % (name, _namespace(meant)[len(IIRDS_HOST):]
                         if str(meant).startswith(IIRDS_HOST) else _namespace(meant))


def _positions_of(graph, terms):
    """Where each term stands, by the fixed preference in POSITION_ORDER."""
    seen = {}
    for s, p, o in graph:
        for term, position in ((p, "predicate"), (o, "class" if p == RDF.type else "value"),
                               (s, "subject")):
            if term in terms:
                current = seen.get(term)
                if current is None or POSITION_ORDER.index(position) < POSITION_ORDER.index(current):
                    seen[term] = position
    return seen


@_lint("L13", "a name in the iiRDS namespace that the standard does not define",
       fix="Correct the spelling, or move the term into a namespace of your own and "
           "link it into iiRDS: a property with rdfs:subPropertyOf, a class with "
           "rdfs:subClassOf, an instance with an rdf:type of an iiRDS class (section "
           "7.3). A name in the iiRDS namespace that the vocabulary does not define "
           "resolves to nothing for a consumer that trusts the namespace and looks "
           "it up there.")
def l13_undefined_iirds_terms(ctx):
    """The namespace was trusted and the name never was.

    `is_iirds_term` tests a prefix, which is what most rules want: it answers
    "is this the standard's business". Whether the standard actually has the
    name is a different question, and no rule asked it of an arbitrary iiRDS
    IRI -- so a package could misspell a predicate, a class or a value and
    pass every rule, in the standard's own namespace, where a consumer has
    the least reason to doubt it.

    Reported once per distinct name however often it occurs, in a fixed
    order, with the term that was probably meant and a remedy that fits the
    position the name was used in. The vocabulary IRI itself (an empty local
    name) is not a name and is not reported.
    """
    undefined = set()
    for triple in ctx.graph:
        for term in triple:
            if (isinstance(term, URIRef) and term not in undefined
                    and ctx.ontology.is_iirds_term(term) and not ctx.ontology.is_defined(term)
                    and _local(term)):
                undefined.add(term)
    positions = _positions_of(ctx.graph, undefined)
    for term in sorted(undefined, key=str):
        position = positions.get(term, "value")
        meant = _suggest(term, position, ctx.ontology)
        parts = []
        if meant is not None:
            spelled = _spelled(term, meant)
            if _local(term) != _local(term).strip() and _local(term).strip() == _local(meant):
                parts.append("has trailing or leading whitespace; did you mean %s?" % spelled)
            else:
                parts.append("did you mean %s?" % spelled)
        if (term, None, None) in ctx.graph:
            parts.append("described in this package, not in the standard")
        yield Violation("name is in the iiRDS namespace but the vocabulary does not define it",
                        subject=ctx.ref(term),
                        detail="; ".join(parts) if parts else None,
                        fix=REMEDY_BY_POSITION[position])


# ---------------------------------------------------------------------------
# A namespace that is nearly, but not, one of iiRDS's
# ---------------------------------------------------------------------------

#: How alike a namespace has to be to one of the four before it is called a
#: near miss. The nearest legitimate namespace in the reference corpus, an
#: example's own `http://myCompany.de/iirds/myPackage/`, scores below 0.6
#: (the test reads the corpus and pins the number); a slash for the hash,
#: `https` for `http`, or `www.` in front score above 0.9. Anything on the
#: standard's own host is reported whatever its distance: nobody else mints
#: names there.
NAMESPACE_NEAR_ENOUGH = 0.85
IIRDS_HOSTS = ("http://iirds.tekom.de/", "https://iirds.tekom.de/")


def _namespace_part(iri) -> str:
    text = str(iri)
    cut = max(text.rfind("#"), text.rfind("/"))
    return text[:cut + 1]


def _namespace_as_written(term) -> str:
    """The namespace the author wrote, where it can be told from the IRI.

    The standard's own prose writes its namespaces without the `#` ("iiRDS
    Core: http://iirds.tekom.de/iirds"), and a document that copies that
    runs every name into the namespace: `http://iirds.tekom.de/iirdsPackage`
    splits, by its last slash, into a namespace nobody wrote and a name
    nobody meant. When the IRI begins with an iiRDS namespace less its `#`
    and continues with a bare name, that stem is the namespace as written.
    """
    text = str(term)
    for known in sorted(IIRDS_NAMESPACES, key=len, reverse=True):
        stem = known[:-1]
        rest = text[len(stem):]
        if text.startswith(stem) and rest and "#" not in rest and "/" not in rest:
            return stem
    return _namespace_part(term)


def _meant_by(namespace):
    """The iiRDS namespaces a misspelt one could be, fewest first.

    A namespace that several of the standard's begin with (`.../domain/`)
    is offered all of them: by letters the shortest would win, and a wrong
    suggestion costs more than none.
    """
    if namespace + "#" in IIRDS_NAMESPACES:
        return [namespace + "#"]
    scored = sorted(((difflib.SequenceMatcher(None, namespace, known).ratio(), known)
                     for known in IIRDS_NAMESPACES), reverse=True)
    best, nearest = scored[0]
    if best < NAMESPACE_NEAR_ENOUGH and not namespace.startswith(IIRDS_HOSTS):
        return []
    begun = [known for known in IIRDS_NAMESPACES if known.startswith(namespace)]
    if nearest in begun:
        return begun
    return [known for ratio, known in scored if ratio == best]


@_lint("L14", "a namespace that is nearly, but not, an iiRDS namespace",
       fix="Write the namespace exactly as the standard publishes it: "
           "http://iirds.tekom.de/iirds# for the core vocabulary and "
           "http://iirds.tekom.de/iirds/domain/{handover,machinery,software}# for the "
           "domains. A namespace one character away is a different vocabulary to every "
           "consumer, so the names under it resolve to nothing however right they are.")
def l14_near_miss_namespace(ctx):
    """`iirds/` for `iirds#`, `https` for `http`, `www.` in front.

    Such a package used to be reported as a set of proprietary classes that
    are not linked into iiRDS (L5) and a container that declares no
    iirds:Package (M3) -- every finding true, every one of them the wrong
    place to look. L13 is the mirror image: right namespace, wrong name.
    This is wrong namespace, right names, and it says how many of the names
    under it the standard actually has.
    """
    by_namespace = {}
    for triple in ctx.graph:
        for term in triple:
            if isinstance(term, URIRef) and not ctx.ontology.is_iirds_term(term):
                namespace = _namespace_as_written(term)
                # An IRI that is all namespace -- the standard's host, the
                # vocabulary itself -- is not a name under anything.
                if namespace and str(term) != namespace:
                    by_namespace.setdefault(namespace, set()).add(term)
    for namespace in sorted(by_namespace):
        meant = _meant_by(namespace)
        if not meant:
            continue
        names = by_namespace[namespace]
        locals_ = [str(term)[len(namespace):] for term in names]
        if len(meant) > 1:
            # The names decide between the candidates where they can: the
            # host alone with Package and Topic under it means the core.
            defining = [candidate for candidate in meant
                        if any(ctx.ontology.is_defined(URIRef(candidate + local)) for local in locals_)]
            if len(defining) == 1:
                meant = defining
        known = sum(1 for local in locals_
                    if any(ctx.ontology.is_defined(URIRef(candidate + local)) for candidate in meant))
        suggestion = meant[0] if len(meant) == 1 else "one of " + ", ".join(meant)
        yield Violation("namespace is nearly, but not, an iiRDS namespace",
                        subject=namespace,
                        detail="%d name%s under it, %d of them iiRDS names; did you mean %s?"
                               % (len(names), "" if len(names) == 1 else "s", known, suggestion))


# ---------------------------------------------------------------------------
# A name the declared edition of iiRDS does not have yet
# ---------------------------------------------------------------------------

def _named(term) -> str:
    """The name as a reader writes it: the local name when it is the core
    vocabulary's, the domain beside it otherwise -- `Operation` is a core
    name since 1.0 and a handover name since 1.3, and a message about the
    second must not read as a claim about the first."""
    namespace = _namespace(term)
    if namespace == IIRDS_NAMESPACES[0]:
        return _local(term)
    return "%s in %s" % (_local(term), namespace[len(IIRDS_HOST):]
                         if namespace.startswith(IIRDS_HOST) else namespace)


@_lint("L15", "a name the edition of iiRDS validated against does not have yet",
       fix="Declare the edition whose vocabulary the metadata uses in iirds:iiRDSVersion, "
           "or use the names that edition has. A consumer that reads the package as the "
           "declared edition has no definition for the name and can only ignore what it "
           "says. Every later edition keeps every earlier name, so a package that declares "
           "the newer edition keeps every statement it makes; the newer edition's own "
           "requirements then apply to it.")
def l15_name_from_a_later_edition(ctx):
    """Only the newest ontology ships, so L13 judges every package against
    the 1.3 vocabulary: a package declaring 1.0 that uses `is-based-on`
    (1.3) is using a name the standard defines. The per-edition inventory
    says when the name arrived, and the edition named here is the first
    that has it -- a single edition, because no edition has ever dropped a
    name (the inventory test holds that). Held to the edition the run
    validates against: the declared one, or the one `--iirds-version`
    asked for, like every other version-scoped rule -- and the detail says
    which when they differ. Reported once per name; a name no edition has
    is L13's, not this rule's, and a name the inventory does not know yet
    (a bundle refreshed ahead of it) is left alone rather than raised on.
    A value that is a literal -- the profile `H`, which 1.3 introduced --
    is outside what this rule can see.
    """
    editions = version_terms()
    edition = ctx.version
    if edition not in editions:
        return
    present = editions[edition]
    later = set()
    for triple in ctx.graph:
        for term in triple:
            if (isinstance(term, URIRef) and term not in later and str(term) not in present
                    and ctx.ontology.is_iirds_term(term) and ctx.ontology.is_defined(term)):
                later.add(term)
    if ctx.declared_version == edition:
        where = "this package declares %s" % edition
    else:
        where = "this run validates against %s, the package declares %s" % (
            edition, ctx.declared_version or "no edition")
    for term in sorted(later, key=str):
        arrived = next((e for e in VERSIONS if str(term) in editions.get(e, ())), None)
        if arrived is None:
            continue
        yield Violation("%s is not in iiRDS %s" % (_named(term), edition), subject=str(term),
                        detail="defined from iiRDS %s on; %s" % (arrived, where))
