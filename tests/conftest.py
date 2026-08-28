"""Fixtures for the test suite.

The container builder itself lives in `tools/make_fixture_package.py` so that
CI can produce a package for the installed-wheel smoke test without importing
pytest. One builder, imported here, rather than two that drift apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdflib.plugins.shared.jsonld.context import Context

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
           "build_package", "make_package", "version_tuple"]

ROOT = Path(__file__).resolve().parents[1]


def shacl_or_skip():
    """pyshacl, or a skip -- unless this run was told it must have it.

    The differential gate is the strongest cross-check this project has, and
    an importorskip at module scope turns all of it off without a word.
    `pip install -e ".[dev]"` does not bring pyshacl, so a local `make check`
    could report the tree good while the gate that compares two independent
    implementations of every rule was not running at all -- and say nothing,
    because a skip is not a failure.

    Under `make` the absence is a failure, because the Makefile is what
    claims to run what CI runs. A bare `pytest` still skips politely.
    """
    import os

    try:
        import pyshacl
    except ImportError:
        if os.environ.get("IIRDS_REQUIRE_SHACL"):
            pytest.fail("this run requires pyshacl and does not have it; the "
                        "differential gate is thirty-three tests and skipping "
                        "them is not the same as passing them. "
                        "`pip install -e \".[shacl]\"`, or `make dev`.")
        pytest.skip("pyshacl is not installed; the differential gate does not "
                    "run. `make check` refuses this, a bare pytest does not.",
                    allow_module_level=True)
    return pyshacl


def version_tuple(text: str):
    """A release as numbers, so 0.10.0 sorts above 0.2.0 rather than below it."""
    parts = text.split(".")
    # isdecimal, not isdigit: `"\u00b2".isdigit()` is true and `int("\u00b2")` raises.
    assert all(part.isdecimal() for part in parts), (
        "iirds %s is not a plain release; this comparison cannot judge it" % text)
    return tuple(int(part) for part in parts)


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


# ---------------------------------------------------------------------------
# Nothing this suite parses may ask rdflib to fetch a context
#
# The metadata guard in `iirds` enumerates the JSON-LD constructs that make the
# parser go and fetch something. That is pattern-matching a specification which
# moves -- `@import` is what 1.1 added, and not knowing about it is how the
# guard came to let a supplier read files off the machine doing the reading.
#
# An enumeration cannot assert its own completeness. This can: rdflib routes
# every context dereference, network or filesystem, through one private
# function, so a test that parses a document rdflib would fetch from goes red
# here whatever keyword turns out to be responsible -- including one nobody
# has heard of yet. It costs nothing, because no conformant document reaches
# it. Suite-wide, for the checker's tests as much as the library's: the
# checker parses through the same guard.
# ---------------------------------------------------------------------------

class Dereferenced(BaseException):
    """Raised by the seal below, and deliberately not an Exception.

    The reader catches Exception around its parse -- correctly, so a hostile
    document becomes an error string rather than a traceback. That would
    swallow this too, and then the seal would only be as strong as whatever
    each test happens to assert about the string: one asserting `graph is
    None` would pass while the parser had just been out to the filesystem.
    Deriving from BaseException puts the seal above the code under test,
    which is the only place a seal can stand.
    """


@pytest.fixture(autouse=True, scope="session")
def seal_context_dereference():
    # Asserted, not assumed: a rename would turn the seal into a decoration
    # that passes for ever, which is the failure mode it exists to prevent.
    assert hasattr(Context, "_fetch_context"), (
        "rdflib no longer routes every context dereference through one "
        "function; this seal is not sealing anything")
    original = Context._fetch_context

    def refuse(self, source, *args, **kwargs):
        raise Dereferenced("the parser was asked to dereference %r" % (source,))

    Context._fetch_context = refuse
    try:
        yield
    finally:
        Context._fetch_context = original
