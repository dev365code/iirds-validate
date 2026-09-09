"""The JSON report is an interface, and interfaces are pinned.

`--format json` and `report.as_dict()` are what another program reads: a
build that fails on `ok`, a dashboard that counts `summary.errors`, a
stored report compared against next quarter's. The last of those is why
`schemaVersion` follows the meaning of the fields and not only their
names: two documents of one shape can answer differently. The README offers them and
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
    "judgedBy",          # what judged it, so a later run can be compared to it
    "packageDigest",     # which bytes were judged, or why there is no answer
}

#: The envelope. A stored report is read next quarter against a run of a
#: later build, and `rulesChecked` as a number can say the two runs differed
#: while being unable to say *which* rule appeared. Every key here exists to
#: stop a difference claiming more than it knows.
JUDGED_BY = {
    "toolVersion",       # the build
    "kinds",             # what the command asked to be checked
    "rulesRun",          # which rules this run actually answered, by name
    "ruleSetDigest",     # the cheap "same rule set?" before anything is compared
    "includesInfo",      # whether the quiet findings were kept
    "rulesSource",       # the rule bodies, which the rule-set digest cannot see
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
    assert set(document["judgedBy"]) == JUDGED_BY
    assert document["findings"], "this fixture must produce findings to pin them"
    for finding in document["findings"]:
        assert set(finding) == FINDING, finding.get("rule")


def test_the_schema_version_is_two(make_package):
    """It changes when the shape above changes incompatibly **or when the
    meaning of a field changes**, and a stored report from an older release
    must stay readable, so it changes rarely and never by accident.

    The second half is what moved it to 2, and it is the harder half to see.
    Not one key changed: `judgedBy.rulesRun` did. It used to name the three
    rules the runner answers itself only when they fired, so a clean answer
    from them was unrepresentable and every failure looked like a rule that
    had just arrived. Now it names them either way. Two reports, identical in
    shape, mean different things -- and a reader comparing them across the
    change would be told a package broke something it never touched, which is
    the failure the envelope exists to prevent. A per-key check cannot see
    that. Only the number can say it.
    """
    assert report_of(make_package).as_dict()["schemaVersion"] == 2


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
