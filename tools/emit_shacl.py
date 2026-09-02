#!/usr/bin/env python3
"""Emit the iiRDS validation rules as SHACL shapes — the language-neutral encoding.

iirds-consortium/models#24 (opened by Vladimir Alexiev, April 2025) proposes
exactly this and has sat unanswered — not because the Turtle is hard, but
because the real cost is reading 314 prose obligations into rules, which this
repository has already paid for and documented (docs/divergences.md).
The shapes are therefore generated from the SAME sources as the Python rules
— the registry, the generated class table, the ontology closures — so the two
encodings cannot drift apart by accident, and a differential gate proves on
every fixture that they agree.

Completeness is enforced, not hoped for: every rule id in the registry must
appear in exactly one bucket below (CORE_FORMS / SPARQL_PLANNED /
DEFERRED_V11 / NOT_EXPRESSIBLE / NOOP), or this tool refuses to emit
anything. Skipping a rule is a syntax error here, never a silence.

    python tools/emit_shacl.py            # write shapes/ and MANIFEST.json
    python tools/emit_shacl.py --check    # regenerate and byte-compare

Licence discipline: the shapes are this project's Apache-2.0 artifact. They
reference iiRDS term IRIs (facts) and must never copy ontology triples or
prose (CC BY-ND) — tests/test_licensing.py enforces both vectors, structural
and textual, after the catalogue's `en` field was found smuggling
ontology descriptions in as titles. Catalogue-sourced rules carry the
catalogue's own message wording where the registry kept it (MIT, plusmeta,
with notices in shapes/); remedy texts are this project's throughout. That
mix is fine to relicense: MIT subsists under any outbound terms the
Consortium might prefer, CC BY-ND material would not — which is why the
ontology boundary is the one a test guards.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iirds_validate import terms as T  # noqa: E402
from iirds_validate.model import IIRDS_NAMESPACES as _IIRDS_NS  # noqa: E402
from iirds_validate.model import Severity  # noqa: E402
from iirds_validate.ontology import load as load_ontology  # noqa: E402
from iirds_validate.registry import PROVENANCE, all_rules  # noqa: E402
from iirds_validate.rules.schema_tables import MUST_HAVE_IRI  # noqa: E402

OUT = ROOT / "shapes"
EDITION = "1.3"

IVS = "https://w3id.org/iirds-validate/shapes#"
IVM = "https://w3id.org/iirds-validate/shapes/meta#"
PREFIXES = """@prefix rdf:      <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix sh:       <http://www.w3.org/ns/shacl#> .
@prefix rdfs:     <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dcterms:  <http://purl.org/dc/terms/> .
@prefix iirds:    <http://iirds.tekom.de/iirds#> .
@prefix iirdsHov: <http://iirds.tekom.de/iirds/domain/handover#> .
@prefix mach:     <http://iirds.tekom.de/iirds/domain/machinery#> .
@prefix sw:       <http://iirds.tekom.de/iirds/domain/software#> .
@prefix ivs:      <%s> .
@prefix ivm:      <%s> .
""" % (IVS, IVM)

#: `rdf:about=""` resolves to the parse base and comes back as a URIRef, so
#: sh:nodeKind sh:IRI alone would pass what `is_named` rejects. Every emitted
#: nodeKind shape carries this exclusion, and the shapes README states the
#: convention: validate metadata parsed against base <urn:iirds:package:>.
BASE_EXCLUSION = "sh:not [ sh:in ( <urn:iirds:package:> ) ]"

SEVERITY = {Severity.ERROR: "sh:Violation",
            Severity.WARNING: "sh:Warning",
            Severity.INFO: "sh:Info"}

_ONTOLOGY = load_ontology()
IU_CLOSURE = tuple(sorted("iirds:" + str(c).split("#")[-1]
                          for c in _ONTOLOGY.subclasses_of(T.InformationUnit)))
SELECTOR_CLOSURE = tuple(sorted("iirds:" + str(c).split("#")[-1]
                                for c in _ONTOLOGY.subclasses_of(T.Selector)))

_PREFIX_OF = {"IIRDS": "iirds", "MACH": "mach", "SW": "sw", "HOV": "iirdsHov"}

#: Classes the ontology's own descriptions mark "not intended to be used
#: directly" — the same marker rules/lint.py L10 reads, computed the same way
#: so the two encodings cannot disagree about what counts as abstract.
_ABSTRACT_MARKER = "not int"
ABSTRACT_CLASSES = tuple(sorted(
    str(cls) for cls, description in _ONTOLOGY.graph.subject_objects(T.IIRDS_DESCRIPTION)
    if _ABSTRACT_MARKER in str(description).lower()))


#: Catalogue spec links end in a text fragment quoting the sentence they
#: point at. For M78-M94 that quoted sentence is the ontology's own
#: description -- the prose evicted from sh:message, which came back
#: riding in percent-encoded. Those links keep their section anchor
#: and lose the quotation; every other fragment quotes the specification
#: sentence it cites, which is the feature worth keeping.
_ONTOLOGY_PROSE = tuple(
    " ".join(str(o).split())
    for _s, _p, o in _ONTOLOGY.graph
    if (str(_p).endswith("#description") or str(_p).endswith("comment"))
    and len(" ".join(str(o).split())) >= 25)


def _spec_link(rule):
    url = rule.spec
    if url and ":~:text=" in url:
        base, _, fragment = url.partition(":~:text=")
        text = " ".join(unquote(fragment).split())
        # Both fragment syntaxes: a plain quotation, and the range form
        # prefix-,start,-suffix whose pieces quote scraps of the target.
        # Any piece that is (or sits inside) an ontology description means
        # the link is pointing at the schema reference's prose, and the
        # section anchor alone says that without carrying the words.
        pieces = [text] + [piece.strip("-, ")
                           for piece in text.replace("-,", ",").replace(",-", ",").split(",")]
        for piece in pieces:
            if len(piece) < 12:
                continue
            if any(piece in prose or prose in piece for prose in _ONTOLOGY_PROSE):
                return base
    return url


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# The buckets. Every rule id lands in exactly one, enforced in emit().
# ---------------------------------------------------------------------------

#: rule id -> (family, params). The third encoding of the reading, kept
#: declarative on purpose; the differential gate is its standing proof.
CORE_FORMS = {}

# -- must-have-IRI: the generated table drives this, so the two artefacts
#    cannot disagree about which class belongs to which rule.
for _rid, _prefix, _cls in MUST_HAVE_IRI:
    CORE_FORMS[_rid] = ("nodekind_iri", {"targets": ("%s:%s" % (_PREFIX_OF[_prefix], _cls),)})
CORE_FORMS["R1"] = ("nodekind_iri", {"targets": ("iirds:ClassificationType",)})
CORE_FORMS["R2"] = ("nodekind_iri", {"targets": ("iirdsHov:DocumentCategory",)})
CORE_FORMS["M2.1"] = ("nodekind_iri", {"targets": IU_CLOSURE})

for _rid, _path in (("M2.3", "iirds:dateOfCreation"), ("M2.4", "iirds:dateOfLastModification"),
                    ("M2.5", "iirds:revision"), ("M2.6", "iirds:title"),
                    ("M2.7", "iirds:has-abstract"), ("M2.8", "iirds:is-replacement-of"),
                    ("M2.9", "iirds:is-version-of"), ("M6", "iirds:is-version-of")):
    CORE_FORMS[_rid] = ("at_most_one", {"targets": IU_CLOSURE, "path": _path})

for _rid, _target, _path in (
        ("M21.2", "iirds:ContentLifeCycleStatus", "iirds:dateOfEffect"),
        ("M21.3", "iirds:ContentLifeCycleStatus", "iirds:dateOfExpiry"),
        ("M21.4", "iirds:ContentLifeCycleStatus", "iirds:dateOfStatus"),
        ("M21.5", "iirds:ContentLifeCycleStatus", "iirds:purpose"),
        ("M21.6", "iirds:ContentLifeCycleStatus", "iirds:relates-to-party"),
        ("M24.1", "iirds:DirectoryNode", "iirds:has-next-sibling"),
        ("M24.2", "iirds:DirectoryNode", "iirds:has-directory-structure-type"),
        ("M24.3", "iirds:DirectoryNode", "iirds:has-first-child"),
        ("M24.4", "iirds:DirectoryNode", "iirds:relates-to-information-unit"),
        ("M95", "iirds:Component", "iirds:relates-to-party")):
    CORE_FORMS[_rid] = ("at_most_one", {"targets": (_target,), "path": _path})

for _rid, _target, _path in (
        ("M4", "iirds:Package", "iirds:iiRDSVersion"),
        ("M10", "iirds:Rendition", "iirds:source"),
        ("M11", "iirds:Rendition", "iirds:format"),
        ("M14.1", "iirds:RangeSelector", "iirds:has-start-selector"),
        ("M14.2", "iirds:RangeSelector", "iirds:has-end-selector"),
        ("M16.1", "iirds:Event", "iirds:has-event-code"),
        ("M16.2", "iirds:Event", "iirds:has-event-type"),
        ("M19.1", "iirds:Identity", "iirds:identifier"),
        ("M19.3", "iirds:Identity", "iirds:has-identity-domain"),
        ("M21.1", "iirds:ContentLifeCycleStatus", "iirds:has-content-lifecycle-status-value"),
        ("M22.1", "iirds:Party", "iirds:has-party-role"),
        ("M23", "iirds:Party", "iirds:relates-to-vcard"),
        ("M35", "iirds:Identity", "iirds:identifier"),
        ("M36", "iirds:Identity", "iirds:has-identity-domain"),
        ("M96.1", "iirds:ExternalClassification", "iirds:has-classification-domain"),
        ("M96.2", "iirds:ExternalClassification", "iirds:classificationIdentifier"),
        ("M15.2", "iirds:Document", "iirdsHov:has-document-category")):
    CORE_FORMS[_rid] = ("exactly_one", {"targets": (_target,), "path": _path})

CORE_FORMS["M19.2"] = ("nonempty_min1", {"targets": ("iirds:Identity",),
                                         "path": "iirds:identifier"})
CORE_FORMS["M96.3"] = ("nonempty_values", {"targets": ("iirds:ExternalClassification",),
                                           "path": "iirds:classificationIdentifier"})
CORE_FORMS["M8"] = ("m8_container_package", {})
CORE_FORMS["R5"] = ("r5_named_parent_is_not_nested", {})
CORE_FORMS["R6"] = ("r6_content_of_a_nested_package", {})
CORE_FORMS["R7"] = ("r7_container_package_is_not_inside_another", {})
CORE_FORMS["M9"] = ("no_absolute_source", {"targets": ("iirds:Rendition",),
                                           "path": "iirds:source"})

CORE_FORMS["M15.1"] = ("alternative_min1", {
    "targets": ("iirds:Document",),
    "paths": ("iirds:has-document-type", "iirds:is-applicable-for-document-type")})
for _rid, _path in (("M15.3", "iirds:language"), ("M15.4", "iirds:title"),
                    ("M15.6", "iirds:has-rendition")):
    CORE_FORMS[_rid] = ("min_one", {"targets": ("iirds:Document",), "path": _path})
CORE_FORMS["M15.5"] = ("qualified_class_min1", {
    "targets": ("iirds:Document",), "path": "iirds:is-version-of",
    "cls": "iirds:InformationObject"})
CORE_FORMS["M15.7a"] = ("product_variant_identity", {
    "types": ("iirds:ObjectInstanceURI", "iirds:ObjectTypeURI", "iirds:SerialNumber")})
CORE_FORMS["M15.7c"] = ("variant_type_identity", {"types": ("iirds:ProductType",)})
CORE_FORMS["M15.11b"] = ("class_forbidden", {"targets": ("iirds:DirectoryNode", "iirds:nil")})
CORE_FORMS["M15.11c"] = ("class_forbidden", {"targets": SELECTOR_CLOSURE})

CORE_FORMS["M94"] = ("forbidden_property", {"path": "iirds:relates-to-administrative-metadata"})
CORE_FORMS["M13.1"] = ("selector_value", {"path": "rdf:value"})
CORE_FORMS["M13.2"] = ("selector_value", {"path": "<http://purl.org/dc/terms/conformsTo>"})
CORE_FORMS["M25"] = ("m25_closed_list", {})
CORE_FORMS["M26"] = ("m26_first_child_type", {})
CORE_FORMS["M27"] = ("m27_first_child_is_head", {})
CORE_FORMS["M24.5"] = ("m24_5_root_has_type", {})
CORE_FORMS["L7"] = ("l7_title_with_package_exempt", {})

#: The SPARQL-expressible ones. Absolute IRIs inline; VALUES is forbidden
#: inside SHACL-SPARQL constraints (pre-binding restrictions), so membership
#: tests use FILTER IN. Graph-global rules use the fixed-node idiom —
#: sh:targetNode pointing at the shape itself, so the constraint runs once per
#: graph; the gate compares rule fire-SETS, so focus granularity is out of
#: scope by design (MANIFEST says so). No sh:SPARQLTarget anywhere: pySHACL
#: 0.40 silently ignores it, and a target an engine ignores is a rule that
#: never fires — the exact failure mode this project hunts.
II = "http://iirds.tekom.de/iirds#"
RDFS_ = "http://www.w3.org/2000/01/rdf-schema#"
RDF_ = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

#: Python's is_iirds_term tests four exact namespaces, and the broad prefix
#: "http://iirds.tekom.de/" was measured to disagree with it in both
#: directions (a squatter at .../custom# fooled one encoding each way). The
#: SPARQL mirror is the same four, spelled out.


def _ns_test(var):
    return "(" + " || ".join('STRSTARTS(STR(%s), "%s")' % (var, ns)
                             for ns in _IIRDS_NS) + ")"

#: The five iiRDS/H "named party" MUSTs share one reading
#: (rules/handover.py _needs_named_party): the subject must reach a Party
#: holding the role, whose vcard is either undescribed in this package
#: (then L1 owns the dangling reference -- one unresolvable pointer must
#: not produce the same finding five times) or states a
#: vcard:organization-name. Deferred at first release for exactly this
#: subtlety; the differential gate now holds the reading in both encodings.
#: UNION branches are evaluated independently and only then joined, so a
#: branch containing nothing but a FILTER sees ?card *unbound* -- and
#: `NOT EXISTS { ?card ?cp ?co }` with an unbound ?card asks "is the graph
#: empty", which it never is. Each branch therefore carries its own
#: relates-to-vcard triple, binding the card before testing it (found by
#: the softening pin the moment these shapes first ran).
_NAMED_VCARD = ("{ ?party <%(ii)srelates-to-vcard> ?card .\n"
                "      FILTER NOT EXISTS { ?card ?cp ?co } }\n"
                "    UNION\n"
                "    { ?party <%(ii)srelates-to-vcard> ?namedcard .\n"
                "      ?namedcard <%(vc)sorganization-name> ?orgname }")


def _named_party_query(cls, role):
    return ("""SELECT $this ?value WHERE {
  ?value <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)s""" + cls + """> .
  FILTER NOT EXISTS {
    ?value <%(ii)srelates-to-party> ?party .
    ?party <%(ii)shas-party-role> <%(ii)s""" + role + """> .
    """ + _NAMED_VCARD + """
  } }""")


def _domain_manufacturer_query(type_list):
    return ("""SELECT $this ?value WHERE {
  ?variant <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sProductVariant> .
  ?variant <%(ii)shas-identity> ?identity .
  ?identity <%(ii)shas-identity-domain> ?value .
  ?value <%(ii)shas-identity-type> ?idtype .
  FILTER (?idtype IN (""" + type_list + """))
  FILTER NOT EXISTS {
    ?value <%(ii)srelates-to-party> ?party .
    ?party <%(ii)shas-party-role> <%(ii)sManufacturer> .
    """ + _NAMED_VCARD + """
  } }""")


SPARQL_FORMS = {
    # Where a violating node exists, the query binds it to ?value: a SPARQL
    # constraint's ?value binding becomes the result's sh:value, so a global
    # check reports "at this node" instead of "somewhere in the graph". The
    # first M3 query reports an absence and has no node to name.
    # rdf:type/rdfs:subClassOf*, not bare rdf:type: a package typed only
    # with its own declared subclass of iirds:Package is a Package (section
    # 7). The five named-party MUSTs, M17, M18, M24.6 and M22.2 all got this
    # repair; M3 was the straggler, caught later -- in the false-reject
    # direction, the worst one.
    "M3": ("fixed", ["""SELECT $this WHERE {
  FILTER NOT EXISTS { ?p <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sPackage> } }""",
                     """SELECT $this ?value WHERE {
  ?value <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sPackage> .
  FILTER NOT EXISTS { ?value <%(ii)sis-part-of-package> ?x1 .
                      ?x1 <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sPackage> .
                      FILTER (!sameTerm(?x1, ?value)) }
  ?p2 <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sPackage> .
  FILTER NOT EXISTS { ?p2 <%(ii)sis-part-of-package> ?x2 .
                      ?x2 <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sPackage> .
                      FILTER (!sameTerm(?x2, ?p2)) }
  FILTER (?value != ?p2) }"""]),
    # rdf:type/rdfs:subClassOf*: the same instance test sh:class performs,
    # so a package-declared subclass of Component satisfies the "declares one
    # of its own" escape in both encodings (section 7 again).
    "M17": ("fixed", ["""SELECT $this ?value WHERE {
  ?value <%(ii)srelates-to-component> ?o .
  FILTER NOT EXISTS { ?c <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sComponent> } }"""]),
    "M18": ("fixed", ["""SELECT $this ?value WHERE {
  ?value <%(ii)srelates-to-product-variant> ?o .
  FILTER NOT EXISTS { ?v <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sProductVariant> } }"""]),
    "M24.6": ("fixed", ["""SELECT $this ?value WHERE {
  ?value <%(rdf)stype>/<%(rdfs)ssubClassOf>* ?nt .
  FILTER (?nt IN (<%(ii)sDirectoryNode>, <%(ii)snil>))
  FILTER NOT EXISTS { ?root <%(rdf)stype>/<%(rdfs)ssubClassOf>* ?rt .
      FILTER (?rt IN (<%(ii)sDirectoryNode>, <%(ii)snil>))
      ?root <%(ii)shas-directory-structure-type> ?t ; <%(ii)shas-first-child> ?c } }"""]),
    "M30": ("fixed", ["""SELECT $this ?value WHERE {
  { ?value a <%(rdfs)sClass> } UNION { ?value a <%(rdf)sProperty> }
  UNION { ?value ?p ?o .
          FILTER (?p IN (<%(rdfs)ssubClassOf>, <%(rdfs)ssubPropertyOf>,
                         <%(rdfs)sdomain>, <%(rdfs)srange>))
          FILTER %(ns_o)s }
  FILTER %(ns_v)s }"""]),
    "M16.3": ("fixed", ["""SELECT $this ?value WHERE {
  ?value <%(rdfs)ssubClassOf> <%(ii)sEvent> .
  FILTER (!%(ns_v)s)
  FILTER NOT EXISTS { ?value a <%(rdfs)sClass> } }"""]),
    "M1": ("fixed", ["""SELECT $this ?value WHERE { ?value a <%(ii)sInformationUnit> }"""]),
    "M12": ("fixed", ["""SELECT $this ?value WHERE { ?value a <%(ii)sSelector> }"""]),
    # rdf:type/rdfs:subClassOf*, like M3 and the named-party five: a package's
    # own subclass of iirds:Topic is a Topic under section 7, and the profile
    # excludes topics so a receiving system need not understand them. M1 and
    # M12 below stay on exact typing on purpose -- their sentence is "you used
    # the parent class directly", which a subclass instance has not done.
    "M15.11a": ("fixed", ["""SELECT $this ?value WHERE {
  ?value <%(rdf)stype>/<%(rdfs)ssubClassOf>* ?t .
  FILTER (?t IN (<%(ii)sInformationUnit>, <%(ii)sTopic>, <%(ii)sFragment>)) }"""]),
    "L10": ("fixed", ["""SELECT $this ?value WHERE { ?value a ?t . FILTER (?t IN (%(abstract)s)) }"""]),
    # rdflib keeps a non-empty relative rdf:about RELATIVE (only "" resolves
    # to the base), so the honest test is the one Python makes: no scheme.
    "M5": ("fixed", ["""SELECT $this ?value WHERE {
  ?value a ?t . FILTER %(ns_t)s
  FILTER isIRI(?value)
  FILTER (!REGEX(STR(?value), "^[A-Za-z][A-Za-z0-9+.-]*:")
          || STR(?value) = "urn:iirds:package:") }"""]),
    # Python compares str(value).strip(), so "1.3"@en and " 1.3 " are valid
    # there; sh:in is RDF term equality and disagreed on both. The
    # mirror is a whitespace-tolerant regex over STR(), which drops the tag.
    # \\s, not a literal space: pretty-printers pad with tabs and newlines,
    # and " *" was measured to reject a conformant package. pySHACL evaluates
    # REGEX with Python-re semantics, where \\s also covers NBSP, matching
    # str.strip(); XPath-strict engines are narrower there, which the README's
    # "tested on pySHACL 0.40" already prices in. S5's group is optional
    # because an empty or blank value means "unrestricted" -- valid.
    "S4": ("subjects", "iirds:iiRDSVersion", ["""SELECT $this ?value WHERE {
  $this <%(ii)siiRDSVersion> ?value .
  FILTER (!REGEX(STR(?value), "^\\\\\\\\s*(1[.]0|1[.]0[.]1|1[.]1|1[.]2|1[.]3)\\\\\\\\s*$")) }"""]),
    "S5": ("subjects", "iirds:formatRestriction", ["""SELECT $this ?value WHERE {
  $this <%(ii)sformatRestriction> ?value .
  FILTER (!REGEX(STR(?value), "^\\\\\\\\s*(A|H)?\\\\\\\\s*$")) }"""]),
    "M19.4": ("subjects", "iirds:has-identity-domain", ["""SELECT $this ?value WHERE {
  $this <%(ii)shas-identity-domain> ?value .
  FILTER EXISTS { ?value ?p2 ?o2 }
  FILTER NOT EXISTS {
    ?value <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sIdentityDomain> } }"""]),
    # Python exempts a role that is (a) an instance of PartyRole under the
    # closure, (b) any term the bundled ontology defines, or (c) undescribed
    # (L1's business). The old namespace-prefix exemption approximated (b)
    # and thereby hid misspelled terms inside the real namespace -- the exact
    # defect this rule exists to catch. (b) is now the literal
    # list, generated from the same ontology Python reads.
    "M22.2": ("subjects", "iirds:has-party-role", ["""SELECT $this ?value WHERE {
  $this <%(ii)shas-party-role> ?value .
  FILTER EXISTS { ?value ?p2 ?o2 }
  FILTER NOT EXISTS { ?value <%(rdf)stype>/<%(rdfs)ssubClassOf>* <%(ii)sPartyRole> }
  FILTER (?value NOT IN (%(defined_terms)s)) }"""]),
}

SPARQL_FORMS["M15.8"] = ("fixed", [_named_party_query("Document", "Author")])
SPARQL_FORMS["M15.9"] = ("fixed", [_named_party_query("Package", "Creator")])
SPARQL_FORMS["M15.10"] = ("fixed", [_named_party_query("InformationObject", "Creator")])
SPARQL_FORMS["M15.7b"] = ("fixed", [_domain_manufacturer_query(
    "<%(ii)sObjectInstanceURI>, <%(ii)sObjectTypeURI>, <%(ii)sSerialNumber>")])
SPARQL_FORMS["M15.7d"] = ("fixed", [_domain_manufacturer_query("<%(ii)sProductType>")])

#: The other half of _NAMED_VCARD. Its first branch lets an undescribed card
#: satisfy all five queries above, so that one broken pointer does not arrive
#: five times; this reports that pointer once instead, and the two spellings
#: of "the package never describes it" are deliberately identical.
SPARQL_FORMS["R4"] = ("fixed", ["""SELECT DISTINCT $this ?value WHERE {
  ?party <%(ii)srelates-to-vcard> ?value .
  FILTER NOT EXISTS { ?value ?cp ?co } }"""])

#: Expressible but deferred past v1: the softenings (undescribed-vcard tests,
#: label exemption nests) are the subtlest readings in the codebase, and the
#: stop-line is a pass+fail fixture pair per shape before it ships.
DEFERRED_V11 = {
    "L1": "dangling-reference exemptions (WELL_KNOWN, ontology terms)",
    "L3": "reachability over (first-child|next-sibling)*",
    "L4": "cycle detection via property-path +",
    "L5": "proprietary-class linkage exemption nest",
    "L6": "structural-node and label exemption nest",
    "L8": "external-vocabulary filters",
    # Core has no path that yields the predicates a node uses -- every path
    # names its predicate -- so the position this rule cares about most
    # cannot be reached. A sh:sparql constraint expresses all three
    # positions and would carry the edition's whole term list as a VALUES
    # block; that is a shape worth emitting and not one to bolt on here.
    "L13": "needs the predicates a node uses, which no Core path yields",
}

#: No RDF graph to look at, or two graphs, or graph×ZIP joins. Verbatim family
#: reasons; the differential gate derives its exclusion set from THIS table.
NOT_EXPRESSIBLE = {}
for _rid in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11.1",
             "C11.1H", "C11.2", "C12", "C13", "C14", "C15", "C16.1", "C16.2", "R3"):
    NOT_EXPRESSIBLE[_rid] = "container: the subject is ZIP bytes and entry metadata; no graph exists yet"
for _rid in ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10"):
    NOT_EXPRESSIBLE[_rid] = "content: the subject is XHTML files inside the archive"
for _rid in ("S1", "S2", "S3", "S9"):
    NOT_EXPRESSIBLE[_rid] = "system: the subject is the run itself, not the graph"
for _rid in ("S6", "S7", "S8"):
    NOT_EXPRESSIBLE[_rid] = "archive: entry names, encryption bits, ZIP64 records"
for _rid in ("L2", "L11", "L12", "R8", "R9"):
    NOT_EXPRESSIBLE[_rid] = "graph×ZIP join: the verdict depends on which files the archive carries"
NOT_EXPRESSIBLE["L9"] = "compares the RDF/XML and JSON-LD graphs before the merge SHACL would validate"

NOOP = {"M96.4": "a MAY with nothing to violate; registered so `iirds rules` lists the catalogue"}


# ---------------------------------------------------------------------------
# Family emitters. Each returns the body lines of one named node shape.
# ---------------------------------------------------------------------------

def _prop(pid, path, *constraints):
    lines = ["%s a sh:PropertyShape ;" % pid, "  sh:path %s ;" % path]
    lines += ["  %s ;" % c for c in constraints]
    lines[-1] = lines[-1].rstrip(" ;") + " ."
    return lines


def _enrich_property_shapes(extra_lines, rule):
    """Results point at the property shape, so the property shape must carry
    the reader-facing metadata too — a Jena user's violation otherwise arrives
    as the engine's generic message with no remedy, no severity, no rule id
    (consortium review, blocker 4)."""
    if not extra_lines:
        return extra_lines
    meta = ['  sh:message "%s" ;' % esc(rule.title),
            "  sh:severity %s ;" % SEVERITY[rule.severity],
            '  ivm:ruleId "%s" ;' % rule.id]
    if rule.fix:
        meta.append('  sh:description "%s" ;' % esc(rule.fix))
    if rule.spec:
        meta.append("  dcterms:source <%s> ;" % _spec_link(rule))
    out = []
    for line in extra_lines:
        out.append(line)
        if line.endswith("a sh:PropertyShape ;"):
            out.extend(meta)
    return out


def _targets(targets):
    return "sh:targetClass " + ", ".join(targets)


def family_nodekind_iri(sid, p):
    return (["%s" % _targets(p["targets"]),
             "sh:nodeKind sh:IRI", BASE_EXCLUSION], [])


def family_exactly_one(sid, p):
    pid = sid + "-p"
    return (["%s" % _targets(p["targets"]), "sh:property %s" % pid],
            _prop(pid, p["path"], "sh:minCount 1", "sh:maxCount 1"))


def family_at_most_one(sid, p):
    pid = sid + "-p"
    return (["%s" % _targets(p["targets"]), "sh:property %s" % pid],
            _prop(pid, p["path"], "sh:maxCount 1"))


def family_min_one(sid, p):
    pid = sid + "-p"
    return (["%s" % _targets(p["targets"]), "sh:property %s" % pid],
            _prop(pid, p["path"], "sh:minCount 1"))


def family_nonempty_min1(sid, p):
    # sh:pattern violates on blank nodes per spec; Python's str(value).strip()
    # treats a bnode id as non-empty. Blank values pass here, as there.
    pid = sid + "-p"
    return (["%s" % _targets(p["targets"]), "sh:property %s" % pid],
            _prop(pid, p["path"], "sh:minCount 1",
                  'sh:or ( [ sh:nodeKind sh:BlankNode ] [ sh:pattern "\\\\S" ] )'))


def family_nonempty_values(sid, p):
    pid = sid + "-p"
    return (["%s" % _targets(p["targets"]), "sh:property %s" % pid],
            _prop(pid, p["path"],
                  'sh:or ( [ sh:nodeKind sh:BlankNode ] [ sh:pattern "\\\\S" ] )'))


def family_no_absolute_source(sid, p):
    # Python fires on '"://" in value or value.startswith("/")' — not on every
    # RFC-3986 scheme. urn:... and mailto:... are M5/L8's business, not this
    # rule's (disagreements in both directions). Mirror exactly.
    pid = sid + "-p"
    return (["%s" % _targets(p["targets"]), "sh:property %s" % pid],
            _prop(pid, p["path"], 'sh:not [ sh:pattern "(://|^/)" ]'))


def family_alternative_min1(sid, p):
    pid = sid + "-p"
    path = "[ sh:alternativePath ( %s ) ]" % " ".join(p["paths"])
    return (["%s" % _targets(p["targets"]), "sh:property %s" % pid],
            _prop(pid, path, "sh:minCount 1"))


def family_qualified_class_min1(sid, p):
    pid = sid + "-p"
    return (["%s" % _targets(p["targets"]), "sh:property %s" % pid],
            _prop(pid, p["path"],
                  "sh:qualifiedValueShape [ sh:class %s ]" % p["cls"],
                  "sh:qualifiedMinCount 1", "sh:qualifiedMaxCount 1"))


def family_value_in(sid, p):
    pid = sid + "-p"
    return (["%s" % _targets(p["targets"]), "sh:property %s" % pid],
            _prop(pid, p["path"], "sh:in ( %s )" % " ".join(p["values"])))


def family_forbidden_property(sid, p):
    pid = sid + "-p"
    return (["sh:targetSubjectsOf %s" % p["path"], "sh:property %s" % pid],
            _prop(pid, p["path"], "sh:maxCount 0"))


def family_m8_container_package(sid, p):
    # The enclosing package must not render; a nested one is content and may.
    # Nested means part of a different package *this graph describes as one*.
    # Core cannot compare a value node with the focus node it hangs off, so
    # this counts instead: the value nodes of a zero-or-ONE path are the focus
    # node and its direct parents, they are a set so a self-loop does not
    # double it, and two or more Packages among them is exactly "there is a
    # Package-valued parent other than me". Zero-or-*more* is wrong here --
    # it walks the chain, so a focus whose parent is a Topic that is itself
    # part of a real Package would borrow the grandparent's type and be
    # exempted. Mirrors rules/schema.py m8 through container_packages.
    return (["sh:targetClass iirds:Package",
             "sh:or ( [ sh:property [ sh:path [ sh:zeroOrOnePath iirds:is-part-of-package ] ; "
             "sh:qualifiedValueShape [ sh:class iirds:Package ] ; "
             "sh:qualifiedMinCount 2 ] ] "
             "[ sh:property [ sh:path iirds:has-rendition ; sh:maxCount 0 ] ] )"], [])


def family_r6_content_of_a_nested_package(sid, p):
    # Section 5.3: this document must not describe the content of a package it
    # says is nested. Focus is anything carrying the relation; a Package focus
    # is R5's business and passes the first branch.
    #
    # "Nested" is the same predicate as m8 above, one level in: count instead
    # of comparing. The value nodes of a zero-or-ONE path are the node and its
    # direct parents, they are a set so a self-loop does not double it, and two
    # or more Packages among them is exactly "there is a Package-valued parent
    # other than me". The first draft of this shape said Core could not express
    # it and shipped SPARQL -- the comment on m8 in this same file already had
    # the answer. Mirrors rules/requirements.py r6 through container_packages.
    return (["sh:targetSubjectsOf iirds:is-part-of-package",
             "sh:or ( [ sh:class iirds:Package ] "
             "[ sh:property [ sh:path iirds:is-part-of-package ; "
             "sh:qualifiedValueShape [ sh:class iirds:Package ; "
             "sh:property [ sh:path [ sh:zeroOrOnePath iirds:is-part-of-package ] ; "
             "sh:qualifiedValueShape [ sh:class iirds:Package ] ; "
             "sh:qualifiedMinCount 2 ] ] ; "
             "sh:qualifiedMaxCount 0 ] ] )"], [])


def family_r7_container_package_is_not_inside_another(sid, p):
    # Section 6.2: the package that represents this container must not be a
    # member of another package. Same counting trick as m8 and r6, used twice
    # over the same zero-or-ONE path, whose value nodes are the focus node and
    # its direct parents: two or more of them means "a parent other than me",
    # and two or more *Packages* among them means "a Package parent other than
    # me", which is what makes a node a nested child rather than this
    # container's own. A nested child is allowed the relation -- section 6.3.3
    # asks for it -- so the shape passes on either of those.
    # Mirrors rules/requirements.py r7 through container_packages.
    path = "[ sh:zeroOrOnePath iirds:is-part-of-package ]"
    return (["sh:targetClass iirds:Package",
             "sh:or ( [ sh:property [ sh:path %s ; sh:maxCount 1 ] ] "
             "[ sh:property [ sh:path %s ; "
             "sh:qualifiedValueShape [ sh:class iirds:Package ] ; "
             "sh:qualifiedMinCount 2 ] ] )" % (path, path)], [])


def family_selector_value(sid, p):
    # RangeSelectors delegate to their endpoints (M14); everything else typed
    # into the Selector family must carry the value/scheme pair.
    return (["sh:targetClass " + ", ".join(SELECTOR_CLOSURE),
             "sh:or ( [ sh:class iirds:RangeSelector ] "
             "[ sh:property [ sh:path %s ; sh:minCount 1 ; sh:maxCount 1 ] ] )" % p["path"]], [])


#: The bundled ontology says nil ⊑ DirectoryNode, so Python's ontology-closure
#: instances_of(DirectoryNode) includes anything typed `a iirds:nil` — a
#: closure the data graph cannot give SHACL. Everywhere a shape asks "is this
#: a DirectoryNode", it must ask "DirectoryNode or nil" (five rules).
DIRNODE_OR_NIL = "[ sh:or ( [ sh:class iirds:DirectoryNode ] [ sh:class iirds:nil ] ) ]"


def family_m25_closed_list(sid, p):
    # sh:in is the node iirds:nil; sh:class iirds:nil is an instance of it.
    # The requirement says "relating to an instance of the class iirds:nil",
    # so a package that mints its own terminator is doing what it asks -- and
    # a minted terminator is a DirectoryNode by the ontology's own hierarchy,
    # so without this alternative the shape demands an end for the end.
    return (["sh:targetObjectsOf iirds:has-first-child, iirds:has-next-sibling",
             "sh:or ( [ sh:in ( iirds:nil ) ] "
             "[ sh:class iirds:nil ] "
             "[ sh:not %s ] "
             "[ sh:property [ sh:path iirds:has-next-sibling ; "
             "sh:qualifiedValueShape [ sh:or ( [ sh:in ( iirds:nil ) ] "
             "[ sh:class iirds:DirectoryNode ] [ sh:class iirds:nil ] ) ] ; "
             "sh:qualifiedMinCount 1 ] ] )"
             % DIRNODE_OR_NIL], [])


def family_m26_first_child_type(sid, p):
    return (["sh:targetObjectsOf iirds:has-first-child",
             "sh:or ( [ sh:in ( iirds:nil ) ] [ sh:class iirds:DirectoryNode ] "
             "[ sh:class iirds:nil ] )"], [])


def family_r5_named_parent_is_not_nested(sid, p):
    # Section 6.3.3: the package a child names as its parent must have no
    # is-part-of-package of its own. Counted rather than compared -- no value
    # of this path may itself be a Package that is inside something, which
    # rules out a self-loop, a chain and a cycle in one constraint.
    # A named property shape for the same reason as m27 above.
    pid = sid + "-p"
    return (["sh:targetClass iirds:Package",
             "sh:property %s" % pid],
            _prop(pid, "iirds:is-part-of-package",
                  "sh:qualifiedValueShape [ sh:class iirds:Package ; "
                  "sh:property [ sh:path iirds:is-part-of-package ; sh:minCount 1 ] ]",
                  "sh:qualifiedMaxCount 0"))


def family_m27_first_child_is_head(sid, p):
    # A level's first child heads its sibling list: nothing points at it via
    # has-next-sibling. No nil exemption: Python's m27 has none, and the gate
    # holds the two encodings to the same reading.
    # A named property shape, not an inline blank one: pySHACL attributes the
    # violation to the property shape it fails in, and a blank node there is a
    # result nobody can map back to a rule id.
    pid = sid + "-p"
    return (["sh:targetObjectsOf iirds:has-first-child",
             "sh:property %s" % pid],
            _prop(pid, "[ sh:inversePath iirds:has-next-sibling ]",
                  "sh:maxCount 0"))


def family_m24_5_root_has_type(sid, p):
    # Only the root carries the structure type, and a root is what nothing
    # links to — so the violation is a LINKED node carrying it. First shipped
    # inverted ("a root must have the type"), which the differential gate
    # caught on its first run: the mutant suites fired M24.5 where Python was
    # silent. Mirrors rules/schema.py m24_5_only_root_has_structure_type.
    return (["sh:targetObjectsOf iirds:has-first-child, iirds:has-next-sibling",
             "sh:or ( [ sh:not %s ] "
             "[ sh:property [ sh:path iirds:has-directory-structure-type ; "
             "sh:maxCount 0 ] ] )" % DIRNODE_OR_NIL], [])


def family_product_variant_identity(sid, p):
    # iiRDS/H: the Document relates to a variant, and some variant carries an
    # instance identity. Mirrors rules/handover.py m15_7a.
    pid1, pid2 = sid + "-p1", sid + "-p2"
    body = _prop(pid1, "iirds:relates-to-product-variant", "sh:minCount 1")
    body += _prop(pid2,
                  "( iirds:relates-to-product-variant iirds:has-identity "
                  "iirds:has-identity-domain iirds:has-identity-type )",
                  "sh:qualifiedValueShape [ sh:in ( %s ) ]" % " ".join(p["types"]),
                  "sh:qualifiedMinCount 1")
    return (["sh:targetClass iirds:Document",
             "sh:property %s" % pid1, "sh:property %s" % pid2], body)


def family_variant_type_identity(sid, p):
    pid = sid + "-p"
    return (["sh:targetClass iirds:ProductVariant", "sh:property %s" % pid],
            _prop(pid, "( iirds:has-identity iirds:has-identity-domain "
                       "iirds:has-identity-type )",
                  "sh:qualifiedValueShape [ sh:in ( %s ) ]" % " ".join(p["types"]),
                  "sh:qualifiedMinCount 1"))


def family_class_forbidden(sid, p):
    # An empty blank node shape conforms for every node, so its negation
    # fails for every node: "instances of this class must not exist".
    return (["%s" % _targets(p["targets"]), "sh:not [ ]"], [])


def family_l7_title_with_package_exempt(sid, p):
    return (["sh:targetClass " + ", ".join(IU_CLOSURE),
             "sh:or ( [ sh:class iirds:Package ] "
             "[ sh:property [ sh:path iirds:title ; sh:minCount 1 ] ] )"], [])


FAMILIES = {name[len("family_"):]: fn for name, fn in list(globals().items())
            if name.startswith("family_")}


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------

def sort_key(rid):
    head, tail = rid[0], rid[1:]
    parts = tail.replace(".", " ").split()
    return (head, [int(part) if part.isdigit() else 999 for part in parts], rid)


def shape_iri(rule_id: str) -> str:
    return "ivs:" + rule_id


def metadata_lines(rule) -> list:
    lines = ['rdfs:label "%s"' % esc(rule.title),
             "sh:severity %s" % SEVERITY[rule.severity],
             'sh:message "%s"' % esc(rule.title),
             'ivm:ruleId "%s"' % rule.id,
             'ivm:ruleSource "%s"' % ("catalogue" if rule.id[0] not in "RLSB"
                                      or rule.id in () else "catalogue"),
             ]
    # ruleSource: mirror Finding.source exactly
    from iirds_validate.registry import CATALOG
    lines[4] = 'ivm:ruleSource "%s"' % ("catalogue" if rule.id in CATALOG else "iirds-validate")
    if rule.fix:
        lines.append('sh:description "%s"' % esc(rule.fix))
    if rule.spec:
        lines.append("dcterms:source <%s>" % _spec_link(rule))
    if rule.versions:
        lines.append('ivm:versions "%s"' % ",".join(rule.versions))
    for req in rule.covers:
        lines.append('ivm:covers "%s"' % req)
    return lines


def emit_shape(rule) -> str:
    family, params = CORE_FORMS[rule.id]
    head, extra = FAMILIES[family](shape_iri(rule.id), params)
    sid = shape_iri(rule.id)
    lines = ["%s a sh:NodeShape ;" % sid]
    for item in metadata_lines(rule):
        lines.append("  %s ;" % item)
    for item in head:
        lines.append("  %s ;" % item)
    lines[-1] = lines[-1].rstrip(" ;") + " ."
    out = "\n".join(lines)
    if extra:
        out += "\n" + "\n".join(_enrich_property_shapes(extra, rule))
    return out + "\n"


def header(filename: str, description: str) -> str:
    return ("# %s — %s\n"
            "# Generated by tools/emit_shacl.py; do not edit by hand.\n"
            "# Licence: Apache-2.0 (this file is iirds-validate's artifact; it references\n"
            "# iiRDS term IRIs but copies no ontology content). Rule ids come from\n"
            "# the plusmeta catalogue at commit %s; where a\n"
            "# catalogue-sourced shape's message keeps the catalogue's rule\n"
            "# wording, that text is MIT, (c) plusmeta GmbH -- see\n"
            "# THIRD-PARTY-NOTICES.md. Remedy texts are this project's own.\n"
            "# Convention: validate metadata parsed against base <urn:iirds:package:>.\n\n"
            % (filename, description, PROVENANCE["_commit"][:12])) + PREFIXES + "\n"


def build() -> dict:
    rules = {r.id: r for r in all_rules()}

    buckets = {}
    for name, table in (("core", CORE_FORMS), ("sparql", SPARQL_FORMS),
                        ("deferred_v1.1", DEFERRED_V11),
                        ("not_expressible", NOT_EXPRESSIBLE), ("noop", NOOP)):
        for rid in table:
            if rid in buckets:
                raise SystemExit("%s classified twice: %s and %s" % (rid, buckets[rid], name))
            if rid not in rules:
                raise SystemExit("%s is classified but not registered" % rid)
            buckets[rid] = name
    missing = sorted(set(rules) - set(buckets))
    if missing:
        raise SystemExit("unclassified rules — refusing to emit: %s" % missing)

    files = {"iirds-core.ttl": [], "iirds-handover-core.ttl": []}
    emitted, version_excluded = [], []
    for rid in sorted(CORE_FORMS, key=sort_key):
        rule = rules[rid]
        if rule.versions and EDITION not in rule.versions:
            version_excluded.append(rid)
            continue
        target_file = ("iirds-handover-core.ttl" if "H" in (rule.variants or ())
                       else "iirds-core.ttl")
        files[target_file].append(emit_shape(rule))
        emitted.append(rid)

    def emit_sparql_shape(rule) -> str:
        form = SPARQL_FORMS[rule.id]
        sid = shape_iri(rule.id)
        subst = {"ii": II, "rdfs": RDFS_, "rdf": RDF_,
                 "abstract": ", ".join("<%s>" % c for c in ABSTRACT_CLASSES),
                 "ns_s": _ns_test("?s"), "ns_o": _ns_test("?o"),
                 "ns_v": _ns_test("?value"), "ns_t": _ns_test("?t"),
                 "vc": "http://www.w3.org/2006/vcard/ns#",
                 "defined_terms": ", ".join(
                     "<%s>" % term for term in
                     sorted(str(term) for term in _ONTOLOGY.defined_terms()))}
        lines = ["%s a sh:NodeShape ;" % sid]
        for item in metadata_lines(rule):
            lines.append("  %s ;" % item)
        if form[0] == "fixed":
            lines.append("  sh:targetNode %s ;" % sid)
            queries = form[1]
        else:
            lines.append("  sh:targetSubjectsOf %s ;" % form[1])
            queries = form[2]
        for query in queries:
            lines.append('  sh:sparql [ sh:select """%s""" ] ;' % (query % subst))
        lines[-1] = lines[-1].rstrip(" ;") + " ."
        return "\n".join(lines) + "\n"

    sparql_files = {"iirds-sparql.ttl": [], "iirds-handover-sparql.ttl": []}
    sparql_emitted = []
    for rid in sorted(SPARQL_FORMS, key=sort_key):
        rule = rules[rid]
        if rule.versions and EDITION not in rule.versions:
            version_excluded.append(rid)
            continue
        target = ("iirds-handover-sparql.ttl" if "H" in (rule.variants or ())
                  else "iirds-sparql.ttl")
        sparql_files[target].append(emit_sparql_shape(rule))
        sparql_emitted.append(rid)

    outputs = {
        "iirds-core.ttl": header("iirds-core.ttl",
                                 "SHACL Core shapes for iiRDS %s, all profiles" % EDITION)
                          + "\n".join(files["iirds-core.ttl"]),
        "iirds-handover-core.ttl": header("iirds-handover-core.ttl",
                                          "SHACL Core shapes, iiRDS/H additions")
                                   + "\n".join(files["iirds-handover-core.ttl"]),
        "iirds-sparql.ttl": header("iirds-sparql.ttl",
                                   "SHACL-SPARQL shapes (needs SHACL-AF: pySHACL, "
                                   "Jena, TopBraid)")
                            + "\n".join(sparql_files["iirds-sparql.ttl"]),
        "iirds-handover-sparql.ttl": header("iirds-handover-sparql.ttl",
                                            "SHACL-SPARQL shapes, iiRDS/H additions")
                                     + "\n".join(sparql_files["iirds-handover-sparql.ttl"]),
    }

    # One-file forms, because pySHACL's CLI takes a single shapes file and
    # silently keeps only the last -s: the documented quickstart must be a
    # command that actually runs every shape.
    outputs["iirds-complete.ttl"] = (
        header("iirds-complete.ttl",
               "everything for a non-handover package: core + SPARQL in one file "
               "(SHACL-AF engine required; Core-only engines: use iirds-core.ttl)")
        + "\n".join(files["iirds-core.ttl"]) + "\n"
        + "\n".join(sparql_files["iirds-sparql.ttl"]))
    outputs["iirds-handover-complete.ttl"] = (
        header("iirds-handover-complete.ttl",
               "everything for an iiRDS/H package, one file: core + SPARQL, "
               "base + handover")
        + "\n".join(files["iirds-core.ttl"]) + "\n"
        + "\n".join(sparql_files["iirds-sparql.ttl"]) + "\n"
        + "\n".join(files["iirds-handover-core.ttl"]) + "\n"
        + "\n".join(sparql_files["iirds-handover-sparql.ttl"]))

    from iirds_validate import __version__ as _project_version
    manifest = {
        "_generated_by": "tools/emit_shacl.py",
        "_shapes_version": _project_version,
        "_edition": EDITION,
        "_catalogue_commit": PROVENANCE["_commit"],
        "_shape_namespace": IVS,
        "_note": ("Every registered rule appears in exactly one bucket; the emitter refuses "
                  "to run otherwise. not_expressible reasons are the differential gate's "
                  "exclusion list — one source, no ad-hoc skips."),
        "counts": {"core_emitted": len(emitted),
                   "version_excluded": len(version_excluded),
                   "sparql_emitted": len(sparql_emitted),
                   "deferred_v1.1": len(DEFERRED_V11),
                   "not_expressible": len(NOT_EXPRESSIBLE),
                   "noop": len(NOOP)},
        "core_emitted": emitted,
        "sparql_emitted": sparql_emitted,
        "version_excluded": {rid: list(rules[rid].versions) for rid in version_excluded},
        "deferred_v1.1": DEFERRED_V11,
        "not_expressible": NOT_EXPRESSIBLE,
        "noop": NOOP,
        "shapes": dict(
            {rid: {"iri": IVS + rid,
                   "file": ("iirds-1.3/iirds-handover-core.ttl"
                            if "H" in (rules[rid].variants or ())
                            else "iirds-1.3/iirds-core.ttl")}
             for rid in emitted},
            **{rid: {"iri": IVS + rid,
                     "file": ("iirds-1.3/iirds-handover-sparql.ttl"
                              if "H" in (rules[rid].variants or ())
                              else "iirds-1.3/iirds-sparql.ttl")}
               for rid in sparql_emitted}),
    }
    return outputs, manifest


def write(outputs, manifest) -> None:
    directory = OUT / ("iirds-%s" % EDITION)
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in outputs.items():
        (directory / name).write_text(text, "utf-8")
    (OUT / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", "utf-8")


def check(outputs, manifest) -> int:
    directory = OUT / ("iirds-%s" % EDITION)
    problems = []
    for name, text in outputs.items():
        path = directory / name
        if not path.exists():
            problems.append("missing: %s" % name)
        elif path.read_text("utf-8") != text:
            problems.append("stale: %s" % name)
    manifest_path = OUT / "MANIFEST.json"
    expected = json.dumps(manifest, indent=1, ensure_ascii=False) + "\n"
    if not manifest_path.exists() or manifest_path.read_text("utf-8") != expected:
        problems.append("stale: MANIFEST.json")
    for line in problems:
        print("  " + line, file=sys.stderr)
    if problems:
        print("shapes/ is out of date; rerun tools/emit_shacl.py", file=sys.stderr)
        return 1
    print("shapes/ is up to date: %d core + %d SPARQL shapes "
          "(%d deferred, %d not expressible)"
          % (manifest["counts"]["core_emitted"], manifest["counts"]["sparql_emitted"],
             manifest["counts"]["deferred_v1.1"], manifest["counts"]["not_expressible"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    outputs, manifest = build()
    if args.check:
        return check(outputs, manifest)
    write(outputs, manifest)
    return check(outputs, manifest)


if __name__ == "__main__":
    sys.exit(main())
