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
    """A sweep over an empty list is a green test that checks nothing."""
    assert len(FIXTURES) > 80, len(FIXTURES)


@pytest.mark.parametrize("source", FIXTURES, ids=[Path(p).stem[:40] for p in FIXTURES])
def test_every_corpus_fixture_reports_the_same_thing_every_run(tmp_path, source):
    metadata = Path(source).read_text("utf-8", errors="replace")
    try:
        package = build_package(tmp_path, "stable.iirds", metadata=metadata)
    except Exception as exc:                      # a fixture the builder cannot hold
        pytest.skip(str(exc)[:80])
    reports = {_report(package) for _ in range(RUNS)}
    assert len(reports) == 1, "%d distinct reports from %d runs" % (len(reports), RUNS)


SAMPLES = sorted(glob.glob(os.path.join(os.environ.get("IIRDS_SAMPLE_CONTENT", ""), "*.iirds")))


@pytest.mark.skipif(not SAMPLES, reason="set IIRDS_SAMPLE_CONTENT to the sample packages")
@pytest.mark.parametrize("package", SAMPLES, ids=[Path(p).stem for p in SAMPLES])
def test_every_consortium_package_reports_the_same_thing_every_run(package):
    """The material this project has least excuse to be unstable on."""
    reports = {_report(package) for _ in range(RUNS)}
    assert len(reports) == 1, "%d distinct reports from %d runs" % (len(reports), RUNS)
