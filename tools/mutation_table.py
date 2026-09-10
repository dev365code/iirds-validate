#!/usr/bin/env python3
"""Every claim this project makes about a gate, as a mutation somebody can run.

    python tools/mutation_table.py            # list the table
    python tools/mutation_table.py --check    # the table still matches the code
    python tools/mutation_table.py --run      # apply each one and check it dies

A gate is worth what it catches. Saying a test covers a line is a claim about
the test, and the only way to hold a claim like that is to break the line and
watch the test go red. Each row here is one break, the checks that must fail
because of it, and what it would mean if they did not.

The harness holds itself to the same standard:

  * **the mutation has to take effect.** Every row asserts its original text
    appears exactly once in the file it names. A row whose anchor has drifted
    is an error, not a pass -- it would otherwise report a gate as sound while
    changing nothing.
  * **the bytecode has to be the new bytecode.** Restoring a file to its
    previous size leaves a `.pyc` CPython still considers valid, because the
    source mtime it records has one-second resolution. Every apply and restore
    clears `__pycache__` and touches the file.
  * **the checks have to run.** A selection that collects nothing exits 5, and
    a run where everything skipped exits 0 while asserting nothing. Both are
    broken rows, not killed mutants.
  * **one row must survive.** If every row dies, the likeliest explanation is a
    harness that reports red whatever it is given. The canary is a change that
    genuinely does not matter, and its dying means the rest of the table means
    nothing.

It works on a copy of the tree, so an interrupted run cannot leave a mutation
in your working directory.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PACKAGE = "src/iirds_validate/package.py"
SYSTEM = "src/iirds_validate/rules/system.py"
CONTAINER = "src/iirds_validate/rules/container.py"
CLI = "src/iirds_validate/cli.py"
LINKS = "tests/test_unpacked_links.py"

#: (id, file, original, mutated, checks that must go red, why it matters)
#: A check is a pytest path, or `tools/<script> <args>` for a gate that is a tool.
TABLE = [
    ("links/only-the-last-component-is-followed",
     PACKAGE,
     "        if _is_link(here):",
     "        if _is_link(here) and not pending:",
     [LINKS],
     "a link to `b/secret` reads as inside while `b` is a link out of the container"),

    ("links/a-step-above-the-root-is-allowed",
     PACKAGE,
     "            if not done:\n                return LEAVES, None",
     "            if False:\n                return LEAVES, None",
     [LINKS],
     "`../..` out of the container resolves and the file outside is read"),

    ("links/an-absolute-target-is-trusted",
     PACKAGE,
     "                if inner is None:",
     "                if False:",
     [LINKS],
     "a link to /etc/passwd is followed because its text is absolute"),

    ("links/no-cap-on-the-chain",
     PACKAGE,
     "MAX_LINK_HOPS = 32",
     "MAX_LINK_HOPS = 10 ** 9",
     [LINKS],
     "the tool reads names the system itself refuses with ELOOP"),

    ("links/directory-links-unclassified",
     PACKAGE,
     "            if _is_link(full):\n                directories.remove(name)",
     "            if False:\n                directories.remove(name)",
     [LINKS],
     "a directory link out of the container is walked through"),

    ("links/no-follow-at-the-read",
     PACKAGE,
     '        verdict, where = _resolve(self._roots, name.split("/"))',
     "        verdict, where = INSIDE, os.path.join(self._top, *name.split('/'))",
     [LINKS],
     "a file swapped for a link after the listing is read"),

    ("links/markers-answered-by-the-far-end",
     PACKAGE,
     '    return (os.path.lexists(str(path / MIMETYPE_FILE))\n'
     '            or os.path.lexists(str(path / METADATA_RDF)))',
     "    return (path / MIMETYPE_FILE).exists() or (path / METADATA_RDF).exists()",
     [LINKS],
     "whether a file somewhere else exists decides whether a directory is a container"),

    ("links/an-unlistable-directory-is-silence",
     PACKAGE,
     "    for here, directories, files in os.walk(top, followlinks=False, onerror=refuse):",
     "    for here, directories, files in os.walk(top, followlinks=False):",
     [LINKS],
     "a directory the check cannot read is skipped and the package passes on what is left"),

    ("links/one-root-spelling-only",
     PACKAGE,
     "        self._roots = (self._top, os.path.abspath(str(self.path)))",
     "        self._roots = (self._top,)",
     [LINKS],
     "a container reached by one of its names reports its own files as leaving it"),

    ("links/the-search-trusts-its-candidates",
     PACKAGE,
     "        verdict, where = _resolve(roots, candidate.relative_to(path).parts)",
     "        verdict, where = INSIDE, str(candidate)",
     [LINKS],
     "a `.iirds` name that is a link out of the searched directory is opened"),

    ("links/the-search-roots-unresolved",
     PACKAGE,
     "    roots = (os.path.realpath(str(path)), os.path.abspath(str(path)))",
     "    roots = (os.path.abspath(str(path)),)",
     [LINKS],
     "an ordinary alias inside a build directory is refused and nothing is checked"),

    ("links/a-link-to-nothing-is-listed-as-a-file",
     PACKAGE,
     "                elif not os.path.lexists(target):",
     "                elif False:",
     [LINKS],
     "a name no rule can read is listed as one the container holds"),

    ("s6/ignores-links-out",
     SYSTEM,
     "    for name in ctx.package.outward_links:",
     "    for name in ():",
     [LINKS],
     "an entry that leads out of the container is refused in silence"),

    ("s6/ignores-absolute-links",
     SYSTEM,
     "    for name in ctx.package.absolute_links:",
     "    for name in ():",
     [LINKS],
     "an entry written as an absolute path is refused in silence"),

    ("s6/ignores-chains",
     SYSTEM,
     "    for name in ctx.package.chained_links:",
     "    for name in ():",
     [LINKS],
     "a chain no reader can follow is refused in silence"),

    ("s6/ignores-links-to-nothing",
     SYSTEM,
     "    for name in ctx.package.dangling_links:",
     "    for name in ():",
     [LINKS],
     "an entry that points at nothing is absent from the report entirely"),

    ("c7/does-not-count-a-refused-entry",
     CONTAINER,
     "               + list(ctx.package.absolute_links))",
     ")",
     [LINKS],
     "a container whose META-INF holds one link is told its META-INF is missing"),

    ("cli/says-nothing-about-what-it-refused",
     CLI,
     "        if missing or empty or leaving:",
     "        if missing or empty:",
     [LINKS],
     "a gate passes while checking less than it was asked to"),

    # The canary. It has to survive: if it dies, the harness is reporting red
    # for everything and the rows above prove nothing.
    ("canary/a-comment-nobody-reads",
     PACKAGE,
     "#: What `_resolve` answers. Four facts about a name, because they are four",
     "#: What `_resolve` answers. Four facts about a name -- they are four",
     [LINKS],
     "nothing: the text of a comment is not a gate"),
]

CANARY = "canary/a-comment-nobody-reads"


def clear(tree: Path) -> None:
    for cache in tree.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def run(tree: Path, checks: list):
    """Whatever the row names: a pytest selection, or a gate that is a tool.

    Returns the worst exit code and what pytest printed -- `None` when the row
    names no pytest selection at all, which is not the same as one that printed
    nothing. An exit code alone cannot tell a test that ran from one that
    declined to; `_ran` reads the summary line for that.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    tools = [c for c in checks if c.startswith("tools/")]
    tests = [c for c in checks if not c.startswith("tools/")]
    worst, said = 0, None
    for spec in tools:
        code = subprocess.run([sys.executable, *spec.split()], cwd=tree,
                              capture_output=True, text=True, env=env).returncode
        worst = worst or code
    if tests:
        done = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *tests],
                              cwd=tree, capture_output=True, text=True, env=env)
        worst = worst or done.returncode
        said = done.stdout + done.stderr
    return worst, said


def _ran(said: str) -> bool:
    """Whether pytest asserted anything at all.

    A selection where everything skipped exits 0, so the mutation was applied,
    nothing objected, and the row would be reported as survived -- a finding
    about the run rather than about the gate.
    """
    return re.search(r"\b\d+ passed", said) is not None


def anchors():
    """Rows whose original text is not in the file exactly once."""
    drifted = []
    for row in TABLE:
        row_id, rel, old, _new, _checks, _why = row
        found = (ROOT / rel).read_text(encoding="utf-8").count(old)
        if found != 1:
            drifted.append("%s: the anchor appears %d times in %s" % (row_id, found, rel))
    return drifted


def apply(tree: Path, row) -> None:
    row_id, rel, old, new, _checks, _why = row
    where = tree / rel
    text = where.read_text(encoding="utf-8")
    found = text.count(old)
    if found != 1:
        raise SystemExit("%s: the anchor appears %d times in %s; the table has drifted "
                         "from the code and the row proves nothing" % (row_id, found, rel))
    where.write_text(text.replace(old, new), encoding="utf-8")
    where.touch()
    clear(tree)


def main() -> int:
    parser = argparse.ArgumentParser(description="mutations this project's gates must catch")
    parser.add_argument("--run", action="store_true", help="apply each row and check it dies")
    parser.add_argument("--check", action="store_true", help="only: the table still matches the code")
    args = parser.parse_args()

    if args.check:
        drifted = anchors()
        for line in drifted:
            print(line, file=sys.stderr)
        print("%d rows, %d of them drifted" % (len(TABLE), len(drifted)))
        return 1 if drifted else 0

    if not args.run:
        for row_id, rel, _old, _new, checks, why in TABLE:
            print("%s\n    %s\n    dies in: %s\n    why: %s" % (row_id, rel, ", ".join(checks), why))
        print("\n%d rows, one of them the canary." % len(TABLE))
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "tree"
        shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "build", "dist", "*.egg-info", ".pytest_cache", ".ruff_cache"))

        survivors, broken = [], []
        for row in TABLE:
            row_id, rel, _old, _new, checks, _why = row
            pristine = (tree / rel).read_text(encoding="utf-8")

            clear(tree)
            code, said = run(tree, checks)
            if code != 0:
                broken.append("%s: the checks it names already fail before the mutation" % row_id)
                continue
            if said is not None and not _ran(said):
                broken.append("%s: the checks it names assert nothing here" % row_id)
                continue

            apply(tree, row)
            code, _said = run(tree, checks)
            (tree / rel).write_text(pristine, encoding="utf-8")
            (tree / rel).touch()
            clear(tree)

            if code == 5:
                broken.append("%s: the selection %s collects nothing" % (row_id, checks))
            elif code == 0:
                survivors.append(row_id)
            print("%-7s %s" % ("survived" if code == 0 else "killed", row_id))

        print()
        for line in broken:
            print(line, file=sys.stderr)
        unexpected = [row_id for row_id in survivors if row_id != CANARY]
        if CANARY not in survivors:
            print("the canary died: the harness is reporting red whatever it is given, "
                  "and nothing above it means anything", file=sys.stderr)
        print("%d rows, %d survived (%s)" % (len(TABLE), len(survivors),
                                             ", ".join(survivors) or "none"))
        return 1 if (broken or unexpected or CANARY not in survivors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
