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

from rdflib import Literal

from .. import terms as T
from ..model import ORGANISATION_TYPES, VCARD, Violation
from ..registry import CATALOG, rule

ORGANISATION_NAME = VCARD["organization-name"]

# ORGANISATION_TYPES is in model.py, beside the namespace and the divergence
# it records; section 6.8.3's R12 reads it too.


def _spec_sans_quote(rule_id: str):
    """The catalogue's link, minus its text fragment. For four rules here
    the fragment quotes "mandatory for each iirds:Document" while the rule
    governs Package, InformationObject or IdentityDomain -- a reader lands
    on a sentence about the wrong class. The section anchor is kept; the
    misleading quotation is not."""
    url = CATALOG.get(rule_id, {}).get("spec") or ""
    return url.partition(":~:text=")[0] or None


def _parties(ctx, subject, role):
    """Parties reachable from `subject` that hold `role`."""
    for party in ctx.values(subject, T.relates_to_party):
        if role in ctx.values(party, T.has_party_role):
            yield party


def _names_an_organisation(ctx, party) -> bool:
    """The party identifies a real organisation, not just a role.

    A handover package outlives the project that produced it, so "Author" with
    nothing behind it is not something anyone can follow up on.

    The sentence asks for three things and all three are asked here: a vcard,
    an organisation, a stated name.

    One deliberate softening, found by running the reference tool's own
    handover fixtures. If the vcard reference resolves to nothing the package
    describes, this stays quiet and R4 reports the dangling pointer once: one
    unresolvable pointer should not produce the same finding five times and
    bury the real problem. That case used to be left to L1, which is a lint and
    does not run under `check` -- so a handover package whose manufacturer,
    author and creator all pointed at nothing passed conformance in silence.
    Softening it was right; giving it away was not.

    And one deliberate widening: either spelling in ORGANISATION_TYPES will
    do, for the reasons recorded there.

    The type used to go unasked altogether, on the reasoning that the substance
    of the requirement is that the party can be identified. It is not: a card
    typed `vcard:Individual` and stating an `organization-name` breached all
    three of section 8.3.2's named-party sentences and passed in silence, and
    those sentences are the whole reason a handover package can be traced to
    the firm that shipped it. Accommodating a spelling is not the same as
    dropping the word. Across every corpus this repository holds -- ours,
    tekom's samples, the reference's fixtures -- every card carrying an
    organisation name carries one of the two spellings too, so nothing that
    passed before fails now.

    The type is asked through `is_instance`, not by comparing `rdf:type`
    values, which was the first form of this check and was wrong for the
    reason `Context.is_instance` states: "exact typing is how section 7 gets
    forgotten one rule at a time". A package that declares its own class a
    subclass of `vcard:Organization` and types the card with it has said the
    card is an organisation, and reporting it beside the `vcard:Individual`
    case would put a conformant package and a broken one under one finding.
    """
    cards = ctx.values(party, T.relates_to_vcard)
    if not cards:
        return False
    for card in cards:
        if not _describes(ctx, card):
            return True                     # undescribed: R4 owns it
        if ctx.has(card, ORGANISATION_NAME) \
                and any(ctx.is_instance(card, cls) for cls in ORGANISATION_TYPES):
            return True
    return False


def _describes(ctx, node) -> bool:
    """The package says something about this node rather than merely naming it.

    One reading used in two places: R4 reports the pointer that resolves to
    nothing, and the five named-party MUSTs stay quiet about the same pointer
    so a single broken reference does not arrive five times. If the two
    readings ever drifted, the case would fall between them and be reported by
    nobody -- which is exactly what happened while it belonged to a lint.
    """
    return (node, None, None) in ctx.graph


def _needs_named_party(ctx, cls, role, what):
    """The shape shared by M15.7b, M15.7d, M15.8, M15.9 and M15.10."""
    for subject in ctx.instances_of(cls):
        named = [p for p in _parties(ctx, subject, role) if _names_an_organisation(ctx, p)]
        if not named:
            yield Violation(
                "iiRDS/H: %s must relate to an iirds:Party with iirds:has-party-role %s "
                "that names a vcard:Organization" % (what, str(role).split("#")[-1]),
                subject=ctx.ref(subject), detail=ctx.label_of(subject))


@rule("R4", covers=("x8-3-2-metadata-requirements#9", "x8-3-2-metadata-requirements#12",
                    "x8-3-2-metadata-requirements#13",),
      kind="schema", prio="MUST",
      versions=("1.0", "1.0.1", "1.1", "1.2", "1.3"), variants=(),
      title="a vcard a party points at must be described in the package",
      spec=_spec_sans_quote("M15.8"), diagnosis="cause",
      fix="Describe the vcard in this package as a vcard:Organization carrying a "
          "vcard:organization-name, or drop the iirds:relates-to-vcard. A pointer at "
          "an IRI nothing here describes leaves the party unidentifiable to anyone "
          "holding only the package — which in iiRDS/H is the reader the profile is "
          "written for, and is why the five named-party MUSTs are MUSTs there.")
def r4_party_vcard_is_described(ctx):
    """The cause behind five MUSTs that agree to stay quiet.

    A handover package outlives the project that produced it, so every party
    in the chain has to be identifiable from the package alone. Five MUSTs say
    so, and all five soften when the vcard reference resolves to nothing --
    otherwise one broken pointer arrives five times and buries what happened.

    The softening needs an owner in the same run, and it did not have one:
    dangling references belong to L1, a lint, so `check` reported nothing at
    all about a package whose manufacturer, author and creator each pointed at
    an IRI the package never mentions again. Reported here once per vcard, as
    a cause, which is what the five findings would have been consequences of.

    Three of section 8.3.2's sentences are covered by this rule together with
    the one that softens for them -- #9 and #12 with M15.7b and M15.7d, #13
    with M15.10. #13 was claimed by M15.10 alone, which meant the one shape
    M15.10 deliberately stays quiet about was claimed by a rule that cannot
    report it. The pairing holds because both sides ask `_describes` the same
    question over the same population: whatever the five let through, this
    reports.
    """
    # Every profile, not only iiRDS/H. The softening this owns belongs to
    # section 8.3.2's five, which are iiRDS/H -- but a pointer at nothing is a
    # pointer at nothing anywhere, and gating the cause to the profile left
    # `check` silent about it outside and let R12 answer it instead, which
    # reported the same defect twice inside. A rule may run wider than the
    # sentences it claims.
    #
    # Literals are R12's: "points at a vcard this package never describes" is
    # the wrong sentence for a value that is not a pointer at all.
    # A name a vocabulary defines is R12's, for the same reason a literal is:
    # this rule's sentence is "never describes it", and something does. R12
    # stood aside for a pointer at nothing by asking the ontology; nothing here
    # asked back, and `_describes` cannot answer it -- it reads `ctx.graph`,
    # which the ontology is not merged into, so `iirds:Topic` and
    # `vcard:Organization` both looked like pointers at nothing. Both rules
    # then spoke about one mistake, and this one printed the advice R12's
    # docstring says must never appear about a class of the standard: describe
    # it in this package.
    cards = {o for _s, o in ctx.graph.subject_objects(T.relates_to_vcard)
             if not isinstance(o, Literal) and not ctx.names_a_defined_term(o)}
    for card in sorted((c for c in cards if not _describes(ctx, c)), key=ctx.ref):
        users = sorted(ctx.ref(p) for p in ctx.graph.subjects(T.relates_to_vcard, card))
        yield Violation("iirds:relates-to-vcard points at a vcard this package never "
                        "describes, so no party using it names an organisation",
                        subject=ctx.ref(card), detail="referenced by %s" % ", ".join(users))


# --------------------------------------------------------------------------
# What a handover document must carry
# --------------------------------------------------------------------------

@rule("M15.2",
       fix="Add exactly one iirdsHov:has-document-category to the Document, naming one of the handover document categories. In iiRDS/H a receiving plant sorts incoming documents by this before anything reads them.")
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
                   if ctx.is_instance(o, T.InformationObject)]
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


@rule("M15.7a", covers=("x8-3-2-metadata-requirements#7",
                        "x8-3-2-metadata-requirements#8",),
       fix="Add iirds:relates-to-product-variant on the Document, relating it to the product variant it documents. In a handover the receiving plant files documents against equipment, and this is the link that makes that possible.")
def m15_7a_product_variant_instance_identity(ctx):
    """The document has to say which machine, not merely which model."""
    yield from _variant_instance_identity(ctx, T.Document, "iirds:Document")


#: Which class this builder is reading, in the words a remedy needs: the noun
#: for the subject and the rule that answers the party half of the same
#: bullet. The message was parameterised when these rules were split and one
#: remedy was not, so R13 -- whose finding is about the Package -- told the
#: reader about "the product variant this document names" and sent them to
#: M15.7b, the Document-half rule. It is the only remedy in the registry that
#: names another rule, and the one it named was the wrong half.
_HALF = {
    str(T.Package): ("package", "R14"),
    str(T.Document): ("document", "M15.7b"),
}

#: One literal per half, at module level, because that is a form
#: `tests/test_remediation.py` can read. Building the sentence with `%` put the
#: only remedy that names another rule beyond the reach of the gate that checks
#: remedies name terms which exist -- which is the state that gate was written
#: to refuse, and it refused it.
VARIANT_IDENTITY_FIX = {
    "package": "Give the product variant this package names an iirds:has-identity "
               "whose iirds:IdentityDomain declares an iirds:has-identity-type of "
               "iirds:ObjectInstanceURI, iirds:ObjectTypeURI or iirds:SerialNumber, "
               "and relate that domain to an iirds:Party with iirds:has-party-role "
               "iirds:Manufacturer carrying a vcard that names an organisation -- "
               "without the party the identity answers this and R14 takes its place. "
               "The relation from the package is already there; what is missing is "
               "which machine, as distinct from which model.",
    "document": "Give the product variant this document names an iirds:has-identity "
                "whose iirds:IdentityDomain declares an iirds:has-identity-type of "
                "iirds:ObjectInstanceURI, iirds:ObjectTypeURI or iirds:SerialNumber, "
                "and relate that domain to an iirds:Party with iirds:has-party-role "
                "iirds:Manufacturer carrying a vcard that names an organisation -- "
                "without the party the identity answers this and M15.7b takes its "
                "place. The relation from the document is already there; what is "
                "missing is which machine, as distinct from which model.",
}


def _variant_instance_identity(ctx, cls, label):
    """Section 8.3.2's "at least one iirds:relates-to-product-variant" bullet
    and the two under it, for whichever of its two lists is being read.

    The Package list and the Document list state these word for word, so they
    are one check asked twice. Written apart they would drift, which is what
    happened while only one of the two lists had rules at all.
    """
    noun, sibling = _HALF[str(cls)]
    for doc in ctx.instances_of(cls):
        variants = ctx.values(doc, T.relates_to_product_variant)
        if not variants:
            yield Violation("iiRDS/H: %s must relate to at least one "
                            "iirds:ProductVariant" % label, subject=ctx.ref(doc))
            continue
        if not any(any(_identities_of_type(ctx, v, T.INSTANCE_IDENTITY_TYPES)) for v in variants):
            # Its own remedy: the Document already relates to a variant, and
            # what is missing sits on the variant rather than on the document.
            yield Violation("iiRDS/H: the related iirds:ProductVariant must carry an identity "
                            "whose domain has an identity type of ObjectInstanceURI, "
                            "ObjectTypeURI or SerialNumber",
                            subject=ctx.ref(doc),
                            fix=VARIANT_IDENTITY_FIX[noun])


def _documented_variants(ctx, cls=None):
    """The product variants section 8.3.2 binds: the ones a subject names.

    Each of its variant requirements opens "at least one
    iirds:relates-to-product-variant relating to an iirds:ProductVariant" and
    continues "**This** iirds:ProductVariant MUST relate to ...", so the
    subject is the variant the document points at, and "at least one"
    introduces it. Read over every iirds:ProductVariant in the graph instead,
    these rules failed a package for carrying a model it documents elsewhere.
    """
    for subject in ctx.instances_of(cls or T.Document):
        variants = list(ctx.values(subject, T.relates_to_product_variant))
        if variants:
            yield subject, variants


@rule("M15.7b", covers=("x8-3-2-metadata-requirements#9",), spec=_spec_sans_quote("M15.7b"),
       fix="Relate the identity domain of one of this variant's instance identities to an iirds:Party whose iirds:has-party-role is iirds:Manufacturer, and give that party an iirds:relates-to-vcard pointing at a vcard:Organization this package describes with a vcard:organization-name. One identity is enough; the others may carry a number that names nobody. Identifier schemes are unique only within the organisation that issues them, so the domain has to say whose scheme it is.")
def m15_7b_instance_identity_manufacturer(ctx):
    """Section 8.3.2 nests this under "This iirds:ProductVariant MUST relate
    to an iirds:Identity with an iirds:IdentityDomain": the definite article
    in "The iirds:IdentityDomain MUST relate to an iirds:Party ..." points at
    the identity the line above introduced, so one qualifying identity
    satisfies it and a second serial number naming nobody does not fail the
    package. Read over every matching domain, this reported conformant
    packages -- the reading M15.10 was corrected away from, kept here until
    the same review looked at the siblings.
    """
    yield from _variant_domain_manufacturer(
        ctx, T.Document, T.INSTANCE_IDENTITY_TYPES, "iirds:Document", "instance identity")


def _variant_domain_manufacturer(ctx, cls, types, label, which):
    """The "The iirds:IdentityDomain MUST relate to an iirds:Party with
    iirds:has-party-role iirds:Manufacturer" bullet, which section 8.3.2
    states four times -- twice per list, once for each kind of identity.

    Existential, and the population is the variants the subject names. Both
    were got wrong once here: read over every domain it failed a package
    carrying a second serial number that names nobody, and read over every
    variant in the graph it failed a package for a model documented elsewhere.
    """
    for doc, variants in _documented_variants(ctx, cls):
        domains = [d for variant in variants
                   for _i, d in _identities_of_type(ctx, variant, types)]
        if domains and not any(_names_an_organisation(ctx, party)
                               for domain in domains
                               for party in _parties(ctx, domain, T.Manufacturer)):
            yield Violation("iiRDS/H: no %s of a product variant this "
                            "%s names has an identity domain relating to an "
                            "iirds:Party with role Manufacturer that names a "
                            "vcard:Organization" % (which, label),
                            subject=ctx.ref(doc), detail=ctx.label_of(doc))


@rule("M15.7c", covers=("x8-3-2-metadata-requirements#10",
                        "x8-3-2-metadata-requirements#11",),
       fix="Relate the ProductVariant to a second iirds:Identity carrying the product type, with its own IdentityDomain. A handover needs both what this machine is and which type it belongs to, because manuals are written per type.")
def m15_7c_product_type_identity(ctx):
    """The second variant bullet, on the same population as the first: one of
    the variants the document names has to carry the product type as well as
    the instance."""
    yield from _variant_product_type_identity(ctx, T.Document, "iirds:Document")


def _variant_product_type_identity(ctx, cls, label):
    """"This iirds:ProductVariant MUST relate to an iirds:Identity with an
    iirds:IdentityDomain" and "The iirds:IdentityDomain MUST have an
    iirds:has-identity-type of iirds:ProductType" -- the second pair of the
    six, stated identically in both of section 8.3.2's lists."""
    for doc, variants in _documented_variants(ctx, cls):
        if not any(any(_identities_of_type(ctx, variant, (T.ProductType,)))
                   for variant in variants):
            yield Violation("iiRDS/H: no product variant this %s names carries an "
                            "identity whose domain has an identity type of "
                            "iirds:ProductType" % label,
                            subject=ctx.ref(doc), detail=ctx.label_of(doc))


@rule("M15.7d", covers=("x8-3-2-metadata-requirements#12",), spec=_spec_sans_quote("M15.7d"),
       fix="Relate the identity domain of one of this variant's ProductType identities to an iirds:Party whose iirds:has-party-role is iirds:Manufacturer, and give that party an iirds:relates-to-vcard pointing at a vcard:Organization this package describes with a vcard:organization-name. One identity is enough. Identifier schemes are unique only within the organisation that issues them, so the domain has to say whose scheme it is.")
def m15_7d_product_type_manufacturer(ctx):
    """The same nesting as M15.7b, for the product type rather than the
    instance: one qualifying identity satisfies the bullet."""
    yield from _variant_domain_manufacturer(
        ctx, T.Document, (T.ProductType,), "iirds:Document", "ProductType identity")


# --------------------------------------------------------------------------
# Who is answerable for what
# --------------------------------------------------------------------------

@rule("M15.8",
       fix="Relate the Document to an iirds:Party whose iirds:has-party-role is iirds:Author, and give that party an iirds:relates-to-vcard pointing at a vcard:Organization this package describes with a vcard:organization-name. A role alone does not answer this: a handover document with no responsible organisation leaves the receiving plant with nobody to ask about it.")
def m15_8_document_author(ctx):
    yield from _needs_named_party(ctx, T.Document, T.Author, "iirds:Document")


@rule("M15.9", spec=_spec_sans_quote("M15.9"),
       fix="Relate the Package to an iirds:Party whose iirds:has-party-role is iirds:Creator, and give that party an iirds:relates-to-vcard pointing at a vcard:Organization this package describes with a vcard:organization-name. A role alone does not answer this. It names who delivered this consignment, as distinct from who authored any one document inside it.")
def m15_9_package_creator(ctx):
    yield from _needs_named_party(ctx, T.Package, T.Creator, "iirds:Package")


@rule("M15.10", covers=("x8-3-2-metadata-requirements#13",), spec=_spec_sans_quote("M15.10"),
      title="an information object's identity domain must name its creator",
       fix="Relate one of this information object's identity domains to an iirds:Party whose iirds:has-party-role is iirds:Creator, and give that party an iirds:relates-to-vcard pointing at a vcard:Organization this package describes with a vcard:organization-name. One domain is enough; the others may carry an internal number and name nobody. Responsibility for the underlying content can differ from responsibility for the delivered document, and a plant needs both, but section 8.3.2 hangs it on the identity domain rather than on the object, because what is attributed is the scheme the content is known by.")
def m15_10_information_object_creator(ctx):
    """"The following metadata is mandatory for each iirds:InformationObject:
    at least one iirds:has-identity relating to an iirds:Identity with an
    iirds:IdentityDomain. The iirds:IdentityDomain MUST relate to an
    iirds:Party with iirds:has-party-role iirds:Creator ..." (section 8.3.2).

    The party hangs off the domain, which is the shape M15.7b and M15.7d
    already follow for the manufacturer; the Package and Document bullets put
    a party on the subject itself, and those are M15.9 and M15.8. This rule
    read the object's own iirds:relates-to-party, which is the catalogue's
    wording and a sentence the specification does not contain: appendix A
    gives iirds:relates-to-party the domain iirds:Component,
    iirds:IdentityDomain, iirds:ClassificationDomain, iirds:InformationUnit,
    iirds:ContentLifeCycleStatus and iirds:ProductVariant, and an information
    object is none of those. It therefore reported a MUST-level error on both
    of the fixtures the catalogue marks as passing for it, and on Example 63,
    the specification's own iiRDS/H package.

    One identity satisfies it. "at least one" introduces the domain the next
    sentence speaks of, and section 6.8.1 lets an object carry further
    identities -- an internal number that names nobody -- which a reading over
    every domain would fail. The finding names the object, because which of
    its domains to mend is the author's choice, and because two objects
    sharing one unmended domain are two failures rather than one.
    """
    for obj in ctx.instances_of(T.InformationObject):
        domains = [domain for identity in ctx.values(obj, T.has_identity)
                   for domain in ctx.values(identity, T.has_identity_domain)]
        if not domains:
            # Its own remedy: there is no domain here to relate a party to, and
            # an Identity minted without an IRI or an iirds:identifier trades
            # this finding for M19.1, M19.2 and M35.
            yield Violation("iiRDS/H: iirds:InformationObject must relate to an iirds:Identity "
                            "with an iirds:IdentityDomain",
                            subject=ctx.ref(obj), detail=ctx.label_of(obj),
                            fix="Give the information object an iirds:has-identity pointing at "
                                "an iirds:Identity that has an IRI of its own and an "
                                "iirds:identifier, and give that identity an "
                                "iirds:has-identity-domain pointing at an iirds:IdentityDomain "
                                "with an IRI. Then relate that domain to an iirds:Party whose "
                                "iirds:has-party-role is iirds:Creator, carrying an "
                                "iirds:relates-to-vcard to a vcard:Organization this package "
                                "describes with a vcard:organization-name.")
        elif not any(_names_an_organisation(ctx, party)
                     for domain in domains for party in _parties(ctx, domain, T.Creator)):
            yield Violation("iiRDS/H: no iirds:IdentityDomain of this iirds:InformationObject "
                            "relates to an iirds:Party with role Creator that names a "
                            "vcard:Organization",
                            subject=ctx.ref(obj), detail=ctx.label_of(obj))


# --------------------------------------------------------------------------
# What a handover package may not contain
# --------------------------------------------------------------------------

@rule("M15.11a", covers=("x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#1",),
       fix="Retype the information unit as iirds:Document or iirds:Package, or take it out of the handover package. iiRDS/H deliberately restricts the shapes a receiving system has to understand, and that restriction is the profile's whole value.")
def m15_11a_documents_only(ctx):
    # instances_of, not typed_exactly: the profile excludes topics so that a
    # receiving system need not understand them, and section 7 says an
    # instance of a package's own subclass of iirds:Topic is a Topic. Exact
    # typing let the excluded thing in by the one route the standard
    # explicitly sanctions.
    for cls in (T.Topic, T.Fragment):
        for unit in ctx.instances_of(cls):
            yield Violation("iiRDS/H packages must contain only iirds:Document and "
                            "iirds:Package information units",
                            subject=ctx.ref(unit), detail=ctx.ref(cls).split("#")[-1])


@rule("M15.11b", covers=("x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#6",),
       fix="Remove the iirds:DirectoryNode instances. iiRDS/H carries documents, not a navigation tree; a handover package is filed by the receiving system rather than browsed as authored.")
def m15_11b_no_directory_node(ctx):
    for node in ctx.instances_of(T.DirectoryNode):
        yield Violation("iiRDS/H packages must not contain iirds:DirectoryNode instances",
                        subject=ctx.ref(node))


@rule("M15.11c", covers=("x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#4",),
       fix="Remove the iirds:Selector instances. iiRDS/H delivers whole documents, so addressing a fragment inside one has no meaning on the receiving side.")
def m15_11c_no_selector(ctx):
    for selector in ctx.instances_of(T.Selector):
        yield Violation("iiRDS/H packages must not contain iirds:Selector instances",
                        subject=ctx.ref(selector))


# --------------------------------------------------------------------------
# The same six sentences, for the other subject
#
# Section 8.3.2 states its product-variant requirements twice: once under "The
# following metadata is mandatory for each iirds:Package" and once under "for
# each iirds:Document", word for word. M15.7a to M15.7d read the second list.
# These four read the first, through the same builders, so a correction to the
# reading reaches both -- which is the whole reason the builders exist.
#
# The two lists are not redundant. A package delivers documentation about one
# machine and each document inside it may name a narrower variant; asking only
# the document's question lets a package that identifies nothing pass. The
# conformant fixture this repository has asserted clean for weeks was exactly
# that package.
# --------------------------------------------------------------------------

_PKG = "iirds:Package"


@rule("R13", kind="schema", prio="MUST", versions=("1.3",), variants=("H",),
      title="an iiRDS/H package must name a product variant with an instance identity",
      spec=_spec_sans_quote("M15.7a"),
      covers=("x8-3-2-metadata-requirements#1", "x8-3-2-metadata-requirements#2"),
      fix="Add iirds:relates-to-product-variant on the iirds:Package, relating it to the "
          "product variant this delivery is about, and give that variant an iirds:has-identity "
          "whose iirds:IdentityDomain declares an iirds:has-identity-type of "
          "iirds:ObjectInstanceURI, iirds:ObjectTypeURI or iirds:SerialNumber. The documents "
          "inside may name narrower variants; this says what the consignment as a whole is for.")
def r13_package_variant_instance_identity(ctx):
    yield from _variant_instance_identity(ctx, T.Package, _PKG)


@rule("R14", kind="schema", prio="MUST", versions=("1.3",), variants=("H",),
      title="a package's instance identity domain must name its manufacturer",
      spec=_spec_sans_quote("M15.7b"),
      covers=("x8-3-2-metadata-requirements#3",),
      fix="Relate the identity domain of the package's product variant to an iirds:Party whose "
          "iirds:has-party-role is iirds:Manufacturer, and give that party an "
          "iirds:relates-to-vcard pointing at a vcard:Organization this package describes with "
          "a vcard:organization-name. One qualifying identity is enough.")
def r14_package_instance_identity_manufacturer(ctx):
    yield from _variant_domain_manufacturer(
        ctx, T.Package, T.INSTANCE_IDENTITY_TYPES, _PKG, "instance identity")


@rule("R15", kind="schema", prio="MUST", versions=("1.3",), variants=("H",),
      title="an iiRDS/H package must name a product variant with a product type identity",
      spec=_spec_sans_quote("M15.7c"),
      covers=("x8-3-2-metadata-requirements#4", "x8-3-2-metadata-requirements#5"),
      fix="Give the product variant the package names a second iirds:has-identity whose "
          "iirds:IdentityDomain declares iirds:has-identity-type iirds:ProductType. The "
          "instance identity says which machine; this says which model, and a receiving plant "
          "needs both to file the delivery against its equipment.")
def r15_package_variant_product_type(ctx):
    yield from _variant_product_type_identity(ctx, T.Package, _PKG)


@rule("R16", kind="schema", prio="MUST", versions=("1.3",), variants=("H",),
      title="a package's product type identity domain must name its manufacturer",
      spec=_spec_sans_quote("M15.7d"),
      covers=("x8-3-2-metadata-requirements#6",),
      fix="Relate the ProductType identity domain of the package's product variant to an "
          "iirds:Party whose iirds:has-party-role is iirds:Manufacturer, with an "
          "iirds:relates-to-vcard pointing at a vcard:Organization this package describes "
          "with a vcard:organization-name.")
def r16_package_product_type_manufacturer(ctx):
    yield from _variant_domain_manufacturer(
        ctx, T.Package, (T.ProductType,), _PKG, "ProductType identity")
