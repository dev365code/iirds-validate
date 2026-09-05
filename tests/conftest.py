"""Fixtures for the test suite.

The container builder itself lives in `tools/make_fixture_package.py` so that
CI can produce a package for the installed-wheel smoke test without importing
pytest. One builder, imported here, rather than two that drift apart.
"""
from __future__ import annotations

import os
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

# The warning policy of pyproject's `filterwarnings` reaches this interpreter
# and no other. Nine modules run the tool as a child process, and a warning
# raised there went to a stderr nobody read while the parent stayed green.
# The children inherit this: a RuntimeWarning from anywhere (runpy raises
# the `-m` one, about our module) and a UserWarning -- `warnings.warn`'s
# default, the category this package's own code would raise -- are errors
# there too. Not `error` outright: on the dependency floor the libraries'
# own DeprecationWarnings would end every child, and the module field of a
# `-W` filter is a literal name, not a prefix, so "our packages" cannot be
# said there. Only set where the caller has not chosen a policy of their own.
os.environ.setdefault("PYTHONWARNINGS", "error::RuntimeWarning,error::UserWarning")


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

#: Which tests actually passed, by `module::name`. `docs/scope.md` publishes
#: how many coverage claims are "held by a package", and each of those names a
#: test in `tests/test_covers_is_earned.py`. That file could only check the
#: function existed -- so marking one `@pytest.mark.skip` left the number
#: standing and the claim held by a function nobody ran, which is the state
#: the number exists to rule out. Recorded here and compared by
#: `tools/held_claims.py`, after the run, the way rule coverage is.
PASSED: set = set()
#: Every test the run collected, whatever became of it. What passed is not
#: enough to say a claim is held: a parametrised case list that ran one row
#: and skipped twenty-six leaves the function name in PASSED and nothing to
#: say the other rows were ever there. `tools/held_claims.py` compares the
#: two.
COLLECTED: set = set()
#: test -> the rules that fired while it ran. What a named case actually did,
#: as against what its name suggests. `COUNTEREXAMPLES` stands on a package and
#: a rule that reports it; `NAMED_CASES` stood on a string, so a claim could
#: point at a test about something else entirely and nothing noticed.
FIRED_BY_TEST: dict = {}
#: The test running now, as a stack because a fixture may run inside one.
CURRENT_TEST: list = []
PASSED_FILE = Path(__file__).resolve().parents[1] / ".passed-tests.json"


def _tree_fingerprint() -> str:
    """What the suite was run against.

    `tools/held_claims.py` reads this record after the fact, and nothing said
    which tree it described. A run that collected nothing leaves the previous
    record in place -- the writer below only writes when something passed --
    so deleting a test file and running `make exercised` reported every claim
    held, on yesterday's evidence.
    """
    import hashlib

    digest = hashlib.sha256()
    root = Path(__file__).resolve().parents[1]
    for folder in ("src/iirds_validate", "tests"):
        for path in sorted((root / folder).rglob("*.py")):
            digest.update(path.name.encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def pytest_collection_modifyitems(items):
    for item in items:
        path, _, name = item.nodeid.partition("::")
        COLLECTED.add("%s::%s" % (Path(path).stem, name))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    path, _, name = item.nodeid.partition("::")
    CURRENT_TEST.append("%s::%s" % (Path(path).stem, name.partition("[")[0]))
    try:
        yield
    finally:
        CURRENT_TEST.pop()


def pytest_runtest_logreport(report):
    """Both spellings of what passed: the bare function and, for a
    parametrised test, the case.

    Only the bare name was kept, so one passing parameter marked the whole
    function as passed and a claim held by one row of a table looked held when
    the other rows had been skipped. The parametrised id is what
    `tools/held_claims.py` needs to check a table row by row.
    """
    if report.when == "call" and report.passed:
        path, _, name = report.nodeid.partition("::")
        stem = Path(path).stem
        PASSED.add("%s::%s" % (stem, name.partition("[")[0]))
        if "[" in name:
            PASSED.add("%s::%s" % (stem, name))


@pytest.fixture(autouse=True, scope="session")
def _observe_which_rules_fire():
    """Wrap the runner's three entry points and record what they report."""
    from iirds_validate import runner

    originals = {name: getattr(runner, name) for name in ("run", "check", "lint")}

    def wrap(fn):
        def wrapped(*args, **kwargs):
            report = fn(*args, **kwargs)
            ids = {f.rule.id for f in report.findings}
            FIRED.update(ids)
            if CURRENT_TEST:
                FIRED_BY_TEST.setdefault(CURRENT_TEST[-1], set()).update(ids)
            # A subject that is an rdflib term rather than text renders, and
            # then the report's grouping concatenates it and rdflib warns on
            # stderr that the result "does not look like a valid URI". Every
            # run in the suite is checked, so a new rule cannot bring one in.
            odd = [(f.rule.id, type(f.violation.subject).__name__) for f in report.findings
                   if f.violation.subject is not None and type(f.violation.subject) is not str]
            assert odd == [], "a finding's subject must be plain text: %r" % odd
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
    if PASSED:
        PASSED_FILE.write_text(json.dumps(
            {"tree": _tree_fingerprint(), "passed": sorted(PASSED),
             "collected": sorted(COLLECTED),
             "fired_by_test": {k: sorted(v) for k, v in sorted(FIRED_BY_TEST.items())}},
            indent=1) + "\n", "utf-8")


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
