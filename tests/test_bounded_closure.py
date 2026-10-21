"""R61's closure stops at a ceiling counted in facts, and says that it did.

R61 asks whether a resource is an instance of two disjoint classes after
closing the package's statements together with the bundled ontology's class
and property declarations. That closure can be made expensive: every class in
a chain of rdfs:subClassOf statements is a subclass of every class above it,
so a chain n classes long holds about n*n/2 of those statements, and each of
them meets the others on its way in. A chain of 400 classes, a few dozen
kilobytes of metadata, held R61 for most of a minute, and doubling the chain
multiplied that by about eight.

The ceiling counts what the closure derives, not how long it takes, so it
falls in the same place on every machine and under every Python and rdflib
this project supports, and past it R61 reports that it stopped instead of
answering for the package without the rest.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

from conftest import MINIMAL_RDF, build_package
from iirds import pack
from iirds_validate import runner
from iirds_validate.model import METADATA_RDF
from iirds_validate.rules.schema import MAX_DERIVED_PER_FACT, _closure_start, _disjoint_rdfs_facts

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "corpus" / "plusmeta" / "files"
IIRDS = "http://iirds.tekom.de/iirds#"

STOPPED = ("the disjointness check stopped at its ceiling without seeing the package "
           "through, and reports nothing about any resource: none is named an instance "
           "of disjoint classes, and none is cleared")

#: Measured once, where the corpus cannot go: the Consortium's two sample
#: packages, which this repository does not carry. Facts the closure derived,
#: and facts it started from.
SAMPLES = {"iirds-sample-1.iirds": (3157, 1418), "iirds-sample-2.iirds": (2274, 998)}


def chain(n, blank=False):
    """`x` is a C0 and an iirds:Topic, C0 is a subclass of C1, and so on up to
    Cn, a subclass of iirds:Document. Closed, `x` is a Topic and a Document,
    which are disjoint: R61 reports `x`, or says it stopped first. With
    `blank` the classes are blank nodes, which each parse labels afresh."""
    name = 'rdf:nodeID="c%d"' if blank else 'rdf:about="https://example.org/C%d"'
    target = 'rdf:nodeID="c%d"' if blank else 'rdf:resource="https://example.org/C%d"'
    body = ['<rdf:Description %s><rdfs:subClassOf %s/></rdf:Description>' % (name % i, target % (i + 1))
            for i in range(n)]
    body.append('<rdf:Description %s><rdfs:subClassOf rdf:resource="%sDocument"/></rdf:Description>'
                % (name % n, IIRDS))
    body.append('<rdf:Description rdf:about="https://example.org/x"><rdf:type %s/>'
                '<rdf:type rdf:resource="%sTopic"/></rdf:Description>' % (target % 0, IIRDS))
    return MINIMAL_RDF.replace("</rdf:RDF>", "\n".join(body) + "\n</rdf:RDF>")


def r61(tmp_path, metadata):
    report = runner.run(build_package(tmp_path, "closure.iirds", metadata=metadata), ("schema",))
    return [(f.violation.message, f.violation.subject, f.violation.detail)
            for f in report.findings if f.rule.id == "R61"]


def test_the_ceiling_is_ten_times_the_most_a_measured_package_needs(tmp_path):
    """The ceiling is derived, not chosen: ten times the most any measured
    package derives for each fact it starts from, rounded up. The corpus is
    measured on every run, as `run_fragment` would read each file, and the
    samples were measured once and are recorded above. A file added to the
    corpus or taken out of it changes what was measured, and this says so
    before the derivation in `schema.py` goes stale."""
    growth = []
    for number, fragment in enumerate(sorted(CORPUS.iterdir())):
        container = tmp_path / str(number)
        (container / METADATA_RDF).parent.mkdir(parents=True)
        (container / METADATA_RDF).write_bytes(fragment.read_bytes())
        ctx = runner.load(pack(container, tmp_path / ("%d.iirds" % number)), version="1.3")
        try:
            started = len(_closure_start(ctx))
            growth.append((len(_disjoint_rdfs_facts(ctx)[0]) - started) / started)
        finally:
            ctx.package.close()
    assert len(growth) == 132
    most = max(growth + [derived / started for derived, started in SAMPLES.values()])
    assert math.ceil(10 * most) == MAX_DERIVED_PER_FACT, most


def test_a_chain_of_four_hundred_classes_stops_at_the_ceiling_and_says_so(tmp_path):
    """The bytes are the claim. CI runs this under every Python the project
    supports and under the oldest rdflib it accepts, and a ceiling that is a
    count puts every one of them here."""
    assert r61(tmp_path, chain(400)) == [(
        STOPPED, None,
        "the closure starts from 1076 facts, the package's statements with the "
        "bundled ontology's class and property declarations, and derives at most "
        "23 for each of them, 24748 in all; this package needs more")]


def test_below_the_ceiling_the_verdict_is_r61s_own(tmp_path):
    """A chain of 150 closes inside the ceiling, and `x` is reported for what
    it is: the ceiling stops a closure, it does not excuse a package."""
    found = r61(tmp_path, chain(150))
    assert [subject for _message, subject, _detail in found] == ["https://example.org/x"], found
    assert found[0][0] != STOPPED


def test_a_deep_hierarchy_of_the_package_s_own_classes_is_not_cut(tmp_path):
    """Twenty classes of the package's own, one under the next and the last
    under iirds:Document, and a thousand documents typed with the lowest: the
    closure derives about eleven facts for each one it starts from. Nothing
    here is disjoint, so R61 says nothing -- and not that it stopped."""
    body = ['<rdf:Description rdf:about="https://example.org/K%d">'
            '<rdfs:subClassOf rdf:resource="https://example.org/K%d"/></rdf:Description>' % (i, i + 1)
            for i in range(19)]
    body.append('<rdf:Description rdf:about="https://example.org/K19">'
                '<rdfs:subClassOf rdf:resource="%sDocument"/></rdf:Description>' % IIRDS)
    body += ['<rdf:Description rdf:about="https://example.org/d%d"><rdf:type rdf:resource='
             '"https://example.org/K0"/><iirds:title>d%d</iirds:title></rdf:Description>' % (i, i)
             for i in range(1000)]
    assert r61(tmp_path, MINIMAL_RDF.replace("</rdf:RDF>", "\n".join(body) + "\n</rdf:RDF>")) == []


def test_where_the_ceiling_falls_does_not_depend_on_the_order_the_closure_runs_in(tmp_path):
    """Only a new process can vary string hashing, and with blank nodes the
    labels a parse gives them. The closure derives one set of facts however
    they arrive, and the ceiling counts that set, so every seed stops in the
    same place and says the same thing."""
    package = build_package(tmp_path, "blank.iirds", metadata=chain(200, blank=True))
    script = (
        "import json, sys;"
        "sys.path[:0] = [%r];"
        "from iirds_validate import runner;"
        "r = runner.run(%r, ('schema',));"
        "print(json.dumps([(f.violation.message, f.violation.subject, f.violation.detail)"
        " for f in r.findings if f.rule.id == 'R61']))"
        % (str(ROOT / "src"), str(package)))
    seen = set()
    for seed in ("0", "1", "2", "3"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        seen.add(subprocess.run([sys.executable, "-c", script], env=env,
                                capture_output=True, text=True, check=True).stdout)
    assert len(seen) == 1, seen
    assert [message for message, _subject, _detail in json.loads(seen.pop())] == [STOPPED]
