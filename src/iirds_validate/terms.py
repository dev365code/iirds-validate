"""Every iiRDS term the rules refer to, in one place.

Two reasons this module exists rather than spelling terms inline.

1. `rdflib.Namespace` subclasses `str`, so attribute access collides with the
   string methods. `IIRDS.format` returns `str.format` — a bound method, not the
   iiRDS property — and a rule written that way matches nothing while the
   package looks clean. rdflib special-cases a handful of names (`title` is one)
   but not the rest, which makes the trap worse: some spellings work and some
   silently do not. Bracket syntax always works, so it is the only form used
   here.

2. Property names have to come from the ontology, not from the prose of a rule.
   The specification sentence for M16 says "iirds:eventCode"; the ontology
   defines `iirds:has-event-code`. `tests/test_terms.py` asserts that every name
   below is really defined in the bundled ontology, which turns that class of
   mistake into a failing test instead of a false pass.
"""
from __future__ import annotations

from rdflib import URIRef

from .model import HOV, IIRDS

# --- classes ---------------------------------------------------------------
InformationUnit = IIRDS["InformationUnit"]
InformationObject = IIRDS["InformationObject"]
Document = IIRDS["Document"]
Topic = IIRDS["Topic"]
Fragment = IIRDS["Fragment"]
Package = IIRDS["Package"]
Rendition = IIRDS["Rendition"]
Selector = IIRDS["Selector"]
RangeSelector = IIRDS["RangeSelector"]
FragmentSelector = IIRDS["FragmentSelector"]
Event = IIRDS["Event"]
Identity = IIRDS["Identity"]
IdentityDomain = IIRDS["IdentityDomain"]
IdentityType = IIRDS["IdentityType"]
Party = IIRDS["Party"]
PartyRole = IIRDS["PartyRole"]
ContentLifeCycleStatus = IIRDS["ContentLifeCycleStatus"]
DirectoryNode = IIRDS["DirectoryNode"]
ProductVariant = IIRDS["ProductVariant"]
#: The list terminator. Declared in the ontology as a subclass of
#: DirectoryNode, though it is used as an individual.
nil = IIRDS["nil"]

# --- properties ------------------------------------------------------------
title = IIRDS["title"]
language = IIRDS["language"]
revision = IIRDS["revision"]
purpose = IIRDS["purpose"]
identifier = IIRDS["identifier"]
source = IIRDS["source"]
fmt = IIRDS["format"]                        # `IIRDS.format` would be str.format
formatRestriction = IIRDS["formatRestriction"]
dateOfCreation = IIRDS["dateOfCreation"]
dateOfLastModification = IIRDS["dateOfLastModification"]
dateOfEffect = IIRDS["dateOfEffect"]
dateOfExpiry = IIRDS["dateOfExpiry"]

has_abstract = IIRDS["has-abstract"]
has_rendition = IIRDS["has-rendition"]
has_first_child = IIRDS["has-first-child"]
has_next_sibling = IIRDS["has-next-sibling"]
has_directory_structure_type = IIRDS["has-directory-structure-type"]
has_start_selector = IIRDS["has-start-selector"]
has_end_selector = IIRDS["has-end-selector"]
has_selector = IIRDS["has-selector"]
has_event_code = IIRDS["has-event-code"]
has_event_type = IIRDS["has-event-type"]
has_party_role = IIRDS["has-party-role"]
has_identity = IIRDS["has-identity"]
has_identity_domain = IIRDS["has-identity-domain"]
has_identity_type = IIRDS["has-identity-type"]
has_document_type = IIRDS["has-document-type"]
has_content_lifecycle_status = IIRDS["has-content-lifecycle-status"]

is_version_of = IIRDS["is-version-of"]
is_replacement_of = IIRDS["is-replacement-of"]
is_applicable_for_document_type = IIRDS["is-applicable-for-document-type"]
relates_to_information_unit = IIRDS["relates-to-information-unit"]
relates_to_party = IIRDS["relates-to-party"]
relates_to_vcard = IIRDS["relates-to-vcard"]
relates_to_product_variant = IIRDS["relates-to-product-variant"]

#: Declared on iirds:Package. Not present in every release of the ontology, so
#: it is exempt from the "must be defined" test below.
iiRDSVersion = IIRDS["iiRDSVersion"]
is_part_of_package = IIRDS["is-part-of-package"]

# --- handover domain (iiRDS/H, new in 1.3) ---------------------------------
hov_has_document_category = HOV["has-document-category"]

#: One snapshot, taken at the end of the module, filtered by type rather than
#: by name. Two positional snapshots meant a term added below the first one was
#: absent from CLASSES and therefore never checked by tests/test_terms.py —
#: the exact silent-skip this module exists to prevent, inside this module.
#: `isinstance(value, URIRef)` also excludes the IIRDS/HOV namespaces, which is
#: why no name exclusions are needed.
TERMS = {name: value for name, value in list(globals().items())
         if isinstance(value, URIRef)}
CLASSES = {name: value for name, value in TERMS.items() if name[0].isupper()}
PROPERTIES = {name: value for name, value in TERMS.items() if name[0].islower()}

#: Terms the ontology files do not declare even though the specification uses
#: them. Tracked explicitly so the guard test stays meaningful.
NOT_IN_ONTOLOGY = {
    "iiRDSVersion",
    "is_part_of_package",
    "formatRestriction",
}
