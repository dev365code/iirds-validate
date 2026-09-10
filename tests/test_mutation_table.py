"""The table of mutations has to still be about this code.

`tools/mutation_table.py` says, row by row, what breaking a line does and which
checks must go red because of it. A row whose anchor has drifted -- the line
reworded, moved, or deleted -- proves nothing, and the table would go on
listing it as a claim this project makes. Running the whole sweep takes about
half a minute and is a thing somebody does deliberately; keeping the table
honest is cheap enough to do on every run.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import mutation_table  # noqa: E402  (the path above is what makes it importable)


def test_every_row_still_names_a_line_this_code_has():
    """One occurrence, exactly. Zero means the row cannot be applied; more than
    one means it would change places nobody reasoned about."""
    assert mutation_table.anchors() == []


def test_every_row_names_files_that_are_here():
    # A check may be a pytest path or `tools/<script> <args>`; the first word
    # of either is the file that has to be there.
    missing = sorted({name for row in mutation_table.TABLE
                      for name in [row[1], *row[4]]
                      if not (ROOT / name.split()[0]).exists()})
    assert missing == [], missing


def test_the_canary_is_in_the_table():
    """The row that must survive. Without it, a harness that reported red for
    everything would read as a table where every gate holds."""
    assert mutation_table.CANARY in {row[0] for row in mutation_table.TABLE}


def test_no_row_leaves_the_code_it_mutates_unchanged():
    """A row whose replacement equals its original applies cleanly, changes
    nothing, and is reported as a gate that holds."""
    idle = [row[0] for row in mutation_table.TABLE if row[2] == row[3]]
    assert idle == [], idle
