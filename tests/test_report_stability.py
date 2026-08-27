"""The same input must give the same report — over everything, not a sample.

The claim in README.md is that output is byte-identical between runs. It has
been checked by one fixture at a time, and a fixture checks the sites it
happens to reach: the one in tests/test_determinism.py drives a blank-node
Rendition under a named Topic, which is named by the route that reaches it and
so was never at risk. Meanwhile a Consortium sample package produced three
different reports from three runs of the shipped release, and two rules were
naming a different real thing each time.

So this file asks the question of the whole corpus at once, and of the
Consortium's packages when they are present. It is slow by design: a property
this project sells cannot be sampled.
"""
from __future__ import annotations

import glob
import json
import os
import tempfile
from pathlib import Path

import pytest

from conftest import build_package
from iirds_validate import runner

ROOT = Path(__file__).resolve().parents[1]
RUNS = 3


def _report(package) -> str:
    return json.dumps(runner.run(package, runner.ALL_KINDS).as_dict(), sort_keys=True)


def _fixtures():
    corpus = sorted(glob.glob(str(ROOT / "tests" / "corpus" / "**" / "*.rdf"), recursive=True))
    return [p for p in corpus if "metadata" in Path(p).name or "Example" in Path(p).name]


FIXTURES = _fixtures()


def test_the_corpus_is_actually_there():
    """A sweep over an empty list is a green test that checks nothing.

    This counts paths, which is only the number of comparisons because the
    sweep below no longer turns a failure to build into a skip. It used to:
    every fixture skipped and the file still exited zero, so anything that
    made the builder raise -- a new precondition, a changed signature --
    would have disarmed the whole sweep in silence. No fixture in the corpus
    reaches that branch today, which is what made it safe to remove and
    dangerous to keep."""
    assert len(FIXTURES) > 80, len(FIXTURES)


@pytest.mark.parametrize("source", FIXTURES, ids=[Path(p).stem[:40] for p in FIXTURES])
def test_every_corpus_fixture_reports_the_same_thing_every_run(tmp_path, source):
    metadata = Path(source).read_text("utf-8", errors="replace")
    package = build_package(tmp_path, "stable.iirds", metadata=metadata)
    reports = {_report(package) for _ in range(RUNS)}
    assert len(reports) == 1, "%d distinct reports from %d runs" % (len(reports), RUNS)


#: An unset variable means "no samples", not "glob the working directory",
#: which is what os.path.join("", "*.iirds") does.
_SAMPLE_DIR = os.environ.get("IIRDS_SAMPLE_CONTENT", "")
SAMPLES = (sorted(glob.glob(os.path.join(_SAMPLE_DIR, "*.iirds"))) if _SAMPLE_DIR else [])


@pytest.mark.skipif(not SAMPLES, reason="set IIRDS_SAMPLE_CONTENT to the sample packages")
@pytest.mark.parametrize("package", SAMPLES, ids=[Path(p).stem for p in SAMPLES])
def test_every_consortium_package_reports_the_same_thing_every_run(package):
    """The material this project has least excuse to be unstable on."""
    reports = {_report(package) for _ in range(RUNS)}
    assert len(reports) == 1, "%d distinct reports from %d runs" % (len(reports), RUNS)


def test_a_report_survives_a_console_that_cannot_show_its_arrow():
    """A console that cannot encode U+2192 is the default on a Windows
    machine outside an English locale, and the remedy marker was written
    there without asking: the report stopped at the first remedy, mid-run,
    with a traceback where the rest of the findings should have been. The
    exit code was still 1, so a build reading only that saw nothing wrong.

    Found by comparing one run against itself through a second surface, on a
    machine none of the reading had happened on.
    """
    import io

    from iirds_validate import report as report_module
    from iirds_validate import runner

    package = build_package(Path(tempfile.mkdtemp()), "cp1252.iirds",
                            mimetype=b"application/zip")
    report = runner.run(str(package), runner.ALL_KINDS)
    assert report.findings, "this fixture is supposed to have a remedy to print"

    narrow = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")
    report_module.render_text(report, stream=narrow)
    narrow.flush()
    text = narrow.buffer.getvalue().decode("cp1252")
    assert "->" in text, text
    assert "FAIL" in text, "the report stopped before it finished"

    wide = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="")
    report_module.render_text(report, stream=wide)
    wide.flush()
    assert "→" in wide.buffer.getvalue().decode("utf-8"), (
        "a console that can show the arrow should still get it")
