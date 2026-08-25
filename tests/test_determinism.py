"""The same package must produce the same report — every run, either encoding.

This is the project's largest claim, and until these tests existed it was
false. rdflib mints a fresh identifier for every blank node on every parse, so
a report naming one read `N8892b8d9…` on Monday and `N39e7e968…` on Tuesday for
an unchanged package. Two things break at once. A JSON report cannot be diffed
between runs, which removes the point of emitting JSON. And the same graph
written as RDF/XML and as JSON-LD produced *different* findings — which is the
one property the whole graph-based design exists to guarantee.

Neither shows up in a test that only counts findings, which is what the suite
did. Both show up immediately if you compare the text.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from conftest import (
    ATTRIBUTE_STYLE_RDF,
    DESCRIPTION_STYLE_RDF,
    MINIMAL_JSONLD,
    MINIMAL_RDF,
    build_package,
)
from iirds_validate import runner

ROOT = Path(__file__).resolve().parents[1]

#: Renditions are the usual blank nodes in a real package, and dropping the
#: format from one is a defect reported *against* the blank node — so it is
#: also the shortest route to a report that names one.
BROKEN_RDF = MINIMAL_RDF.replace(
    "        <iirds:format>application/xhtml+xml</iirds:format>\n", "")

#: rdflib's own shape for a generated identifier.
_GENERATED = re.compile(r"\bN[0-9a-f]{20,}\b")


#: A topic with six titles. The cardinality rules list the values they found,
#: and listing is where a set becomes an order.
MANY_TITLES = MINIMAL_RDF.replace(
    "    <iirds:title>A topic</iirds:title>\n",
    "".join('    <iirds:title>Title %s</iirds:title>\n' % word
            for word in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")))


def _lines(report):
    """Everything a reader sees, `detail` included.

    It was excluded, and `detail` is exactly where the non-determinism was: a
    rule that lists four of six values it found was listing whichever four came
    out of the store first. Comparing the fields either side of it proved the
    property for the fields that already held it.
    """
    return sorted("%s|%s|%s|%s" % (f.rule.id, f.violation.subject,
                                   f.violation.message, f.violation.detail)
                  for f in report.findings)


def test_three_runs_of_one_package_give_three_identical_reports(tmp_path):
    package = build_package(tmp_path, "repeat.iirds", metadata=BROKEN_RDF)
    reports = [_lines(runner.check(package)) for _ in range(3)]

    assert reports[0], "the fixture must actually produce findings, or this proves nothing"
    assert reports[0] == reports[1] == reports[2]


def test_no_finding_names_a_generated_identifier(tmp_path):
    """The identifier is meaningless to the reader as well as unstable.

    "urn:test:topic1 has-rendition" tells somebody where to look in their own
    file. "N8892b8d9c4f14e2ab0…" tells them nothing at all, and tells them
    something different next time.
    """
    package = build_package(tmp_path, "named.iirds", metadata=BROKEN_RDF)
    report = runner.check(package)

    text = json.dumps(report.as_dict())
    assert not _GENERATED.search(text), _GENERATED.search(text).group(0)
    assert any("has-rendition" in (f.violation.subject or "") for f in report.findings)


def test_the_json_report_is_byte_identical_across_runs(tmp_path):
    """What a build pipeline actually does with the output: store it, and diff
    the next one against it. A field that changes every run makes every build
    look like a regression.
    """
    package = build_package(tmp_path, "json.iirds", metadata=BROKEN_RDF)
    first = json.dumps(runner.check(package).as_dict(), sort_keys=True)
    second = json.dumps(runner.check(package).as_dict(), sort_keys=True)
    assert first == second


def test_the_two_rdf_serialisations_agree_finding_for_finding(tmp_path):
    """Not "the same number of findings" — the same findings, word for word.

    The suite's existing serialisation test compared two empty lists, so it
    would have passed had the tool reported nothing at all for either form.
    Comparing the text of a report that is *not* empty is what makes the claim
    testable, and comparing it against a file that is the same graph rather
    than merely similar information is what makes it the right claim.
    """
    nested = build_package(tmp_path, "nested.iirds", metadata=BROKEN_RDF)
    attributed = build_package(tmp_path, "attributed.iirds", metadata=ATTRIBUTE_STYLE_RDF.replace(
        "      <x:format>application/xhtml+xml</x:format>\n", ""))

    assert _lines(runner.check(nested)), "the defect must be reported at all"
    assert _lines(runner.check(nested)) == _lines(runner.check(attributed))


def test_naming_a_blank_node_survives_the_node_being_given_an_identifier(tmp_path):
    """The description-style fixture is *not* the same graph — it replaces the
    anonymous rendition with `urn:test:rendition1` — so the reports differ in
    exactly one place: what the finding is filed against. That is correct and
    worth pinning, because it is the difference between a report that follows
    the author's own file and one that invents names for things.
    """
    nested = runner.check(build_package(tmp_path, "n.iirds", metadata=BROKEN_RDF))
    named = runner.check(build_package(tmp_path, "d.iirds", metadata=DESCRIPTION_STYLE_RDF.replace(
        "    <ii:format>application/xhtml+xml</ii:format>\n", "")))

    assert [f.rule.id for f in nested.findings] == [f.rule.id for f in named.findings]
    assert [f.violation.subject for f in nested.findings] == ["urn:test:topic1 has-rendition"]
    assert [f.violation.subject for f in named.findings] == ["urn:test:rendition1"]


def test_rdf_xml_and_json_ld_agree_finding_for_finding(tmp_path):
    """iiRDS 1.3 accepts JSON-LD alongside RDF/XML for the same metadata. A
    package whose metadata passes in one encoding and fails in the other is a
    validator defect, not a package defect, and a consumer reading only one of
    the two files would have no way to tell which.

    Both packages carry a metadata.rdf, because the specification still
    requires one; the JSON-LD file is the additional encoding, and the rules
    read the union. So the comparison here is between the RDF/XML-only package
    and one where the same defective graph arrives by both routes.
    """
    described = DESCRIPTION_STYLE_RDF.replace(
        "    <ii:format>application/xhtml+xml</ii:format>\n", "")
    broken_jsonld = MINIMAL_JSONLD.replace(
        '\n     "format": "application/xhtml+xml",', "").replace(
        '"format": "application/xhtml+xml", ', "")

    rdf_only = build_package(tmp_path, "as-rdf.iirds", metadata=described)
    both = build_package(tmp_path, "as-both.iirds", metadata=described, jsonld=broken_jsonld)

    assert _lines(runner.check(rdf_only)), "the defect must be reported at all"
    assert _lines(runner.check(rdf_only)) == _lines(runner.check(both))


def test_the_report_is_byte_identical_across_hash_seeds(tmp_path):
    """The axis the in-process tests cannot reach.

    String hashing is fixed for the life of a process, so three runs inside one
    interpreter agree with each other whatever the underlying order is. The
    claim in README.md is about seeds, and only a new process can vary one.
    """
    import subprocess
    import sys

    package = build_package(tmp_path, "seeds.iirds", metadata=MANY_TITLES)
    script = (
        "import json, sys;"
        "sys.path[:0] = [%r];"
        "from iirds_validate import runner;"
        "print(json.dumps(runner.check(%r).as_dict(), sort_keys=True))"
        % (str(ROOT / "src"), str(package)))

    reports = set()
    for seed in ("0", "1", "2", "3", "4"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, "-c", script], env=env,
                             capture_output=True, text=True, check=True).stdout
        assert '"findings"' in out, out
        reports.add(out)
    assert len(reports) == 1, "%d distinct reports across five seeds" % len(reports)
