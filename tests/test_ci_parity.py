"""`make check` and CI must run the same commands.

Three red builds in this project came from the same shape of mistake: a check
that existed in one place and not the other. `make check` was created to close
that, and within a day of its creation two gates had been added to it that CI
did not run -- so the Makefile said the tree was good and CI was not asking.

The failure is quiet in the dangerous direction. A gate only in CI is noisy and
gets fixed. A gate only in the Makefile means CI is not checking something
somebody believes it checks, and nothing says so.

This is a text comparison, not a build system, on purpose: something that
understands both files would be a third thing to keep in step.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = (ROOT / "Makefile").read_text("utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")

#: Commands `make check` runs that CI is not expected to, with the reason.
#: Empty today. An entry here is a deliberate exemption and needs justifying.
LOCAL_ONLY: dict = {}


def _check_targets():
    """The targets `check:` depends on, in order."""
    line = re.search(r"^check:(.*)$", MAKEFILE, re.M)
    assert line, "the Makefile has no check target"
    return line.group(1).split()


def _what_make_would_run():
    """The commands `make check` runs, from make.

    Read by asking make rather than by matching the Makefile's text. Every
    way a gate was found to disappear was a place where the two diverge, and
    none of them touched a recipe: `shapes/` and `tools/` are real
    directories, so dropping them from `.PHONY` made both targets "up to
    date" and four gates vanished; a second `check:` line adds a prerequisite
    the first-match search cannot see; a target defined twice runs its *last*
    recipe and the search reads the first; a line continuation, an indented
    comment and a whitespace-only line each truncated a recipe; a command held
    in a variable was invisible.

    `make -n` executes nothing. It is not a third thing to keep in step with
    the other two -- it *is* the thing the other two are about.
    """
    make = shutil.which("make")
    assert make, "make is how these gates run; the comparison needs it"
    printed = subprocess.run([make, "-n", "check"], cwd=str(ROOT), text=True,
                             capture_output=True, check=True).stdout
    out = []
    for line in printed.splitlines():
        command = line.strip()
        if not command.startswith(("python", "/")):
            continue
        # Drop the interpreter the way `_normalise` drops `$(PYTHON)`: what is
        # being compared is the gate, not how python is spelled.
        out.append(_normalise(command.split(None, 1)[1] if " " in command else command))
    return out


#: Recipe prefixes and directives that keep a command running while stopping it
#: from failing. `@` is cosmetic; these are not, and one of them was introduced
#: into this file by a repair that stripped all three as one class -- a
#: `-`-prefixed gate still appears in `make -n` and in the Makefile's text, and
#: cannot fail.
_CANNOT_FAIL = (
    (re.compile(r"^\t\s*[-+@]*-", re.M), "a recipe line prefixed with `-` ignores its exit status"),
    (re.compile(r"^\.IGNORE:", re.M), ".IGNORE: makes every recipe unable to fail"),
    (re.compile(r"^MAKEFLAGS\s*[+:]?=.*\B-i\b", re.M), "-i in MAKEFLAGS ignores every error"),
)


def _commands_of(target: str):
    """The $(PYTHON) recipe lines of one target, for attribution only.

    What runs comes from `_what_make_would_run`; this says which target each
    command sits under, which make's own output does not report. The two are
    compared, so a divergence between them is a failure rather than a silent
    difference of opinion.
    """
    body = re.search(r"^%s:.*?\n((?:\t.*\n|#.*\n|\n)*)" % re.escape(target),
                     MAKEFILE, re.M)
    if not body:
        return []
    out = []
    for raw in body.group(1).splitlines():
        if raw.startswith("#"):
            continue
        stripped = raw.strip().lstrip("@").strip()
        if stripped.startswith("$(PYTHON)"):
            out.append(stripped.replace("$(PYTHON)", "").strip())
    return out


def _normalise(command: str) -> str:
    """What the command is, ignoring how the interpreter is spelled.

    CI reaches for `/tmp/v/bin/python` in the installed-wheel job and plain
    `python` elsewhere; the Makefile uses `$(PYTHON)`. None of that is the
    thing being compared.
    """
    command = command.replace("-m pytest", "pytest").replace("-m ruff", "ruff")
    return re.sub(r"\s+", " ", command).strip()


CHECKS = [(target, _normalise(command))
          for target in _check_targets()
          for command in _commands_of(target)
          if "$@" not in command]           # fixture-building recipes, not gates


#: What `make check` depends on, by name. A floor of eight against a real
#: fourteen let six targets be deleted from the dependency list and every test
#: here still passed -- including `shapes`, `versions`, `requirements` and
#: `exercised`, which is the generated-file comparison, the edition check, the
#: obligation index and both claim gates. A count is not a list.
CHECK_TARGETS = ("lint", "generated", "corpus", "versions", "requirements",
                 "shapes", "test", "exercised", "tools")

#: And the commands, by name for the same reason. A count of fifteen is
#: satisfied by fifteen copies of one gate: replacing `ruff check .` with a
#: second `pytest -q` kept the number and removed the reason this Makefile
#: has a `lint` target at all.
CHECK_COMMANDS = (
    "ruff check .",
    "tools/propose_class_rules.py --check",
    "tools/vendor_corpus.py --check",
    "tools/crossvalidate.py --check",
    "tools/explain_silence.py --quiet",
    "tools/version_inventory.py",
    "tools/extract_requirements.py",
    "tools/requirement_coverage.py",
    "tools/emit_shacl.py --check",
    "pytest -q",
    "tools/rule_coverage.py --check",
    "tools/held_claims.py --check",
    "-m iirds_validate.ontology --verify",
    "tools/serialisation_equivalence.py fixtures/bad.iirds",
    "tools/serialisation_equivalence.py fixtures/good.iirds --allow-clean",
)


def test_the_makefile_text_and_make_agree_about_what_check_runs():
    """The text reader is only for attribution, so it has to match make.

    Every way a gate was found to disappear lived in this gap and none of them
    touched a recipe line: `.PHONY` losing a name while `shapes/` and `tools/`
    exist as directories, a second `check:` line, a target defined twice, a
    line continuation, an indented comment, a command held in a variable.
    """
    from_text = sorted(command for _target, command in CHECKS)
    from_make = sorted(_what_make_would_run())
    assert from_text == from_make, (
        "the Makefile reads as %s and make runs %s"
        % (sorted(set(from_text) - set(from_make)), sorted(set(from_make) - set(from_text))))


def test_nothing_in_the_makefile_stops_a_gate_from_failing():
    """A gate that runs and cannot fail is worse than one that does not run:
    it reports success. `-` on a recipe line, `.IGNORE:` and `-i` in MAKEFLAGS
    each do that while leaving the command in `make -n` and in the text, so
    neither of the other two checks can see it.

    This file introduced the first of the three itself, by stripping `@`, `-`
    and `+` from a recipe line as though they were one class of cosmetic
    modifier. Before that strip, the count caught a `-`-prefixed gate; after
    it, `make shapes` exited 0 with a broken manifest and every test passed.
    """
    for pattern, why in _CANNOT_FAIL:
        assert not pattern.search(MAKEFILE), why


def test_the_check_target_runs_every_gate_it_is_supposed_to():
    """Named rather than counted. Removing a target from `check:` is a change
    somebody has to make here as well, which is a diff a reviewer reads."""
    assert tuple(_check_targets()) == CHECK_TARGETS, _check_targets()
    assert tuple(c for _t, c in CHECKS) == CHECK_COMMANDS, [c for _t, c in CHECKS]


@pytest.mark.parametrize("target,command", CHECKS, ids=[c for _t, c in CHECKS])
def test_ci_runs_everything_make_check_runs(target, command):
    if command in LOCAL_ONLY:
        pytest.skip(LOCAL_ONLY[command])
    assert command in _normalise(WORKFLOW), \
        "`make %s` runs %r and no CI job does" % (target, command)


# ---------------------------------------------------------------------------
# The platforms the README names are the platforms CI runs
#
# The same shape of mistake one level out: a claim that exists in one place and
# a check that exists in another. The badge line names three operating systems
# and the matrix ran two, and nothing said so -- the tool does work on the
# third, which is exactly why nobody would have noticed it going wrong.
# ---------------------------------------------------------------------------

#: What a runner label calls each of them.
RUNNERS = {"Linux": "ubuntu", "macOS": "macos", "Windows": "windows"}


def claimed_platforms():
    """The operating systems README.md tells a reader this runs on."""
    badge = re.search(r"(?m)^&nbsp;\*\*Apache-2\.0\*\*.*$",
                      (ROOT / "README.md").read_text("utf-8"))
    assert badge, "README.md no longer carries the badge line in the expected shape"
    return sorted(name for name in RUNNERS if name in badge.group(0))


def test_the_readme_names_the_platforms_ci_actually_runs():
    named = claimed_platforms()
    assert named, "the badge line names no operating system at all"
    missing = sorted(name for name in named if RUNNERS[name] not in WORKFLOW)
    assert missing == [], (
        "README.md says this runs on %s and no CI row does: a claim nobody "
        "checks is a claim that goes wrong quietly" % ", ".join(missing))


def test_make_actually_switches_the_differential_gate_on():
    """conftest.shacl_or_skip reads IIRDS_REQUIRE_SHACL and turns a missing
    pyshacl from a skip into a failure. It was read in one place and set in
    none: the commit that added it said "under make the absence is now a
    failure", and it was not. A gate whose switch nobody checks is a gate
    that is off, so the switch is checked here."""
    assert re.search(r"(?m)^export IIRDS_REQUIRE_SHACL\s*:?=\s*1\s*$", MAKEFILE), (
        "the Makefile does not export IIRDS_REQUIRE_SHACL, so `make check` "
        "skips the differential gate in silence when pyshacl is absent")


def test_make_dev_installs_what_make_check_requires():
    """Requiring it is only reasonable if `make dev` provides it."""
    assert "pyshacl" in MAKEFILE, "make dev does not install pyshacl"


def test_the_ci_row_that_has_pyshacl_requires_it():
    """The Makefile exports IIRDS_REQUIRE_SHACL, so a local run refuses to
    skip the differential gate. CI does not use the Makefile: it runs the
    commands directly, and the one job that installs pyshacl was not asking
    for it -- so an install that quietly failed would have left that job
    green with the gate off. The matrix rows deliberately do not have it and
    deliberately do skip; this is about the row that is supposed to."""
    job = re.search(r"(?ms)^      - name: the shapes agree with the Python rules.*?\n(?=      - name:|\n  \w)",
                    WORKFLOW)
    assert job, "the differential-gate step is no longer in the expected shape"
    assert re.search(r"IIRDS_REQUIRE_SHACL:\s*[\"']?1", job.group(0)), (
        "the job that installs pyshacl does not require it, so a failed "
        "install would skip the gate and pass")


def test_make_actually_requires_the_cached_specification():
    """The other switch of the same shape. The specification is not
    redistributable, so the checks that hold the published requirement index
    to the document it was read from can only run where a copy was fetched --
    and a skip is not a failure. Under make it is one, and the switch is
    checked here rather than trusted, because the last switch of this shape
    was read in one place and set in none."""
    assert re.search(r"(?m)^export IIRDS_REQUIRE_SPEC_CACHE\s*:?=\s*1\s*$", MAKEFILE), (
        "the Makefile does not export IIRDS_REQUIRE_SPEC_CACHE, so `make check` "
        "would hold the requirement index to nothing when the cache is absent")


def test_no_ci_row_installs_the_library_from_an_index():
    """`iirds` ships from this tree, beside the checker. A matrix row that
    pinned it from an index would put a release ahead of `src/` on the path
    and run the suite against code nobody is looking at."""
    assert not re.search(r'pin:\s*"iirds', WORKFLOW), "a matrix row still installs iirds from an index"


#: Tools CI runs that `make check` does not, each with the reason it is not
#: local. A tool may legitimately be CI-only — it needs the network, or it
#: belongs to a release — but "nobody noticed" is not a reason, and until this
#: list existed there was no way to tell the two apart. The parity test above
#: reads make -> CI; this reads CI -> make, which is the direction a tool goes
#: missing in.
CI_ONLY = {
    "build_zipapp": "release machinery: it builds the single-file .pyz, which "
                    "the release workflow does and a working tree has no use for",
    "extract_catalog": "needs the reference tool's repository over the network, "
                       "and this suite runs offline",
    "shim_overlap": "asks what an *installed* distribution owns, so it needs a "
                    "venv with the wheels in it — the release workflow builds "
                    "them and a working tree does not",
}


def test_every_tool_ci_runs_is_run_locally_or_says_why_not():
    """`explain_silence.py` was in neither list: CI ran it, `make check` did
    not, and nothing said whether that was a decision. It takes nine seconds
    and reads only files that ship, so it is local now — and the two that stay
    in CI have to say what keeps them there."""
    import re

    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    makefile = (ROOT / "Makefile").read_text("utf-8")

    in_ci = set(re.findall(r"tools/([a-z_]+)\.py", ci))
    in_make = set(re.findall(r"tools/([a-z_]+)\.py", makefile))
    unexplained = sorted(in_ci - in_make - set(CI_ONLY))
    assert unexplained == [], (
        "CI runs these and `make check` does not, with no reason recorded: %s"
        % unexplained)

    stale = sorted(name for name in CI_ONLY if name in in_make or name not in in_ci)
    assert stale == [], (
        "these are listed as CI-only and are not: %s" % stale)
