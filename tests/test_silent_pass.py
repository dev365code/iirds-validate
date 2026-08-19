"""The failure mode this project exists to eliminate, turned on itself.

README.md indicts the alternative tool for reporting a clean package when its
rules did not actually run. Three ways this tool did the same thing were found
in review; each one is pinned here. If any of these ever goes green-with-no-
findings again, the project has lost its argument.
"""
from __future__ import annotations

import multiprocessing

import pytest

from conftest import MINIMAL_RDF

from iirds_validate import runner
from iirds_validate.model import Severity

BROKEN_XML = "<rdf:RDF><unclosed>"
BROKEN_JSONLD = "{ this is not json"

#: Seven levels of nested internal entities. Small on disk, enormous once
#: expanded — the classic amplification attack against an XML parser. Realistic
#: here: the packages a manufacturer validates arrive from suppliers.
ENTITY_BOMB = (
    '<?xml version="1.0"?><!DOCTYPE rdf:RDF [' +
    "".join('<!ENTITY e%d "%s">' % (i, ("&e%d;" % (i - 1)) * 8 if i else "x" * 32)
            for i in range(7)) +
    ']><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
    ' xmlns:iirds="http://iirds.tekom.de/iirds#">'
    '<iirds:Package rdf:about="urn:p"><iirds:title>&e6;</iirds:title></iirds:Package>'
    '</rdf:RDF>'
)


def errors(report):
    return [f for f in report.findings if f.severity is Severity.ERROR]


def test_unparsable_jsonld_is_reported_even_in_an_unrestricted_package(make_package):
    """metadata.jsonld is only *mandatory* in iiRDS/H, but it is *allowed*
    anywhere from 1.3. Gating the parse check on the variant meant a corrupt
    file in an ordinary package was read, failed, and thrown away."""
    report = runner.check(make_package(metadata=MINIMAL_RDF, jsonld=BROKEN_JSONLD))

    assert not report.ok, "a corrupt metadata.jsonld must fail the run"
    assert "C16.2" in {f.rule.id for f in errors(report)}


def test_lint_does_not_report_clean_on_unparsable_metadata(make_package):
    """`lint` runs no container rules, so nothing was left to notice that the
    graph was empty because the metadata had not parsed. Every L rule then
    found nothing, and CI went green."""
    report = runner.lint(make_package(metadata=BROKEN_XML))

    assert not report.ok, "lint must not pass a package whose metadata did not parse"
    assert errors(report)


def test_lint_does_not_report_clean_when_there_is_no_metadata_at_all(make_package):
    report = runner.lint(make_package(metadata=None))
    assert not report.ok
    assert errors(report)


def _validate(path, queue):                       # pragma: no cover - child process
    queue.put(len(runner.check(path).findings))


def test_entity_expansion_is_refused_rather_than_expanded(make_package):
    """A 600-byte file must not be able to stop the validator.

    Run in a child process: if the guard regresses, the parser hangs, and a
    hanging test that gets killed is a clearer signal than a suite that never
    finishes.
    """
    path = make_package(metadata=ENTITY_BOMB)

    queue = multiprocessing.Queue()
    child = multiprocessing.Process(target=_validate, args=(str(path), queue))
    child.start()
    child.join(timeout=15)
    if child.is_alive():
        child.terminate()
        child.join()
        pytest.fail("validating a 600-byte entity bomb did not finish within 15 s")

    report = runner.check(path)
    assert not report.ok, "metadata declaring XML entities must be refused"


def test_deep_table_of_contents_does_not_crash_a_rule(make_package):
    """`iirds:has-next-sibling` is a linked list, so a flat table of contents of
    N entries is N deep. A recursive walk blew the stack at 1000 — an ordinary
    size for a machine manual — and reported it as a MUST violation naming an
    internal exception."""
    nodes = "".join(
        '  <iirds:DirectoryNode rdf:about="urn:n%d">\n'
        '    <iirds:has-next-sibling rdf:resource="urn:n%d"/>\n'
        '  </iirds:DirectoryNode>\n' % (i, i + 1) for i in range(5000))
    metadata = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
        ' xmlns:iirds="http://iirds.tekom.de/iirds#">\n'
        '  <iirds:Package rdf:about="urn:p">'
        '<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion></iirds:Package>\n'
        + nodes +
        '  <iirds:DirectoryNode rdf:about="urn:n5000"/>\n</rdf:RDF>\n')

    report = runner.run(make_package(metadata=metadata), runner.ALL_KINDS)

    crashes = [f for f in report.findings if f.rule.id == "S3"]
    assert not crashes, [f.violation.detail for f in crashes]


def test_no_rule_crashes_on_any_fixture(make_package):
    """A crashed rule is a rule that checked nothing. Cheap blanket guard."""
    from conftest import DESCRIPTION_STYLE_RDF

    for name, metadata in (("minimal", MINIMAL_RDF),
                           ("description-style", DESCRIPTION_STYLE_RDF),
                           ("empty-graph", '<?xml version="1.0"?><rdf:RDF '
                            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>')):
        report = runner.run(make_package(name="%s.iirds" % name, metadata=metadata),
                            runner.ALL_KINDS)
        assert not [f for f in report.findings if f.rule.id == "S3"], name
