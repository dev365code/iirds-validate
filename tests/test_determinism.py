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

import pytest

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


def test_a_fixture_built_twice_is_the_same_bytes(tmp_path):
    """A package this repository builds must not carry the clock.

    `zipfile.writestr` given a name stamps the current time, so every entry
    but `mimetype` -- immune by accident, because a bare `ZipInfo` dates to
    1980 -- moved with the build. Two builds differed, and any digest taken
    over one was a fact about the machine that made it: `docs/golden-report.json`
    pinned `packageDigest` here and CI disagreed with this machine on the
    first run.

    Asserted as the dates rather than by building twice and sleeping: the
    difference only shows across the two-second granularity a DOS timestamp
    has, and a test that sleeps for it is a test nobody keeps.
    """
    import zipfile

    from conftest import build_package

    package = build_package(tmp_path, "twice.iirds", extra=(("x/y.txt", "data"),))
    dates = {info.filename: info.date_time
             for info in zipfile.ZipFile(package).infolist()}
    assert dates, "the fixture has no entries"
    moving = {name: when for name, when in dates.items() if when != (1980, 1, 1, 0, 0, 0)}
    assert not moving, "these entries carry the build time: %s" % sorted(moving)

    # and the compression is still what the fixture is a fixture of: a
    # `ZipInfo` carries its own `compress_type`, defaulting to stored.
    kinds = {info.filename: info.compress_type
             for info in zipfile.ZipFile(package).infolist()}
    assert kinds["mimetype"] == zipfile.ZIP_STORED, kinds
    assert all(kind == zipfile.ZIP_DEFLATED
               for name, kind in kinds.items() if name != "mimetype"), kinds


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


#: What `test_the_report_is_byte_identical_across_hash_seeds` does not reach.
#: It calls `runner.check`, which is one command on one archive; the flag a
#: user can type (`--fragment`), the command that runs every rule, and the
#: unpacked container are three other paths, and a report that varies on any
#: of them is a report two runs of one package disagree about.
#:
#: `--fragment` is where this was found: the rules a snippet cannot satisfy
#: are held in a `frozenset`, and writing them into the report by iterating
#: it put them in whatever order the seed produced. Seven distinct documents
#: across eight seeds.
OTHER_ENTRY_POINTS = {
    "fragment": "runner.run_fragment(%r, runner.ALL_KINDS)",
    "every rule": "runner.run(%r, runner.ALL_KINDS)",
    "unpacked": "runner.run(%r, runner.ALL_KINDS)",
}


@pytest.mark.parametrize("entry", sorted(OTHER_ENTRY_POINTS))
def test_every_way_in_gives_one_report_across_hash_seeds(tmp_path, entry):
    import subprocess
    import sys
    import zipfile

    package = build_package(tmp_path, "seeds.iirds", metadata=MANY_TITLES)
    if entry == "fragment":
        target = tmp_path / "metadata.rdf"
        target.write_text(MANY_TITLES, "utf-8")
    elif entry == "unpacked":
        target = tmp_path / "unpacked"
        with zipfile.ZipFile(package) as archive:
            archive.extractall(target)
    else:
        target = package

    script = ("import json, sys;"
              "sys.path[:0] = [%r];"
              "from iirds_validate import runner;"
              "print(json.dumps(" + OTHER_ENTRY_POINTS[entry] + ".as_dict(), sort_keys=True))"
              ) % (str(ROOT / "src"), str(target))

    reports = set()
    for seed in ("0", "1", "2", "3", "4", "5", "6", "7"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, "-c", script], env=env,
                             capture_output=True, text=True, check=True).stdout
        assert '"findings"' in out, out
        reports.add(out)
    assert len(reports) == 1, ("%d distinct reports across eight seeds via %s"
                               % (len(reports), entry))


#: Two container packages side by side -- neither nested, so both survive
#: into the pool and the choice between them is what has to be stable. M3
#: reports the pair; detection still has to answer, and answer the same way
#: twice. Plain RDF/XML: the instability is not a property of the encoding.
SIBLING_PACKAGES = MINIMAL_RDF.replace(
    "</rdf:RDF>",
    '  <iirds:Package rdf:about="urn:test:aaa-other">\n'
    '    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n'
    '    <iirds:formatRestriction>H</iirds:formatRestriction>\n'
    '  </iirds:Package>\n</rdf:RDF>')


def test_the_detected_version_is_the_same_across_hash_seeds(tmp_path):
    """The axis above this one reaches the report; this one reaches the
    *rule set*, which is chosen before any rule runs.

    Detection reads a package off the graph, and graph order is not stable
    between processes. Measured on the graph below: a parsed graph answers
    an indexed lookup in document order, but copying it does not carry that
    order over -- the copy is filled by iterating the original, which is not
    ordered, and the copy then answers the same lookup in whatever order it
    was filled. Every run copies, because merging the sources is how the one
    graph is built, so nothing downstream may rely on graph order at all.

    What that costs when detection does rely on it: the same bytes were
    judged 1.3/H against one rule set and 1.0/H against another, and the
    profile and the version came off two different packages.
    """
    import subprocess
    import sys

    package = build_package(tmp_path, "detect.iirds", metadata=SIBLING_PACKAGES)
    script = (
        "import json, sys;"
        "sys.path[:0] = [%r];"
        "from iirds_validate import runner;"
        "r = runner.check(%r);"
        "print(json.dumps([r.version, r.variant, r.checked, r.skipped]))"
        % (str(ROOT / "src"), str(package)))

    seen = set()
    for seed in ("0", "1", "2", "3", "4", "5", "6"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, "-c", script], env=env,
                             capture_output=True, text=True, check=True).stdout
        assert out.strip().startswith("["), out
        seen.add(out)
    assert len(seen) == 1, (
        "%d different verdicts across seven hash seeds: %s"
        % (len(seen), sorted(s.strip() for s in seen)))


#: Two blank-node packages. The second says one thing where the first says
#: two, and spells it so that a digest joining its parts with a separator
#: cannot tell the difference: the literal holds the separator and then the
#: exact text of the part it is impersonating.
FORGED_BOUNDARY = MINIMAL_RDF.replace(
    '  <iirds:Package rdf:about="urn:test:package">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:title>Test package</iirds:title>\n'
    '  </iirds:Package>\n',
    '  <iirds:Package>\n'
    '    <iirds:iiRDSVersion>1.0</iirds:iiRDSVersion>\n'
    '    <iirds:title>zzz</iirds:title>\n'
    '  </iirds:Package>\n'
    '  <iirds:Package>\n'
    '    <iirds:iiRDSVersion>1.0\n'
    'http://iirds.tekom.de/iirds#title zzz</iirds:iiRDSVersion>\n'
    '  </iirds:Package>\n')

#: One package reaches a blank node, the other reaches nothing. A digest that
#: leaves blank objects out entirely cannot tell them apart.
BLANK_OBJECT = MINIMAL_RDF.replace(
    '  <iirds:Package rdf:about="urn:test:package">\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:title>Test package</iirds:title>\n'
    '  </iirds:Package>\n',
    '  <iirds:Package>\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '    <iirds:formatRestriction><rdf:Description/></iirds:formatRestriction>\n'
    '  </iirds:Package>\n'
    '  <iirds:Package>\n'
    '    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n'
    '  </iirds:Package>\n')


@pytest.mark.parametrize("metadata", [FORGED_BOUNDARY, BLANK_OBJECT],
                         ids=["forged-boundary", "blank-object"])
def test_two_blank_packages_are_told_apart_across_hash_seeds(tmp_path, metadata):
    """Ordering blank-node packages by what they say only works while two of
    them that say different things get different names.

    Where they collide, `sorted` keeps graph order -- which is the hash-seed
    order the ordering exists to escape -- so the same bytes are judged
    against a different version and a different rule set from one run to the
    next. Both documents below are shapes a digest built by joining parts
    with a separator, or by leaving blank objects out, cannot distinguish.
    """
    import subprocess
    import sys

    package = build_package(tmp_path, "collide.iirds", metadata=metadata)
    script = (
        "import json, sys;"
        "sys.path[:0] = [%r];"
        "from iirds_validate import runner;"
        "r = runner.check(%r);"
        "print(json.dumps([r.version, r.variant, r.checked, len(r.findings)]))"
        % (str(ROOT / "src"), str(package)))

    seen = set()
    for seed in ("0", "1", "2", "3", "4", "5", "6", "7"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, "-c", script], env=env,
                             capture_output=True, text=True, check=True).stdout
        assert out.strip().startswith("["), out
        seen.add(out)
    assert len(seen) == 1, (
        "%d different verdicts across eight hash seeds: %s"
        % (len(seen), sorted(s.strip() for s in seen)))


def test_a_report_does_not_give_two_nodes_the_same_name(tmp_path):
    """The same digest names blank nodes in the report. Two packages that
    say different things printed as one name reads as the tool contradicting
    itself: `M3` complaining of two packages and naming one, twice."""
    package = build_package(tmp_path, "labels.iirds", metadata=FORGED_BOUNDARY)
    report = runner.run(package, runner.ALL_KINDS)
    for finding in report.findings:
        names = (finding.violation.detail or "").split(", ")
        assert len(names) == len(set(names)), (
            "%s names the same node twice: %s"
            % (finding.rule.id, finding.violation.detail))


#: A table of contents whose sibling list runs back on itself. Which of the two
#: nodes a walk meets first decides which one the report names, so a walk whose
#: order is the order a set happens to hash in names a different one per run.
CYCLE_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:about="urn:test:toc">
    <iirds:has-first-child rdf:resource="urn:test:n1"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n1"><iirds:has-next-sibling rdf:resource="urn:test:n2"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n2"><iirds:has-next-sibling rdf:resource="urn:test:n1"/></iirds:DirectoryNode>
</rdf:RDF>""")


def test_a_loop_in_the_table_of_contents_is_named_the_same_way_across_hash_seeds(tmp_path):
    """L4 reports the node at which a walk finds itself back where it has been,
    and the walk began at whichever directory node a set produced first -- so the
    same package named `n1` in one run and `n2` in the next."""
    import subprocess
    import sys

    assert CYCLE_RDF != MINIMAL_RDF
    package = build_package(tmp_path, "loop.iirds", metadata=CYCLE_RDF)
    script = (
        "import json, sys;"
        "sys.path[:0] = [%r];"
        "from iirds_validate import runner;"
        "r = runner.run(%r, runner.ALL_KINDS).as_dict();"
        "print(json.dumps([f for f in r['findings'] if f['rule'] == 'L4'], sort_keys=True))"
        % (str(ROOT / "src"), str(package)))
    reports = set()
    for seed in ("0", "1", "2", "3", "4", "5", "6", "7"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, "-c", script], env=env,
                             capture_output=True, text=True, check=True).stdout
        assert '"L4"' in out, "the loop was not reported at all: %s" % out
        reports.add(out)
    assert len(reports) == 1, "%d distinct L4 findings across eight seeds: %s" % (len(reports), sorted(reports))


#: One loop, entered from a node with two edges into it. Which node the report
#: names follows from the order the walk takes them in, and that order is the
#: order of their names: the walk meets `n1` first and comes back to it.
TWO_WAYS_IN_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:about="urn:test:a">
    <iirds:has-first-child rdf:resource="urn:test:n1"/>
    <iirds:has-next-sibling rdf:resource="urn:test:n2"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n1"><iirds:has-next-sibling rdf:resource="urn:test:n2"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n2"><iirds:has-next-sibling rdf:resource="urn:test:n1"/></iirds:DirectoryNode>
</rdf:RDF>""")


def test_the_node_a_loop_is_named_by_is_the_first_by_name(tmp_path):
    """Not only the same node every run, but the one a reader can predict: the
    loop's own first node by name, whichever of its nodes the walk came in by."""
    assert TWO_WAYS_IN_RDF != MINIMAL_RDF
    report = runner.run(build_package(tmp_path, "ways.iirds", metadata=TWO_WAYS_IN_RDF), runner.ALL_KINDS)
    loops = [f for f in report.findings if f.rule.id == "L4"]
    assert [f.violation.subject for f in loops] == ["urn:test:n1"], [
        (f.violation.subject, f.violation.detail) for f in loops]


def _l4_across_seeds(tmp_path, name, metadata, seeds=8):
    """Every distinct list of L4 findings `seeds` runs give for one package, each
    under its own hash seed -- and each parse mints its own blank-node labels."""
    import subprocess
    import sys

    package = build_package(tmp_path, name, metadata=metadata)
    script = (
        "import json, sys;"
        "sys.path[:0] = [%r];"
        "from iirds_validate import runner;"
        "r = runner.run(%r, runner.ALL_KINDS).as_dict();"
        "print(json.dumps([[f['subject'], f['detail']] for f in r['findings'] if f['rule'] == 'L4']))"
        % (str(ROOT / "src"), str(package)))
    reports = set()
    for seed in range(seeds):
        env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONDONTWRITEBYTECODE="1")
        reports.add(subprocess.run([sys.executable, "-c", script], env=env,
                                   capture_output=True, text=True, check=True).stdout.strip())
    return reports


#: The loop's own first node is not where a walk in name order comes back to:
#: the walk enters at `z2`, the only way in, and `b1` is first by name.
FIRST_BY_NAME_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:about="urn:test:a">
    <iirds:has-first-child rdf:resource="urn:test:z2"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:z2"><iirds:has-next-sibling rdf:resource="urn:test:b1"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:b1"><iirds:has-next-sibling rdf:resource="urn:test:z2"/></iirds:DirectoryNode>
</rdf:RDF>""")


def test_a_loop_is_named_by_its_first_node_and_not_by_the_way_in(tmp_path):
    assert FIRST_BY_NAME_RDF != MINIMAL_RDF
    report = runner.run(build_package(tmp_path, "way-in.iirds", metadata=FIRST_BY_NAME_RDF), runner.ALL_KINDS)
    loops = [(f.violation.subject, f.violation.detail) for f in report.findings if f.rule.id == "L4"]
    assert loops == [("urn:test:b1", "urn:test:b1, urn:test:z2")], loops


#: Two blank ways in that one subject points at with one property, so they share
#: a name -- `urn:test:p has-next-sibling`. Sorted by that name alone they stayed
#: in the order the graph produced them, the hash-seed order, and the one taken
#: first decided where the walk met the loop behind them.
TIED_WAYS_IN_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:about="urn:test:p">
    <iirds:has-next-sibling rdf:nodeID="e1"/>
    <iirds:has-next-sibling rdf:nodeID="e2"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="e1"><iirds:has-first-child rdf:resource="urn:test:x"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="e2"><iirds:has-first-child rdf:resource="urn:test:y"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:x"><iirds:has-next-sibling rdf:resource="urn:test:y"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:y"><iirds:has-next-sibling rdf:resource="urn:test:x"/></iirds:DirectoryNode>
</rdf:RDF>""")


def test_two_ways_in_that_share_a_name_do_not_choose_the_node_reported(tmp_path):
    assert TIED_WAYS_IN_RDF != MINIMAL_RDF
    reports = _l4_across_seeds(tmp_path, "tied.iirds", TIED_WAYS_IN_RDF)
    assert reports == {json.dumps([["urn:test:x", "urn:test:x, urn:test:y"]])}, sorted(reports)


#: A loop of blank nodes behind a named one. None of the three carries a label,
#: so each says the same thing; the two no named subject points at share one
#: name, a hash of what they say, and the walk can come into the loop at either.
BLANK_LOOP_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:about="urn:test:toc"><iirds:has-first-child rdf:nodeID="b1"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b1"><iirds:has-next-sibling rdf:nodeID="b2"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b2"><iirds:has-next-sibling rdf:nodeID="b3"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b3"><iirds:has-next-sibling rdf:nodeID="b1"/></iirds:DirectoryNode>
</rdf:RDF>""")


def test_a_loop_of_blank_nodes_is_written_the_same_way_across_hash_seeds(tmp_path):
    assert BLANK_LOOP_RDF != MINIMAL_RDF
    reports = _l4_across_seeds(tmp_path, "blank-loop.iirds", BLANK_LOOP_RDF)
    assert len(reports) == 1, sorted(reports)
    [(subject, detail)] = json.loads(reports.pop())
    names = detail.split(", ")
    # The loop's nodes in the order of their names, named by the first.
    assert len(names) == 3 and names == sorted(names) and subject == names[0], detail
    assert names.count("urn:test:toc has-first-child") == 1 and subject.startswith("_:"), detail


#: Two loops through one node, every node blank and told apart only by what it
#: says. A walk that reported where it came back to found one loop or both
#: depending on where it started; the two are one loop structure -- each node
#: reaches every other -- and that is what is reported, once.
TWO_LOOPS_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:about="urn:test:toc"><iirds:has-first-child rdf:nodeID="x"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="x"><rdfs:label>x</rdfs:label><iirds:has-next-sibling rdf:nodeID="y"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="y"><rdfs:label>y</rdfs:label>
    <iirds:has-next-sibling rdf:nodeID="x"/>
    <iirds:has-first-child rdf:nodeID="z"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="z"><rdfs:label>z</rdfs:label><iirds:has-next-sibling rdf:nodeID="y"/></iirds:DirectoryNode>
</rdf:RDF>""")


def test_two_loops_through_one_node_are_found_the_same_way_across_hash_seeds(tmp_path):
    assert TWO_LOOPS_RDF != MINIMAL_RDF
    reports = _l4_across_seeds(tmp_path, "two-loops.iirds", TWO_LOOPS_RDF)
    assert len(reports) == 1 and len(json.loads(next(iter(reports)))) == 1, sorted(reports)


#: Two blank ways in that share a name, `urn:test:p has-first-child`, and are
#: told apart only by what they say -- with a loop between them and a second
#: loop through one of them. A walk that reported where it came back to found
#: both loops taken one way first and one taken the other; reported as the one
#: structure the two loops make, the order the ways are taken in decides nothing.
TIED_TWO_LOOPS_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:about="urn:test:p">
    <iirds:has-first-child rdf:nodeID="u"/>
    <iirds:has-first-child rdf:nodeID="v"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="u"><rdfs:label>u</rdfs:label><iirds:has-next-sibling rdf:nodeID="v"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="v"><rdfs:label>v</rdfs:label>
    <iirds:has-next-sibling rdf:nodeID="u"/>
    <iirds:has-first-child rdf:resource="urn:test:w"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:w"><iirds:has-next-sibling rdf:nodeID="v"/></iirds:DirectoryNode>
</rdf:RDF>""")


def test_two_ways_in_that_share_a_name_do_not_choose_the_findings(tmp_path):
    assert TIED_TWO_LOOPS_RDF != MINIMAL_RDF
    reports = _l4_across_seeds(tmp_path, "tied-loops.iirds", TIED_TWO_LOOPS_RDF)
    assert len(reports) == 1 and len(json.loads(next(iter(reports)))) == 1, sorted(reports)


#: Two blank roots that say the same thing four levels down -- the depth a
#: digest of what a node says reaches -- and part ways after it, into one
#: structure of two loops through `zn`. Ordered by name and digest the two roots
#: tie, and which loop a walk met first decided whether one finding or two.
DEEP_TIE_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:nodeID="u"><rdfs:label>Contents</rdfs:label><iirds:has-first-child rdf:nodeID="a1"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="v"><rdfs:label>Contents</rdfs:label><iirds:has-first-child rdf:nodeID="b1"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a1"><rdfs:label>entry</rdfs:label><iirds:has-next-sibling rdf:nodeID="a2"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a2"><rdfs:label>entry</rdfs:label><iirds:has-next-sibling rdf:nodeID="a3"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a3"><rdfs:label>entry</rdfs:label><iirds:has-next-sibling rdf:nodeID="a4"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a4"><rdfs:label>entry</rdfs:label><iirds:has-next-sibling rdf:resource="urn:test:zm"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b1"><rdfs:label>entry</rdfs:label><iirds:has-next-sibling rdf:nodeID="b2"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b2"><rdfs:label>entry</rdfs:label><iirds:has-next-sibling rdf:nodeID="b3"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b3"><rdfs:label>entry</rdfs:label><iirds:has-next-sibling rdf:nodeID="b4"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b4"><rdfs:label>entry</rdfs:label><iirds:has-next-sibling rdf:resource="urn:test:zn"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:zm"><iirds:has-next-sibling rdf:resource="urn:test:zn"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:zn"><iirds:has-next-sibling rdf:resource="urn:test:zm"/><iirds:has-first-child rdf:resource="urn:test:zo"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:zo"><iirds:has-next-sibling rdf:resource="urn:test:zn"/></iirds:DirectoryNode>
</rdf:RDF>""")


def test_two_roots_alike_four_levels_down_do_not_choose_the_findings(tmp_path):
    assert DEEP_TIE_RDF != MINIMAL_RDF
    reports = _l4_across_seeds(tmp_path, "deep-tie.iirds", DEEP_TIE_RDF, seeds=16)
    assert reports == {json.dumps([["urn:test:zm", "urn:test:zm, urn:test:zn, urn:test:zo"]])}, sorted(reports)


#: The same tie, found apart from the one above. Two blank ways in share the
#: name of the node that points at both, `urn:j2:A has-first-child`, with a
#: loop between them; from one of them a chain of seven runs back to it, from
#: the other a chain of seven runs out, and every node of both chains is named
#: alike again, by `urn:j2:Z`, and says the same thing as far as a digest
#: reaches. The two loops are one structure of nine nodes, and a walk found one
#: finding or two as the seed fell.
OWNED_TIE_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:about="urn:j2:A">
    <iirds:has-first-child rdf:nodeID="u"/>
    <iirds:has-first-child rdf:nodeID="v"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="u"><iirds:has-next-sibling rdf:nodeID="v"/><iirds:has-first-child rdf:nodeID="a0"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="v"><iirds:has-next-sibling rdf:nodeID="u"/><iirds:has-first-child rdf:nodeID="b0"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a0"><iirds:has-next-sibling rdf:nodeID="a1"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a1"><iirds:has-next-sibling rdf:nodeID="a2"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a2"><iirds:has-next-sibling rdf:nodeID="a3"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a3"><iirds:has-next-sibling rdf:nodeID="a4"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a4"><iirds:has-next-sibling rdf:nodeID="a5"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a5"><iirds:has-next-sibling rdf:nodeID="a6"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="a6"><iirds:has-next-sibling rdf:resource="urn:j2:terminal"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b0"><iirds:has-next-sibling rdf:nodeID="b1"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b1"><iirds:has-next-sibling rdf:nodeID="b2"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b2"><iirds:has-next-sibling rdf:nodeID="b3"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b3"><iirds:has-next-sibling rdf:nodeID="b4"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b4"><iirds:has-next-sibling rdf:nodeID="b5"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b5"><iirds:has-next-sibling rdf:nodeID="b6"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:nodeID="b6"><iirds:has-next-sibling rdf:nodeID="v"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:j2:terminal"/>
  <rdf:Description rdf:about="urn:j2:Z">
    <iirds:has-first-child rdf:nodeID="a0"/><iirds:has-first-child rdf:nodeID="a1"/>
    <iirds:has-first-child rdf:nodeID="a2"/><iirds:has-first-child rdf:nodeID="a3"/>
    <iirds:has-first-child rdf:nodeID="a4"/><iirds:has-first-child rdf:nodeID="a5"/>
    <iirds:has-first-child rdf:nodeID="a6"/><iirds:has-first-child rdf:nodeID="b0"/>
    <iirds:has-first-child rdf:nodeID="b1"/><iirds:has-first-child rdf:nodeID="b2"/>
    <iirds:has-first-child rdf:nodeID="b3"/><iirds:has-first-child rdf:nodeID="b4"/>
    <iirds:has-first-child rdf:nodeID="b5"/><iirds:has-first-child rdf:nodeID="b6"/>
  </rdf:Description>
</rdf:RDF>""")


def test_ways_in_named_alike_and_alike_as_deep_as_a_digest_do_not_choose_the_findings(tmp_path):
    assert OWNED_TIE_RDF != MINIMAL_RDF
    reports = _l4_across_seeds(tmp_path, "owned-tie.iirds", OWNED_TIE_RDF, seeds=16)
    members = ["urn:j2:A has-first-child"] * 2 + ["urn:j2:Z has-first-child"] * 7
    assert reports == {json.dumps([["urn:j2:A has-first-child", ", ".join(members)]])}, sorted(reports)


#: One structure of two loops that share a node, and a loop of its own apart.
SHARED_AND_APART_RDF = MINIMAL_RDF.replace("</rdf:RDF>", """\
  <iirds:DirectoryNode rdf:about="urn:test:a"><iirds:has-next-sibling rdf:resource="urn:test:b"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:b">
    <iirds:has-next-sibling rdf:resource="urn:test:a"/>
    <iirds:has-first-child rdf:resource="urn:test:c"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:c"><iirds:has-next-sibling rdf:resource="urn:test:b"/></iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:p"><iirds:has-next-sibling rdf:resource="urn:test:p"/></iirds:DirectoryNode>
</rdf:RDF>""")


def test_a_loop_structure_is_reported_once_and_one_apart_once_more(tmp_path):
    """The nodes that each reach every other are one finding, however many ways
    round them there are: breaking that structure is one repair. A node that
    points at itself is a structure of one."""
    assert SHARED_AND_APART_RDF != MINIMAL_RDF
    report = runner.run(build_package(tmp_path, "shared.iirds", metadata=SHARED_AND_APART_RDF), runner.ALL_KINDS)
    loops = sorted((f.violation.subject, f.violation.detail) for f in report.findings if f.rule.id == "L4")
    assert loops == [("urn:test:a", "urn:test:a, urn:test:b, urn:test:c"),
                     ("urn:test:p", "urn:test:p")], loops

