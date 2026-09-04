"""The record of unreached decision lines has to be able to hold them all.

`tools/silent_paths.py` reports the lines in the rule modules that no test has
executed, and keeps a baseline so the number cannot grow quietly. The number it
publishes is a count of keys, and the key was `function :: statement` — chosen
over the line number because a record keyed on line numbers goes stale the
moment anything above it gains a line, and a stale record nobody reads is not a
record.

The trouble is that a key has to be unique and that one is not. Four `continue`
statements in one function collapse into one entry, and the count that is meant
to say "this many decisions are unmeasured" says "this many distinct sentences
are unmeasured", which is a smaller number for the same code. It is smallest
exactly where the risk is highest: a function with several unreached exits.

The tool has no test of its own, which is why this was possible. What is
checked here is the property the key needs, over the real rule modules — not
over a fixture, because the collisions are in the real ones.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import silent_paths  # noqa: E402


def _keys_per_file():
    """Every key the tool would mint, per file, in source order."""
    out = {}
    for path in sorted(silent_paths.RULES.glob("*.py")):
        source = path.read_text("utf-8")
        lines = source.splitlines()
        kinds = silent_paths.executable_lines(path)
        where = silent_paths.enclosing(ast.parse(source))
        out[path.name] = [(line, silent_paths.key_for(where, lines, line, kinds))
                          for line in sorted(kinds)]
    return out


def test_no_two_decision_lines_share_a_key():
    """One line, one entry. Twenty-six lines of the rule modules used to share
    a key with another -- `_suggest` has three identical `return None`, and
    `m30_no_schema_in_metadata` has three identical `continue` -- so the
    baseline could record a function as measured while two of its exits had
    never run."""
    collisions = []
    for name, rows in _keys_per_file().items():
        seen = {}
        for line, key in rows:
            if key in seen:
                collisions.append((name, key, seen[key], line))
            seen[key] = line
    assert collisions == [], collisions


def test_the_key_does_not_move_when_a_line_is_added_above_it():
    """Why the key is not the line number, kept as a test rather than as the
    comment it was. A record keyed on offsets is stale after any edit and a
    stale record is one nobody reads."""
    source = "def f(ctx):\n    if ctx:\n        return None\n    return None\n"
    shifted = "import os\n\n\n" + source

    def keys(text):
        tree = ast.parse(text)
        lines = text.splitlines()
        kinds = {node.lineno: "silent" for node in ast.walk(tree)
                 if isinstance(node, ast.Return)}
        where = silent_paths.enclosing(tree)
        return [silent_paths.key_for(where, lines, line, kinds)
                for line in sorted(kinds)]

    assert keys(source) == keys(shifted)
    assert len(set(keys(source))) == 2, "and the two identical returns stay apart"
