"""Schema rules (M*) — conformance of the metadata graph.

Every rule here operates on an rdflib Graph, so it is blind to whether the
package wrote its metadata as RDF/XML or JSON-LD, and to which of the several
legal RDF/XML shapes it chose. Rule ids match plusmeta's catalogue so results
from the two tools can be compared directly.
"""
from __future__ import annotations

from rdflib import URIRef
from rdflib.namespace import RDF, RDFS

from .. import terms as T
from ..context import container_packages, package_nodes
from ..model import DCTERMS, PACKAGE_BASE, Violation, is_absolute_iri, is_named
from ..registry import rule


def _exactly_one(ctx, cls, prop, label):
    """`prop` must appear once on every instance of `cls`.

    Distinct from "has at least one": the specification's cardinality tables
    give 1, not 1..*, for these, and a second value is as much a defect as none
    — a consumer has no way to choose between them.
    """
    for subj in ctx.instances_of(cls):
        values = ctx.values(subj, prop)
        if len(values) != 1:
            yield Violation("%s must have exactly one %s" % (
                                str(cls).split("#")[-1], label),
                            subject=ctx.ref(subj),
                            detail="%d found" % len(values))


def _at_most_one(ctx, cls, prop, label):
    """Shared body for the many 'MUST NOT have more than one X' rules."""
    for subj in ctx.instances_of(cls):
        values = ctx.values(subj, prop)
        if len(values) > 1:
            # ctx.ref, then sorted, then sliced. Sorting alone still named the
            # four by their minted identifiers when the values were blank
            # nodes, so the same package reported a different four next run.
            listed = sorted(ctx.ref(v) for v in values)[:4]
            yield Violation("more than one %s" % label,
                            subject=ctx.ref(subj),
                            detail="%d values: %s" % (len(values),
                                                      ", ".join(v[:40] for v in listed)))


# --------------------------------------------------------------------------
# Information units
# --------------------------------------------------------------------------

@rule("M1",
       fix="Retype the instance as one of the InformationUnit subclasses: Topic, Fragment, Document or Package. The parent class says only that something informational is here, which a consumer cannot route, index or display.")
def m1_no_direct_information_unit(ctx):
    for subj in ctx.typed_exactly(T.InformationUnit):
        yield Violation("iirds:InformationUnit used directly; use one of its subclasses",
                        subject=ctx.ref(subj))


@rule("M2.1",
       fix="Give the element an rdf:about with an IRI. Anonymous information units cannot be referenced from a table of contents, from another package, or from a later revision of this one.")
def m2_1_information_unit_iri(ctx):
    for subj in ctx.information_units():
        if not is_named(subj):
            yield Violation("instance of an iirds:InformationUnit subclass must have an IRI, "
                            "not be a blank node or an empty rdf:about",
                            subject=ctx.ref(subj))


@rule("M2.3",
       fix="Keep one iirds:dateOfCreation and remove the rest. Two creation dates give a consumer no way to choose, and most will silently take whichever they read first.")
def m2_3(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.dateOfCreation, "iirds:dateOfCreation")


@rule("M2.4",
       fix="Keep one iirds:dateOfLastModification and remove the rest. Consumers use it to decide whether a redelivery is newer, so an ambiguous value defeats the comparison.")
def m2_4(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.dateOfLastModification,
                            "iirds:dateOfLastModification")


@rule("M2.5",
       fix="Keep one iirds:revision and remove the rest. It is the identifier a reader quotes when reporting a problem, and two of them make that useless.")
def m2_5(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.revision, "iirds:revision")


@rule("M2.6",
       fix="Keep one iirds:title and remove the rest. Where the same content exists in several languages, the specification models that as one information unit per language, all related to the same iirds:InformationObject (section 6.10.1).")
def m2_6(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.title, "iirds:title")


@rule("M2.7",
       fix="Keep one iirds:has-abstract and remove the rest. An abstract is what a search result shows, and there is room for one.")
def m2_7(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.has_abstract, "iirds:has-abstract")


@rule("M2.8",
       fix="Keep one iirds:is-replacement-of and remove the rest. If this unit genuinely supersedes several, model that on the units it replaces instead.")
def m2_8(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.is_replacement_of,
                            "iirds:is-replacement-of")


@rule("M2.9",
       fix="Keep one iirds:is-version-of and remove the rest. A version belongs to exactly one information object; two would make the revision history a graph nobody can walk.")
def m2_9(ctx):
    yield from _at_most_one(ctx, T.InformationUnit, T.is_version_of, "iirds:is-version-of")


# --------------------------------------------------------------------------
# Package
# --------------------------------------------------------------------------

@rule("M3",
       fix="Provide exactly one iirds:Package instance describing this container. It is the root a consumer starts from, so zero leaves the package unidentified and two leave it ambiguous.")
def m3_exactly_one_package(ctx):
    # One reading of "the package that represents this container", shared with
    # M8 and with version detection, so a node cannot be the container for one
    # of them and a nested child for the next.
    packages = package_nodes(ctx.graph)
    own = container_packages(ctx.graph)
    if not packages:
        yield Violation("metadata declares no iirds:Package for this container")
    elif len(own) > 1:
        yield Violation("more than one iirds:Package represents this container",
                        detail=", ".join(sorted(ctx.ref(p) for p in own)[:5]))


@rule("M4",
       fix="Add iirds:iiRDSVersion to the iirds:Package instance, with a published version such as 1.3. A consumer needs it to decide which rules apply before reading anything else.")
def m4_package_version(ctx):
    yield from _exactly_one(ctx, T.Package, T.iiRDSVersion, "iirds:iiRDSVersion")


@rule("M5",
       fix="Use an absolute IRI in rdf:about, such as a urn:uuid: or a URL under a domain you control. Relative IRIs resolve against a base that changes when the package is merged into a larger set, so identifiers silently collide. RECOMMENDED, not required.")
def m5_absolute_iris(ctx):
    for subj in ctx.iirds_subjects():
        if isinstance(subj, URIRef) and not is_absolute_iri(subj) or str(subj) == PACKAGE_BASE:
            yield Violation("relative IRI in rdf:about; absolute IRIs are recommended",
                            subject=ctx.ref(subj))


@rule("M6",
       fix="Relate the information unit to exactly one information object with iirds:is-version-of. Two would make it a version of two different things at once, and a consumer merging revisions cannot resolve that.")
def m6_one_information_object(ctx):
    for unit in ctx.information_units():
        objs = ctx.values(unit, T.is_version_of)
        if len(objs) > 1:
            yield Violation("information unit relates to more than one information object "
                            "via iirds:is-version-of",
                            subject=ctx.ref(unit), detail="%d objects" % len(objs))


@rule("M8",
       fix="Remove the iirds:has-rendition relations whose subject is the iirds:Package element for this container. A rendition is the file an information unit is delivered as, and this package is what the delivery is, not something inside it. A package nested inside another one is content and may have renditions; this one is not nested inside anything.")
def m8_package_no_rendition(ctx):
    for pkg in container_packages(ctx.graph):
        if ctx.has(pkg, T.has_rendition):
            yield Violation("the iirds:Package representing this container must not be the "
                            "subject of iirds:has-rendition",
                            subject=ctx.ref(pkg))


# --------------------------------------------------------------------------
# Renditions and selectors
# --------------------------------------------------------------------------

@rule("M9",
       fix="Make the URL relative to the container root, such as content/topic1.xhtml. An absolute path or a file: URL points outside the package, where a consumer has nothing.")
def m9_relative_source(ctx):
    for rend in ctx.instances_of(T.Rendition):
        for src in ctx.values(rend, T.source):
            value = str(src)
            if "://" in value or value.startswith("/"):
                yield Violation("iirds:source must be relative to the package root",
                                subject=ctx.ref(rend), detail=value)


@rule("M10",
       fix="Add iirds:source to the Rendition, naming the file inside the container it renders. A Rendition without one describes a form of the content that the package does not carry.")
def m10_rendition_source(ctx):
    yield from _exactly_one(ctx, T.Rendition, T.source, "iirds:source")


@rule("M11",
       fix="Give the Rendition exactly one iirds:format, holding the media type of the file it points at, for example application/xhtml+xml or application/pdf. Add one if there is none; remove the extras if there are several.")
def m11_rendition_format(ctx):
    yield from _exactly_one(ctx, T.Rendition, T.fmt, "iirds:format")


@rule("M12",
       fix="Use one of the Selector subclasses instead: FragmentSelector, RangeSelector or one of the others. The base class does not say how to address the part, so a consumer cannot resolve it.")
def m12_no_direct_selector(ctx):
    for subj in ctx.typed_exactly(T.Selector):
        yield Violation("iirds:Selector used directly; use one of its subclasses",
                        subject=ctx.ref(subj))


def _value_selectors(ctx):
    """Selectors that address content by a value.

    A RangeSelector does not: it delegates to iirds:has-start-selector and
    iirds:has-end-selector, which is what M14.1 and M14.2 check. Asking it for
    an rdf:value reports every correctly-built range in a package.
    """
    ranges = set(ctx.instances_of(T.RangeSelector))
    return [s for s in ctx.instances_of(T.Selector) if s not in ranges]


@rule("M13.1",
       fix="Add rdf:value to the Selector, holding the expression that picks out the part, and dcterms:conformsTo naming the scheme it is written in. Without the value there is nothing to evaluate.")
def m13_1_selector_value(ctx):
    for sel in _value_selectors(ctx):
        if len(ctx.values(sel, RDF.value)) != 1:
            yield Violation("a selector that addresses content by value must have exactly "
                            "one rdf:value", subject=ctx.ref(sel))


@rule("M13.2",
       fix="Add dcterms:conformsTo to the Selector, naming the scheme its rdf:value is written in, such as an XPath or media fragment specification. Without it a consumer cannot tell how to interpret the expression.")
def m13_2_selector_conforms_to(ctx):
    for sel in _value_selectors(ctx):
        if len(ctx.values(sel, DCTERMS.conformsTo)) != 1:
            yield Violation("a selector that addresses content by value must have exactly "
                            "one dcterms:conformsTo", subject=ctx.ref(sel))


@rule("M14.1",
       fix="Add iirds:has-start-selector to the RangeSelector. A range is defined by its two endpoints, so one missing leaves it unresolvable.")
def m14_1_range_start(ctx):
    yield from _exactly_one(ctx, T.RangeSelector, T.has_start_selector, "iirds:has-start-selector")


@rule("M14.2",
       fix="Add iirds:has-end-selector to the RangeSelector. A range with only a start selects from there to nowhere in particular.")
def m14_2_range_end(ctx):
    yield from _exactly_one(ctx, T.RangeSelector, T.has_end_selector, "iirds:has-end-selector")


# --------------------------------------------------------------------------
# Documents, events, identities, parties
# --------------------------------------------------------------------------

@rule("M15.1",
       fix="Relate the Document to one of the standardised iiRDS document types. It is what a consumer uses to route a document — installation, maintenance, spare parts — before anyone opens it.")
def m15_1_document_type(ctx):
    for doc in ctx.instances_of(T.Document):
        if not (ctx.has(doc, T.has_document_type)
                or ctx.has(doc, T.is_applicable_for_document_type)):
            yield Violation("iirds:Document must relate to a standardised iirds:DocumentType",
                            subject=ctx.ref(doc))


@rule("M16.1",
       fix="Add iirds:has-event-code to the Event, holding the code as the machine emits it. It is the string a technician reads off the panel, and it is what makes an event findable.")
def m16_1_event_code(ctx):
    yield from _exactly_one(ctx, T.Event, T.has_event_code, "iirds:has-event-code")


@rule("M16.2",
       fix="Relate the Event to an event type with iirds:has-event-type. The code identifies the specific event; the type says what kind of thing it is, and a consumer needs both.")
def m16_2_event_type(ctx):
    yield from _exactly_one(ctx, T.Event, T.has_event_type, "iirds:has-event-type")


@rule("M19.1",
       fix="Give the Identity exactly one iirds:has-identity-domain. The domain says which scheme the identifier belongs to, and an identifier without a scheme is a string that may collide with anything.")
def m19_1_identity_identifier(ctx):
    """The catalogue's wording for M19.1 is about the domain, but the reference
    tool checks the identifier here and checks the domain under M19.3. Both
    checks exist either way; adopting their assignment is what keeps a
    rule-by-rule comparison meaningful. The wording is recorded in
    docs/divergences.md.
    """
    for ident in ctx.instances_of(T.Identity):
        values = ctx.values(ident, T.identifier)
        if len(values) != 1:
            yield Violation("iirds:Identity must have exactly one iirds:identifier",
                            subject=ctx.ref(ident), detail="%d found" % len(values))


@rule("M19.3",
       fix="Relate the Identity to exactly one domain with iirds:has-identity-domain, removing the extras. Two domains would make one value mean two different things at once.")
def m19_3_identity_domain(ctx):
    for ident in ctx.instances_of(T.Identity):
        domains = ctx.values(ident, T.has_identity_domain)
        if len(domains) != 1:
            yield Violation("iirds:Identity must point to exactly one iirds:IdentityDomain",
                            subject=ctx.ref(ident), detail="%d domains" % len(domains))


@rule("M19.2",
       fix="Add iirds:identifier to the Identity, holding the value itself. The domain says what kind of identifier it is; this is the identifier.")
def m19_2_identity_value(ctx):
    for ident in ctx.instances_of(T.Identity):
        values = [v for v in ctx.values(ident, T.identifier) if str(v).strip()]
        if not values:
            yield Violation("iirds:Identity must carry a non-empty iirds:identifier",
                            subject=ctx.ref(ident))


@rule("M21.2",
       fix="Keep one iirds:dateOfEffect and remove the rest. It is the date a consumer uses to decide whether this status applies today.")
def m21_2(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.dateOfEffect,
                            "iirds:dateOfEffect")


@rule("M21.3",
       fix="Keep one iirds:dateOfExpiry and remove the rest. Two expiry dates give no answer to the only question the property is asked.")
def m21_3(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.dateOfExpiry,
                            "iirds:dateOfExpiry")


@rule("M21.4",
       fix="Keep one iirds:dateOfStatus and remove the rest. It records when the status was set, which is what distinguishes a current status from a stale one.")
def m21_4(ctx):
    """The wording says iirds:purpose; the reference tool checks dateOfStatus
    here and purpose under M21.5. Following the wording for both would leave
    dateOfStatus unchecked by anything, which is the worse outcome."""
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.dateOfStatus, "iirds:dateOfStatus")


@rule("M21.5",
       fix="Keep one iirds:purpose and remove the rest. It says why the status exists, and a consumer displays it as a single line.")
def m21_5(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.purpose, "iirds:purpose")


@rule("M21.6",
       fix="Keep one iirds:relates-to-party and remove the rest. It names who set the status; several would leave responsibility unassigned rather than shared.")
def m21_6(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.relates_to_party,
                            "iirds:relates-to-party")


@rule("M22.1",
       fix="Add iirds:has-party-role to the Party, relating it to a PartyRole such as iirds:Author or iirds:Manufacturer. A party with no role tells a consumer that an organisation is involved and not how.")
def m22_1_party_role(ctx):
    yield from _exactly_one(ctx, T.Party, T.has_party_role, "iirds:has-party-role")


# --------------------------------------------------------------------------
# Directory structure (table of contents)
# --------------------------------------------------------------------------

@rule("M24.1",
       fix="Keep one iirds:has-next-sibling and remove the rest. A node has one successor in its level; two would make the table of contents a graph rather than a list.")
def m24_1(ctx):
    yield from _at_most_one(ctx, T.DirectoryNode, T.has_next_sibling,
                            "iirds:has-next-sibling")


@rule("M24.2",
       fix="Keep one iirds:has-directory-structure-type and remove the rest. It says what kind of structure this is, and one node cannot be the root of two kinds at once.")
def m24_2(ctx):
    yield from _at_most_one(ctx, T.DirectoryNode, T.has_directory_structure_type,
                            "iirds:has-directory-structure-type")


@rule("M24.3",
       fix="Keep one iirds:has-first-child and remove the rest. A level begins at one node, and the rest of it is reached by following siblings from there.")
def m24_3(ctx):
    yield from _at_most_one(ctx, T.DirectoryNode, T.has_first_child,
                            "iirds:has-first-child")


@rule("M24.4",
       fix="Keep one iirds:relates-to-information-unit and remove the rest. A directory node stands for one entry in the table of contents.")
def m24_4(ctx):
    yield from _at_most_one(ctx, T.DirectoryNode, T.relates_to_information_unit,
                            "iirds:relates-to-information-unit")


@rule("M24.6",
       fix="Give the package at least one root node carrying iirds:has-directory-structure-type together with its first child. Without a root there is no entry point, and the whole structure is unreachable.")
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


def _linked_nodes(ctx):
    """Directory nodes that sit inside a list: children and siblings.

    A root node is referenced by nothing, which is what distinguishes it — the
    rules about list membership must not fire on it.
    """
    linked = set()
    for prop in (T.has_first_child, T.has_next_sibling):
        linked.update(o for _s, o in ctx.graph.subject_objects(prop))
    return linked


@rule("M24.5",
       fix="Add iirds:has-directory-structure-type to the root node. It is what tells a consumer whether this structure is a table of contents, a parts list, or something else, and only the root carries it.")
def m24_5_only_root_has_structure_type(ctx):
    """The structure type names the whole structure, so only its root carries
    it. A node reachable from another node is not a root."""
    linked = _linked_nodes(ctx)
    for node in ctx.instances_of(T.DirectoryNode):
        if node in linked and ctx.has(node, T.has_directory_structure_type):
            yield Violation("only the root node of a directory structure may have "
                            "iirds:has-directory-structure-type",
                            subject=ctx.ref(node), detail=ctx.label_of(node))


def _closes_a_level(ctx):
    """What may sit at the end of a chain.

    The MUST reads "relating to an instance of the class iirds:nil", and
    iirds:nil is declared a class, so a package that mints its own terminator
    and types it iirds:nil is doing what the sentence says. The sample
    packages instead point straight at the class IRI, which is what everyone
    ships. Both end a level, and so does the terminator itself: a package is
    allowed to declare what it points at, and declaring iirds:nil an
    iirds:DirectoryNode used to make this rule demand an end for the end.
    """
    return {T.nil} | set(ctx.instances_of(T.nil))


@rule("M25",
       fix="Add iirds:has-next-sibling pointing at iirds:nil on the last node of the level, or at the next iirds:DirectoryNode if the level continues. Without the terminator a consumer cannot distinguish the end of a list from data that was truncated in transit.")
def m25_lists_are_closed(ctx):
    """Every level is a closed list: the last node points at iirds:nil.

    Without the terminator a consumer cannot tell the end of a list from
    truncated data -- and a sibling link that lands on neither a node nor the
    terminator leaves exactly that ambiguity while satisfying a check that
    asks only whether the property is present.
    """
    closers = _closes_a_level(ctx)
    nodes = set(ctx.instances_of(T.DirectoryNode))
    for node in sorted((_linked_nodes(ctx) & nodes) - closers, key=ctx.ref):
        siblings = sorted(ctx.values(node, T.has_next_sibling), key=ctx.ref)
        if not siblings:
            yield Violation("the last node in a list level must have iirds:has-next-sibling "
                            "relating to iirds:nil",
                            subject=ctx.ref(node), detail=ctx.label_of(node))
        elif not any(s in closers or s in nodes for s in siblings):
            yield Violation("iirds:has-next-sibling leaves this level open: it relates neither "
                            "to another iirds:DirectoryNode nor to iirds:nil",
                            subject=ctx.ref(node), detail=ctx.ref(siblings[0]))


@rule("M26",
       fix="Point iirds:has-first-child at an iirds:DirectoryNode. A lower level starts with a node like any other, and pointing at something else breaks the walk.")
def m26_first_child_is_a_directory_node(ctx):
    nodes = set(ctx.instances_of(T.DirectoryNode))
    for parent, child in ctx.graph.subject_objects(T.has_first_child):
        if child == T.nil or child in nodes:
            continue
        yield Violation("iirds:has-first-child must reference an iirds:DirectoryNode",
                        subject=ctx.ref(parent), detail=ctx.ref(child))


@rule("M27",
       fix="Make the first child of the lower level the head of its own sibling chain. Each level is a linked list, and the child link enters it at the first item.")
def m27_first_child_starts_a_new_list(ctx):
    """The node on the next level down heads its own chain. If something else
    already points at it as a sibling, the same nodes are reachable twice and
    the tree is ill-defined."""
    siblings = {o for _s, o in ctx.graph.subject_objects(T.has_next_sibling)}
    for parent, child in ctx.graph.subject_objects(T.has_first_child):
        if child in siblings:
            yield Violation("iirds:has-first-child must reference the first item of a list, "
                            "but this node is also a iirds:has-next-sibling of another",
                            subject=ctx.ref(parent), detail=ctx.ref(child))





# --------------------------------------------------------------------------
# Extensions: what a package may add to the standard vocabulary
# --------------------------------------------------------------------------

@rule("M16.3",
       fix="Declare the extension as a class with rdfs:subClassOf pointing at iirds:Event. Adding an instance of an undeclared type gives a consumer nothing to fall back on.")
def m16_3_event_extension_is_a_class(ctx):
    """A proprietary event type has to be declared, not merely referenced.

    Section 7 lets a package add its own subclasses. A subclass that is never
    declared as a class is a dangling name: a consumer sees the relationship
    and has nothing to resolve it to.
    """
    for subject in ctx.graph.subjects(RDFS.subClassOf, T.Event):
        if ctx.ontology.is_iirds_term(subject):
            continue
        if RDFS.Class not in ctx.values(subject, T.RDF_TYPE):
            yield Violation("an extension of iirds:Event must be defined as a class",
                            subject=ctx.ref(subject),
                            detail="add rdf:type rdfs:Class")


def _referenced_but_not_typed(ctx, prop, cls):
    typed = set(ctx.instances_of(cls))
    seen = set()
    for _subject, obj in ctx.graph.subject_objects(prop):
        if obj in typed or obj in seen:
            continue
        seen.add(obj)
        yield obj


def _relies_solely_on_an_external_vocabulary(ctx, prop, cls):
    """The package points outward and declares nothing of its own.

    Deliberately narrower than "every referenced IRI must be declared". The
    specification says the package "MUST also contain metadata labels as
    instances of iirds:Component" — labels, not a label per reference — and
    tekom's own sample package for external product ontologies references more
    components than it declares. Reading the rule strictly would fail the
    standard's own example, which is a strong signal that the strict reading is
    not the intended one. Individual unresolvable references are still
    reported, as L1 and L8, where they belong.
    """
    referenced = {o for _s, o in ctx.graph.subject_objects(prop)}
    if not referenced:
        return False
    return not ctx.instances_of(cls)


@rule("M17",
       fix="Relate your product entities to iirds:ProductVariant rather than typing them with an external product ontology alone. iiRDS consumers know the iiRDS classes; the external vocabulary can stay alongside as an equivalence.")
def m17_external_product_ontology_is_mapped(ctx):
    """Referencing an external product ontology is allowed; relying on it is not."""
    if _relies_solely_on_an_external_vocabulary(ctx, T.relates_to_component, T.Component):
        yield Violation("the package relates to components but declares no iirds:Component "
                        "of its own, so a consumer without the external ontology has nothing "
                        "to resolve them against",
                        subject="iirds:relates-to-component")


@rule("M18",
       fix="Add proprietary product classes as subclasses of iirds:ProductVariant. That way a consumer with no knowledge of your vocabulary still recognises the instances as product variants.")
def m18_product_variants_are_declared(ctx):
    """Product variants are a proprietary extension, so they travel in the package."""
    if _relies_solely_on_an_external_vocabulary(ctx, T.relates_to_product_variant,
                                                T.ProductVariant):
        yield Violation("the package relates to product variants but declares no "
                        "iirds:ProductVariant of its own",
                        subject="iirds:relates-to-product-variant")


@rule("M30",
       fix="Remove the statement. It restates a relationship the iiRDS ontology already defines, which bloats every package and lets a stale copy contradict the real one. Linking your own class to an iiRDS class is a different thing and is allowed.")
def m30_no_schema_in_metadata(ctx):
    """metadata.rdf carries a package's metadata, not a copy of the standard.

    Declaring proprietary subclasses of iiRDS classes is fine and expected —
    what is forbidden is restating the iiRDS schema itself, which bloats every
    package and lets a stale copy contradict the real one.

    Which turns on what the statement *says*, not on whose term is the subject.
    `iirds:Component rdfs:subClassOf iirds:InformationObject` is a copy of the
    ontology. `iirds:Component rdfs:subClassOf myCompany:ProductPart` is not: it
    is the standard's own way of declaring a proprietary class equivalent to an
    iiRDS one, since RDFS has no owl:equivalentClass and mutual subclassing is
    how equivalence is written.

    This rule used to fire on the subject alone, and so reported the
    specification's Example 43 — titled "Adding a proprietary class as an
    equivalent class" — as a violation. It also contradicted L5, which asks for
    exactly that link. Found by running the standard's own examples through
    this validator; see tests/test_spec_examples.py.
    """
    schema_predicates = (RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range)
    for subject in sorted(ctx.iirds_subjects() | {s for s in ctx.graph.subjects()
                                                  if ctx.ontology.is_iirds_term(s)}, key=str):
        if not ctx.ontology.is_iirds_term(subject):
            continue
        types = ctx.values(subject, T.RDF_TYPE)
        if RDFS.Class in types or RDF.Property in types:
            yield Violation("metadata.rdf must not redeclare the iiRDS schema",
                            subject=ctx.ref(subject), detail="declared as a class or property here")
            continue
        for predicate in schema_predicates:
            for obj in ctx.values(subject, predicate):
                # Only when both ends are the standard's. One end proprietary is
                # an extension, which iiRDS sanctions and L5 recommends.
                if not ctx.ontology.is_iirds_term(obj):
                    continue
                yield Violation("metadata.rdf must not redeclare the iiRDS schema",
                                subject=ctx.ref(subject),
                                detail="states %s %s" % (str(predicate).split("#")[-1],
                                                         str(obj).split("#")[-1]))
                break


@rule("M94",
      title="iirds:relates-to-administrative-metadata must not be used directly",
       fix="Use one of the subclasses of the administrative metadata relation instead. The general form says only that some administrative relation exists, which a consumer cannot act on.")
def m94_administrative_metadata_relation_not_direct(ctx):
    """The generic relation is a grouping, like the classes M78 to M93 cover."""
    for subject, _obj in ctx.graph.subject_objects(T.relates_to_administrative_metadata):
        yield Violation("iirds:relates-to-administrative-metadata is not intended to be used "
                        "directly; use one of its subproperties",
                        subject=ctx.ref(subject))


# --------------------------------------------------------------------------
# Identities and classifications
# --------------------------------------------------------------------------

@rule("M19.4",
       fix="Type the target of iirds:has-identity-domain as iirds:IdentityDomain. Pointing at something else leaves a consumer unable to tell which scheme the identifier is in.")
def m19_4_identity_domain_is_typed(ctx):
    # The whole closure, not the package's own half: everything beneath
    # iirds:IdentityDomain is an identity domain, and this rule asks what a
    # node *is* rather than demanding something of a population -- the
    # direction where a wider reading can only make it quieter. Asking for the
    # parent type verbatim reported a package for doing what section 7
    # sanctions and L5 recommends.
    domains = set(ctx.instances_of(T.IdentityDomain))
    for identity, domain in ctx.graph.subject_objects(T.has_identity_domain):
        if (domain, None, None) not in ctx.graph:
            continue          # not described here at all; L1 reports the dangling reference
        if domain not in domains:
            yield Violation("the object of iirds:has-identity-domain must be an instance of "
                            "iirds:IdentityDomain",
                            subject=ctx.ref(identity), detail=ctx.ref(domain))





@rule("M21.1",
       fix="Relate the ContentLifeCycleStatus to an iirds:ContentLifeCycleStatusValue with iirds:has-content-lifecycle-status-value. Without it the status object records dates for a status nobody named.")
def m21_1_lifecycle_status_value(ctx):
    yield from _exactly_one(ctx, T.ContentLifeCycleStatus, T.has_content_lifecycle_status_value, "iirds:has-content-lifecycle-status-value")


@rule("M22.2",
       fix="Point iirds:has-party-role at an instance of iirds:PartyRole or one of its subclasses. Pointing at anything else — a vCard, a plain resource — leaves the role unstated even though the property is present.")
def m22_2_role_is_a_party_role(ctx):
    """M22.1 asks whether the party has a role; this asks whether the thing it
    points at is one. They were the same function here, which double-reported
    one defect and left the actual check missing."""
    for party, role in ctx.graph.subject_objects(T.has_party_role):
        if ctx.is_instance(role, T.PartyRole) or role in ctx.ontology.defined_terms():
            continue
        if (role, None, None) not in ctx.graph:
            continue          # undescribed reference: L1's business
        yield Violation("iirds:has-party-role must point to an iirds:PartyRole",
                        subject=ctx.ref(party), detail=ctx.ref(role))


@rule("M23",
       fix="Add iirds:relates-to-vcard on the Party, pointing at a vCard that describes it. The role says what the party does; the vCard says who it is, which is what a reader needs to make contact.")
def m23_party_has_a_vcard(ctx):
    """A role without a description is not something anyone can act on."""
    yield from _exactly_one(ctx, T.Party, T.relates_to_vcard, "iirds:relates-to-vcard")


@rule("M95",
       fix="Keep one iirds:relates-to-party on the Component and remove the rest. If several organisations are genuinely involved, model each on its own relation type rather than repeating this one.")
def m95_component_party(ctx):
    yield from _at_most_one(ctx, T.Component, T.relates_to_party, "iirds:relates-to-party")


@rule("M96.1", versions=("1.2", "1.3"),  # external classification arrives in 1.2
       fix="Give the external classification exactly one iirds:has-classification-domain. The domain names the scheme — eCl@ss, ETIM, or your own — and a classification identifier means nothing without it.")
def m96_1_classification_domain(ctx):
    for classification in ctx.instances_of(T.ExternalClassification):
        domains = ctx.values(classification, T.has_classification_domain)
        if len(domains) != 1:
            yield Violation("iirds:ExternalClassification must point to exactly one "
                            "classification domain",
                            subject=ctx.ref(classification), detail="%d found" % len(domains))


@rule("M96.2", versions=("1.2", "1.3"),  # external classification arrives in 1.2
       fix="Give the external classification exactly one iirds:classificationIdentifier. Two identifiers in one classification leave a consumer unable to tell which one is meant.")
def m96_2_classification_identifier_count(ctx):
    for classification in ctx.instances_of(T.ExternalClassification):
        identifiers = ctx.values(classification, T.classificationIdentifier)
        if len(identifiers) != 1:
            yield Violation("iirds:ExternalClassification must have exactly one "
                            "iirds:classificationIdentifier",
                            subject=ctx.ref(classification), detail="%d found" % len(identifiers))


@rule("M96.3", versions=("1.2", "1.3"),  # external classification arrives in 1.2
       fix="Put a non-empty string in iirds:classificationIdentifier. An empty value is worse than an absent one: it looks answered and matches nothing.")
def m96_3_classification_identifier_non_empty(ctx):
    for classification in ctx.instances_of(T.ExternalClassification):
        for value in ctx.values(classification, T.classificationIdentifier):
            if not str(value).strip():
                yield Violation("iirds:classificationIdentifier must be a non-empty string",
                                subject=ctx.ref(classification))


@rule("M96.4",
       fix="Relate the instance to a classification with iirds:has-external-classification, or remove the empty classification. A ProductVariant, ProductFeature, Component or InformationUnit is classified or it is not.")
def m96_4_external_classification_is_optional(ctx):
    """A MAY, so there is nothing to violate.

    Registered rather than skipped so that `iirds rules` lists the whole
    catalogue and coverage counts what is genuinely covered — the permission
    is honoured by M96.1 to M96.3 checking the shape when it is used, and by
    nothing complaining when it is not.
    """
    return ()


# --------------------------------------------------------------------------
# Aliases
# --------------------------------------------------------------------------
#
# The catalogue carries three rules whose wording is character-for-character
# identical to a rule already above. They are not mistakes to be collapsed: the
# reference tool reports both identifiers, and this project's claim that its
# results can be diffed against that tool rule by rule only holds if both
# appear. Registering the same function twice is the honest way to say "these
# are the same check", and costs nothing — `rule()` returns the function
# unchanged, so the decorators stack.

#: The reference tool gives M35 the same assertion as M19.1 and M36 the same
#: as M19.3. Registering the same function twice says so exactly.
rule("M35", fix="Add iirds:identifier to the Identity, holding the value. An identity with a "
                 "domain and no value names a scheme without saying which member of it."
     )(m19_1_identity_identifier)
rule("M36", fix="Relate the Identity to an iirds:IdentityDomain. Serial numbers and asset "
                 "URIs are only unique within a scheme, so the value alone is ambiguous."
     )(m19_3_identity_domain)


