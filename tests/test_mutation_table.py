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


def test_the_ci_shards_add_up_to_the_table():
    """CI runs the sweep as shards, each under a time limit of its own: the
    comparison rows run pySHACL, minutes a row, and the whole table run as one
    job outlasts the platform's limit for a job. A sweep split that way is the
    sweep only if the shards add up to the table -- every row in one shard and
    in no other, and the workflow asking for every shard it splits into."""
    import re

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = workflow.split("\n  mutations:\n", 1)[1].split("\n  wheel:\n", 1)[0]
    run = re.search(r"python tools/mutation_table\.py --run --shard \$\{\{ matrix\.shard \}\}/(\d+)\n", job)
    assert run, "the mutations job does not run one shard of the table"
    n = int(run.group(1))
    listed = re.search(r"\n        shard: \[([\d, ]+)\]\n", job)
    assert listed and [int(s) for s in listed.group(1).split(",")] == list(range(1, n + 1)), job
    assert re.search(r"\n    timeout-minutes: \d+\n", job), "a shard with no limit of its own runs to the platform's"
    assert "fail-fast: false" in job, "one failing shard would cancel the rest, and their rows go unrun"

    shards = [mutation_table.shard(mutation_table.TABLE, "%d/%d" % (k, n)) for k in range(1, n + 1)]
    ran = [row[0] for rows in shards for row in rows]
    assert sorted(ran) == sorted(row[0] for row in mutation_table.TABLE), "a row is in no shard"
    assert len(ran) == len(set(ran)), "a row is in two shards"
    assert max(map(len, shards)) - min(map(len, shards)) <= 1, [len(rows) for rows in shards]
