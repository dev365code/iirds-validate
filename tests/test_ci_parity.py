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


def _commands_of(target: str):
    """The $(PYTHON) recipe lines of one target."""
    body = re.search(r"^%s:.*?\n((?:\t.*\n|\n)*)" % re.escape(target), MAKEFILE, re.M)
    if not body:
        return []
    out = []
    for raw in body.group(1).splitlines():
        stripped = raw.strip()
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


def test_the_check_target_has_recipes_to_compare():
    assert len(CHECKS) >= 8, CHECKS


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
