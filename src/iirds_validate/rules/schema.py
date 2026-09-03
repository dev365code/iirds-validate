"""Schema rules (M*) — conformance of the metadata graph.

Every rule here operates on an rdflib Graph, so it is blind to whether the
package wrote its metadata as RDF/XML or JSON-LD, and to which of the several
legal RDF/XML shapes it chose. Rule ids match plusmeta's catalogue so results
from the two tools can be compared directly.
"""
from __future__ import annotations

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS

from .. import terms as T
from ..context import container_packages, package_nodes
from ..model import DCTERMS, PACKAGE_BASE, Violation, is_absolute_iri, is_named
from ..registry import CATALOG, rule


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

@rule("M1", covers=("x6-2-information-units#1", "x6-2-information-units#2"),
       fix="Retype the instance as one of the InformationUnit subclasses: Topic, Fragment, Document or Package. The parent class says only that something informational is here, which a consumer cannot route, index or display.")
def m1_no_direct_information_unit(ctx):
    for subj in ctx.typed_exactly(T.InformationUnit):
        yield Violation("iirds:InformationUnit used directly; use one of its subclasses",
                        subject=ctx.ref(subj))


@rule("M2.1", covers=("x6-2-information-units#3", "x6-2-information-units#4"),
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

@rule("M3", covers=("x6-2-information-units#5",),
       fix="Provide exactly one iirds:Package instance describing this container. It is the root a consumer starts from, so zero leaves the package unidentified and two leave it ambiguous.")
def m3_exactly_one_package(ctx):
    if not ctx.sources:
        return      # S2 says no metadata was usable; "declares no Package" on top is the same absence twice
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


@rule("M6", covers=("x6-2-2-information-objects#2",),
       fix="Relate the information unit to exactly one information object with iirds:is-version-of. Two would make it a version of two different things at once, and a consumer merging revisions cannot resolve that.")
def m6_one_information_object(ctx):
    """"MUST only be related to exactly one" is read as "to at most one".

    Section 6.2.2: "If information objects are used, each information unit
    MUST only be related to exactly one information object via
    iirds:is-version-of." Read as "must have one", it would require every
    information unit in a package that uses information objects to be a
    version of one -- including the `iirds:Package` itself, which is an
    information unit and is a version of nothing. The weight of the sentence
    is on *only*: a unit that is a version of two things is what a consumer
    merging revisions cannot resolve, and that is what this reports.

    Recorded because the reading decides what the claim on this obligation
    covers, and an unwritten reading is a claim nobody can check.
    """
    for unit in ctx.information_units():
        objs = ctx.values(unit, T.is_version_of)
        if len(objs) > 1:
            yield Violation("information unit relates to more than one information object "
                            "via iirds:is-version-of",
                            subject=ctx.ref(unit), detail="%d objects" % len(objs))


@rule("M8", covers=("x6-3-content-references-of-information-units#2",),
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

@rule("M9", covers=("x6-3-content-references-of-information-units#4",),
       fix="Make the URL relative to the container root, such as content/topic1.xhtml. An absolute path or a file: URL points outside the package, where a consumer has nothing.")
def m9_relative_source(ctx):
    for rend in ctx.instances_of(T.Rendition):
        for src in ctx.values(rend, T.source):
            value = str(src)
            if "://" in value or value.startswith("/"):
                yield Violation("iirds:source must be relative to the package root",
                                subject=ctx.ref(rend), detail=value)


@rule("M10", covers=("x6-3-content-references-of-information-units#3",),
       fix="Add iirds:source to the Rendition, naming the file inside the container it renders. A Rendition without one describes a form of the content that the package does not carry.")
def m10_rendition_source(ctx):
    yield from _exactly_one(ctx, T.Rendition, T.source, "iirds:source")


@rule("M11", covers=("x6-3-content-references-of-information-units#5",),
       fix="Give the Rendition exactly one iirds:format, holding the media type of the file it points at, for example application/xhtml+xml or application/pdf. Add one if there is none; remove the extras if there are several.")
def m11_rendition_format(ctx):
    yield from _exactly_one(ctx, T.Rendition, T.fmt, "iirds:format")


@rule("M12", covers=("x6-3-1-reference-part-of-file-by-selector#1", "x6-3-1-reference-part-of-file-by-selector#2"),
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


@rule("M13.1", covers=("x6-3-1-reference-part-of-file-by-selector#3",),
       fix="Add rdf:value to the Selector, holding the expression that picks out the part, and dcterms:conformsTo naming the scheme it is written in. Without the value there is nothing to evaluate.")
def m13_1_selector_value(ctx):
    for sel in _value_selectors(ctx):
        if len(ctx.values(sel, RDF.value)) != 1:
            yield Violation("a selector that addresses content by value must have exactly "
                            "one rdf:value", subject=ctx.ref(sel))


@rule("M13.2", covers=("x6-3-1-reference-part-of-file-by-selector#3",),
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


@rule("M19.3", covers=("x6-8-1-complex-identity#3",),
       fix="Relate the Identity to exactly one domain with iirds:has-identity-domain, removing the extras. Two domains would make one value mean two different things at once.")
def m19_3_identity_domain(ctx):
    for ident in ctx.instances_of(T.Identity):
        domains = ctx.values(ident, T.has_identity_domain)
        if len(domains) != 1:
            yield Violation("iirds:Identity must point to exactly one iirds:IdentityDomain",
                            subject=ctx.ref(ident), detail="%d domains" % len(domains))


@rule("M19.2", covers=("x6-8-1-complex-identity#2",),
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


@rule("M22.1", covers=("x6-8-3-parties-and-roles#2",),
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


@rule("M24.5", covers=("x6-9-1-directory-nodes#5",),
       fix="Remove iirds:has-directory-structure-type from the node named here. The property names a whole structure and marks where it begins, so a node another node points at cannot carry it: a consumer walking the structure would find two beginnings and no way to choose. If the node was meant to begin a structure of its own, keep the property and detach it instead -- but detaching means repairing the chain it leaves, because the node that pointed at it now points at nothing.")
def m24_5_only_root_has_structure_type(ctx):
    """The structure type names the whole structure, so only its root carries
    it. A node reachable from another node is not a root.

    The catalogue titles this rule with the neighbouring sentence -- what a
    root MUST have -- and this checks what a non-root MUST NOT. The remedy
    follows the check, because it is printed under the finding: it used to
    follow the title and told the reader to add the property to the root,
    which leaves the reported node exactly as it was. docs/divergences.md
    carries the row -- and the note that the title's own sentence is checked
    by nobody: M24.6 asks whether *a* root carries the property, while
    section 6.9.1 binds every root.
    """
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


@rule("M25",   # not x6-9-1-directory-nodes#3: see the docstring, and docs/divergences.md
       fix="Add iirds:has-next-sibling pointing at iirds:nil on the last node of the level, or at the next iirds:DirectoryNode if the level continues. Without the terminator a consumer cannot distinguish the end of a list from data that was truncated in transit.")
def m25_lists_are_closed(ctx):
    """Every level is a closed list: the last node points at iirds:nil.

    Without the terminator a consumer cannot tell the end of a list from
    truncated data -- and a sibling link that lands on neither a node nor the
    terminator leaves exactly that ambiguity while satisfying a check that
    asks only whether the property is present.

    Roots are exempt, so this does not cover section 6.9.1's sentence and does
    not claim it. The specification's own Example 48 says a root closes its
    one-element level at `iirds:nil`, and its Example 47 finds the root by that
    very property -- but tekom's `iirds-sample-1` has twenty-seven nodes, one
    root, and no `iirds:has-next-sibling` on it at all, in every one of the
    fifty-one fixtures built from it. Reaching the root would fail the
    Consortium's own package, so the exemption stays and the citation goes.
    `docs/divergences.md` said so before the mapping pass added the claim over
    it; the claim, not the paragraph, was the thing that was wrong.
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


@rule("M26", covers=("x6-9-2-hierarchical-navigation#1",),
       fix="Point iirds:has-first-child at an iirds:DirectoryNode. A lower level starts with a node like any other, and pointing at something else breaks the walk.")
def m26_first_child_is_a_directory_node(ctx):
    nodes = set(ctx.instances_of(T.DirectoryNode))
    for parent, child in ctx.graph.subject_objects(T.has_first_child):
        if child == T.nil or child in nodes:
            continue
        yield Violation("iirds:has-first-child must reference an iirds:DirectoryNode",
                        subject=ctx.ref(parent), detail=ctx.ref(child))


@rule("M27", covers=("x6-9-2-hierarchical-navigation#2",),
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


@rule("M17",   # not x6-7-2-external-product-ontology#6: see the docstring
       fix="Relate your product entities to iirds:ProductVariant rather than typing them with an external product ontology alone. iiRDS consumers know the iiRDS classes; the external vocabulary can stay alongside as an equivalence.")
def m17_external_product_ontology_is_mapped(ctx):
    """Referencing an external product ontology is allowed; relying on it is not.

    This does not cover section 6.7.2's sentence, and claiming it was an
    overclaim now withdrawn. The obligation is conditioned on "an external
    product ontology is available and used in the iiRDS package"; the trigger
    here is `iirds:relates-to-component`, an iiRDS-internal relation. A package
    shaped like the standard's own Example 26 -- foreign `rdfs:Class` product
    entities, referenced by the package's own property, no `iirds:Component`
    anywhere and no `iirds:relates-to-component` either -- violates the
    sentence and is reported by nothing here.

    Recognising "a vocabulary that is a product ontology" is not something a
    rule can do without being told which vocabularies those are, so the gap is
    recorded rather than papered over.
    """
    if _relies_solely_on_an_external_vocabulary(ctx, T.relates_to_component, T.Component):
        yield Violation("the package relates to components but declares no iirds:Component "
                        "of its own, so a consumer without the external ontology has nothing "
                        "to resolve them against",
                        subject="iirds:relates-to-component")


@rule("M18",   # x6-7-4-product-variants#1 belongs to R11, not here
       fix="Add proprietary product classes as subclasses of iirds:ProductVariant. That way a consumer with no knowledge of your vocabulary still recognises the instances as product variants.")
def m18_product_variants_are_declared(ctx):
    """Product variants are a proprietary extension, so they travel in the package.

    Section 6.7.4 says they "MUST be present in the metadata.rdf of the iiRDS
    package", and this asks something else entirely: whether the package leans
    on an outside vocabulary while declaring no `iirds:ProductVariant` of its
    own. Those coincide only by accident, so the claim on that sentence was
    withdrawn from here. R11 holds it now, together with the general sentence
    it is an instance of.
    """
    if _relies_solely_on_an_external_vocabulary(ctx, T.relates_to_product_variant,
                                                T.ProductVariant):
        yield Violation("the package relates to product variants but declares no "
                        "iirds:ProductVariant of its own",
                        subject="iirds:relates-to-product-variant")


def _where_stated(ctx, *triples) -> str:
    """The metadata file or files these statements are actually in.

    Every rule but L9 reads the merged graph, which is right -- and it means a
    finding cannot name a file unless it looks. Section 7.1 names one:
    "The file metadata.rdf MUST NOT contain the iiRDS schema", so a finding
    about it has to say which file, and saying the wrong one sends a reader to
    open a file that is clean.

    Several triples, not one, because a finding can rest on more than one and
    naming the file of only the first is the same defect in a smaller place: a
    subject declared `rdf:Property` in metadata.rdf and `rdfs:Class` in
    metadata.jsonld was reported against metadata.jsonld alone, which is the
    file section 7.1 does *not* name.

    Callers pass triples of URIRefs. A statement whose subject is a blank node
    would not be found here -- rdflib labels blank nodes per parse, so the same
    logical node has different labels in two separately parsed files -- and no
    caller has one, because M30 reaches only iiRDS terms.
    """
    names = sorted({name.rpartition("/")[2] for name, graph in ctx.per_source.items()
                    for triple in triples if triple in graph})
    return " and ".join(names) or "the package metadata"


@rule("M30", covers=("x7-1-iirds-extension-scenarios#5",),
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

    The finding names the file the statement is in, which it used to assert
    rather than look up: a schema restated only in metadata.jsonld was reported
    as "metadata.rdf must not redeclare the iiRDS schema", sending a reader to
    open a file that was clean. What is detected has not changed -- the merged
    graph decides, as everywhere else -- only what the message says it found.
    """
    schema_predicates = (RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range)
    for subject in sorted(ctx.iirds_subjects() | {s for s in ctx.graph.subjects()
                                                  if ctx.ontology.is_iirds_term(s)}, key=str):
        if not ctx.ontology.is_iirds_term(subject):
            continue
        types = ctx.values(subject, T.RDF_TYPE)
        # Both, not the first: a subject declared a property in one file and a
        # class in the other is one finding that belongs to two files.
        declared = [(subject, T.RDF_TYPE, kind) for kind in (RDFS.Class, RDF.Property)
                    if kind in types]
        if declared:
            yield Violation("%s must not redeclare the iiRDS schema"
                            % _where_stated(ctx, *declared),
                            subject=ctx.ref(subject), detail="declared as a class or property here")
            continue
        for predicate in schema_predicates:
            for obj in ctx.values(subject, predicate):
                # Only when both ends are the standard's. One end proprietary is
                # an extension, which iiRDS sanctions and L5 recommends.
                if not ctx.ontology.is_iirds_term(obj):
                    continue
                yield Violation("%s must not redeclare the iiRDS schema"
                                % _where_stated(ctx, (subject, predicate, obj)),
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





@rule("M21.1", covers=("x6-8-2-content-lifecycle-status#2",),
       fix="Relate the ContentLifeCycleStatus to an iirds:ContentLifeCycleStatusValue with iirds:has-content-lifecycle-status-value. Without it the status object records dates for a status nobody named.")
def m21_1_lifecycle_status_value(ctx):
    yield from _exactly_one(ctx, T.ContentLifeCycleStatus, T.has_content_lifecycle_status_value, "iirds:has-content-lifecycle-status-value")


def _points_at_an_instance_of(ctx, prop, cls, message):
    """"MUST have an X which is assigned by property P" -- the X half.

    Three sentences of chapter 6 have this shape and each needs two rules: one
    to count the property, one to ask what it points at. This is the second,
    written once because the third caller arrived and the first two had drifted
    apart on the exemptions.

    The exemptions, and what each is for.

    A term the *ontology* types as the class: `Context.is_instance` reads the
    package's graph and nothing else, so a package pointing
    `iirds:has-party-role` at `iirds:Author` -- the term the standard supplies
    for exactly this -- has said nothing its own graph can confirm. This used
    to be `ctx.ontology.defined_terms()`, which is every subject in the
    ontology file: 327 IRIs, classes and properties included. It let
    `iirds:has-content-lifecycle-status-value` point at `iirds:Topic` and
    `iirds:has-party-role` point at `iirds:Package`, in both encodings, with
    no finding -- a hole of exactly the shape this rule family exists to
    close, held open by the exemption meant to keep it honest. Narrowed to the
    terms the ontology declares to be instances of the class asked about. On
    every corpus here that reclassifies nothing: all 1201 referents were
    already either a genuine instance or undescribed.

    An undescribed IRI: a dangling reference, which is L1's business and not a
    typing error. Two things are not that, and both used to fall out of this
    branch because neither carries triples of its own in the package:

    a *literal*, which L1 says nothing about and which no class can have as an
    instance -- `<iirds:has-content-lifecycle-status-value>Approved</...>` was
    reported by nothing at all; and

    a term the standard itself defines. `iirds:Topic` is not a dangling
    pointer -- the ontology describes it at length -- it is the wrong term,
    which is this rule's whole subject. Sending it to L1 meant the narrowed
    exemption above changed nothing: the second exemption caught what the
    first stopped catching.
    """
    for subject, value in ctx.graph.subject_objects(prop):
        if ctx.is_instance(value, cls) or value in ctx.ontology.instances_of(cls):
            continue
        if (not isinstance(value, Literal)
                and not ctx.ontology.is_defined(value)
                and (value, None, None) not in ctx.graph):
            continue          # undescribed reference: L1's business
        yield Violation(message, subject=ctx.ref(subject), detail=ctx.ref(value))


@rule("R10", covers=("x6-8-2-content-lifecycle-status#2",), kind="schema", prio="MUST",
      versions=("1.0", "1.0.1", "1.1", "1.2", "1.3"),   # as M21.1 and M22.2, its neighbours
      title="iirds:has-content-lifecycle-status-value must point at a status value",
      spec=CATALOG.get("M21.1", {}).get("spec"),   # the same sentence M21.1 counts
      fix="Point iirds:has-content-lifecycle-status-value at an instance of "
          "iirds:ContentLifeCycleStatusValue or one of its subclasses. Pointing at anything "
          "else leaves the status unnamed even though the property is present, and a consumer "
          "sorting by lifecycle state has nothing to sort on.")
def r10_lifecycle_value_is_a_status_value(ctx):
    """The twin of M22.2, for the sentence one section earlier.

    Two sentences in chapter 6 have the same shape. 6.8.3: "An iirds:Party MUST
    have a related iirds:PartyRole that is assigned by the property
    iirds:has-party-role". 6.8.2: "An iirds:ContentLifecyleStatus MUST have an
    iirds:ContentLifecyleStatusValue which is assigned by the
    iirds:has-content-lifecycle-status-value property". Each names a class and
    a property, so each is two questions: is the property there, and does it
    point at that class.

    The party sentence got both -- M22.1 asks the first, M22.2 the second, and
    M22.2 exists because they were once one function. The lifecycle sentence
    got only M21.1, which counts the property, so a status pointing at a Topic
    passed. The asymmetry is the whole evidence: the same reading applied to
    the same shape in the same chapter, one section apart.

    Follows M22.2 exactly, including where it stops. An undescribed *IRI* is a
    dangling reference and L1's business, not a typing error -- a literal is
    neither, and is reported here, because L1 has nothing to say about one and
    a literal can never be an instance of anything.
    """
    yield from _points_at_an_instance_of(
        ctx, T.has_content_lifecycle_status_value, T.ContentLifeCycleStatusValue,
        "iirds:has-content-lifecycle-status-value must point to an "
        "iirds:ContentLifeCycleStatusValue")


@rule("M22.2", covers=("x6-8-3-parties-and-roles#2",),
       fix="Point iirds:has-party-role at an instance of iirds:PartyRole or one of its subclasses. Pointing at anything else — a vCard, a plain resource — leaves the role unstated even though the property is present.")
def m22_2_role_is_a_party_role(ctx):
    """M22.1 asks whether the party has a role; this asks whether the thing it
    points at is one. They were the same function here, which double-reported
    one defect and left the actual check missing."""
    yield from _points_at_an_instance_of(
        ctx, T.has_party_role, T.PartyRole,
        "iirds:has-party-role must point to an iirds:PartyRole")


@rule("M23",   # not x6-8-3-parties-and-roles#3: see the docstring
       fix="Add iirds:relates-to-vcard on the Party, pointing at a vCard that describes it. The role says what the party does; the vCard says who it is, which is what a reader needs to make contact.")
def m23_party_has_a_vcard(ctx):
    """A role without a description is not something anyone can act on.

    Section 6.8.3's sentence has two halves and this counts one: "an
    iirds:Party MUST also have an associated description of itself as
    compliant **vcard:kind object** which is assigned via
    iirds:relates-to-vcard". A party whose vcard is an `iirds:Topic` has the
    property and not the object, and nothing reports it -- the same shape
    R10 was written for, one sentence further down the same section.

    Not fixed here, and the claim withdrawn instead, because the companion
    needs something this repository does not have: the vCard vocabulary, to
    say which classes are kinds. `Ontology.instances_of` reads the bundled
    iiRDS files and vCard is not among them, and bundling a second vocabulary
    is a decision about what this tool ships, not a rider on a mapping
    correction.
    """
    yield from _exactly_one(ctx, T.Party, T.relates_to_vcard, "iirds:relates-to-vcard")


@rule("M95",
       fix="Keep one iirds:relates-to-party on the Component and remove the rest. If several organisations are genuinely involved, model each on its own relation type rather than repeating this one.")
def m95_component_party(ctx):
    yield from _at_most_one(ctx, T.Component, T.relates_to_party, "iirds:relates-to-party")


@rule("M96.1", covers=("x6-8-4-external-classification#7",), versions=("1.2", "1.3"),  # external classification arrives in 1.2
       fix="Give the external classification exactly one iirds:has-classification-domain. The domain names the scheme — eCl@ss, ETIM, or your own — and a classification identifier means nothing without it.")
def m96_1_classification_domain(ctx):
    for classification in ctx.instances_of(T.ExternalClassification):
        domains = ctx.values(classification, T.has_classification_domain)
        if len(domains) != 1:
            yield Violation("iirds:ExternalClassification must point to exactly one "
                            "classification domain",
                            subject=ctx.ref(classification), detail="%d found" % len(domains))


@rule("M96.2", covers=("x6-8-4-external-classification#4",), versions=("1.2", "1.3"),  # external classification arrives in 1.2
       fix="Give the external classification exactly one iirds:classificationIdentifier. Two identifiers in one classification leave a consumer unable to tell which one is meant.")
def m96_2_classification_identifier_count(ctx):
    for classification in ctx.instances_of(T.ExternalClassification):
        identifiers = ctx.values(classification, T.classificationIdentifier)
        if len(identifiers) != 1:
            yield Violation("iirds:ExternalClassification must have exactly one "
                            "iirds:classificationIdentifier",
                            subject=ctx.ref(classification), detail="%d found" % len(identifiers))


@rule("M96.3", covers=("x6-8-4-external-classification#4",), versions=("1.2", "1.3"),  # external classification arrives in 1.2
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
rule("M36", covers=("x6-8-1-complex-identity#3",),
     fix="Relate the Identity to an iirds:IdentityDomain. Serial numbers and asset "
                 "URIs are only unique within a scheme, so the value alone is ambiguous."
     )(m19_3_identity_domain)


