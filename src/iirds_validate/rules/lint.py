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

from urllib.parse import unquote, urlparse

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from .. import terms as T
from ..model import Violation
from ..registry import rule

ALL_VERSIONS = ("1.0", "1.0.1", "1.1", "1.2", "1.3")

VCARD_FN = URIRef("http://www.w3.org/2006/vcard/ns#fn")
DCTERMS_TITLE = URIRef("http://purl.org/dc/terms/title")
LABEL_PROPERTIES = (RDFS.label, SKOS.prefLabel, SKOS.altLabel, T.title, VCARD_FN, DCTERMS_TITLE)

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


def _lint(rule_id, title, prio="RECOMMENDED"):
    return rule(rule_id, kind="lint", prio=prio, title=title,
                versions=ALL_VERSIONS, variants=(), spec=None)


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
                        subject=str(obj),
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
                        subject=str(obj),
                        detail="referenced by %s via %s" % (ctx.label_of(subj), pred.split("#")[-1]))


@_lint("L2", "every iirds:source should resolve to a file inside the container", prio="MUST")
def l2_missing_content_files(ctx):
    """A rendition that points at a file nobody packed."""
    present = set(ctx.package.files)
    for rend in ctx.instances_of(T.Rendition):
        for src in ctx.values(rend, T.source):
            raw = str(src)
            path = unquote(urlparse(raw).path)
            if not path or "://" in raw:
                continue      # absolute URL: out of scope for this check
            candidate = path.lstrip("./").lstrip("/")
            if candidate not in present:
                yield Violation("iirds:source does not resolve to a file in the container",
                                subject=str(rend), detail=raw)


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
        for prop in (T.has_first_child, T.has_next_sibling):
            stack.extend(ctx.values(node, prop))
    for node in sorted(nodes - reachable, key=str):
        yield Violation("directory node is not reachable from any root node",
                        subject=str(node), detail=ctx.label_of(node))


@_lint("L4", "the directory structure should not contain cycles", prio="MUST")
def l4_directory_cycles(ctx):
    """A consumer walking the table of contents would loop forever."""
    colour = {}

    def walk(node, trail):
        state = colour.get(node)
        if state == "done":
            return
        if state == "open":
            loop = trail[trail.index(node):] + [node]
            yield Violation("cycle in the directory structure",
                            subject=str(node),
                            detail=" -> ".join(str(n).split("/")[-1] for n in loop))
            return
        colour[node] = "open"
        for prop in (T.has_first_child, T.has_next_sibling):
            for child in ctx.values(node, prop):
                yield from walk(child, trail + [node])
        colour[node] = "done"

    for start in ctx.instances_of(T.DirectoryNode):
        yield from walk(start, [])


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
        equivalents = list(ctx.graph.objects(cls, URIRef("http://www.w3.org/2002/07/owl#equivalentClass")))
        if any(ctx.ontology.is_iirds_term(p) for p in parents + equivalents):
            continue
        reported.add(cls)
        yield Violation("proprietary class is not linked to any iiRDS class",
                        subject=str(cls),
                        detail="add rdfs:subClassOf or owl:equivalentClass pointing into iiRDS")


@_lint("L6", "proprietary metadata values should carry a human-readable label")
def l6_unlabelled_concepts(ctx):
    """Labels travel inside the package, so a consumer has something to show.

    They are also what a search over the package can match against: an IRI
    ending in `main-spindle` will never match a query written in German or
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
                        subject=str(subj),
                        detail=("typed as %s" % ", ".join(types)) if types else None)


@_lint("L7", "every information unit should have a title")
def l7_untitled_information_units(ctx):
    """Valid without one, unusable without one."""
    for unit in ctx.information_units():
        if ctx.has(unit, T.Package) or T.Package in ctx.values(unit, RDF.type):
            continue
        if not ctx.has(unit, T.title):
            types = [str(t).split("#")[-1] for t in ctx.values(unit, RDF.type)]
            yield Violation("information unit has no iirds:title",
                            subject=str(unit), detail=", ".join(types) or None)
