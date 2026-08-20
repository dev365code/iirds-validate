"""Fixtures for the test suite.

The container builder itself lives in `tools/make_fixture_package.py` so that
CI can produce a package for the installed-wheel smoke test without importing
pytest. One builder, imported here, rather than two that drift apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from make_fixture_package import (  # noqa: E402
    ATTRIBUTE_STYLE_RDF,
    DESCRIPTION_STYLE_RDF,
    MIMETYPE,
    MINIMAL_JSONLD,
    MINIMAL_RDF,
    build_package,
)

__all__ = ["ATTRIBUTE_STYLE_RDF", "DESCRIPTION_STYLE_RDF", "MIMETYPE", "MINIMAL_JSONLD", "MINIMAL_RDF",
           "build_package", "make_package"]


@pytest.fixture
def make_package(tmp_path):
    def factory(**kwargs):
        return build_package(tmp_path, **kwargs)
    return factory


# ---------------------------------------------------------------------------
# Which rules ever actually fire
#
# A rule that produces no finding anywhere in the whole suite has never been
# observed to work. It may be correct and merely untested; it may also be dead,
# and the two are indistinguishable from inside. S8 spent months in that state
# and was inverted the entire time -- it could only ever have fired wrongly,
# and no test would have noticed either way.
#
# So every Report the suite produces is observed here, and the set of rule ids
# seen is written out at the end of the session. `tools/rule_coverage.py`
# compares it against a committed baseline, in the same shape as the
# cross-validation agreement: not a target, but a number that cannot move
# without somebody saying so.
# ---------------------------------------------------------------------------

FIRED: set = set()
OBSERVED = Path(__file__).resolve().parents[1] / ".rule-coverage.json"


@pytest.fixture(autouse=True, scope="session")
def _observe_which_rules_fire():
    """Wrap the runner's three entry points and record what they report."""
    from iirds_validate import runner

    originals = {name: getattr(runner, name) for name in ("run", "check", "lint")}

    def wrap(fn):
        def wrapped(*args, **kwargs):
            report = fn(*args, **kwargs)
            FIRED.update(f.rule.id for f in report.findings)
            return report
        return wrapped

    for name, fn in originals.items():
        setattr(runner, name, wrap(fn))
    yield
    for name, fn in originals.items():
        setattr(runner, name, fn)


def pytest_sessionfinish(session, exitstatus):
    """Write what was seen. Deliberately not an assertion here: a failure
    raised from a session hook reports as an internal error rather than as a
    test, which is the wrong way to tell somebody a rule went dead."""
    import json
    if FIRED:
        OBSERVED.write_text(json.dumps(sorted(FIRED), indent=1) + "\n", "utf-8")
