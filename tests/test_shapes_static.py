"""The emitted SHACL shapes, held to the same standard as everything else.

Three layers. Completeness: every registered rule sits in exactly one emitter
bucket, so a rule can be deferred but never forgotten. Fidelity: severities
mirror the rules', every nodeKind shape carries the base-IRI exclusion that
makes it mean what `is_named` means. And a live smoke: pySHACL over the
emitted files must agree with the Python verdicts on the packages this
project already treats as ground truth — the calibration anchor reports
nothing, the broken fixture reports M11.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import RDF, Graph, Namespace, URIRef

import emit_shacl
from conftest import shacl_or_skip
from iirds_validate.model import PACKAGE_BASE
from iirds_validate.registry import all_rules

ROOT = Path(__file__).resolve().parents[1]
SHAPE_DIR = ROOT / "shapes" / "iirds-1.3"
SH = Namespace("http://www.w3.org/ns/shacl#")
IVS = Namespace(emit_shacl.IVS)
IVM = Namespace(emit_shacl.IVM)

RULES = {r.id: r for r in all_rules()}
MANIFEST = json.loads((ROOT / "shapes" / "MANIFEST.json").read_text("utf-8"))


def test_every_rule_is_classified_exactly_once():
    """The emitter refuses to run otherwise; this pins the property against
    the emitter itself being edited into leniency."""
    seen = {}
    for name, table in (("core", emit_shacl.CORE_FORMS),
                        ("sparql", emit_shacl.SPARQL_FORMS),
                        ("deferred", emit_shacl.DEFERRED_V11),
                        ("not_expressible", emit_shacl.NOT_EXPRESSIBLE),
                        ("noop", emit_shacl.NOOP)):
        for rid in table:
            assert rid not in seen, "%s in both %s and %s" % (rid, seen[rid], name)
            seen[rid] = name
    assert set(seen) == set(RULES), sorted(set(RULES) ^ set(seen))


def test_the_census_numbers_hold():
    counts = MANIFEST["counts"]
    assert counts["core_emitted"] == 122
    assert counts["version_excluded"] == 2          # M16.1/2, MUSTs only through 1.1
    assert counts["sparql_emitted"] == 32
    assert counts["deferred_v1.1"] == 9
    assert counts["not_expressible"] == 47
    assert counts["noop"] == 1


def _shapes_graph():
    graph = Graph()
    for name in ("iirds-core.ttl", "iirds-handover-core.ttl",
                 "iirds-sparql.ttl", "iirds-handover-sparql.ttl"):
        graph.parse(SHAPE_DIR / name, format="turtle")
    return graph


SHAPES = _shapes_graph()


def test_every_emitted_file_is_valid_turtle():
    assert len(SHAPES) > 800


@pytest.mark.parametrize("rule_id",
                         MANIFEST["core_emitted"] + MANIFEST["sparql_emitted"])
def test_each_emitted_shape_exists_and_mirrors_its_rule(rule_id):
    shape = IVS[rule_id]
    assert (shape, RDF.type, SH.NodeShape) in SHAPES, rule_id

    severity = SHAPES.value(shape, SH.severity)
    assert str(severity).split("#")[-1] == \
        {"error": "Violation", "warning": "Warning", "info": "Info"}[str(RULES[rule_id].severity)]

    assert str(SHAPES.value(shape, IVM.ruleId)) == rule_id
    if RULES[rule_id].fix:
        assert SHAPES.value(shape, SH.description) is not None, rule_id


def test_every_nodekind_shape_carries_the_base_exclusion():
    """sh:nodeKind sh:IRI alone would pass rdf:about="", which is_named
    rejects; the sh:not/sh:in pairing is what keeps the two encodings
    synonymous."""
    nodekind_shapes = set(SHAPES.subjects(SH.nodeKind, SH.IRI))
    assert len(nodekind_shapes) >= 63
    base = URIRef(PACKAGE_BASE)
    for shape in nodekind_shapes:
        negation = SHAPES.value(shape, SH["not"])
        assert negation is not None, shape
        members = list(SHAPES.items(SHAPES.value(negation, SH["in"])))
        assert members == [base], shape


def test_version_excluded_rules_have_no_shape_in_the_1_3_set():
    for rule_id in MANIFEST["version_excluded"]:
        assert (IVS[rule_id], None, None) not in SHAPES, rule_id


# ---------------------------------------------------------------------------
# Live smoke — needs pySHACL. Under make its absence is a failure; a bare
# pytest still skips (the rdflib 6 rows in CI are such a run).
#
# Asked for inside the three tests that use it, not at module scope. A
# module-level skip takes the file with it, and most of this file needs
# rdflib and JSON only -- the census, the per-shape mirror, the emitted-id
# set, the constituent-file comparison, the README figures. All of them
# vanished on a run without pyshacl, and one of them says in its own
# docstring that it runs "pyshacl present or not".
# ---------------------------------------------------------------------------

def _core_only():
    graph = Graph()
    graph.parse(SHAPE_DIR / "iirds-core.ttl", format="turtle")
    return graph


CORE_SHAPES = _core_only()


def _fired(data_graph):
    pyshacl = shacl_or_skip()
    _ok, results, _text = pyshacl.validate(
        data_graph, shacl_graph=CORE_SHAPES, advanced=True, inference="none")
    fired = set()
    for _res, _p, source in results.triples((None, SH.sourceShape, None)):
        local = str(source).rsplit("#", 1)[-1]
        fired.add(local.split("-p")[0])          # property shapes are ivs:<id>-p*
    return fired


def test_shacl_reports_nothing_on_the_calibration_anchor():
    """The anchor is the project's definition of an ordinary correct package;
    the second encoding must agree that it is silent."""
    from test_clean_realistic_package import METADATA

    data = Graph().parse(data=METADATA, format="xml", publicID=PACKAGE_BASE)
    assert _fired(data) == set()


def test_shacl_reports_m11_on_the_rendition_with_no_format():
    from conftest import MINIMAL_RDF

    broken = MINIMAL_RDF.replace(
        "        <iirds:format>application/xhtml+xml</iirds:format>\n", "")
    data = Graph().parse(data=broken, format="xml", publicID=PACKAGE_BASE)
    fired = _fired(data)
    assert "M11" in fired
    assert "M10" not in fired, "source is present; only the format is missing"


def test_shacl_and_python_agree_on_the_minimal_fixture():
    """Whatever the shapes say about the suite's baseline package, the Python
    rules must say too — the first breath of the differential gate."""
    from conftest import MINIMAL_RDF

    data = Graph().parse(data=MINIMAL_RDF, format="xml", publicID=PACKAGE_BASE)
    assert _fired(data) == set()


def _sparql_parser_works() -> bool:
    """rdflib's own parser, on the plainest query there is.

    At rdflib 6.0.0 against the pyparsing pip installs today it raises on
    `SELECT * WHERE { ?s ?p ?o }`: the instrument is broken there, not the
    shapes. Nothing at run time parses SPARQL, so the floor row is still a
    floor for the checker; this one syntax check stands down on it and says
    so, and runs everywhere the parser works."""
    from rdflib.plugins.sparql import prepareQuery

    try:
        prepareQuery("SELECT * WHERE { ?s ?p ?o }")
    except Exception:
        return False
    return True


def test_every_sparql_select_is_valid_sparql():
    """Syntax-checked with rdflib alone, so the guard runs on every CI row,
    pyshacl present or not."""
    import pyparsing
    import rdflib
    from rdflib.plugins.sparql import prepareQuery

    if not _sparql_parser_works():
        pytest.skip("rdflib %s cannot parse a trivial SELECT with pyparsing %s; the "
                    "shapes are syntax-checked where the parser works"
                    % (rdflib.__version__, pyparsing.__version__))

    selects = list(SHAPES.objects(None, SH.select))
    assert len(selects) >= 14        # 13 rules; M3 carries two constraints
    for query in selects:
        prepareQuery(str(query))


def test_the_shapes_readme_numbers_are_the_manifest_numbers():
    """The shapes README is the deliverable's face, and its first draft
    already miscounted its own table (114 for 111) within the hour it was
    written. Prose numbers drift wherever no tool holds them; this holds
    them."""
    readme = (ROOT / "shapes" / "README.md").read_text("utf-8")
    per_file = {}
    for entry in MANIFEST["shapes"].values():
        name = entry["file"].rsplit("/", 1)[-1]
        per_file[name] = per_file.get(name, 0) + 1

    # "one per rule" is load-bearing, not decoration: the file also holds the
    # property shapes those node shapes hang off -- eighty-six of them in the
    # core file, forty-six from L16 alone -- and a reader who counts
    # `sh:PropertyShape` gets a different number than this row.
    assert "| %d shapes, one per rule: cardinalities" % per_file["iirds-core.ttl"] in readme
    assert "| %d shapes, one per rule: graph-global" % per_file["iirds-sparql.ttl"] in readme
    assert "| %d iiRDS/H additions" % per_file["iirds-handover-core.ttl"] in readme
    assert "| %d iiRDS/H additions (SPARQL)" % per_file["iirds-handover-sparql.ttl"] in readme

    # The four bucket headings under "What is not here, exactly". The sentence
    # beside them was read and these were not, so the buckets could say
    # anything while the total stayed right.
    for bucket, heading in (("not_expressible", "not expressible"),
                            ("deferred_v1.1", "deferred"),
                            ("version_excluded", "out of edition"),
                            ("noop", "no-op")):
        assert "- **%d %s**" % (MANIFEST["counts"][bucket], heading) in readme, (
            bucket, MANIFEST["counts"][bucket])
    rules = len(all_rules())
    # Derived, both of them. These were literals -- "58 of the 201" while the
    # four buckets under it summed to 57, because a rule was added, one of the
    # two got a shape, and the headline was moved by hand in the wrong
    # direction. A number a reader can add up from the lines below it is a
    # number a test can add up too.
    without_a_shape = rules - len(EMITTED_IDS)
    assert "%d of the %d rules have no shape" % (without_a_shape, rules) in readme
    assert without_a_shape == sum((MANIFEST["counts"]["version_excluded"],
                                   MANIFEST["counts"]["deferred_v1.1"],
                                   MANIFEST["counts"]["not_expressible"],
                                   MANIFEST["counts"]["noop"])), "the buckets must sum to it"
    assert "%d of the %d rules" % (len(MANIFEST["not_expressible"]), rules) in readme
    # Published and pinned by nothing until now: the sentence naming the size
    # of the validator the shapes are tested against sat at 198 while the
    # registry grew past 200.
    assert "the %d-rule Python" % rules in readme
    assert len(MANIFEST["deferred_v1.1"]) == 9
    # The five iiRDS/H MUSTs graduated from the deferred bucket; the gate
    # that once demanded they be named as missing now demands the opposite.
    for rid in ("M15.7b", "M15.7d", "M15.8", "M15.9", "M15.10"):
        assert rid not in MANIFEST["deferred_v1.1"]
    for rid in MANIFEST["deferred_v1.1"]:
        assert rid in readme
    for rid in MANIFEST["version_excluded"]:
        assert rid in readme
    for rid in MANIFEST["noop"]:
        assert rid in readme
    assert "iirds-complete.ttl" in readme and "-a metadata.rdf" in readme


# ---------------------------------------------------------------------------
# The emitted set, pinned by name.
#
# The census counting was gameable: move a rule from
# CORE_FORMS to the deferred bucket, adjust three integers, and an iiRDS/H
# MUST vanishes from the shapes with every test green. Cardinality cannot
# see *which* rules are covered; this list can, and shrinking it now requires
# editing a names list in a test -- a diff a reviewer reads.
# ---------------------------------------------------------------------------

EMITTED_IDS = frozenset((
    "L10", "L16", "L7", "M1", "M10", "M11", "M12", "M13.1", "M13.2", "M14.1",
    "M14.2", "M15.1", "M15.10", "M15.11a", "M15.11b", "M15.11c", "M15.2",
    "M15.3", "M15.4", "M15.5", "M15.6", "M15.7a", "M15.7b", "M15.7c",
    "M15.7d", "M15.8", "M15.9", "M16.3", "M17", "M18",
    "M19.1", "M19.2", "M19.3", "M19.4", "M2.1", "M2.3", "M2.4", "M2.5",
    "M2.6", "M2.7", "M2.8", "M2.9", "M20.1", "M21.1", "M21.2", "M21.3",
    "M21.4", "M21.5", "M21.6", "M22.1", "M22.2", "M23", "M24.1", "M24.2",
    "M24.3", "M24.4", "M24.5", "M24.6", "M25", "M26", "M27", "M3", "M30",
    "M35", "M36", "M37", "M38", "M39", "M4", "M40", "M41", "M42", "M43",
    "M44", "M45", "M46", "M47", "M48", "M49", "M5", "M50", "M51", "M52",
    "M53", "M54", "M55", "M56", "M57", "M58", "M59", "M6", "M60", "M61",
    "M62", "M63", "M64", "M65", "M66", "M67", "M68", "M69", "M7.1", "M70",
    "M71", "M72", "M73", "M74", "M75", "M76", "M77", "M78", "M79", "M8",
    "M80", "M81", "M82", "M83", "M84", "M85", "M86", "M87", "M88", "M89",
    "M9", "M90", "M91", "M92", "M93", "M94", "M95", "M96.1", "M96.2",
    "M96.3", "M97.1", "M97.2", "R1", "R10", "R12", "R2", "R4", "R5",
    "R13", "R14", "R15", "R16", "R17", "R19", "R20", "R21", "R23",
    "R6", "R7", "S4", "S5"))


def test_no_shape_table_names_a_rule_twice():
    """A duplicate key in a dict literal is not an error in Python -- the last
    one wins, silently. `emit_shacl.build()` refuses a rule classified in two
    *tables*, and nothing looked inside one.

    It happened: M19.4 already had a hand-written query in `SPARQL_FORMS`, a
    second entry was added below it, and the file emitted the new one with no
    complaint. The count of edition-specific shapes is what noticed, three
    steps later. Read from the source rather than from the imported dict,
    because by then the duplicate is gone.
    """
    import ast

    # Every tool, not only the emitter: the same thing happened a second time
    # in `version_inventory.py`, where a rewrite left two `NAMES_NO_TERM`
    # literals and the later one won in silence.
    for path in sorted((ROOT / "tools").glob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        # Top level only. A `global NAME` write inside a function is a
        # deliberate rebinding and reads as a duplicate to `ast.walk`;
        # `tools/crossvalidate.py` does exactly that with EMPTY_UPSTREAM.
        assigned = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name) or not target.id.isupper():
                    continue
                assigned.setdefault(target.id, []).append(node)
                if isinstance(node.value, ast.Dict):
                    keys = [k.value for k in node.value.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                    twice = sorted({k for k in keys if keys.count(k) > 1})
                    assert twice == [], "%s: %s names these twice: %s" % (
                        path.name, target.id, twice)
        rebound = sorted(name for name, nodes in assigned.items() if len(nodes) > 1)
        assert rebound == [], "%s assigns these upper-case names twice: %s" % (
            path.name, rebound)


def test_the_emitted_rule_set_is_pinned_by_name():
    emitted = set(MANIFEST["core_emitted"]) | set(MANIFEST["sparql_emitted"])
    gone = EMITTED_IDS - emitted
    new = emitted - EMITTED_IDS
    assert gone == set(), "shapes silently dropped: %s" % sorted(gone)
    assert new == set(), "new shapes -- welcome, but add them here: %s" % sorted(new)


def test_the_complete_files_are_exactly_their_parts():
    """The quickstart tells strangers to run the two -complete files, so the
    suite must prove they equal the parts it actually gates -- byte drift in
    a hand-edited complete file would otherwise be invisible to pytest."""
    from rdflib import Graph
    from rdflib.compare import isomorphic

    def graph(*names):
        g = Graph()
        for name in names:
            g.parse(SHAPE_DIR / name, format="turtle")
        return g

    assert isomorphic(graph("iirds-complete.ttl"),
                      graph("iirds-core.ttl", "iirds-sparql.ttl"))
    assert isomorphic(graph("iirds-handover-complete.ttl"),
                      graph("iirds-core.ttl", "iirds-sparql.ttl",
                            "iirds-handover-core.ttl", "iirds-handover-sparql.ttl"))


def test_the_shapes_without_a_spec_link_are_exactly_the_known_five():
    """The README's dcterms:source claim drifted three times in a
    row (all → all-but-four → the measured truth). Claims about coverage
    live here now, where drift turns red instead of stale."""
    from rdflib import Graph, Namespace

    DCT = Namespace("http://purl.org/dc/terms/")
    SH_NS = Namespace("http://www.w3.org/ns/shacl#")
    graph = Graph()
    for name in ("iirds-core.ttl", "iirds-sparql.ttl",
                 "iirds-handover-core.ttl", "iirds-handover-sparql.ttl"):
        graph.parse(SHAPE_DIR / name, format="turtle")

    # By rule, not by shape: a rule with a spec link puts it on its property
    # shapes too, so one rule emitting forty-six of them would otherwise
    # arrive here as forty-six names and pin a list instead of a fact. Read
    # this way a property shape that lost the link still shows up -- under the
    # id of the rule that should have carried it.
    #
    # The count is pinned beside the set, because reading by rule stops the
    # gate bounding *how many* shapes lack a link: any number of them could
    # then be added under one of these six ids and nothing would notice. The
    # set says which rules, the count says how many shapes, and a change to
    # either is a diff a reviewer reads.
    # Read from the file's own @prefix rather than written out here: the
    # namespace carries the distribution's former name, and the gate in
    # `test_product_name.py` is right to refuse a source file that spells it.
    IVM = Namespace(dict(graph.namespaces())["ivm"])
    missing, shapes_without = set(), 0
    for kind in (SH_NS.NodeShape, SH_NS.PropertyShape):
        for shape in graph.subjects(RDF.type, kind):
            if graph.value(shape, DCT.source) is None:
                shapes_without += 1
                rule_id = graph.value(shape, IVM.ruleId)
                missing.add(str(rule_id) if rule_id else str(shape).rsplit("#", 1)[-1])
    assert missing == {"L7", "L10", "L16", "S4", "S5", "M97.1"}, sorted(missing)
    assert shapes_without == 52, shapes_without


def test_the_manifest_version_is_the_package_version():
    """Bumping the version without regenerating the shapes would ship a
    manifest claiming the old release — and turn the release workflow red
    only after the tag exists. Red here, before the tag."""
    from iirds_validate import __version__

    assert MANIFEST["_shapes_version"] == __version__


def test_the_readme_says_how_many_shapes_are_edition_specific():
    """The shapes carry no version gate; the Python rules do. So a package
    declaring an older edition draws every shape whose rule 1.3 added, and
    stays clean under the rules themselves. That is a boundary a reader has to
    be told about, and the number of shapes it covers moves whenever an
    edition-limited rule gains one -- so it is read here rather than typed."""
    from iirds_validate.registry import all_rules

    every = ("1.0", "1.0.1", "1.1", "1.2", "1.3")
    emitted = set(MANIFEST["core_emitted"]) | set(MANIFEST["sparql_emitted"])
    limited = sorted(r.id for r in all_rules()
                     if r.id in emitted and r.versions and set(r.versions) != set(every))
    assert limited, "no edition-limited shape at all would be surprising"

    readme = (SHAPE_DIR.parent / "README.md").read_text("utf-8")
    assert "%d of them encode a rule that iiRDS 1.3 added" % len(limited) in readme, \
        "shapes/README.md should say %d; it says something else" % len(limited)


def test_a_finding_with_its_own_remedy_publishes_it_in_the_shapes():
    """`sh:description` is the advice a SHACL consumer gets, and it carried
    only the rule's own `fix=`. A rule that reports two different defects
    gives the second its own remedy through `Violation(fix=...)`, and those
    never left Python: the shapes handed a reader the advice for the other
    finding, which is the defect this project fixed in its report (M24.5) and
    left in the encoding it publishes for everyone not running Python.

    The emitter reads them out of the source rather than being told, so this
    holds the derivation to the code.
    """
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    import emit_shacl

    # Across the set: a handover rule's shape lives in the handover files,
    # which iirds-complete.ttl deliberately leaves out.
    published = "\n".join(path.read_text("utf-8")
                          for path in sorted((ROOT / "shapes" / "iirds-1.3").glob("*.ttl")))
    checked = 0
    for rule_id in sorted(set(MANIFEST["core_emitted"]) | set(MANIFEST["sparql_emitted"])):
        for remedy in emit_shacl.per_finding_remedies(rule_id):
            # The whole value, not a substring: a remedy shortened to one
            # character passed a substring test against any file at all.
            assert 'sh:description "%s"' % emit_shacl.esc(remedy) in published, \
                (rule_id, remedy[:60])
            checked += 1
    assert checked, "no rule attaches a remedy to one of its findings any more"
