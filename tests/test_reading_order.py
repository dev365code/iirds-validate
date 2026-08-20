"""A report is read top to bottom, so its order is part of what it says.

Findings used to come out in registry order -- kind, then rule id -- which is
an order about the code rather than about the package. On an archive zipped one
directory too high that put R3 fourth of six: the reader met three findings
telling them to add a mimetype, a META-INF and a metadata.rdf, all of which they
had, before reaching the one saying the package was fine and merely misplaced.

Causes first, consequences last, severity in between, rule id to break ties so
two runs cannot differ.
"""
from __future__ import annotations

import io
import zipfile

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.model import Severity


def _wrapped(tmp_path):
    """A correct package, one directory too deep. Six findings, one cause."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("mypackage/mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, b"application/iirds+zip")
        zf.writestr("mypackage/META-INF/metadata.rdf", MINIMAL_RDF)
        zf.writestr("mypackage/content/topic1.xhtml", "<html/>")
    path = tmp_path / "wrapped.iirds"
    path.write_bytes(buf.getvalue())
    return path


def test_the_finding_that_explains_the_others_comes_first(tmp_path):
    findings = runner.run(_wrapped(tmp_path), runner.ALL_KINDS).findings
    assert findings[0].rule.id == "R3"


def test_a_finding_that_only_follows_from_others_comes_last(tmp_path):
    """S2 says no graph rule could run. True, and useless as an opening line:
    it is the shadow of the real problem rather than the problem."""
    findings = runner.run(_wrapped(tmp_path), runner.ALL_KINDS).findings
    assert findings[-1].rule.id == "S2"
    assert findings[-1].rule.diagnosis == "consequence"


def test_errors_precede_warnings_precede_notes(tmp_path):
    """Between the two ends, the order is how much it matters."""
    metadata = MINIMAL_RDF.replace(
        "        <iirds:format>application/xhtml+xml</iirds:format>\n", "").replace(
        "<iirds:title>A topic</iirds:title>", "")
    package = build_package(tmp_path, "mixed.iirds", metadata=metadata,
                            mimetype=b"application/iirds+zip\n")
    findings = runner.run(package, runner.ALL_KINDS).findings

    ranks = [{Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}[f.severity]
             for f in findings if not f.rule.diagnosis]
    assert ranks == sorted(ranks), [(f.rule.id, str(f.severity)) for f in findings]
    assert Severity.ERROR in {f.severity for f in findings}
    assert Severity.WARNING in {f.severity for f in findings}


def test_the_order_is_total_so_two_runs_cannot_differ(tmp_path):
    """Ordering that leaves ties unbroken would undo the determinism work: the
    same package would produce the same findings in a different sequence."""
    package = _wrapped(tmp_path)
    runs = [[f.rule.id for f in runner.run(package, runner.ALL_KINDS).findings]
            for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


def test_the_json_report_carries_the_same_order_and_says_why(tmp_path):
    """A build gate reading JSON needs the same first line a person gets."""
    report = runner.run(_wrapped(tmp_path), runner.ALL_KINDS)
    findings = report.as_dict()["findings"]
    assert findings[0]["rule"] == "R3"
    assert findings[0]["diagnosis"] == "cause"
    assert findings[-1]["diagnosis"] == "consequence"
    assert findings[1]["diagnosis"] is None


def test_a_clean_package_is_unaffected(tmp_path):
    assert runner.run(build_package(tmp_path, "ok.iirds"), runner.ALL_KINDS).ok
