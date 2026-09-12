#!/usr/bin/env python3
"""The README's table of what has held, written from what the commands print.

    python tools/gen_stable_section.py            # write the table into README.md
    python tools/gen_stable_section.py --check    # it still says what they print

A number typed into prose goes stale on the day the thing it counts moves, and
the reader has no way to tell. This project has three copies of one coverage
figure for that reason, and a release whose notes quoted the one nobody read.
So each row names a command, and the cell beside it is whatever that command
said today. The pinned catalogue commit is the clearest case: it moves at the
next pin, and nobody has to remember that this paragraph mentions it.

Three rules this file is held to. Each was written after the opposite was
found here, in the first draft, passing its own gate:

* **Every command answers offline, from a checkout with nothing built.** The
  draft called `tools/extract_catalog.py --check`, which fetches three files
  from raw.githubusercontent.com -- the one command this repository's CI says
  in its own words "cannot live in the main pipeline". It ran in the lint job,
  on every push. The offline question that command can still answer is which
  commit the committed catalogue came from, and `--pin` asks only that.
* **A command that fails is a failure, not a value.** The draft threw the exit
  status away and quoted whatever came back on either stream, so a tampered
  ontology and a drifted catalogue each rewrote their own row and passed
  `--check` -- and offline, the table published a `URLError` to the front page
  with the build green. Every command here is run through `_must`.
* **A row that cites a test cites one that mentions it.** The row accounting
  for every rule named a test about the web drop page's temporary files.
  `CHANGELOG.md` announces that exact defect in `SECURITY.md` as fixed, and it
  was written straight back in here. Each citation now carries a word the cited
  file has to contain, checked on every run.

What is deliberately not here: anything that needs the suite to have run first.
`tools/rule_coverage.py --check` reads what a run observed, so on a fresh
checkout it has nothing to read; that row names `make check` and carries no
captured output.

The two containers the exit-code rows name are build artefacts -- `fixtures/`
is not committed -- so this builds them when they are missing, with the same
commands `make` and CI use. Without that the gate crashed in CI's lint job,
which builds no fixtures, while passing on every developer machine where they
happened to be lying around.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BEGIN = "<!-- what-has-held: written by tools/gen_stable_section.py -->"
END = "<!-- /what-has-held -->"

GOOD = "fixtures/good.iirds"
BAD = "fixtures/bad.iirds"


class Failed(Exception):
    """A command this table quotes did not succeed. Its output is the message."""


def _run(args):
    """A command in this repository, with the tree's own `src` on the path."""
    env = dict(os.environ, PYTHONPATH="src", PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True,
                          text=True, env=env)
    return done.returncode, (done.stdout + done.stderr).strip()


def _must(args):
    """The output of a command that had to succeed for its row to mean anything.

    The exception is the point. A row whose command failed has nothing true to
    say, and writing the failure into the cell is how a drifted catalogue and a
    tampered ontology both reported themselves as fine.
    """
    code, said = _run(args)
    if code != 0:
        raise Failed("%s exited %d:\n%s" % (" ".join(args), code, said))
    return said


def _fixtures():
    """The two containers the exit-code rows name, built if they are not there."""
    for name, extra in ((GOOD, []), (BAD, ["--broken", "missing-format"])):
        if not (ROOT / name).exists():
            _must(["tools/make_fixture_package.py", name, *extra])


def _cites(path: str, word: str) -> str:
    """A test file named in a cell, once it is known to mention what the cell says.

    `word` is a token out of the claim itself -- the field a row is about, the
    thing a test would have to name to be about the same thing. A citation that
    cannot pass this is a citation to the wrong file, which is how `SECURITY.md`
    came to cite, as the proof for a rule, a test that never mentioned it.
    """
    here = ROOT / path
    if not here.exists():
        raise Failed("%s cites %s, which is not there" % (__file__, path))
    if word not in here.read_text(encoding="utf-8"):
        raise Failed("%s is cited for %r and does not mention it" % (path, word))
    return "`%s`" % path


def _cell(value: str) -> str:
    """One table cell: no pipe may split it, no newline may end the row early."""
    return " ".join(str(value).split()).replace("|", r"\|")


def rows():
    """Each row: what it says, how to see it, what came back."""
    _fixtures()

    document = json.loads(_must(["-m", "iirds_validate", "check", GOOD, "-f", "json"]))
    after = ", ".join("`%s`" % key for key in list(document)[1:])
    ran = len(document["judgedBy"]["rulesRun"])
    excused = {rule for ids in document["notApplicable"].values() for rule in ids}

    clean, _ = _run(["-m", "iirds_validate", "check", GOOD])
    findings, _ = _run(["-m", "iirds_validate", "check", BAD])
    absent, _ = _run(["-m", "iirds_validate", "check", "no-such-file.iirds"])

    pin = _must(["tools/extract_catalog.py", "--pin"])
    ontologies = _must(["-m", "iirds_validate.ontology", "--verify"])
    verified = sum(1 for line in ontologies.splitlines() if line.strip().endswith("ok"))

    return [
        ("The report is a document with a `schemaVersion`, and keys are added without moving it",
         "`iirds check %s -f json`" % GOOD,
         "`\"schemaVersion\": %s`, then %s" % (document["schemaVersion"], after)),
        ("`iirds check` exits `0` when the package drew no error (with `-W`, a warning is one)",
         "`iirds check %s; echo $?`" % GOOD, "`%d`" % clean),
        ("`1` when it did",
         "`iirds check %s; echo $?`" % BAD, "`%d`" % findings),
        ("`2` when nothing was judged: a path that is not there, or an input it refused",
         "`iirds check no-such-file.iirds; echo $?`", "`%d`" % absent),
        ("Every registered rule is answered for: run, or excused with a reason",
         "the same JSON — `judgedBy.rulesRun`, and the top-level `notApplicable`",
         "%d run and %d excused, no overlap, together the whole registry of %d; %s holds it. "
         "`summary.rulesSkipped` is a different count and not the other half"
         % (ran, len(excused), ran + len(excused),
            _cites("tests/test_report_envelope.py", "notApplicable"))),
        ("The rule catalogue here was taken from one pinned upstream commit, and says which "
         "(whether upstream still matches it is a weekly job, not this one)",
         "`python tools/extract_catalog.py --pin`", "`%s`" % pin),
        ("The ontologies shipped here are the recorded ones, checked by digest",
         "`python -m iirds_validate.ontology --verify`", "%d files, every one `ok`" % verified),
        ("The ids that fire are the recorded ones",
         "`make check` — the gate is `tools/rule_coverage.py --check`, which reads what a run "
         "observed, so a fresh checkout has nothing for it to read yet",
         "a rule that stops firing stops the build"),
        ("A validation run makes no network request",
         "%s, which runs a check with the socket sealed"
         % _cites("tests/test_offline.py", "socket"), "the suite"),
    ]


def table() -> str:
    lines = [BEGIN, "", "| what it says | how to see it | what came back |", "|---|---|---|"]
    lines += ["| %s | %s | %s |" % tuple(_cell(cell) for cell in row) for row in rows()]
    lines += ["", END]
    return "\n".join(lines)


def _place(text: str):
    """The one pair of markers, or a reason there is no place to write.

    Splitting on the first of each was enough to regenerate the block and not
    enough to see a second copy of it below: a stale duplicate pasted lower in
    the file was carried through untouched, with `--check` green.
    """
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise Failed("README.md needs exactly one %s and one %s; it has %d and %d"
                     % (BEGIN, END, text.count(BEGIN), text.count(END)))
    if text.index(BEGIN) > text.index(END):
        raise Failed("README.md has %s before %s" % (END, BEGIN))
    head, rest = text.split(BEGIN, 1)
    _old, tail = rest.split(END, 1)
    return head, tail


def main() -> int:
    parser = argparse.ArgumentParser(description="the README's table of what has held")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    try:
        head, tail = _place(text)
        fresh = head + table() + tail
    except Failed as why:
        print(why, file=sys.stderr)
        return 1

    if args.check:
        if fresh != text:
            print("README.md's table is not what the commands print; rerun "
                  "tools/gen_stable_section.py", file=sys.stderr)
            return 1
        print("the table is what the commands print")
        return 0

    readme.write_text(fresh, encoding="utf-8")
    print("README.md: table written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
