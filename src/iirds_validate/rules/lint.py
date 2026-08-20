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

import posixpath
from urllib.parse import unquote, urlparse

from rdflib import BNode, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from .. import terms as T
from ..model import DCTERMS, OWL, VCARD, VERSIONS, Violation
from ..registry import rule

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


def _lint(rule_id, title, prio="RECOMMENDED", conformance=False):
    """Register an interoperability rule.

    `conformance=True` marks the ones that implement a sentence the
    specification states as a MUST. Those also run under `check`: the catalogue
    happens to have no id for them, which is a fact about the catalogue rather
    than about whether the standard requires it.
    """
    return rule(rule_id, kind="lint", prio=prio, title=title,
                versions=ALL_VERSIONS, variants=(), spec=None, conformance=conformance)


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
    seen = set()
    for subj, pred, obj in ctx.graph:
        if not isinstance(obj, URIRef) or not ctx.ontology.is_iirds_term(pred):
            continue
        if ctx.ontology.is_iirds_term(obj) or ctx.ontology.is_defined(obj):
            continue                      # a term from the standard vocabulary
        if str(obj).startswith(WELL_KNOWN) or _described(ctx, obj) or obj in seen:
            continue
        seen.add(obj)
        yield subj, pred, obj


@_lint("L1", "an iiRDS relation should not point at an IRI the package never describes")
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


@_lint("L8", "external references cannot be resolved by an offline consumer", prio="MAY")
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
       prio="MUST", conformance=True)
def l2_missing_content_files(ctx):
    """A rendition that points at a file nobody packed."""
    present = set(ctx.package.files)
    for rend in ctx.instances_of(T.Rendition):
        for src in ctx.values(rend, T.source):
            raw = str(src)
            path = unquote(urlparse(raw).path)
            if not path or "://" in raw:
                continue      # absolute URL: out of scope for this check
            # `lstrip` takes a character set, not a prefix: ".config/a.xhtml"
            # would become "config/a.xhtml" and be reported as missing.
            candidate = posixpath.normpath(path.lstrip("/"))
            if candidate.startswith(".."):
                yield Violation("iirds:source escapes the package root",
                                subject=ctx.ref(rend), detail=raw)
                continue
            if candidate not in present:
                yield Violation("iirds:source does not resolve to a file in the container",
                                subject=ctx.ref(rend), detail=raw)


@_lint("L3", "every iirds:DirectoryNode should be reachable from a root node")
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
    for node in sorted(nodes - reachable, key=str):
        yield Violation("directory node is not reachable from any root node",
                        subject=ctx.ref(node), detail=ctx.label_of(node))


@_lint("L4", "the directory structure should not contain cycles", prio="MUST")
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
                                    detail=" -> ".join(str(n).split("/")[-1] for n in loop))
                continue
            state[node] = "open"
            stack.append((_CLOSE, node))
            for child in _children(ctx, node):
                stack.append((child, trail + [node]))


@_lint("L5", "proprietary classes should be linked to the iiRDS vocabulary")
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


@_lint("L6", "proprietary metadata values should carry a human-readable label")
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

    for subj in sorted(ctx.iirds_subjects(), key=str):
        if isinstance(subj, BNode) or subj in units:
            continue
        if ctx.ontology.is_iirds_term(subj) or str(subj).startswith(WELL_KNOWN):
            continue
        if subj not in referenced:
            continue
        if _labelled(ctx, subj):
            continue
        types = [str(ty).split("#")[-1] for ty in ctx.values(subj, RDF.type)]
        yield Violation("metadata value has no label a consumer could display",
                        subject=ctx.ref(subj),
                        detail=("typed as %s" % ", ".join(types)) if types else None)


@_lint("L7", "every information unit should have a title")
def l7_untitled_information_units(ctx):
    """Valid without one, unusable without one."""
    for unit in ctx.information_units():
        # iirds:Package is itself a subclass of iirds:InformationUnit, but a
        # package is not a thing with a title in the same sense.
        if T.Package in ctx.values(unit, RDF.type):
            continue
        if not ctx.has(unit, T.title):
            types = [str(t).split("#")[-1] for t in ctx.values(unit, RDF.type)]
            yield Violation("information unit has no iirds:title",
                            subject=ctx.ref(unit), detail=", ".join(types) or None)


@_lint("L9", "the RDF/XML and JSON-LD metadata must describe the same graph",
       prio="MUST", conformance=True)
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


@_lint("L10", "abstract iiRDS classes should not be used to type an instance directly")
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


@_lint("L11", "content named .xhtml but declared as another media type is never checked")
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

    for rendition in sorted(ctx.instances_of(T.Rendition), key=str):
        declared = [_media_type(f) for f in ctx.values(rendition, T.fmt)]
        if not declared or XHTML_FORMAT in declared:
            continue          # no format at all is M11's finding, not a second one here
        for source in ctx.values(rendition, T.source):
            name = posixpath.normpath(str(source).lstrip("/"))
            if name.lower().endswith(".xhtml") and ctx.package.has(name):
                yield Violation("this file is named .xhtml but is not declared as iiRDS "
                                "XHTML5, so none of the content rules examined it",
                                subject=name,
                                detail="declared as %s" % ", ".join(sorted(declared)))
