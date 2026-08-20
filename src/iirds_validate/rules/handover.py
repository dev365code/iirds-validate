"""iiRDS/H rules (M15.*) — the handover profile, new in iiRDS 1.3.

Handover documentation is what a plant builder owes the operator when a machine
is delivered, and the profile exists because that hand-off is increasingly a
compliance obligation rather than a courtesy. It is a much narrower thing than
unrestricted iiRDS: documents only, no topics, no navigation structure, and
every party in the chain has to be named well enough to be contacted years
later.

These rules live apart from `schema.py` because they share a filter — every one
of them is gated to `variants=('H',)` by the catalogue — and because five of
them share a shape that is worth writing once.
"""
from __future__ import annotations

from .. import terms as T
from ..model import VCARD, Violation
from ..registry import rule

ORGANISATION_NAME = VCARD["organization-name"]


def _parties(ctx, subject, role):
    """Parties reachable from `subject` that hold `role`."""
    for party in ctx.values(subject, T.relates_to_party):
        if role in ctx.values(party, T.has_party_role):
            yield party


def _names_an_organisation(ctx, party) -> bool:
    """The party identifies a real organisation, not just a role.

    A handover package outlives the project that produced it, so "Author" with
    nothing behind it is not something anyone can follow up on.

    Two deliberate softenings, both found by running the reference tool's own
    handover fixtures. If the vcard reference resolves to nothing the package
    describes, this stays quiet and L1 reports the dangling reference: one
    unresolvable pointer should not produce the same finding five times and
    bury the real problem. And the test is for a stated organisation name
    rather than a declared vcard:Organization type, because those fixtures type
    the node `vcard:organization` — the property, lower case, not the class.
    The substance of the requirement is that the party is identifiable, and
    quibbling with the vocabulary spelling fails packages over something no
    other tool checks.
    """
    cards = ctx.values(party, T.relates_to_vcard)
    if not cards:
        return False
    for card in cards:
        if (card, None, None) not in ctx.graph:
            return True                     # undescribed: L1 owns it
        if ctx.has(card, ORGANISATION_NAME):
            return True
    return False


def _needs_named_party(ctx, cls, role, what):
    """The shape shared by M15.7b, M15.7d, M15.8, M15.9 and M15.10."""
    for subject in ctx.instances_of(cls):
        named = [p for p in _parties(ctx, subject, role) if _names_an_organisation(ctx, p)]
        if not named:
            yield Violation(
                "iiRDS/H: %s must relate to an iirds:Party with iirds:has-party-role %s "
                "that names a vcard:Organization" % (what, str(role).split("#")[-1]),
                subject=ctx.ref(subject), detail=ctx.label_of(subject))


# --------------------------------------------------------------------------
# What a handover document must carry
# --------------------------------------------------------------------------

@rule("M15.2",
       fix="Add exactly one iirdsHov:has-document-type to the Document, naming one of the handover document types. In iiRDS/H a receiving plant sorts incoming documents by this before anything reads them.")
def m15_2_document_category(ctx):
    for doc in ctx.instances_of(T.Document):
        if len(ctx.values(doc, T.hov_has_document_category)) != 1:
            yield Violation("iiRDS/H: iirds:Document must have exactly one "
                            "iirdsHov:has-document-category", subject=ctx.ref(doc))


@rule("M15.3",
       fix="Add iirds:language to the Document, as a BCP 47 tag such as en or de-DE. A handover package crosses organisations, and the receiving side cannot infer which language a file is in.")
def m15_3_language(ctx):
    for doc in ctx.instances_of(T.Document):
        if not ctx.has(doc, T.language):
            yield Violation("iiRDS/H: iirds:Document must have iirds:language", subject=ctx.ref(doc))


@rule("M15.4",
       fix="Add iirds:title to the Document. It is what appears in the receiving system's document list, and a handover document without one arrives unnamed among hundreds.")
def m15_4_title(ctx):
    for doc in ctx.instances_of(T.Document):
        if not ctx.has(doc, T.title):
            yield Violation("iiRDS/H: iirds:Document must have iirds:title", subject=ctx.ref(doc))


@rule("M15.5",
       fix="Add one iirds:is-version-of relating the Document to an iirds:InformationObject. That link is how a plant recognises a later delivery as a revision of a document it already holds instead of as a new one.")
def m15_5_information_object(ctx):
    """Without it there is nothing to hang later revisions of the document off."""
    objects = None
    for doc in ctx.instances_of(T.Document):
        objects = [o for o in ctx.values(doc, T.is_version_of)
                   if T.InformationObject in ctx.values(o, T.RDF_TYPE)]
        if len(objects) != 1:
            yield Violation("iiRDS/H: iirds:Document must have exactly one iirds:is-version-of "
                            "relating to an iirds:InformationObject",
                            subject=ctx.ref(doc), detail="%d found" % len(objects))


@rule("M15.6",
       fix="Add iirds:has-rendition to the Document, pointing at a Rendition whose iirds:source names a file in this container. Without it the metadata describes a document the package does not actually deliver.")
def m15_6_rendition(ctx):
    for doc in ctx.instances_of(T.Document):
        if not ctx.has(doc, T.has_rendition):
            yield Violation("iiRDS/H: iirds:Document must have iirds:has-rendition",
                            subject=ctx.ref(doc))


# --------------------------------------------------------------------------
# Identifying the product the documents are about
# --------------------------------------------------------------------------

def _identities_of_type(ctx, variant, wanted):
    """Identities of a product variant whose domain declares one of `wanted`."""
    for identity in ctx.values(variant, T.has_identity):
        for domain in ctx.values(identity, T.has_identity_domain):
            if any(t in wanted for t in ctx.values(domain, T.has_identity_type)):
                yield identity, domain


@rule("M15.7a",
       fix="Add iirds:relates-to-product-variant on the Document, relating it to the product variant it documents. In a handover the receiving plant files documents against equipment, and this is the link that makes that possible.")
def m15_7a_product_variant_instance_identity(ctx):
    """The document has to say which machine, not merely which model."""
    for doc in ctx.instances_of(T.Document):
        variants = ctx.values(doc, T.relates_to_product_variant)
        if not variants:
            yield Violation("iiRDS/H: iirds:Document must relate to at least one "
                            "iirds:ProductVariant", subject=ctx.ref(doc))
            continue
        if not any(any(_identities_of_type(ctx, v, T.INSTANCE_IDENTITY_TYPES)) for v in variants):
            yield Violation("iiRDS/H: the related iirds:ProductVariant must carry an identity "
                            "whose domain has an identity type of ObjectInstanceURI, "
                            "ObjectTypeURI or SerialNumber",
                            subject=ctx.ref(doc))


@rule("M15.7b",
       fix="Give the instance Identity an iirds:IdentityDomain that names one of ObjectInstanceURI, ObjectTypeURI or SerialNumber. The domain says which identifier scheme the value belongs to; without it a serial number and an asset URI are indistinguishable strings.")
def m15_7b_instance_identity_manufacturer(ctx):
    for variant in ctx.instances_of(T.ProductVariant):
        for _identity, domain in _identities_of_type(ctx, variant, T.INSTANCE_IDENTITY_TYPES):
            named = [p for p in _parties(ctx, domain, T.Manufacturer)
                     if _names_an_organisation(ctx, p)]
            if not named:
                yield Violation("iiRDS/H: the identity domain of an instance identity must "
                                "relate to an iirds:Party with role Manufacturer that names a "
                                "vcard:Organization",
                                subject=ctx.ref(domain), detail=ctx.label_of(variant))


@rule("M15.7c",
       fix="Relate the ProductVariant to a second iirds:Identity carrying the product type, with its own IdentityDomain. A handover needs both what this machine is and which type it belongs to, because manuals are written per type.")
def m15_7c_product_type_identity(ctx):
    for variant in ctx.instances_of(T.ProductVariant):
        if not any(_identities_of_type(ctx, variant, (T.ProductType,))):
            yield Violation("iiRDS/H: iirds:ProductVariant must also carry an identity whose "
                            "domain has an identity type of iirds:ProductType",
                            subject=ctx.ref(variant), detail=ctx.label_of(variant))


@rule("M15.7d",
       fix="Relate the ProductType IdentityDomain to an iirds:Party with iirds:has-party-role. Identifier schemes are only unique within the organisation that issues them, so the domain has to say whose scheme it is.")
def m15_7d_product_type_manufacturer(ctx):
    for variant in ctx.instances_of(T.ProductVariant):
        for _identity, domain in _identities_of_type(ctx, variant, (T.ProductType,)):
            named = [p for p in _parties(ctx, domain, T.Manufacturer)
                     if _names_an_organisation(ctx, p)]
            if not named:
                yield Violation("iiRDS/H: the identity domain of a ProductType identity must "
                                "relate to an iirds:Party with role Manufacturer that names a "
                                "vcard:Organization",
                                subject=ctx.ref(domain), detail=ctx.label_of(variant))


# --------------------------------------------------------------------------
# Who is answerable for what
# --------------------------------------------------------------------------

@rule("M15.8",
       fix="Add iirds:relates-to-Party on the Document, relating it to a Party with a role. A handover document with no responsible organisation leaves the receiving plant with nobody to ask about it.")
def m15_8_document_author(ctx):
    yield from _needs_named_party(ctx, T.Document, T.Author, "iirds:Document")


@rule("M15.9",
       fix="Add iirds:relates-to-Party on the Package, relating it to a Party with a role. It names who delivered this consignment, as distinct from who authored any one document inside it.")
def m15_9_package_creator(ctx):
    yield from _needs_named_party(ctx, T.Package, T.Creator, "iirds:Package")


@rule("M15.10",
       fix="Add iirds:relates-to-Party on the InformationObject, relating it to a Party with a role. Responsibility for the underlying content can differ from responsibility for the delivered document, and a plant needs both.")
def m15_10_information_object_creator(ctx):
    yield from _needs_named_party(ctx, T.InformationObject, T.Creator, "iirds:InformationObject")


# --------------------------------------------------------------------------
# What a handover package may not contain
# --------------------------------------------------------------------------

@rule("M15.11a",
       fix="Retype the information unit as iirds:Document or iirds:Package, or take it out of the handover package. iiRDS/H deliberately restricts the shapes a receiving system has to understand, and that restriction is the profile's whole value.")
def m15_11a_documents_only(ctx):
    for cls in (T.Topic, T.Fragment):
        for unit in ctx.typed_exactly(cls):
            yield Violation("iiRDS/H packages must contain only iirds:Document and "
                            "iirds:Package information units",
                            subject=ctx.ref(unit), detail=ctx.ref(cls).split("#")[-1])


@rule("M15.11b",
       fix="Remove the iirds:DirectoryNode instances. iiRDS/H carries documents, not a navigation tree; a handover package is filed by the receiving system rather than browsed as authored.")
def m15_11b_no_directory_node(ctx):
    for node in ctx.instances_of(T.DirectoryNode):
        yield Violation("iiRDS/H packages must not contain iirds:DirectoryNode instances",
                        subject=ctx.ref(node))


@rule("M15.11c",
       fix="Remove the iirds:Selector instances. iiRDS/H delivers whole documents, so addressing a fragment inside one has no meaning on the receiving side.")
def m15_11c_no_selector(ctx):
    for selector in ctx.instances_of(T.Selector):
        yield Violation("iiRDS/H packages must not contain iirds:Selector instances",
                        subject=ctx.ref(selector))
