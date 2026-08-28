"""The suite's own settings, read by a test rather than trusted.

A configuration table is the one part of a test suite that nothing exercises:
it is read by the runner, not by the tests, so a key that stops working --
renamed, mistyped, overridden by a stray pytest.ini -- takes its guarantee
with it and every test still passes. These check the behaviour the table is
supposed to produce, not the text of the table.
"""

import warnings

import pytest


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
