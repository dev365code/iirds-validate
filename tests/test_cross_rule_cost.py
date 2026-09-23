"""What a rule that crosses two collections costs, measured rather than assumed.

A rule that asks "is every X named by some Y" holds two collections at once,
and both are the sender's to size. Whether it costs X + Y or X times Y is
decided by one line somewhere else -- here, by `_rendered_files` returning a
set rather than a list -- and no test in this repository asked. A sibling
project shipped a validator whose memory grew with that product through four
releases; the verdicts were right the whole time, which is why nothing caught
it.

The axis is a count of comparisons, not a clock. Seconds are a fact about the
machine that ran them, they differ by an order of magnitude between a laptop
and a hosted runner, and a threshold in seconds is either so loose it holds
nothing or so tight it fails on a busy runner. Bytes were the other candidate
and are worse: `tests/test_side_ontology_budget.py` records a gate written
against a byte total that turned out to be the ceiling plus one whatever the
package held -- arithmetic, not a measurement, and a mutant satisfied it.

Counted through the elements themselves. A set membership hashes and compares
about once; a list membership compares its way along. So the comparison count
is what tells the two apart, and it is the same number on every machine.

What this is not: a benchmark, and not a claim that these rules are fast. It
is the one question a reader of a report cannot ask for themselves -- whether
handing this tool a larger package costs proportionally more, or squares.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from iirds_validate import runner
from iirds_validate.rules import handover
from make_fixture_package import build_package

HEAD = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:formatRestriction>H</iirds:formatRestriction>
    <iirds:title>T</iirds:title>
  </iirds:Package>
%s</rdf:RDF>
"""

RENDITION = ('    <iirds:has-rendition><iirds:Rendition>'
             '<iirds:format>application/pdf</iirds:format>'
             '<iirds:source>%s</iirds:source>'
             '</iirds:Rendition></iirds:has-rendition>\n')

DOCUMENT = ('  <iirds:Document rdf:about="urn:test:d1">\n'
            '    <iirds:title>D</iirds:title>\n'
            '    <iirds:has-document-type'
            ' rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>\n'
            '%s  </iirds:Document>\n')


class _Counted(str):
    """A name that says how often it was compared.

    `__hash__` is restated because defining `__eq__` drops the inherited one,
    and a name that cannot be hashed would turn the set under test into an
    error rather than a measurement.
    """

    tally = 0

    def __eq__(self, other):
        type(self).tally += 1
        return str.__eq__(self, other)

    def __hash__(self):
        return str.__hash__(self)


def _comparisons_for(monkeypatch, entries: int, as_list: bool = False) -> int:
    """Run R37 over a package of `entries` files and renditions; count compares.

    The container type comes from the rule's own helper and only its contents
    are replaced, so this measures the shape the code chose. `as_list` is the
    injected reimplementation the gate below has to be able to fail on.

    Rebuilding with `type(got)` rather than `set(...)` is the whole of it. The
    first version of this helper wrote `set(names)` for the un-injected case,
    which made every measurement below a measurement of *this file's* choice
    of container: the rule could have handed back a list and the ratio would
    still have come out linear. A mutant that did exactly that passed it.
    """
    real = handover._rendered_files

    def rendered(ctx):
        got = real(ctx)
        names = (_Counted(name) for name in got)
        return list(names) if as_list else type(got)(names)

    monkeypatch.setattr(handover, "_rendered_files", rendered)

    files = tuple("content/f%04d.pdf" % i for i in range(entries))
    body = DOCUMENT % "".join(RENDITION % name for name in files)
    with tempfile.TemporaryDirectory() as scratch:
        package = build_package(pathlib.Path(scratch), "handover.iirds",
                                metadata=HEAD % body,
                                content=files + ("index.html",))
        _Counted.tally = 0
        report = runner.check(package)
    assert not [f for f in report.findings if f.rule.id == "R37"], \
        "the fixture is supposed to be conformant for R37, so the count is the rule working"
    return _Counted.tally


def test_r37_costs_the_package_once_and_not_squared(monkeypatch):
    """Doubling the package doubles the comparisons, within a factor.

    The bound is a factor and not a number: what a linear pass costs per entry
    is an implementation detail and will move, while the ratio between one
    size and twice it is the claim. Three rather than two leaves room for the
    constant work that does not scale; a squared rule comes in near four and
    keeps going.
    """
    small = _comparisons_for(monkeypatch, 20)
    large = _comparisons_for(monkeypatch, 40)

    # Bounded below as well: a rule that compared nothing would satisfy any
    # ceiling. This is the half that `test_side_ontology_budget.py` had to
    # learn -- its first version held a number the mutant reproduced without
    # doing the work.
    assert small >= 20, small
    assert large >= 40, large

    assert large <= small * 3, (
        "R37 cost %d comparisons over 20 entries and %d over 40, which is not "
        "the package once -- something between the entries and the renditions "
        "now compares its way along instead of hashing" % (small, large))


def test_the_measurement_can_tell_a_squared_rule_from_a_linear_one(monkeypatch):
    """The gate above, pointed at a reimplementation that squares.

    A cost gate nobody has run against a quadratic implementation is a cost
    gate nobody has tested, and this is that run: the same rule, the same
    fixture, a list where the set was.
    """
    small = _comparisons_for(monkeypatch, 20, as_list=True)
    large = _comparisons_for(monkeypatch, 40, as_list=True)

    assert large > small * 3, (small, large)
    with pytest.raises(AssertionError):
        assert large <= small * 3


def test_the_helper_hands_back_something_hashed(monkeypatch):
    """Said directly as well, because the count above is indirect.

    The measurement is what holds the claim; this names the reason, so a
    reader who changes `_rendered_files` meets a sentence rather than a ratio
    that went red for no stated cause.

    Asked of the object and not of the source text. Reading the source for
    `set()` was the first version and it is the shape this project keeps
    having to repair: a set comprehension, a `frozenset`, or a `dict` keyed by
    name are all correct and all would have failed it, while a list built by a
    helper one line away would have passed.
    """
    seen = []
    real = handover._rendered_files

    def watching(ctx):
        got = real(ctx)
        seen.append(got)
        return got

    monkeypatch.setattr(handover, "_rendered_files", watching)

    files = ("content/a.pdf",)
    body = DOCUMENT % "".join(RENDITION % name for name in files)
    with tempfile.TemporaryDirectory() as scratch:
        package = build_package(pathlib.Path(scratch), "handover.iirds",
                                metadata=HEAD % body,
                                content=files + ("index.html",))
        runner.check(package)

    assert seen, "R37 did not run, so nothing here was measured"
    for got in seen:
        assert isinstance(got, (set, frozenset, dict)), (
            "R37 asks whether each entry is among the rendered names; that has to "
            "be a lookup and not a walk, and this came back as %s" % type(got).__name__)
