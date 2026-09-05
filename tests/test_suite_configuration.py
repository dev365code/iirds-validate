"""The suite's own settings, read by a test rather than trusted.

A configuration table is the one part of a test suite that nothing exercises:
it is read by the runner, not by the tests, so a key that stops working --
renamed, mistyped, overridden by a stray pytest.ini -- takes its guarantee
with it and every test still passes. These check the behaviour the table is
supposed to produce, not the text of the table.
"""

import subprocess
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_a_warning_raised_by_this_packages_code_is_a_failure():
    """`filterwarnings = error`, behaviourally. Without it this warning is
    collected and reported at the end of the run, where a warning that means
    something is indistinguishable from eleven that do not."""
    with pytest.raises(UserWarning):
        warnings.warn("a warning from the package under test", stacklevel=1)


def test_the_dependencys_own_deprecation_is_still_only_a_warning():
    """The single exception: rdflib's JSON-LD parser builds a ConjunctiveGraph
    on every parse and warns about it. Nothing here constructs one, and
    failing a suite on a dependency's deprecation schedule would mean the
    suite stops being about this package.

    This provokes the real parse rather than re-raising the message by hand.
    A hand-raised copy comes from this module, so it exercises neither the
    filter's scope nor the path that actually warns -- the first version of
    this test did that, and it agreed with a filter that could not have
    covered the real warning."""
    import rdflib

    graph = rdflib.Graph()
    graph.parse(data='{"@id": "urn:test:subject", "@type": "urn:test:Class"}',
                format="json-ld")
    assert len(graph) == 1, len(graph)


def test_an_expected_failure_that_passes_is_reported(pytestconfig):
    """`xfail_strict = true`. A strict xpass cannot be observed from inside a
    test -- by the time it is decided this test has already reported -- so
    this reads the setting as the runner resolved it, which is the thing a
    stray pytest.ini or a renamed key would change."""
    assert pytestconfig.getini("xfail_strict") is True


def test_an_unregistered_mark_is_an_error(pytestconfig):
    """`--strict-markers`. Same resolution: a mark this project never
    registered should stop the run rather than warn, so a typo in a mark name
    is not a test that quietly applies to nothing."""
    assert pytestconfig.getoption("strict_markers") is True


@pytest.mark.xfail(reason="pinned: with xfail_strict this would fail if it passed",
                   strict=True)
def test_a_marked_failure_still_fails():
    raise AssertionError("if this ever passes, xfail_strict makes it a failure")


def test_a_warning_in_a_child_process_of_the_suite_is_a_failure_too():
    """`filterwarnings` reaches the interpreter running pytest and nothing
    else. Nine test modules run the tool as a child process -- the CLI, the
    zipapp, `-m iirds_validate.ontology` -- and a warning raised there was
    printed to a stderr nobody read, while the parent stayed green. The
    same policy travels in the environment the children inherit: a
    RuntimeWarning from anywhere (the one the `-m` path raised was runpy's,
    about our module) and a UserWarning, the category `warnings.warn` gives
    this package's own code. Those two, not `error` outright: on the
    dependency floor the libraries' own deprecation warnings would end
    every child, and a `-W` module field is a literal name, not a prefix,
    so "this package's modules" cannot be said in the environment."""
    import os
    import subprocess
    import sys

    def child(code):
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    # every child inherits the policy through the environment, so a test
    # that builds its own `dict(os.environ, ...)` keeps it
    assert "PYTHONWARNINGS" in os.environ
    assert child("import warnings; warnings.warn('x', RuntimeWarning)").returncode != 0
    ours = child("import warnings, iirds_validate.model as m; "
                 "warnings.warn_explicit('x', UserWarning, m.__file__, 1, module='iirds_validate.model')")
    assert ours.returncode != 0, ours.stderr
    # and a dependency's DeprecationWarning is still only a warning there
    theirs = child("import warnings; "
                   "warnings.warn_explicit('x', DeprecationWarning, 'f.py', 1, module='rdflib.term')")
    assert theirs.returncode == 0, theirs.stderr


def test_an_empty_parametrize_list_is_a_failure_and_not_a_skip(tmp_path):
    """A parametrized test whose list comes out empty ran zero cases and
    reported `1 skipped`, exit 0.

    Most of the parametrized tests here derive their list -- from the registry,
    from the manifest, from `docs/requirements.json`, from an AST walk over the
    rules. A change that empties one of those sources does not fail: it removes
    every case and reports a skip, which is what a deliberately inapplicable
    test looks like. Twenty-six modules are in that shape.

    Run rather than read. The first version of this asserted the ini value and
    said in the same breath that `--strict-markers` and `--strict-config` were
    "asserted here behaviourally rather than by reading the table" -- both
    halves false: the markers check reads `getoption`, and `--strict-config`
    was asserted nowhere at all. Reading the table proves the table says what
    it says.
    """
    probe = tmp_path / "test_probe.py"
    probe.write_text("import pytest\n"
                     "@pytest.mark.parametrize('x', [])\n"
                     "def test_nothing(x):\n    assert False\n", "utf-8")
    # `-c` because pytest takes its rootdir from the arguments: a probe file
    # outside the tree would be collected under its own rootdir and would not
    # read this project's table at all, which is the thing being checked.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-c", str(ROOT / "pyproject.toml"),
         "-p", "no:cacheprovider", str(probe)],
        cwd=str(ROOT), capture_output=True, text=True)
    assert result.returncode != 0, result.stdout
    assert "Empty parameter set" in result.stdout, result.stdout


def test_a_typo_in_this_table_is_an_error(tmp_path):
    """`--strict-config`, which nothing checked. A misspelled key in
    `[tool.pytest.ini_options]` is otherwise ignored, so a setting somebody
    believes is on can be off for a whole release."""
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\nxfial_strict = true\n", "utf-8")
    probe = tmp_path / "test_probe.py"
    probe.write_text("def test_ok():\n    assert True\n", "utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--strict-config",
         "-c", str(config), "-p", "no:cacheprovider", str(probe)],
        cwd=str(tmp_path), capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "xfial_strict" in (result.stdout + result.stderr)
