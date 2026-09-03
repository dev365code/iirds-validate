"""The JSON report is an interface, and interfaces are pinned.

`--format json` and `report.as_dict()` are what another program reads: a
build that fails on `ok`, a dashboard that counts `summary.errors`, a
stored report compared against next quarter's. The README offers them and
`schemaVersion` announces that they are a contract — and nothing held
either. A key could be renamed, or the version bumped, and every test
still passed, because the tests that read the report each read the one
key they were about.

So the shape is written out here in full. Adding a key is a deliberate
edit of this file, which is the point: a consumer's parser survives a new
key and does not survive a renamed one, so growth is cheap and change is
not.
"""
from __future__ import annotations

import json

from conftest import MINIMAL_RDF
from iirds_validate import runner

#: Every key of the report document, and what a consumer does with it.
DOCUMENT = {
    "schemaVersion",     # this contract's own number
    "package",           # the file or directory judged
    "ok",                # the verdict, the same one the exit code carries
    "iirdsVersion",      # what the package declared, or null
    "validatedAgainst",  # the edition the run actually used
    "variant",           # the profile
    "summary",           # the counts
    "findings",          # the findings, in reading order
    "notes",             # what the run wants said before the findings
    "notApplicable",     # which rules did not run, by reason
    "suppressed",        # rules whose findings were demoted out of the listing
}

SUMMARY = {"errors", "warnings", "info", "rulesChecked", "rulesSkipped",
           "rulesNotImplemented", "findingsNotListed"}

FINDING = {"rule", "source", "kind", "severity", "priority", "message",
           "subject", "detail", "fix", "diagnosis", "title", "spec"}


def report_of(make_package):
    """A package that fails, so that findings are present to be examined."""
    metadata = MINIMAL_RDF.replace("<iirds:title>A topic</iirds:title>", "")
    return runner.run(make_package(metadata=metadata), runner.ALL_KINDS)


def test_the_document_carries_exactly_these_keys(make_package):
    document = report_of(make_package).as_dict()
    assert set(document) == DOCUMENT
    assert set(document["summary"]) == SUMMARY
    assert document["findings"], "this fixture must produce findings to pin them"
    for finding in document["findings"]:
        assert set(finding) == FINDING, finding.get("rule")


def test_the_schema_version_is_one(make_package):
    """It changes when the shape above changes incompatibly, and a stored
    report from an older release must stay readable, so it changes rarely
    and never by accident."""
    assert report_of(make_package).as_dict()["schemaVersion"] == 1


def test_what_the_cli_prints_is_what_the_library_returns(make_package):
    """Two ways in, one document. A consumer that starts with the command
    and moves to the library must not have to re-learn the report."""
    import io
    import json as _json

    from iirds_validate import report as report_module

    result = report_of(make_package)
    out = io.StringIO()
    report_module.render_json(result, out)
    assert _json.loads(out.getvalue()) == _json.loads(_json.dumps(result.as_dict()))


def test_the_document_is_json_with_no_python_left_in_it(make_package):
    """`as_dict` is handed to `json.dumps` by the CLI; a value that is a set,
    a Path or an rdflib term serialises there and nowhere else."""
    document = report_of(make_package).as_dict()
    round_tripped = json.loads(json.dumps(document))
    assert round_tripped == document
    for finding in document["findings"]:
        for key, value in finding.items():
            assert value is None or isinstance(value, (str, int, float, bool)), (key, value)
