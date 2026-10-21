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


def test_nothing_one_row_writes_reaches_the_next(tmp_path, monkeypatch, capsys):
    """A check may write into the tree: `tools/emit_shacl.py` rewrites the
    shapes from the generator a row has just broken. Run in a tree the rows
    share, the next row is judged against what the last one's mutation wrote --
    here, its own checks fail before its own mutation is applied."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tools" / "make.py").write_text(
        'MADE = "1"\nopen("made.txt", "w").write(MADE)\n', encoding="utf-8")
    (tmp_path / "made.txt").write_text("1", encoding="utf-8")
    (tmp_path / "said.py").write_text('SAID = "1"\n', encoding="utf-8")
    (tmp_path / "tests" / "test_both.py").write_text(
        "def test_made():\n    assert open('made.txt').read() == '1'\n\n\n"
        "def test_said():\n    assert open('said.py').read() == 'SAID = \"1\"\\n'\n", encoding="utf-8")
    monkeypatch.setattr(mutation_table, "ROOT", tmp_path)
    monkeypatch.setattr(mutation_table, "TABLE", [
        ("made", "tools/make.py", 'MADE = "1"', 'MADE = "2"', ["tools/make.py", "tests/test_both.py"], ""),
        ("said", "said.py", 'SAID = "1"', 'SAID = "2"', ["tests/test_both.py"], ""),
    ])
    monkeypatch.setattr(sys, "argv", ["mutation_table.py", "--run"])

    assert mutation_table.main() == 0, capsys.readouterr().err
    assert capsys.readouterr().out.split("\n")[:2] == ["killed  made", "killed  said"]


def test_rows_that_ask_the_same_tests_are_dealt_evenly():
    """A row costs what its tests cost, before the mutation and after it:
    seconds for most selections, minutes for the ones that run pySHACL.
    However many shards the table is split into, every selection's rows land
    in them as evenly as they divide, wherever the table lists them."""
    def asked(row):
        return tuple(check for check in row[4] if not check.startswith("tools/"))

    for n in range(1, len(mutation_table.TABLE) + 1):
        shards = [mutation_table.shard(mutation_table.TABLE, "%d/%d" % (k, n)) for k in range(1, n + 1)]
        for selection in {asked(row) for row in mutation_table.TABLE}:
            counts = [sum(asked(row) == selection for row in rows) for rows in shards]
            assert max(counts) - min(counts) <= 1, (n, selection, counts)


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
