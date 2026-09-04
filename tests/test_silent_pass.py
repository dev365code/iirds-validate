"""The failure mode this project exists to eliminate, turned on itself.

README.md indicts the alternative tool for reporting a clean package when its
rules did not actually run. Three ways this tool did the same thing were found
in review; each one is pinned here. If any of these ever goes green-with-no-
findings again, the project has lost its argument.
"""
from __future__ import annotations

import json
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


def test_an_entry_that_escapes_the_container_is_reported(make_package):
    """This validator never extracts anything, so it is not the one at risk.
    The consumer that unpacks the package is, and a build gate is the last
    thing to look at a supplier's archive before something else does."""
    for entry in ("../../../etc/passwd", "/tmp/evil.sh", "content/../../out"):
        report = runner.check(make_package(extra=((entry, "x"),)))
        assert "S6" in {f.rule.id for f in report.findings}, entry
        assert not report.ok, entry


def test_ordinary_entries_are_not_mistaken_for_escapes(make_package):
    report = runner.check(make_package(extra=(("content/sub/deep/a.xhtml", "<html/>"),)))
    assert "S6" not in {f.rule.id for f in report.findings}


def test_metadata_in_utf16_is_read_not_rejected(make_package):
    """rdflib decodes a bytes payload as UTF-8 unconditionally, so a document
    whose byte order mark says otherwise failed to parse at all. XML says the
    BOM decides."""
    for encoding in ("utf-16", "utf-8-sig"):
        report = runner.check(make_package(
            name="%s.iirds" % encoding,
            metadata=MINIMAL_RDF.encode(encoding) if encoding != "utf-8-sig"
            else ("﻿" + MINIMAL_RDF).encode("utf-8")))
        assert report.ok, (encoding, [f.violation.message for f in report.findings])


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_lint_does_not_report_clean_on_metadata_that_is_not_rdfxml(make_package, encoding):
    """`lint` runs no container rule, so C9 was never in its report: the
    graph rules looked at what rdflib made of `<manual>` and found little.
    The lint path emits C9 the way it emits C16.x, and S2 stands. In every
    encoding: the first judge read the stored bytes, saw no element in a
    UTF-32 document, and passed it."""
    report = runner.lint(make_package(
        metadata='<?xml version="1.0"?><manual><title>hello</title></manual>'.encode(encoding)))
    assert not report.ok
    found = {f.rule.id for f in report.findings}
    assert "C9" in found and "S2" in found and "L5" not in found


#: An iiRDS/H package's metadata.jsonld: well-formed JSON-LD 1.1, a graph with
#: statements in it, and not one term of the iiRDS vocabulary anywhere.
NO_IIRDS_JSONLD = json.dumps({
    "@context": {"dc": "http://purl.org/dc/terms/"},
    "@graph": [{"@id": "urn:test:package", "dc:title": "a package, allegedly"}]})

EMPTY_JSONLD = json.dumps({"@context": {"iirds": "http://iirds.tekom.de/iirds#"},
                           "@graph": []})

HANDOVER_RDF = MINIMAL_RDF.replace(
    "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
    "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
    "    <iirds:formatRestriction>H</iirds:formatRestriction>")


@pytest.mark.parametrize("what,jsonld", [("an empty graph", EMPTY_JSONLD),
                                         ("statements, none of them iiRDS", NO_IIRDS_JSONLD)],
                         ids=["empty-graph", "no-iirds-terms"])
def test_a_handover_jsonld_that_carries_no_iirds_metadata_is_reported(make_package, what, jsonld):
    """Section 6.12: "iiRDS/H packages MUST contain iiRDS metadata in JSON-LD
    1.1 syntax."

    The file is there and it parses, which is what was asked, and it contains
    no iiRDS metadata, which is what the sentence asks. A package like this
    satisfied every check and printed PASS -- the shape this file exists for.

    Both ends of "contains nothing": a graph with no statements at all, and a
    graph whose statements are all in somebody else's vocabulary. The second
    is the one a threshold of "is the graph non-empty" would let through.
    """
    report = runner.check(make_package(metadata=HANDOVER_RDF, jsonld=jsonld))
    assert "C16.2" in {f.rule.id for f in errors(report)}, \
        (what, sorted({f.rule.id for f in report.findings}))


def test_a_handover_jsonld_that_carries_less_than_the_rdf_is_reported(make_package):
    """The threshold C16.2 uses is one iiRDS term, and one term is not the
    metadata.

    A metadata.jsonld naming `iirds:Topic` once, in the object position of
    somebody else's property, clears that bar and hands a consumer that reads
    JSON-LD and nothing else a package with no metadata in it -- which is what
    the rule's own remedy says must not happen. The bar is defensible as the
    least that can be asked of the sentence in isolation; what covers the rest
    is L9, which reports every package whose two serialisations are not the
    same graph, and which claims section 6.12's sentence as well as its own
    now. Neither rule stands in for the other: a package whose files agree and
    are both empty of iiRDS metadata is C16.2's, and this one is L9's.
    """
    from iirds_validate.registry import all_rules

    claimants = {rule.id for rule in all_rules()
                 if "x6-12-rdf-serialization#3" in rule.covers}
    thin = json.dumps({"@graph": [{"@id": "urn:junk:1",
                                   "http://example.org/p": {"@id": IIRDS_TOPIC}}]})
    report = runner.check(make_package(metadata=HANDOVER_RDF, jsonld=thin))
    fired = {f.rule.id for f in errors(report)}
    assert claimants & fired, (sorted(claimants), sorted(fired))


IIRDS_TOPIC = "http://iirds.tekom.de/iirds#Topic"


def test_an_iirds_term_anywhere_in_the_json_ld_counts(make_package):
    """C16.2's threshold is one statement mentioning an iiRDS term "in any
    position", and the docstring defends that wording at length. Nothing held
    it: narrowed to the predicate alone, every test still passed.

    A JSON-LD file whose only iiRDS term is a *type* — `{"@type":
    "iirds:Package"}`, whose predicate is `rdf:type` and whose object is the
    iiRDS name — is metadata by anyone's reading, and the rule must not report
    it for want of an iiRDS predicate.
    """
    typed_only = json.dumps({"@context": {"iirds": "http://iirds.tekom.de/iirds#"},
                             "@graph": [{"@id": "urn:test:package", "@type": "iirds:Package"}]})
    report = runner.check(make_package(metadata=HANDOVER_RDF, jsonld=typed_only))
    assert "C16.2" not in {f.rule.id for f in errors(report)}, \
        [f.violation.message for f in report.findings if f.rule.id == "C16.2"]


def test_an_unrestricted_package_with_an_empty_json_ld_is_not_this_rules_business(make_package):
    """Section 6.12's sentence is about iiRDS/H packages. metadata.jsonld is
    optional everywhere else, so an empty one outside the profile breaches
    nothing this rule claims -- L9 reports the disagreement with metadata.rdf,
    under its own sentence. Removing the variant gate broke no test."""
    report = runner.check(make_package(metadata=MINIMAL_RDF, jsonld=EMPTY_JSONLD))
    assert "C16.2" not in {f.rule.id for f in report.findings}, \
        sorted({f.rule.id for f in report.findings})
