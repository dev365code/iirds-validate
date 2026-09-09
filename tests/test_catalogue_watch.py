"""The gate that watches the rule catalogue upstream, and why it said nothing.

`tools/extract_catalog.py --check` answers "has plusmeta changed the rules
since the commit we pinned". It answered "yes" every time it ran, including
every time the answer was no: the payload it builds carries `_commit`, CI
calls it with `--ref master`, and the committed file carries the pinned SHA,
so the two strings differed at that field whatever upstream had done.

The job is advisory -- `continue-on-error` -- so nothing broke and nobody
could tell. A gate that always fires is the mirror image of one that never
fires, and carries the same amount of information.

What it has to answer instead is which rules moved, by name, which is also
what a person needs before deciding whether to move the pin.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "extract_catalog_under_test", ROOT / "tools" / "extract_catalog.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def rule(rid, **changes):
    base = {"id": rid, "kind": "schema", "prio": "MUST", "category": None,
            "versions": ["1.3"], "variants": [], "spec": None, "path": "Class",
            "testFiles": {"true": [], "false": []}, "en": "a rule", "de": "eine Regel"}
    base.update(changes)
    return base


def test_the_same_rules_are_no_difference_whatever_the_provenance_says():
    """The defect, in one assertion. `_commit` is metadata about the
    extraction and not about the rules, and comparing it is what made the
    gate unable to answer "no"."""
    committed = {"_commit": "0bcf19dd", "_retrieved": "2026-08-17",
                 "rules": [rule("M1"), rule("M2")]}
    fresh = {"_commit": "master", "_retrieved": "2026-09-10",
             "rules": [rule("M2"), rule("M1")]}
    assert tool.differences(committed, fresh) == ([], [], [])


def test_a_rule_that_arrived_is_named():
    committed = {"rules": [rule("M1")]}
    fresh = {"rules": [rule("M1"), rule("M2")]}
    added, removed, changed = tool.differences(committed, fresh)
    assert (added, removed) == (["M2"], [])
    assert changed == []


def test_a_rule_that_left_is_named():
    added, removed, changed = tool.differences({"rules": [rule("M1"), rule("M2")]},
                                               {"rules": [rule("M1")]})
    assert (added, removed, changed) == ([], ["M2"], [])


def test_a_rule_that_moved_names_the_fields_that_moved():
    """"Something changed" sends a person to read a hundred and fifty-seven
    rules. The fields are what tells them whether it matters."""
    committed = {"rules": [rule("M30", path="Class, Property, subClassOf")]}
    fresh = {"rules": [rule("M30", path="Class, Property",
                            testFiles={"true": ["M30_true.rdf"], "false": []})]}
    added, removed, changed = tool.differences(committed, fresh)
    assert (added, removed) == ([], [])
    assert changed == [("M30", ["path", "testFiles"])]


def test_the_committed_catalogue_is_the_one_the_pin_describes():
    """Read rather than fetched: the file says which commit it came from, and
    the tool's own default is that commit. The two drifting apart is the
    thing this whole file is about, and it is the cheapest half to check."""
    import json

    committed = json.loads(tool.OUT.read_text("utf-8"))
    assert committed["_commit"] == tool.DEFAULT_REF
    assert committed["rules"], "a catalogue with no rules is not one"


@pytest.mark.parametrize("what", ["_commit", "_retrieved", "_generated_by"])
def test_provenance_is_not_a_rule(what):
    committed = {what: "one", "rules": [rule("M1")]}
    fresh = {what: "another", "rules": [rule("M1")]}
    assert tool.differences(committed, fresh) == ([], [], [])
