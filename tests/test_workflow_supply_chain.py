"""What the workflows will run, held to a commit rather than to a name.

`pypa/gh-action-pypi-publish@release/v1` is a branch. Whatever that branch
points at on the morning of a release is what runs in the job that holds
`id-token: write` and uploads under this project's name -- and a tag is no
better, because a tag can be moved to another commit by whoever owns it. Both
are a promise by somebody else that the code will not change under us, and
nothing here noticed either way.

So every `uses:` names a full commit object, with the human-readable version
beside it: forty characters say nothing to the next person, and the one thing
they need to know before moving a pin is what they are moving from.

There is deliberately no updater. A tool that rewrites these lines is one more
moving reference, with write access to the file that decides what runs. The
cost is real and is the reason this is written down: a pin does not pick up the
fix upstream makes to it, so moving one is a thing somebody has to do.

Two holes were found in the first version of this file, and both let a
workflow run unpinned while every test here was green:

* It swept `*.yml`. GitHub runs `*.yaml` too, so a workflow added -- or
  renamed -- with the other spelling was invisible, and `attacker/exfil@main`
  in it passed.
* Its guard was `at least five uses:`, which `ci.yml` satisfies on its own. A
  whole workflow could leave the sweep and the only sign was two fewer green
  tests than yesterday, which nobody counts. The guard is a list now, for the
  reason `tests/test_ci_parity.py` gives for its own: a count is not a list.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"

#: What GitHub runs out of that directory, both spellings, whatever the case.
RUNS = (".yml", ".yaml")

#: The workflows this repository has. A new one has to be added here on
#: purpose, and is then swept; one that disappears from this list without
#: being deleted is the failure this list exists to catch.
EXPECTED = {"ci.yml", "dco.yml", "release.yml"}

WORKFLOWS = sorted(path for path in WORKFLOWS_DIR.iterdir()
                   if path.is_file() and path.suffix.lower() in RUNS)

#: `uses:` and what follows it, with whatever comment trails on the same line.
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<ref>\S+)\s*(?P<comment>#.*)?$", re.M)

#: A full git object name. `@v7` and `@release/v1` are the two shapes this file
#: exists to refuse; an abbreviated hash is refused as well, because a short
#: one can be made to collide and GitHub resolves it like any other ref.
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def lines():
    """Every `uses:` in every workflow, as (file, action, ref, comment)."""
    found = []
    for path in WORKFLOWS:
        for match in USES.finditer(path.read_text(encoding="utf-8")):
            action, _, ref = match.group("ref").partition("@")
            found.append((path.name, action, ref, (match.group("comment") or "").strip()))
    return found


ALL = lines()


#: A job's block, by the two-space indent under `jobs:`. Read with a pattern
#: rather than a YAML parser because pyyaml is not a declared dependency here,
#: and a gate that only runs where somebody happens to have a package is the
#: defect `tests/test_declared_dependencies.py` exists to refuse.
JOB = re.compile(r"^  ([A-Za-z0-9_-]+):$", re.M)


def jobs_of(path):
    """{job name: its block} for one workflow file, comments removed.

    Full-line comments are dropped because a block runs between one job header
    and the next, so a comment written above a job is attributed to the one
    before it. Without this, a gate reading a block for what the job *runs*
    answers about prose sitting between two jobs.
    """
    text = path.read_text("utf-8")
    start = text.index("\njobs:\n")
    found = list(JOB.finditer(text, start))
    out = {}
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        block = text[m.end():end]
        out[m.group(1)] = "\n".join(line for line in block.split("\n")
                                    if not line.lstrip().startswith("#"))
    return out


#: Any spelling of a permission that lets a job write to the repository.
#: `contents: write` is one; quoting it, spacing it differently, folding the
#: block onto one line and `write-all` are the same grant, and a gate that
#: reads one literal line says nothing about the rest.
WRITES = re.compile(r"contents:\s*['\"]?write|permissions:\s*['\"]?write-all"
                    r"|\{[^}]*contents:\s*['\"]?write")


def test_only_the_job_that_publishes_may_write_to_the_repository():
    """A job that runs build tooling must not be able to move a release.

    The build job makes the distributions and runs the suite, and it held
    `contents: write` so that it could make the release at the end. Anything
    reaching that job -- a dependency, a script, a fixture -- could have
    rewritten a release under this project's name. The permission belongs to a
    job that does one thing and nothing else.
    """
    writers = {}
    for path in WORKFLOWS:
        for name, block in jobs_of(path).items():
            if WRITES.search(block):
                writers["%s:%s" % (path.name, name)] = block
    assert sorted(writers) == ["release.yml:publish-release"], sorted(writers)

    block = writers["release.yml:publish-release"]
    assert "gh release create" in block, "the writer does not make the release"
    # `pip install` on its own is not a signal here: the notes this job
    # publishes tell a reader how to upgrade, and say it three times. What
    # would mean the job builds rather than publishes is installing *this*
    # project.
    for forbidden in ("make check", "pytest", "python -m build", "pip install -e"):
        assert forbidden not in block, (
            "the job holding `contents: write` also runs %r; it must do one "
            "thing" % forbidden)


def test_the_release_carries_what_was_built_rather_than_a_second_build():
    """The publishers upload the artifact the build job made. So must this:
    a second build is a second set of bytes, and the checksum file beside them
    would be describing the first."""
    blocks = jobs_of(WORKFLOWS_DIR / "release.yml")
    assert "gh release create" not in blocks["build"], "the build job still makes it"
    writer = blocks["publish-release"]
    assert "actions/download-artifact" in writer, \
        "the publishing job does not take the built bytes"
    assert re.search(r"^    needs: build$", writer, re.M), \
        "the publishing job does not follow the build"


def test_no_workflow_grants_write_from_above_the_jobs():
    """A job with no `permissions:` inherits the file's default, which is
    outside every job block and so invisible to the sweep above. A default of
    `contents: write` would hand the permission to every job in the file
    without any of them asking for it."""
    for path in WORKFLOWS:
        text = path.read_text("utf-8")
        head = text[:text.index("\njobs:\n")]
        assert not WRITES.search(head), (
            "%s grants write above its jobs: every job inherits it" % path.name)
        # A job with no `permissions:` block inherits the default asserted
        # above, which is why that assertion is the one that matters: five
        # jobs in ci.yml declare nothing and are right not to.


def test_the_workflows_swept_are_the_ones_this_repository_has():
    """The sweep sees every file GitHub would run, by name.

    A glob that matches nothing passes every parametrised test below by having
    no cases, and reads in CI as a row of green. So this is the one assertion
    that does not depend on the sweep: the directory's own contents.
    """
    runs = {path.name for path in WORKFLOWS_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in RUNS}
    assert runs == EXPECTED, (
        "GitHub runs %s; this file expects %s. A workflow that is added, "
        "renamed or deleted is named here on purpose." % (sorted(runs), sorted(EXPECTED)))
    assert {path.name for path in WORKFLOWS} == EXPECTED


@pytest.mark.parametrize("path,action,ref", [(p, a, r) for p, a, r, _ in ALL],
                         ids=["%s:%s" % (p, a) for p, a, _, _ in ALL])
def test_every_action_names_a_commit(path, action, ref):
    assert COMMIT.match(ref), (
        "%s uses %s@%s -- a tag or a branch, which is whoever owns it deciding "
        "later what runs here. (A local action, `./.github/actions/...`, carries "
        "no ref at all and would land here too; this repository has none, and "
        "adopting one means saying so in this file.)" % (path, action, ref))


@pytest.mark.parametrize("path,action,comment", [(p, a, c) for p, a, _, c in ALL],
                         ids=["%s:%s" % (p, a) for p, a, _, _ in ALL])
def test_every_pin_says_which_version_it_is(path, action, comment):
    """Forty characters are unreadable, and an unreadable pin is never moved."""
    assert re.match(r"^#\s*v?\d", comment), (
        "%s pins %s with no version beside it; the comment reads %r"
        % (path, action, comment))


def test_one_action_is_pinned_to_one_commit_under_one_name():
    """Whether a comment names the right release cannot be asked offline, and
    this suite does not reach the network. What can be asked is whether the
    file agrees with itself: the same action appears twenty times over three
    workflows, so a pin moved in one place and not the others, or a version
    label that disagrees with the commit beside it somewhere else, is a
    difference here. Both were green before this test existed.
    """
    seen = defaultdict(set)
    for _path, action, ref, comment in ALL:
        seen[action].add((ref, comment))
    disagreeing = {action: sorted(pairs) for action, pairs in seen.items() if len(pairs) > 1}
    assert not disagreeing, (
        "the same action is pinned two ways: %s" % disagreeing)
