"""The differential gate: SHACL and Python must fire the same rules.

The shapes are a third encoding of one reading (spec → catalogue → Python →
shapes), and two encodings by one author agreeing proves nothing about the
reading — but their *disagreement* proves a translation error with certainty.
That is what this file hunts, on the material the Python rules were already
proven with: the mutation builders that made every generated rule fire, the
cardinality pairs, the conformant iiRDS/H package broken one requirement at a
time, and the calibration anchor.

Comparison is per-(graph, rule) fire-set equality, both sides restricted to
the shapes the emitter actually emitted — the exclusion list is the emitter's
own bucket table, never an ad-hoc skip in a test. Measured cost: ~9 ms per
validation, so the whole gate rides in the ordinary suite.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import Graph, Namespace

from conftest import MINIMAL_RDF, build_package, shacl_or_skip
from iirds_validate import runner
from iirds_validate.model import PACKAGE_BASE

pyshacl = shacl_or_skip()

ROOT = Path(__file__).resolve().parents[1]
SHAPE_DIR = ROOT / "shapes" / "iirds-1.3"
SH = Namespace("http://www.w3.org/ns/shacl#")

MANIFEST = json.loads((ROOT / "shapes" / "MANIFEST.json").read_text("utf-8"))
EMITTED = set(MANIFEST["core_emitted"]) | set(MANIFEST["sparql_emitted"])

#: Every shape id pySHACL ever reports across this whole file. Seven shapes
#: were neutered and the suite stayed green: set-equality per fixture cannot
#: see a shape that fires nowhere. The final test in this file closes
#: that hole by demanding the residue EMITTED - fired be empty.
SH_FIRED_EVER: set = set()


def _graph(*names):
    graph = Graph()
    for name in names:
        graph.parse(SHAPE_DIR / name, format="turtle")
    return graph


CORE = _graph("iirds-core.ttl", "iirds-sparql.ttl")
CORE_H = _graph("iirds-core.ttl", "iirds-sparql.ttl",
                "iirds-handover-core.ttl", "iirds-handover-sparql.ttl")


def shacl_fired(metadata: str, handover: bool = False, severities: dict = None):
    data = Graph().parse(data=metadata, format="xml", publicID=PACKAGE_BASE)
    _ok, results, _ = pyshacl.validate(data, shacl_graph=CORE_H if handover else CORE,
                                       advanced=True, inference="none")
    fired = set()
    for result, _p, source in results.triples((None, SH.sourceShape, None)):
        rid = str(source).rsplit("#", 1)[-1].split("-p")[0]
        fired.add(rid)
        if severities is not None:
            sev = results.value(result, SH.resultSeverity)
            severities.setdefault(rid, set()).add(sev)
    SH_FIRED_EVER.update(fired)
    return fired


def python_fired(tmp_path, name: str, metadata: str, **kw) -> set:
    package = build_package(tmp_path, name, metadata=metadata, **kw)
    report = runner.run(package, runner.ALL_KINDS)
    return {f.rule.id for f in report.findings} & EMITTED


#: What sh:resultSeverity must say, given the rule's declared severity. The
#: shapes mirror the rule's *base* severity: the profile-A demotion is the
#: runner's per-package decision, out of scope for a static shapes file (the
#: shapes README says so out loud).
_SEV = {"error": SH.Violation, "warning": SH.Warning, "info": SH.Info}


def assert_parity(tmp_path, name, metadata, handover=False, **kw):
    py = python_fired(tmp_path, name, metadata, **kw)
    severities = {}
    sh = shacl_fired(metadata, handover=handover, severities=severities)
    assert sh == py, "SHACL %s vs Python %s" % (sorted(sh - py), sorted(py - sh))
    # Same rule, same severity -- a shape may fire in the right place at the
    # wrong volume, and set-equality on ids alone would never notice.
    wrong = {rid: sevs for rid, sevs in severities.items()
             if sevs != {_SEV[_rule_severity(rid)]}}
    assert wrong == {}, wrong
    return py


# ---------------------------------------------------------------------------
# 1. The nodekind mutants — the material that proved the 61 generated rules.
# ---------------------------------------------------------------------------

from iirds_validate.rules.schema_tables import MUST_HAVE_IRI, NAMESPACES  # noqa: E402


def _rule_severity(rid: str) -> str:
    from iirds_validate.registry import all_rules
    by_id = getattr(_rule_severity, "_cache", None)
    if by_id is None:
        by_id = _rule_severity._cache = {r.id: r.severity.value for r in all_rules()}
    return by_id[rid]


BLANK = '''  <rdf:Description>
    <rdf:type rdf:resource="%s"/>
    <rdfs:label xml:lang="en">Anonymous</rdfs:label>
  </rdf:Description>
'''
NAMED = BLANK.replace("<rdf:Description>", '<rdf:Description rdf:about="urn:test:named">')

NODEKIND_ROWS = ([(rid, str(NAMESPACES[p][c])) for rid, p, c in MUST_HAVE_IRI]
                 + [("R1", "http://iirds.tekom.de/iirds#ClassificationType"),
                    ("R2", "http://iirds.tekom.de/iirds/domain/handover#DocumentCategory")])


@pytest.mark.parametrize("rule_id,class_iri", NODEKIND_ROWS,
                         ids=[r for r, _ in NODEKIND_ROWS])
def test_nodekind_parity_on_the_mutant_and_its_repair(rule_id, class_iri, tmp_path):
    # Shape-file selection follows the PACKAGE's declared profile, exactly as
    # the runner selects rules by ctx.variant — never the namespace of a class
    # that happens to appear. First draft selected handover files because R2's
    # class lives in the handover namespace, and M15.11a promptly fired on an
    # unrestricted package; the gate caught its own harness.
    broken = MINIMAL_RDF.replace("</rdf:RDF>", BLANK % class_iri + "</rdf:RDF>")
    fired = assert_parity(tmp_path, "b.iirds", broken)
    assert rule_id in fired, "the mutant must actually provoke its rule"

    repaired = MINIMAL_RDF.replace("</rdf:RDF>", NAMED % class_iri + "</rdf:RDF>")
    assert_parity(tmp_path, "r.iirds", repaired)


# ---------------------------------------------------------------------------
# 2. The cardinality pairs — two distinct values, then one.
# ---------------------------------------------------------------------------

from test_cardinality_rules_fire import PAIRS, _statement  # noqa: E402


@pytest.mark.parametrize("rule_id,cls,prop", PAIRS, ids=[p[0] for p in PAIRS])
def test_cardinality_parity_both_sides_of_the_line(rule_id, cls, prop, tmp_path):
    def metadata(count):
        body = "".join(_statement(prop, "v%d" % n) for n in range(count))
        element = ("  <rdf:Description rdf:about='urn:test:subject'>\n"
                   "    <rdf:type rdf:resource='%s'/>\n%s  </rdf:Description>\n" % (cls, body))
        return MINIMAL_RDF.replace("</rdf:RDF>", element + "</rdf:RDF>")

    fired = assert_parity(tmp_path, "two.iirds", metadata(2))
    assert rule_id in fired
    assert_parity(tmp_path, "one.iirds", metadata(1))


# ---------------------------------------------------------------------------
# 3. iiRDS/H — the conformant package, broken one requirement at a time.
# ---------------------------------------------------------------------------

from test_handover_rules_fire import HANDOVER, REMOVALS, _jsonld  # noqa: E402

H_EXTRA = (("content/doc1.pdf", b"%PDF-1.4"), ("index.html", "<html/>"))


def _h_parity(tmp_path, name, metadata):
    package = build_package(tmp_path, name, metadata=metadata, jsonld=_jsonld(metadata),
                            content=(), extra=H_EXTRA)
    py = {f.rule.id for f in runner.run(package, runner.ALL_KINDS).findings} & EMITTED
    severities = {}
    sh = shacl_fired(metadata, handover=True, severities=severities)
    assert sh == py, "SHACL %s vs Python %s" % (sorted(sh - py), sorted(py - sh))
    wrong = {rid: sevs for rid, sevs in severities.items()
             if sevs != {_SEV[_rule_severity(rid)]}}
    assert wrong == {}, wrong
    return py


def test_the_conformant_handover_package_is_silent_in_both_encodings(tmp_path):
    assert _h_parity(tmp_path, "clean.iirds", HANDOVER) == set()


H_CORE_REMOVALS = [(rid, line) for rid, line in REMOVALS if rid in EMITTED]


@pytest.mark.parametrize("rule_id,line", H_CORE_REMOVALS,
                         ids=[r for r, _ in H_CORE_REMOVALS])
def test_handover_removal_parity(rule_id, line, tmp_path):
    fired = _h_parity(tmp_path, "%s.iirds" % rule_id.replace(".", "_"),
                      HANDOVER.replace(line, "", 1))
    assert rule_id in fired


def test_forbidden_classes_fire_in_both_encodings(tmp_path):
    broken = HANDOVER.replace("</rdf:RDF>", """  <iirds:DirectoryNode rdf:about="urn:test:nav"/>
  <iirds:FragmentSelector rdf:about="urn:test:sel">
    <rdf:value>//x</rdf:value>
  </iirds:FragmentSelector>
</rdf:RDF>""")
    fired = _h_parity(tmp_path, "forbidden.iirds", broken)
    assert {"M15.11b", "M15.11c"} <= fired


# ---------------------------------------------------------------------------
# 4. The clean line-up: anchors across the three profiles.
# ---------------------------------------------------------------------------

from test_clean_realistic_package import METADATA as ANCHOR  # noqa: E402


def test_the_anchor_is_silent_in_both_encodings(tmp_path):
    py = python_fired(tmp_path, "anchor.iirds", ANCHOR, content=(),
                      extra=(("content/doc.xhtml", "<html xmlns='http://www.w3.org/1999/xhtml'><head><title>t</title></head><body><p>x</p></body></html>"),
                             ("content/t1.xhtml", "<html xmlns='http://www.w3.org/1999/xhtml'><head><title>t</title></head><body><p>x</p></body></html>"),
                             ("content/t2.xhtml", "<html xmlns='http://www.w3.org/1999/xhtml'><head><title>t</title></head><body><p>x</p></body></html>")))
    assert py == set()
    assert shacl_fired(ANCHOR) == set()


def test_the_anchor_under_profile_a_is_silent_in_both_encodings(tmp_path):
    metadata = ANCHOR.replace("<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
                              "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>"
                              "<iirds:formatRestriction>A</iirds:formatRestriction>")
    assert shacl_fired(metadata) == set()


# ---------------------------------------------------------------------------
# 5. The SPARQL shapes — a defect and its repair for every one.
# ---------------------------------------------------------------------------

HEAD_ = MINIMAL_RDF.replace("</rdf:RDF>", "")


def _meta(body: str) -> str:
    return HEAD_ + body + "</rdf:RDF>\n"


_PKG_BLOCK = """<iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:title>Test package</iirds:title>
  </iirds:Package>"""

SPARQL_CASES = [
    ("M3", MINIMAL_RDF.replace(_PKG_BLOCK, ""), MINIMAL_RDF),
    ("M17", _meta("""  <rdf:Description rdf:about="urn:test:topic1">
    <iirds:relates-to-component rdf:resource="http://example.com/p#Spindle"/>
  </rdf:Description>
"""), _meta("""  <rdf:Description rdf:about="urn:test:topic1">
    <iirds:relates-to-component rdf:resource="urn:test:c1"/>
  </rdf:Description>
  <iirds:Component rdf:about="urn:test:c1"><rdfs:label xml:lang="en">C</rdfs:label></iirds:Component>
""")),
    ("M18", _meta("""  <rdf:Description rdf:about="urn:test:topic1">
    <iirds:relates-to-product-variant rdf:resource="http://example.com/p#X"/>
  </rdf:Description>
"""), _meta("""  <rdf:Description rdf:about="urn:test:topic1">
    <iirds:relates-to-product-variant rdf:resource="urn:test:v1"/>
  </rdf:Description>
  <iirds:ProductVariant rdf:about="urn:test:v1"><rdfs:label xml:lang="en">V</rdfs:label></iirds:ProductVariant>
""")),
    ("M19.4", _meta("""  <iirds:Identity rdf:about="urn:test:i1">
    <iirds:identifier>X</iirds:identifier>
    <iirds:has-identity-domain rdf:resource="urn:test:d1"/>
  </iirds:Identity>
  <iirds:Component rdf:about="urn:test:d1"><rdfs:label xml:lang="en">nd</rdfs:label></iirds:Component>
"""), _meta("""  <iirds:Identity rdf:about="urn:test:i1">
    <iirds:identifier>X</iirds:identifier>
    <iirds:has-identity-domain rdf:resource="urn:test:d1"/>
  </iirds:Identity>
  <iirds:IdentityDomain rdf:about="urn:test:d1"><rdfs:label xml:lang="en">D</rdfs:label></iirds:IdentityDomain>
""")),
    ("M22.2", _meta("""  <iirds:Party rdf:about="urn:test:p1">
    <iirds:has-party-role rdf:resource="urn:test:r1"/>
  </iirds:Party>
  <iirds:Component rdf:about="urn:test:r1"><rdfs:label xml:lang="en">nr</rdfs:label></iirds:Component>
"""), _meta("""  <iirds:Party rdf:about="urn:test:p1">
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>
  </iirds:Party>
""")),
    # R10 is M22.2's shape one property over, so the pair is written the same
    # way: a status pointing at something that is described and is not a status
    # value, against one pointing at the ontology's own term.
    ("R10", _meta("""  <iirds:ContentLifeCycleStatus rdf:about="urn:test:s1">
    <iirds:has-content-lifecycle-status-value rdf:resource="urn:test:v1"/>
  </iirds:ContentLifeCycleStatus>
  <iirds:Component rdf:about="urn:test:v1"><rdfs:label xml:lang="en">nv</rdfs:label></iirds:Component>
"""), _meta("""  <iirds:ContentLifeCycleStatus rdf:about="urn:test:s1">
    <iirds:has-content-lifecycle-status-value rdf:resource="http://iirds.tekom.de/iirds#Approved"/>
  </iirds:ContentLifeCycleStatus>
""")),
    ("M24.6", _meta("""  <iirds:DirectoryNode rdf:about="urn:test:n1">
    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:DirectoryNode>
"""), _meta("""  <iirds:DirectoryNode rdf:about="urn:test:root">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-first-child rdf:resource="urn:test:n1"/>
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n1">
    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
  </iirds:DirectoryNode>
""")),
    ("M30", _meta("""  <rdf:Description rdf:about="http://iirds.tekom.de/iirds#Component">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#InformationObject"/>
  </rdf:Description>
"""), _meta("""  <rdf:Description rdf:about="http://iirds.tekom.de/iirds#Component">
    <rdfs:subClassOf rdf:resource="http://example.com/p#Part"/>
  </rdf:Description>
""")),
    ("M16.3", _meta("""  <rdf:Description rdf:about="http://example.com/e#Overheat">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Event"/>
  </rdf:Description>
"""), _meta("""  <rdf:Description rdf:about="http://example.com/e#Overheat">
    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Event"/>
  </rdf:Description>
""")),
    ("M1", _meta("""  <iirds:InformationUnit rdf:about="urn:test:iu1">
    <iirds:title>direct</iirds:title>
  </iirds:InformationUnit>
"""), MINIMAL_RDF),
    ("M12", _meta("""  <iirds:Selector rdf:about="urn:test:sel1"/>
"""), _meta("""  <iirds:FragmentSelector rdf:about="urn:test:sel1">
    <rdf:value>//x</rdf:value>
    <dcterms:conformsTo xmlns:dcterms="http://purl.org/dc/terms/" rdf:resource="http://www.w3.org/TR/xpath/"/>
  </iirds:FragmentSelector>
""")),
    ("L10", _meta("""  <iirds:Qualification rdf:about="urn:test:q1">
    <rdfs:label xml:lang="en">Tech</rdfs:label>
  </iirds:Qualification>
"""), _meta("""  <iirds:Role rdf:about="urn:test:q1">
    <rdfs:label xml:lang="en">Tech</rdfs:label>
  </iirds:Role>
""")),
    ("M5", _meta("""  <iirds:Component rdf:about="component/spindle">
    <rdfs:label xml:lang="en">Spindle</rdfs:label>
  </iirds:Component>
"""), _meta("""  <iirds:Component rdf:about="urn:test:spindle">
    <rdfs:label xml:lang="en">Spindle</rdfs:label>
  </iirds:Component>
""")),
]


@pytest.mark.parametrize("rule_id,broken,repaired", SPARQL_CASES,
                         ids=[c[0] for c in SPARQL_CASES])
def test_sparql_shape_parity_on_defect_and_repair(rule_id, broken, repaired, tmp_path):
    fired = assert_parity(tmp_path, "broken.iirds", broken)
    assert rule_id in fired, "the defect must actually provoke its rule"
    assert_parity(tmp_path, "repaired.iirds", repaired)


def test_m15_11a_parity_in_the_handover_profile(tmp_path):
    broken = HANDOVER.replace("</rdf:RDF>", """  <iirds:Topic rdf:about="urn:test:t9">
    <iirds:title>Not allowed in H</iirds:title>
  </iirds:Topic>
</rdf:RDF>""")
    fired = _h_parity(tmp_path, "m15_11a.iirds", broken)
    assert "M15.11a" in fired


# ---------------------------------------------------------------------------
# 6. Tier 2: the whole vendored corpus, both encodings, every parsable file.
# ---------------------------------------------------------------------------

import vendor_corpus  # noqa: E402
from crossvalidate import wrap  # noqa: E402
from iirds_validate.registry import all_rules  # noqa: E402

RULES_BY_ID = {r.id: r for r in all_rules()}
CORPUS_MANIFEST = json.loads(vendor_corpus.MANIFEST.read_text("utf-8"))


def _applicable(effective_version: str, variant: str) -> set:
    out = set()
    for rid in EMITTED:
        rule = RULES_BY_ID[rid]
        if rule.versions and effective_version not in rule.versions:
            continue
        if "H" in (rule.variants or ()) and variant != "H":
            continue
        out.add(rid)
    return out


#: What the applicability mask hides, named file by file. The shapes are
#: deliberately version-blind (one edition, 1.3, no runtime switch), so on a
#: corpus file declaring an older edition they fire rules Python rightly
#: skips. Masking that difference is correct; masking it *silently* is how
#: the review hid seven files\' divergence from us. Any change to
#: this dict -- growth or shrinkage -- must arrive as a deliberate edit here.
VERSION_GATED_EXTRAS = {
    "M96-1_false.rdf": ["M96.1"],
    "M96-2_false.rdf": ["M96.2"],
    "M96-3_false.rdf": ["M96.3"],
    "M96-4_false.rdf": ["M96.3"],
    "M97-1_false.rdf": ["M96.3", "M97.1", "M97.2"],
    "M97-2_false.rdf": ["M96.3"],
    "metadata_iirds_sample-M9_false.rdf": ["M8"],
    # The corpus's one self-looping package. Section 6.3.3 is 1.3-only in
    # the cached specification and this file declares 1.0, so the rule
    # stands down here while the shape, which has no version, does not.
    "metadata_iirds_sample-M5_false.rdf": ["R5"],
}


def test_the_whole_corpus_agrees_between_encodings(tmp_path):
    """117 parsable reference fixtures, rule-set equality per file. The same
    corpus that cross-validates the Python rules against plusmeta now
    cross-validates the shapes against the Python rules."""
    disagreements = []
    checked = 0
    rdflib_rejects = []
    masked = {}
    for name, meta in sorted(CORPUS_MANIFEST["files"].items()):
        if meta["parses"] not in ("ok", "needs_namespace_wrapper"):
            continue
        raw = (vendor_corpus.FILES / name).read_bytes()
        if meta["parses"] == "needs_namespace_wrapper":
            text = raw.decode("utf-8", "replace")
            body = text.split("?>", 1)[1] if text.lstrip().startswith("<?xml") else text
            raw = (vendor_corpus.NAMESPACE_WRAPPER % body).encode("utf-8")

        package = wrap(raw, tmp_path / ("c%d.iirds" % checked))
        report = runner.run(package, runner.ALL_KINDS)
        applicable = _applicable(report.effective_version, report.variant)
        python_ids = {f.rule.id for f in report.findings} & applicable

        try:
            data = Graph().parse(data=raw.decode("utf-8", "replace"), format="xml",
                                 publicID=PACKAGE_BASE)
        except Exception:
            # rdflib's RDF/XML reader is stricter than ElementTree (and one of
            # its error paths crashes outright). The Python side survives these
            # because build_graph catches the failure and reports it — there is
            # no graph for either encoding to disagree about. Counted and
            # pinned below, never silently skipped.
            rdflib_rejects.append(name)
            continue
        shapes = CORE_H if report.variant == "H" else CORE
        _ok, results, _ = pyshacl.validate(data, shacl_graph=shapes,
                                           advanced=True, inference="none")
        shacl_ids = set()
        for _r, _p, source in results.triples((None, SH.sourceShape, None)):
            shacl_ids.add(str(source).rsplit("#", 1)[-1].split("-p")[0])
        SH_FIRED_EVER.update(shacl_ids)
        extra = sorted(shacl_ids - applicable)
        if extra:
            masked[name] = extra
        shacl_ids &= applicable

        if shacl_ids != python_ids:
            disagreements.append((name[:60], sorted(shacl_ids - python_ids),
                                  sorted(python_ids - shacl_ids)))
        checked += 1

    assert checked == 114, checked   # 117 parsable - the 3 pinned rejects
    # Named, not merely bounded: "<= 5" would let two more files drop out of
    # the comparison without anyone saying so. These three trip an
    # rdflib RDF/XML error path; the Python side still validates them because
    # build_graph reports the parse failure as a finding.
    assert sorted(rdflib_rejects) == [
        "Example 46 - Tagging.rdf",
        "metadata_iirds_sample_pass-M77_false.rdf",
        "metadata_iirds_sample_pass-M77_true.rdf",
    ], rdflib_rejects
    assert disagreements == [], disagreements[:8]
    assert masked == VERSION_GATED_EXTRAS


# ---------------------------------------------------------------------------
# 6b. Provocations for the shapes nothing else reaches.
#
# The coverage test below found these five sitting out the entire suite --
# three of them exactly the shapes the review proved wrong and
# this campaign repaired. A repair that is never provoked is indistinguishable
# from the defect it replaced.
# ---------------------------------------------------------------------------

_NIL = 'rdf:resource="http://iirds.tekom.de/iirds#nil"'

_TOC = _meta("""  <iirds:DirectoryNode rdf:about="urn:test:root">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-first-child rdf:resource="urn:test:n1"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n1">
    <iirds:has-next-sibling rdf:resource="urn:test:n2"/>
    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n2">
    <iirds:has-next-sibling %s/>
    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:DirectoryNode>
""" % _NIL)

PROVOCATIONS = [
    # S4: the version literal is checked after strip() in Python, so the
    # repair is deliberately padded -- whitespace tolerance is part of parity.
    ("S4", MINIMAL_RDF.replace(">1.3<", ">9.9<"),
           MINIMAL_RDF.replace(">1.3<", "> 1.3 <")),
    ("S5", MINIMAL_RDF.replace("</iirds:Package>",
        "  <iirds:formatRestriction>X</iirds:formatRestriction>\n  </iirds:Package>"),
          MINIMAL_RDF.replace("</iirds:Package>",
        "  <iirds:formatRestriction> A </iirds:formatRestriction>\n  </iirds:Package>")),
    # M25: a sibling chain that just stops, against one terminated at nil.
    ("M25", _TOC.replace('    <iirds:has-next-sibling %s/>\n' % _NIL, ""), _TOC),
    # M27: the level's first child must head its list -- nothing may reach it
    # via has-next-sibling. (Python has no nil exemption here; neither may we.)
    ("M27", _TOC.replace('<iirds:DirectoryNode rdf:about="urn:test:n1">',
        '''<iirds:DirectoryNode rdf:about="urn:test:n0">
    <iirds:has-next-sibling rdf:resource="urn:test:n1"/>
    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n1">'''), _TOC),
    # M24.5: a child claiming to be a root.
    ("M24.5", _TOC.replace('<iirds:DirectoryNode rdf:about="urn:test:n1">',
        '<iirds:DirectoryNode rdf:about="urn:test:n1">\n'
        '    <iirds:has-directory-structure-type '
        'rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>'), _TOC),
]

# The ontology says iirds:nil is a subclass of iirds:DirectoryNode, so a node
# *typed* iirds:nil is a directory node to Python's ontology closure -- and
# must be one to the shapes too. The review found the old shapes
# blind to exactly this; a child typed nil that claims the root's structure
# type has to fire M24.5 in both encodings or the closure mirror is a fiction.
PROVOCATIONS.append(("M24.5-typed-nil", _TOC.replace(
    '''<iirds:DirectoryNode rdf:about="urn:test:n1">
    <iirds:has-next-sibling rdf:resource="urn:test:n2"/>''',
    '''<iirds:nil rdf:about="urn:test:n1">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-next-sibling rdf:resource="urn:test:n2"/>''').replace(
    '''    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n2">''',
    '''    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:nil>
  <iirds:DirectoryNode rdf:about="urn:test:n2">''', 1), _TOC))


@pytest.mark.parametrize("rule_id,broken,repaired", PROVOCATIONS,
                         ids=[c[0] for c in PROVOCATIONS])
def test_provocation_parity_on_defect_and_repair(rule_id, broken, repaired, tmp_path):
    rid = rule_id.split("-")[0]
    assert rid in assert_parity(tmp_path, "broken.iirds", broken)
    assert rid not in assert_parity(tmp_path, "repaired.iirds", repaired)


# ---------------------------------------------------------------------------
# 6c. The review's disagreement archetypes, kept as fixtures.
#
# Each of these is a place where the two encodings used to give different
# answers. The repairs made them agree; these pin the agreement so it cannot
# quietly rot. The assertion of record is assert_parity's set equality --
# the named rule is only the reason the fixture exists.
# ---------------------------------------------------------------------------

def test_a_leading_slash_is_absolute_in_both_encodings(tmp_path):
    # Python: '://' in value OR value.startswith('/'). The old shape knew only
    # the first half, so /abs/topic.xhtml fired Python-only.
    fired = assert_parity(tmp_path, "slash.iirds",
                          MINIMAL_RDF.replace(">content/topic1.xhtml<",
                                              ">/content/topic1.xhtml<"))
    assert "M9" in fired


def test_namespace_lookalikes_fool_neither_encoding(tmp_path):
    # is_iirds_term is startswith on the four exact namespaces, '#' included.
    # The old shapes matched on a broader prefix, so a term minted under
    # .../iirdsx# counted as an iiRDS term to SHACL and not to Python.
    lookalike = MINIMAL_RDF.replace(
        "</rdf:RDF>",
        '''  <rdf:Description rdf:about="http://iirds.tekom.de/iirdsx#Widget">
    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:topic1">
    <rdf:type rdf:resource="http://iirds.tekom.de/iirdsx#Widget"/>
  </rdf:Description>
</rdf:RDF>''')
    assert_parity(tmp_path, "lookalike.iirds", lookalike)


def test_m15_5_fires_on_two_information_objects_as_well_as_none(tmp_path):
    # "Exactly one" has two failure directions. The removal fixtures walk the
    # zero side; the old shape had sh:qualifiedMinCount only, so the two side
    # fired Python-only.
    doubled = HANDOVER.replace(
        '<iirds:is-version-of rdf:resource="urn:test:io1"/>',
        '<iirds:is-version-of rdf:resource="urn:test:io1"/>\n'
        '    <iirds:is-version-of rdf:resource="urn:test:io2"/>')
    doubled = doubled.replace(
        '</iirds:InformationObject>',
        '''</iirds:InformationObject>

  <iirds:InformationObject rdf:about="urn:test:io2">
    <iirds:title>Operating instructions, second object</iirds:title>
    <iirds:relates-to-party rdf:resource="urn:test:party-creator"/>
  </iirds:InformationObject>''', 1)
    fired = _h_parity(tmp_path, "two_ios.iirds", doubled)
    assert "M15.5" in fired


def test_a_proprietary_subclass_is_its_parent_in_both_encodings(tmp_path):
    # iiRDS section 7: proprietary classes subclass iiRDS classes, and a
    # consumer processes them as the parent. SHACL gets this by definition
    # (targetClass follows the data graph's rdfs:subClassOf); Python's closure
    # originally walked only the bundled ontology and was blind. This fixture
    # caught that as a SHACL-only L7 -- the differential gate arguing with
    # its own author -- and now pins the repaired agreement: the untitled
    # instance below is an information unit to both encodings.
    subclassed = MINIMAL_RDF.replace(
        "</rdf:RDF>",
        '''  <rdf:Description rdf:about="urn:acme:SpecialTopic">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Topic"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:special1">
    <rdf:type rdf:resource="urn:acme:SpecialTopic"/>
  </rdf:Description>
</rdf:RDF>''')
    assert "L7" in assert_parity(tmp_path, "subclass.iirds", subclassed)


def test_a_proprietary_package_is_exempt_in_both_encodings(tmp_path):
    # The other direction of the same reading, and the one the test above
    # cannot reach. L7 exempts iirds:Package -- a package is not a thing
    # with a title in the sense the rule means -- and SHACL gets that
    # exemption by definition too, because sh:class follows the data
    # graph's rdfs:subClassOf. Python compared rdf:type values, so a
    # package typed with a subclass it declares itself lost the exemption
    # and was reported for having no title while the shapes stayed silent.
    subclassed = MINIMAL_RDF.replace(
        '  <iirds:Package rdf:about="urn:test:package">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '    <iirds:title>Test package</iirds:title>\n'
        '  </iirds:Package>\n',
        '  <rdf:Description rdf:about="urn:acme:DeliveryPackage">\n'
        '    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Package"/>\n'
        '  </rdf:Description>\n'
        '  <rdf:Description rdf:about="urn:test:package">\n'
        '    <rdf:type rdf:resource="urn:acme:DeliveryPackage"/>\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '  </rdf:Description>\n')
    assert "L7" not in assert_parity(tmp_path, "pkgsubclass.iirds", subclassed)


# ---------------------------------------------------------------------------
# 6d. Divergences, pinned. The first repair fixed eighteen instances;
# a later review found the *classes* those instances belonged to
# still alive elsewhere. Each case here disagreed between encodings on
# 2026-08-21 and now must agree forever.
# ---------------------------------------------------------------------------

def test_s4_tolerates_the_whitespace_a_pretty_printer_emits(tmp_path):
    # An indenting serialiser pads with newlines and tabs; " *" rejected a
    # conformant package -- the worst direction for a validator to be wrong.
    padded = MINIMAL_RDF.replace(">1.3<", ">\n      1.3\n    <")
    assert "S4" not in assert_parity(tmp_path, "pretty.iirds", padded)
    nbsp = MINIMAL_RDF.replace(">1.3<", ">\u00a01.3\u00a0<")
    assert "S4" not in assert_parity(tmp_path, "nbsp.iirds", nbsp)


def test_s5_reads_an_empty_restriction_as_unrestricted(tmp_path):
    empty = MINIMAL_RDF.replace(
        "</iirds:Package>",
        "  <iirds:formatRestriction></iirds:formatRestriction>\n  </iirds:Package>")
    assert "S5" not in assert_parity(tmp_path, "empty.iirds", empty)
    tabbed = MINIMAL_RDF.replace(
        "</iirds:Package>",
        "  <iirds:formatRestriction>\tA\t</iirds:formatRestriction>\n  </iirds:Package>")
    assert "S5" not in assert_parity(tmp_path, "tabbed.iirds", tabbed)


def test_m5_ignores_types_from_a_lookalike_namespace(tmp_path):
    # The bare-domain STRSTARTS survived in M5 after the same defect was
    # repaired in M30/M16.3/M22.2 -- fixing instances, not the class.
    lookalike = MINIMAL_RDF.replace("</rdf:RDF>", '''  <rdf:Description rdf:about="component/spindle">
    <rdf:type rdf:resource="http://iirds.tekom.de/iirdsx#Widget"/>
  </rdf:Description>
</rdf:RDF>''')
    assert "M5" not in assert_parity(tmp_path, "lookalike5.iirds", lookalike)


def test_m17_counts_a_proprietary_component_subclass_as_declared(tmp_path):
    subclassed = MINIMAL_RDF.replace("</rdf:RDF>", '''  <rdf:Description rdf:about="urn:test:topic1">
    <iirds:relates-to-component rdf:resource="urn:test:c1"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:acme:MyComp">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Component"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:c1">
    <rdf:type rdf:resource="urn:acme:MyComp"/>
    <rdfs:label xml:lang="en">C</rdfs:label>
  </rdf:Description>
</rdf:RDF>''')
    assert "M17" not in assert_parity(tmp_path, "subcomp.iirds", subclassed)


_MY_NODE = '''  <rdf:Description rdf:about="urn:acme:MyNode">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#DirectoryNode"/>
  </rdf:Description>
'''


def test_m24_6_sees_a_proprietary_directory_node_in_both_roles(tmp_path):
    # Hardcoded type pairs diverged in both directions: a subclassed node
    # with no root fired Python-only; the same node *as* the root fired
    # SHACL-only. The closure path answers both.
    rootless = MINIMAL_RDF.replace("</rdf:RDF>", _MY_NODE + '''  <rdf:Description rdf:about="urn:test:lone">
    <rdf:type rdf:resource="urn:acme:MyNode"/>
  </rdf:Description>
</rdf:RDF>''')
    assert "M24.6" in assert_parity(tmp_path, "rootless.iirds", rootless)

    rooted = MINIMAL_RDF.replace("</rdf:RDF>", _MY_NODE + '''  <rdf:Description rdf:about="urn:test:root">
    <rdf:type rdf:resource="urn:acme:MyNode"/>
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-first-child rdf:resource="urn:test:n1"/>
  </rdf:Description>
  <iirds:DirectoryNode rdf:about="urn:test:n1">
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:DirectoryNode>
</rdf:RDF>''')
    assert "M24.6" not in assert_parity(tmp_path, "rooted.iirds", rooted)


def test_m22_2_catches_a_misspelled_role_inside_the_real_namespace(tmp_path):
    # The namespace-prefix exemption hid exactly the typo this rule exists
    # to catch. The defined-terms list does not.
    typo = MINIMAL_RDF.replace("</rdf:RDF>", '''  <iirds:Party rdf:about="urn:test:party1">
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#NotARealTerm"/>
  </iirds:Party>
  <rdf:Description rdf:about="http://iirds.tekom.de/iirds#NotARealTerm">
    <rdfs:label xml:lang="en">looks official, is not</rdfs:label>
  </rdf:Description>
</rdf:RDF>''')
    fired = assert_parity(tmp_path, "typo.iirds", typo)
    assert "M22.2" in fired


def test_m22_2_accepts_a_proprietary_party_role_subclass(tmp_path):
    subclassed = MINIMAL_RDF.replace("</rdf:RDF>", '''  <rdf:Description rdf:about="urn:acme:ChiefRole">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#PartyRole"/>
  </rdf:Description>
  <iirds:Party rdf:about="urn:test:party1">
    <iirds:has-party-role rdf:resource="urn:test:role1"/>
  </iirds:Party>
  <rdf:Description rdf:about="urn:test:role1">
    <rdf:type rdf:resource="urn:acme:ChiefRole"/>
  </rdf:Description>
</rdf:RDF>''')
    assert "M22.2" not in assert_parity(tmp_path, "chief.iirds", subclassed)


def test_m15_5_counts_a_proprietary_information_object_subclass(tmp_path):
    # Python used exact typing where the shape used sh:class; section 7 says
    # the shape was right. Fixed in the rule, pinned here in H parity.
    subclassed = HANDOVER.replace(
        '<iirds:InformationObject rdf:about="urn:test:io1">',
        '''<rdf:Description rdf:about="urn:acme:SpecialIO">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#InformationObject"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:io1">
    <rdf:type rdf:resource="urn:acme:SpecialIO"/>''').replace(
        '</iirds:InformationObject>', '</rdf:Description>')
    fired = _h_parity(tmp_path, "subio.iirds", subclassed)
    assert "M15.5" not in fired


def test_m15_11a_sees_a_topic_typed_with_a_package_subclass(tmp_path):
    """The profile excludes topics because a receiving system should not have
    to understand them. Section 7 says an instance of a package's own subclass
    of iirds:Topic is a Topic, so exact typing let the excluded thing in by
    the one route the standard explicitly sanctions."""
    subclassed = HANDOVER.replace("</rdf:RDF>", '''  <rdf:Description rdf:about="urn:acme:HowTo">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Topic"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:howto1">
    <rdf:type rdf:resource="urn:acme:HowTo"/>
    <iirds:title>How to change the filter</iirds:title>
  </rdf:Description>
</rdf:RDF>''')
    assert "M15.11a" in _h_parity(tmp_path, "subtopic.iirds", subclassed)


def test_m19_4_accepts_a_proprietary_identity_domain_subclass(tmp_path):
    """The mirror image: a type test that demands the parent verbatim reports
    a package for doing what section 7 sanctions."""
    subclassed = MINIMAL_RDF.replace("</rdf:RDF>", '''  <rdf:Description rdf:about="urn:acme:PlantDomain">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#IdentityDomain"/>
  </rdf:Description>
  <iirds:Identity rdf:about="urn:test:identity1">
    <iirds:identifier>X1</iirds:identifier>
    <iirds:has-identity-domain rdf:resource="urn:test:domain1"/>
  </iirds:Identity>
  <rdf:Description rdf:about="urn:test:domain1">
    <rdf:type rdf:resource="urn:acme:PlantDomain"/>
  </rdf:Description>
</rdf:RDF>''')
    assert "M19.4" not in assert_parity(tmp_path, "subdomain.iirds", subclassed)


# ---------------------------------------------------------------------------
# 6e. The five named-party MUSTs and their softening.
#
# Deferred at first release as "the subtlest readings in the codebase"; now
# that they are shapes, the subtlety itself is pinned: a party whose vCard
# this package does not describe passes all five (the pointer is reported
# once, by R4, rather than five times by these). Both encodings must hold
# that reading, or the shapes fail conformant packages the CLI passes -- and
# both must report the pointer, which is the half that went missing for a
# release: it belonged to a lint, so `check` said nothing at all.
# ---------------------------------------------------------------------------

def test_an_undescribed_vcard_soft_passes_the_named_party_musts(tmp_path):
    softened = HANDOVER.replace('''  <vcard:Organization rdf:about="urn:test:supplier-card">
    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>
  </vcard:Organization>''', "")
    fired = _h_parity(tmp_path, "soft.iirds", softened)
    assert fired & {"M15.7b", "M15.7d", "M15.8", "M15.9", "M15.10"} == set()
    assert "R4" in fired


def test_any_card_semantics_one_named_one_nameless_stays_silent(tmp_path):
    # An "all cards must be named" mis-encoding survives the other pins;
    # this one kills it.
    extra = HANDOVER.replace(
        '<iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>',
        '<iirds:relates-to-vcard rdf:resource="urn:test:supplier-card"/>\n'
        '    <iirds:relates-to-vcard rdf:resource="urn:test:bare-card"/>', 1)
    extra = extra.replace("</rdf:RDF>", '''  <rdf:Description rdf:about="urn:test:bare-card">
    <rdf:type rdf:resource="http://www.w3.org/2006/vcard/ns#Organization"/>
  </rdf:Description>
</rdf:RDF>''')
    fired = _h_parity(tmp_path, "mixed_cards.iirds", extra)
    assert fired & {"M15.7b", "M15.7d", "M15.8", "M15.9", "M15.10"} == set()


def test_a_roleless_party_with_a_good_card_does_not_leak_across_parties(tmp_path):
    # A UNION branch that binds its card from a free variable instead of the
    # role-holding party would soft-pass here; both encodings must fire.
    leaky = HANDOVER.replace(
        "    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>\n", ""
    ).replace("</rdf:RDF>", '''  <iirds:Party rdf:about="urn:test:bystander">
    <iirds:relates-to-vcard rdf:resource="urn:test:ghost-card"/>
  </iirds:Party>
</rdf:RDF>''')
    fired = _h_parity(tmp_path, "bystander.iirds", leaky)
    assert {"M15.7b", "M15.7d", "M15.8", "M15.9", "M15.10"} <= fired


def test_a_described_vcard_without_a_name_fails_them_in_both_encodings(tmp_path):
    # The other side of the softening: described-but-nameless is the real
    # defect, and it must fire everywhere the chain is required.
    nameless = HANDOVER.replace(
        "    <vcard:organization-name>Rotor Works GmbH</vcard:organization-name>\n", "")
    fired = _h_parity(tmp_path, "nameless.iirds", nameless)
    assert {"M15.7b", "M15.7d", "M15.8", "M15.9", "M15.10"} <= fired


def test_m3_sees_a_subclass_typed_package_in_both_directions(tmp_path):
    # M3 was still testing bare rdf:type after five sibling rules got the
    # section-7 repair -- and in the false-reject
    # direction: a conformant package typed via its own declared subclass
    # failed SHACL-only. Both directions pinned.
    subclass_decl = '''  <rdf:Description rdf:about="urn:acme:DeliveryPackage">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Package"/>
  </rdf:Description>
'''
    retyped = MINIMAL_RDF.replace(
        '<iirds:Package rdf:about="urn:test:package">',
        subclass_decl + '  <rdf:Description rdf:about="urn:test:package">\n'
        '    <rdf:type rdf:resource="urn:acme:DeliveryPackage"/>').replace(
        "</iirds:Package>", "</rdf:Description>")
    assert "M3" not in assert_parity(tmp_path, "sub_pkg.iirds", retyped)

    second = MINIMAL_RDF.replace("</rdf:RDF>", subclass_decl + '''  <rdf:Description rdf:about="urn:test:package2">
    <rdf:type rdf:resource="urn:acme:DeliveryPackage"/>
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:title>Second, subclass-typed</iirds:title>
  </rdf:Description>
</rdf:RDF>''')
    assert "M3" in assert_parity(tmp_path, "two_pkg.iirds", second)


def test_m25_accepts_a_terminator_the_package_mints(tmp_path):
    """"relating to an instance of the class iirds:nil" is the requirement's
    own wording, and iirds:nil really is a class -- so a package that mints its
    own terminator and types it is doing what the sentence says. Python reads
    it that way. The shape's identity test is `sh:in ( iirds:nil )`, which is
    the node and not the class, so the minted terminator falls through to the
    branch that demands a sibling of the end of the list."""
    minted = _TOC.replace('rdf:resource="http://iirds.tekom.de/iirds#nil"',
                          'rdf:resource="urn:test:end"').replace(
        "</rdf:RDF>", '''  <iirds:nil rdf:about="urn:test:end"/>
</rdf:RDF>''')
    assert "M25" not in assert_parity(tmp_path, "minted.iirds", minted)


# ---------------------------------------------------------------------------
# The archetype set-equality cannot catch
#
# Both encodings read the bare presence of iirds:is-part-of-package as
# nesting, so both granted the exemption and this gate saw nothing: it
# compares the two against each other, and two readings that are wrong the
# same way agree. What it can catch is the two drifting apart while that is
# repaired, which is what these fixtures are for -- there was no fixture
# anywhere combining a self-loop with anything else.
# ---------------------------------------------------------------------------

def test_a_self_loop_is_not_nesting_in_either_encoding(tmp_path):
    """§6.2: the container's instance "MUST NOT be a member of *another*
    iiRDS package". Naming itself is not membership in another package, so
    the exemption §6.3 grants a nested child does not reach it."""
    self_loop = MINIMAL_RDF.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        '    <iirds:is-part-of-package rdf:resource="urn:test:package"/>\n').replace(
        "</rdf:RDF>",
        '  <rdf:Description rdf:about="urn:test:package">\n'
        '    <iirds:has-rendition rdf:resource="urn:test:elsewhere"/>\n'
        '  </rdf:Description>\n</rdf:RDF>')
    assert "M8" in assert_parity(tmp_path, "self_m8.iirds", self_loop)

    nested = self_loop.replace(
        'rdf:resource="urn:test:package"/>',
        'rdf:resource="urn:test:outer"/>', 1).replace(
        "</rdf:RDF>",
        '  <iirds:Package rdf:about="urn:test:outer">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '  </iirds:Package>\n</rdf:RDF>')
    assert "M8" not in assert_parity(tmp_path, "nested_m8.iirds", nested), (
        "a package that really is part of another one is content, and content "
        "renders")


def test_a_self_loop_beside_a_real_package_is_two_containers_in_both_encodings(tmp_path):
    """The other rule reading the same predicate. One self-looping package
    and one ordinary one are two packages representing this container."""
    two = MINIMAL_RDF.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        '    <iirds:is-part-of-package rdf:resource="urn:test:package"/>\n').replace(
        "</rdf:RDF>",
        '  <iirds:Package rdf:about="urn:test:second">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '  </iirds:Package>\n</rdf:RDF>')
    assert "M3" in assert_parity(tmp_path, "self_m3.iirds", two)

    child = two.replace('rdf:resource="urn:test:package"/>',
                        'rdf:resource="urn:test:second"/>', 1)
    assert "M3" not in assert_parity(tmp_path, "child_m3.iirds", child), (
        "one package inside the other leaves one representing this container")


#: The same five ways of naming a parent that is not one, as metadata bodies.
NOT_A_PARENT_SHAPES = {
    "absent": '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n',
    "a-topic": '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n',
    "a-literal": '    <iirds:is-part-of-package>urn:test:outer</iirds:is-part-of-package>\n',
    "a-blank-node": '    <iirds:is-part-of-package><rdf:Description/></iirds:is-part-of-package>\n',
    "self-and-absent": '    <iirds:is-part-of-package rdf:resource="urn:test:package"/>\n'
                       '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n',
}
EXTRA = {"a-topic": '  <iirds:Topic rdf:about="urn:test:outer"/>\n'}


def _with_parent(shape, tail=""):
    return MINIMAL_RDF.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n" + NOT_A_PARENT_SHAPES[shape]
    ).replace("</rdf:RDF>", EXTRA.get(shape, "") + tail + "</rdf:RDF>")


RENDERS = ('  <rdf:Description rdf:about="urn:test:package">\n'
           '    <iirds:has-rendition rdf:resource="urn:test:elsewhere"/>\n'
           '  </rdf:Description>\n')
SECOND = ('  <iirds:Package rdf:about="urn:test:second">\n'
          '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
          '  </iirds:Package>\n')

#: The same, except the second package also names a parent that is not one.
#: M3's query asks for two container packages and tests each side separately,
#: so a *clean* second package satisfies either side on its own and neither
#: class test is pinned by it. Here every package carries a bogus parent, so
#: dropping either test empties the set that side selects and the finding
#: disappears -- which is what makes both of them load-bearing.
SECOND_ALSO_BOGUS = ('  <iirds:Package rdf:about="urn:test:second">\n'
                     '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
                     '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n'
                     '  </iirds:Package>\n')


@pytest.mark.parametrize("shape", sorted(NOT_A_PARENT_SHAPES), ids=sorted(NOT_A_PARENT_SHAPES))
def test_a_parent_that_is_not_a_package_exempts_nothing_in_either_encoding(tmp_path, shape):
    """Both encodings read the predicate, so both granted the exemption to any
    object at all -- and agreeing about it is why the gate saw nothing."""
    assert "M8" in assert_parity(tmp_path, "np8_%s.iirds" % shape,
                                 _with_parent(shape, RENDERS))


@pytest.mark.parametrize("shape", sorted(NOT_A_PARENT_SHAPES), ids=sorted(NOT_A_PARENT_SHAPES))
def test_a_parent_that_is_not_a_package_leaves_two_containers_in_either_encoding(tmp_path, shape):
    """M3 reads the same predicate. This is the pair that catches its SPARQL
    being left behind when the Python moves."""
    assert "M3" in assert_parity(tmp_path, "np3_%s.iirds" % shape,
                                 _with_parent(shape, SECOND))


def test_a_parent_that_is_not_a_package_does_not_borrow_its_own_parents_type(tmp_path):
    """The operator pin. The focus is a Package that renders; its parent is an
    iirds:Topic; that Topic is itself part of a real Package. §6.3.3 asks the
    child to reference an iirds:Package -- one hop, not a chain. A zero-or-more
    path walks the chain, finds two Packages among the value nodes and exempts
    the focus, while the rule reports it. Zero-or-one is what makes the two
    agree, and this graph is the only thing in the suite that can tell them
    apart."""
    chain = _with_parent("a-topic", RENDERS).replace(
        '  <iirds:Topic rdf:about="urn:test:outer"/>\n',
        '  <iirds:Topic rdf:about="urn:test:outer">\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:grand"/>\n'
        '  </iirds:Topic>\n'
        '  <iirds:Package rdf:about="urn:test:grand">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '  </iirds:Package>\n')
    assert "M8" in assert_parity(tmp_path, "chain_m8.iirds", chain)


@pytest.mark.parametrize("shape", sorted(NOT_A_PARENT_SHAPES), ids=sorted(NOT_A_PARENT_SHAPES))
def test_both_of_m3s_class_tests_are_load_bearing(tmp_path, shape):
    """Every package here names a parent that is not one, so M3's query has
    to apply the class test on both sides to find its pair. With a clean
    second package -- the fixture above -- either side alone suffices and
    neither test is held."""
    assert "M3" in assert_parity(tmp_path, "m3both_%s.iirds" % shape,
                                 _with_parent(shape, SECOND_ALSO_BOGUS))


def test_the_content_of_a_nested_package_is_not_described_here_in_either_encoding(tmp_path):
    """§5.3: "An iiRDS package that contains a nested iiRDS package MUST NOT
    contain metadata about the content of the nested iiRDS package."

    Three graphs, because the third is the one that decides the encoding. A
    unit pointing at a package that is inside another package is the breach;
    a unit pointing at the package this container is about is the ordinary
    shape both Consortium samples use; and a unit pointing at a package that
    names *itself* is neither, because a self-loop is not membership in
    another package and container_packages keeps such a package as a root.
    That last clause is why the shape is SPARQL: comparing the value with the
    focus node is beyond Core, and without the comparison the shape would
    report a breach where Python is silent."""
    parent = ('  <iirds:Package rdf:about="urn:test:outer">\n'
              '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
              '  </iirds:Package>\n')
    child = ('  <iirds:Package rdf:about="urn:test:nested">\n'
             '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
             '    <iirds:is-part-of-package rdf:resource="urn:test:outer"/>\n'
             '  </iirds:Package>\n')

    def unit(target):
        return ('  <iirds:Topic rdf:about="urn:test:topic">\n'
                '    <iirds:title>A unit</iirds:title>\n'
                '    <iirds:is-part-of-package rdf:resource="%s"/>\n'
                '  </iirds:Topic>\n' % target)

    def graph(*blocks):
        return MINIMAL_RDF.replace("</rdf:RDF>", "".join(blocks) + "</rdf:RDF>")

    assert "R6" in assert_parity(
        tmp_path, "r6_nested.iirds", graph(parent, child, unit("urn:test:nested")))
    assert "R6" not in assert_parity(
        tmp_path, "r6_own.iirds", graph(parent, child, unit("urn:test:outer")))

    loop = ('  <iirds:Package rdf:about="urn:test:loop">\n'
            '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
            '    <iirds:is-part-of-package rdf:resource="urn:test:loop"/>\n'
            '  </iirds:Package>\n')
    assert "R6" not in assert_parity(
        tmp_path, "r6_loop.iirds", graph(loop, unit("urn:test:loop"))), (
        "a package inside itself is not inside another package; R5 answers for it")


def test_an_older_package_is_outside_what_the_shapes_encode(tmp_path):
    """The boundary of the differential gate, measured rather than described.

    The shapes carry no version gate -- they are the 1.3 rule set, which is
    what the directory they live in says -- so a package declaring an older
    edition draws every shape whose rule 1.3 added. The Python rules gate on
    the declared version and stay silent. Twenty-nine emitted shapes encode a
    rule that does not apply to every edition, so this is a boundary and not
    a one-off, and every other test in this file feeds 1.3 graphs, which is
    why nothing here had ever seen it.

    Pinned rather than repaired: gating a shape on iirds:iiRDSVersion would
    put an inference about editions inside an artefact whose whole point is
    that a SHACL engine can run it without this project's code. The repair
    that belongs here is saying so, which shapes/README.md and
    docs/divergences.md now do.
    """
    chain = MINIMAL_RDF.replace("</rdf:RDF>",
        '  <iirds:Package rdf:about="urn:test:a">\n'
        '    <iirds:iiRDSVersion>%(v)s</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:b"/>\n'
        '  </iirds:Package>\n'
        '  <iirds:Package rdf:about="urn:test:b">\n'
        '    <iirds:iiRDSVersion>%(v)s</iirds:iiRDSVersion>\n'
        '    <iirds:is-part-of-package rdf:resource="urn:test:c"/>\n'
        '  </iirds:Package>\n'
        '  <iirds:Package rdf:about="urn:test:c">\n'
        '    <iirds:iiRDSVersion>%(v)s</iirds:iiRDSVersion>\n'
        '  </iirds:Package>\n</rdf:RDF>')

    def graph(version):
        return (chain % {"v": version}).replace(
            "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
            "<iirds:iiRDSVersion>%s</iirds:iiRDSVersion>" % version, 1)

    assert "R5" in assert_parity(tmp_path, "edition_13.iirds", graph("1.3")), (
        "the two encodings agree on the edition the shapes are for")

    older = graph("1.2")
    assert "R5" not in python_fired(tmp_path, "edition_12.iirds", older), (
        "R5 is gated to 1.3 because that is the only edition on hand carrying "
        "the sentence")
    assert "R5" in shacl_fired(older), (
        "if this stops firing the shapes have grown a version gate, which is "
        "a change worth noticing rather than a test worth deleting")


# ---------------------------------------------------------------------------
# 7. No shape may sit out the whole suite.
#
# Set-equality per fixture proves agreement on what fires; it proves nothing
# about a shape that never fires. The review demonstrated exactly
# that: seven shapes were quietly disabled and every test above stayed green,
# because no fixture ever provoked them. This test runs last in the file and
# demands that every emitted shape has been seen firing at least once — a
# constraint under which a disabled shape turns the gate red by definition.
# (Same shape as `.rule-coverage.json` on the Python side: observed, not
# assumed. File-order matters and pytest honours definition order; running
# this test alone is meaningless and it says so.)
# ---------------------------------------------------------------------------

def test_every_emitted_shape_has_fired_somewhere_in_this_file():
    never_fired = EMITTED - SH_FIRED_EVER
    assert len(SH_FIRED_EVER) > 50, (
        "the accumulator is empty-ish; this test only means something after "
        "the whole file has run -- do not run it in isolation")
    assert never_fired == set(), sorted(never_fired)


def test_the_container_package_is_not_inside_another_in_either_encoding(tmp_path):
    """§6.2: "The corresponding iirds:Package instance of an iiRDS package
    MUST NOT be a member of another iiRDS package expressed by the property
    iirds:is-part-of-package."

    Three graphs again, and the middle one is why this is not a one-line
    shape: a package that names a parent this document also describes is a
    nested child declared the way §6.3.3 asks, and it must pass. The third is
    the self-loop, which is not membership in another package."""
    named_elsewhere = MINIMAL_RDF.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        '    <iirds:is-part-of-package rdf:resource="urn:test:parent-elsewhere"/>\n')
    assert "R7" in assert_parity(tmp_path, "r7_elsewhere.iirds", named_elsewhere)

    declared = named_elsewhere.replace("</rdf:RDF>",
        '  <iirds:Package rdf:about="urn:test:parent-elsewhere">\n'
        '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
        '  </iirds:Package>\n</rdf:RDF>')
    assert "R7" not in assert_parity(tmp_path, "r7_declared.iirds", declared), (
        "a package whose parent is described here is a nested child, and "
        "§6.3.3 asks it to carry exactly this relation")

    loop = MINIMAL_RDF.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        '    <iirds:is-part-of-package rdf:resource="urn:test:package"/>\n')
    assert "R7" not in assert_parity(tmp_path, "r7_loop.iirds", loop), (
        "itself is not another package; R5 answers for the self-loop"
    )


@pytest.mark.parametrize("rule_id,block", [
    ("M15.7b", "SECOND_INSTANCE"), ("M15.7d", "SECOND_TYPE"), ("M15.10", "SECOND_OBJECT"),
])
def test_a_second_identity_is_silent_in_both_encodings(rule_id, block, tmp_path):
    """Section 8.3.2's bullets are existential: one qualifying identity
    satisfies each. The Python rules were read over every matching domain and
    corrected; the shapes were read the same way and were not, and this file
    could not see it — no fixture here carried a second identity, and the
    comparison is over the *set* of rule ids, so a rule that fires in one
    encoding and not the other is only visible when it is the only difference.
    """
    from test_handover_rules_fire import (
        SECOND_INSTANCE,
        SECOND_TYPE,
        _package,
        _with_second_identity,
    )

    blocks = {"SECOND_INSTANCE": SECOND_INSTANCE, "SECOND_TYPE": SECOND_TYPE}
    if block == "SECOND_OBJECT":
        from test_handover_rules_fire import HANDOVER
        metadata = HANDOVER.replace(
            '  <iirds:IdentityDomain rdf:about="urn:test:domain-object">',
            '  <iirds:Identity rdf:about="urn:test:identity-io2">\n'
            '    <iirds:identifier>IO-ALT</iirds:identifier>\n'
            '    <iirds:has-identity-domain rdf:resource="urn:test:domain-io2"/>\n'
            '  </iirds:Identity>\n\n'
            '  <iirds:IdentityDomain rdf:about="urn:test:domain-io2"/>\n\n'
            '  <iirds:IdentityDomain rdf:about="urn:test:domain-object">', 1).replace(
            '    <iirds:has-identity rdf:resource="urn:test:identity-object"/>',
            '    <iirds:has-identity rdf:resource="urn:test:identity-object"/>\n'
            '    <iirds:has-identity rdf:resource="urn:test:identity-io2"/>', 1)
    else:
        metadata = _with_second_identity(blocks[block])

    report = runner.run(_package(tmp_path, "second.iirds", metadata), runner.ALL_KINDS)
    assert rule_id not in {f.rule.id for f in report.findings}
    assert rule_id not in shacl_fired(metadata, handover=True)
