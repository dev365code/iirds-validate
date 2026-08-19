"""Schema rules (M*) — conformance of the metadata graph.

Every rule here operates on an rdflib Graph, so it is blind to whether the
package wrote its metadata as RDF/XML or JSON-LD, and to which of the several
legal RDF/XML shapes it chose. Rule ids match plusmeta's catalogue so results
from the two tools can be compared directly.
"""
from __future__ import annotations

from rdflib import BNode, URIRef
from rdflib.namespace import RDF

from .. import terms as T
from ..model import DCTERMS, Violation
from ..registry import rule


_SCHEME = __import__("re").compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _is_absolute(iri) -> bool:
    """An absolute IRI has a scheme. urn:uuid:... counts; #frag-only does not."""
    return isinstance(iri, URIRef) and bool(_SCHEME.match(str(iri)))


def _at_most_one(ctx, cls, prop, label):
    """Shared body for the many 'MUST NOT have more than one X' rules."""
    for subj in ctx.instances_of(cls):
        values = ctx.values(subj, prop)
        if len(values) > 1:
            yield Violation("more than one %s" % label,
                            subject=str(subj),
                            detail="%d values: %s" % (len(values), ", ".join(str(v)[:40] for v in values[:4])))


# --------------------------------------------------------------------------
# Information units
# --------------------------------------------------------------------------

@rule("M1")
def m1_no_direct_information_unit(ctx):
    for subj in ctx.typed_exactly(T.InformationUnit):
        yield Violation("iirds:InformationUnit used directly; use one of its subclasses",
                        subject=str(subj))


@rule("M2.1")
def m2_1_information_unit_iri(ctx):
    for subj in ctx.information_units():
        if isinstance(subj, BNode):
            yield Violation("instance of an iirds:InformationUnit subclass must have an IRI, "
                            "not be a blank node",
                            subject=str(subj))


@rule("M2.3")
def m2_3(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.dateOfCreation, "iirds:dateOfCreation")


@rule("M2.4")
def m2_4(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.dateOfLastModification,
                            "iirds:dateOfLastModification")


@rule("M2.5")
def m2_5(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.revision, "iirds:revision")


@rule("M2.6")
def m2_6(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.title, "iirds:title")


@rule("M2.7")
def m2_7(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.has_abstract, "iirds:has-abstract")


@rule("M2.8")
def m2_8(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.is_replacement_of,
                            "iirds:is-replacement-of")


@rule("M2.9")
def m2_9(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.is_version_of, "iirds:is-version-of")


# --------------------------------------------------------------------------
# Package
# --------------------------------------------------------------------------

@rule("M3")
def m3_exactly_one_package(ctx):
    packages = ctx.instances_of(T.Package)
    # A nested child package is referenced by iirds:is-part-of-package; only the
    # package that is not part of another one represents this container.
    own = [p for p in packages if not ctx.has(p, T.is_part_of_package)]
    if not packages:
        yield Violation("metadata declares no iirds:Package for this container")
    elif len(own) > 1:
        yield Violation("more than one iirds:Package represents this container",
                        detail=", ".join(str(p) for p in own[:5]))


@rule("M4")
def m4_package_version(ctx):
    for pkg in ctx.instances_of(T.Package):
        if ctx.has(pkg, T.is_part_of_package):
            continue
        if not ctx.has(pkg, T.iiRDSVersion):
            yield Violation("iirds:Package must carry iirds:iiRDSVersion", subject=str(pkg))


@rule("M5")
def m5_absolute_iris(ctx):
    for subj in ctx.iirds_subjects():
        if isinstance(subj, URIRef) and not _is_absolute(subj):
            yield Violation("relative IRI in rdf:about; absolute IRIs are recommended",
                            subject=str(subj))


@rule("M6")
def m6_one_information_object(ctx):
    for unit in ctx.information_units():
        objs = ctx.values(unit, T.is_version_of)
        if len(objs) > 1:
            yield Violation("information unit relates to more than one information object "
                            "via iirds:is-version-of",
                            subject=str(unit), detail="%d objects" % len(objs))


@rule("M7.1")
def m7_1_information_object_iri(ctx):
    for obj in ctx.instances_of(T.InformationObject):
        if isinstance(obj, BNode) or not _is_absolute(obj):
            yield Violation("iirds:InformationObject must have an absolute IRI", subject=str(obj))


@rule("M8")
def m8_package_no_rendition(ctx):
    for pkg in ctx.instances_of(T.Package):
        if ctx.has(pkg, T.is_part_of_package):
            continue
        if ctx.has(pkg, T.has_rendition):
            yield Violation("the iirds:Package representing this container must not be the "
                            "subject of iirds:has-rendition",
                            subject=str(pkg))


# --------------------------------------------------------------------------
# Renditions and selectors
# --------------------------------------------------------------------------

@rule("M9")
def m9_relative_source(ctx):
    for rend in ctx.instances_of(T.Rendition):
        for src in ctx.values(rend, T.source):
            value = str(src)
            if "://" in value or value.startswith("/"):
                yield Violation("iirds:source must be relative to the package root",
                                subject=str(rend), detail=value)


@rule("M10")
def m10_rendition_source(ctx):
    for rend in ctx.instances_of(T.Rendition):
        if not ctx.has(rend, T.source):
            yield Violation("iirds:Rendition must have iirds:source", subject=str(rend))


@rule("M11")
def m11_rendition_format(ctx):
    for rend in ctx.instances_of(T.Rendition):
        if not ctx.has(rend, T.fmt):
            yield Violation("iirds:Rendition must have iirds:format", subject=str(rend))


@rule("M12")
def m12_no_direct_selector(ctx):
    for subj in ctx.typed_exactly(T.Selector):
        yield Violation("iirds:Selector used directly; use one of its subclasses",
                        subject=str(subj))


@rule("M13.1")
def m13_1_selector_value(ctx):
    for sel in ctx.instances_of(T.Selector):
        if isinstance(sel, BNode) and not ctx.values(sel, RDF.value):
            yield Violation("iirds:Selector must have rdf:value", subject=str(sel))
        elif not isinstance(sel, BNode) and not ctx.values(sel, RDF.value):
            yield Violation("iirds:Selector must have rdf:value", subject=str(sel))


@rule("M13.2")
def m13_2_selector_conforms_to(ctx):
    for sel in ctx.instances_of(T.Selector):
        if not ctx.values(sel, DCTERMS.conformsTo):
            yield Violation("iirds:Selector must have dcterms:conformsTo", subject=str(sel))


@rule("M14.1")
def m14_1_range_start(ctx):
    for sel in ctx.instances_of(T.RangeSelector):
        if not ctx.has(sel, T.has_start_selector):
            yield Violation("iirds:RangeSelector must have iirds:has-start-selector",
                            subject=str(sel))


@rule("M14.2")
def m14_2_range_end(ctx):
    for sel in ctx.instances_of(T.RangeSelector):
        if not ctx.has(sel, T.has_end_selector):
            yield Violation("iirds:RangeSelector must have iirds:has-end-selector",
                            subject=str(sel))


# --------------------------------------------------------------------------
# Documents, events, identities, parties
# --------------------------------------------------------------------------

@rule("M15.1")
def m15_1_document_type(ctx):
    for doc in ctx.instances_of(T.Document):
        if not (ctx.has(doc, T.has_document_type)
                or ctx.has(doc, T.is_applicable_for_document_type)):
            yield Violation("iirds:Document must relate to a standardised iirds:DocumentType",
                            subject=str(doc))


@rule("M16.1")
def m16_1_event_code(ctx):
    for ev in ctx.instances_of(T.Event):
        if not ctx.has(ev, T.has_event_code):
            yield Violation("iirds:Event must have iirds:eventCode", subject=str(ev))


@rule("M16.2")
def m16_2_event_type(ctx):
    for ev in ctx.instances_of(T.Event):
        if not ctx.has(ev, T.has_event_type):
            yield Violation("iirds:Event must have iirds:eventType", subject=str(ev))


@rule("M19.1")
def m19_1_identity_domain(ctx):
    for ident in ctx.instances_of(T.Identity):
        domains = ctx.values(ident, T.has_identity_domain)
        if len(domains) != 1:
            yield Violation("iirds:Identity must point to exactly one iirds:IdentityDomain",
                            subject=str(ident), detail="%d domains" % len(domains))


@rule("M19.2")
def m19_2_identity_value(ctx):
    for ident in ctx.instances_of(T.Identity):
        values = [v for v in ctx.values(ident, T.identifier) if str(v).strip()]
        if not values:
            yield Violation("iirds:Identity must carry a non-empty iirds:identifier",
                            subject=str(ident))


@rule("M20.1")
def m20_1_identity_domain_iri(ctx):
    for dom in ctx.instances_of(T.IdentityDomain):
        if isinstance(dom, BNode) or not _is_absolute(dom):
            yield Violation("iirds:IdentityDomain must have an absolute IRI", subject=str(dom))


@rule("M21.2")
def m21_2(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.dateOfEffect,
                            "iirds:dateOfEffect")


@rule("M21.3")
def m21_3(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.dateOfExpiry,
                            "iirds:dateOfExpiry")


@rule("M21.4")
def m21_4(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.purpose, "iirds:purpose")


@rule("M21.6")
def m21_6(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.relates_to_party,
                            "iirds:relates-to-party")


@rule("M22.1")
def m22_1_party_role(ctx):
    for party in ctx.instances_of(T.Party):
        if not ctx.has(party, T.has_party_role):
            yield Violation("iirds:Party must have iirds:has-party-role", subject=str(party))


# --------------------------------------------------------------------------
# Directory structure (table of contents)
# --------------------------------------------------------------------------

@rule("M24.1")
def m24_1(ctx):
    yield from _at_most_one(ctx, T.DirectoryNode, T.has_next_sibling,
                            "iirds:has-next-sibling")


@rule("M24.2")
def m24_2(ctx):
    yield from _at_most_one(ctx, T.DirectoryNode, T.has_directory_structure_type,
                            "iirds:has-directory-structure-type")


@rule("M24.3")
def m24_3(ctx):
    yield from _at_most_one(ctx, T.DirectoryNode, T.has_first_child,
                            "iirds:has-first-child")


@rule("M24.4")
def m24_4(ctx):
    yield from _at_most_one(ctx, T.DirectoryNode, T.relates_to_information_unit,
                            "iirds:relates-to-information-unit")


@rule("M24.6")
def m24_6_root_node(ctx):
    nodes = ctx.instances_of(T.DirectoryNode)
    if not nodes:
        return
    roots = [n for n in nodes
             if ctx.has(n, T.has_directory_structure_type)
             and ctx.has(n, T.has_first_child)]
    if not roots:
        yield Violation("no root directory node: at least one iirds:DirectoryNode must have "
                        "both iirds:has-directory-structure-type and iirds:has-first-child",
                        detail="%d directory nodes present" % len(nodes))


@rule("M35")
def m35_identity_identifier(ctx):
    for ident in ctx.instances_of(T.Identity):
        if not ctx.has(ident, T.identifier):
            yield Violation("iirds:Identity must have iirds:identifier", subject=str(ident))


# --------------------------------------------------------------------------
# iiRDS/H — handover, new in 1.3
# --------------------------------------------------------------------------

@rule("M15.2")
def m15_2_hov_document_category(ctx):
    for doc in ctx.instances_of(T.Document):
        if len(ctx.values(doc, T.hov_has_document_category)) != 1:
            yield Violation("iiRDS/H: iirds:Document must have exactly one "
                            "iirdsHov:has-document-category",
                            subject=str(doc))


@rule("M15.3")
def m15_3_hov_language(ctx):
    for doc in ctx.instances_of(T.Document):
        if not ctx.has(doc, T.language):
            yield Violation("iiRDS/H: iirds:Document must have iirds:language", subject=str(doc))


@rule("M15.4")
def m15_4_hov_title(ctx):
    for doc in ctx.instances_of(T.Document):
        if not ctx.has(doc, T.title):
            yield Violation("iiRDS/H: iirds:Document must have iirds:title", subject=str(doc))


@rule("M15.6")
def m15_6_hov_rendition(ctx):
    for doc in ctx.instances_of(T.Document):
        if not ctx.has(doc, T.has_rendition):
            yield Violation("iiRDS/H: iirds:Document must have iirds:has-rendition",
                            subject=str(doc))


@rule("M15.11b")
def m15_11b_hov_no_directory_node(ctx):
    for node in ctx.instances_of(T.DirectoryNode):
        yield Violation("iiRDS/H packages must not contain iirds:DirectoryNode instances",
                        subject=str(node))


@rule("M15.11c")
def m15_11c_hov_no_selector(ctx):
    for sel in ctx.instances_of(T.Selector):
        yield Violation("iiRDS/H packages must not contain iirds:Selector instances",
                        subject=str(sel))
