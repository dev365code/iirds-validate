"""The three places this project states its own release, held together.

A release whose changelog entry is still headed "unreleased" ships notes
that promise rather than record, and a `pyproject.toml` that disagrees
with `__version__` ships a wheel whose metadata contradicts the package
inside it. Nothing else in the suite reads these three together, so
nothing else notices when a bump lands in two of them and not the third.

The reading is deliberately not "the top entry is this release": writing
the entry as the work lands, under an undated heading, and dating it at
the release is a working style this project's sibling uses. What cannot
happen is *shipping* under that undated heading.

The checks are functions over changelog text rather than assertions over
this repository's file, because a gate nobody has run against a bad
changelog is a gate nobody has tested. The table at the bottom is that
run: every state below was accepted by the first version of this file.
"""
import re
from pathlib import Path

import pytest

from iirds_validate import __version__

ROOT = Path(__file__).resolve().parents[1]

#: Every `## ` line, whatever it says. Deliberately loose: a heading this
#: file cannot read has to reach an assertion that names it, not fall out
#: of the search and be reported as an entry that is not there.
HEADING = re.compile(r"^##[ \t]+(?P<text>.*?)[ \t]*$", re.M)

#: `0.4.2 — 2026-08-26`, or `0.3.3 — unreleased`. One shape, on purpose.
ENTRY = re.compile(r"^(?P<release>\S+)[ \t]+[—-][ \t]+(?P<rest>.+)$")

DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

#: A release as PEP 440 spells the shapes a Python project actually ships.
#: Anything else this gate refuses to order rather than guessing at.
RELEASE = re.compile(r"^(?P<numbers>[0-9]+(?:\.[0-9]+)*)"
                     r"(?:(?P<pre>a|b|rc)(?P<pren>[0-9]+))?"
                     r"(?:\.post(?P<post>[0-9]+))?"
                     r"(?:\.dev(?P<dev>[0-9]+))?$")

_STAGE = {"a": 0, "b": 1, "rc": 2}


def release_key(release: str):
    """A release as something sortable, or None where it is not a release.

    Ordered the way PEP 440 orders them, which text order does not: a
    release candidate comes *before* the release it is a candidate for,
    and 0.10.0 comes after 0.9.0. Only the shapes a project ships are
    handled -- a local version or an epoch is refused rather than
    silently mis-ordered.
    """
    found = RELEASE.match(release)
    if not found:
        return None
    numbers = tuple(int(part) for part in found.group("numbers").split("."))
    if found.group("dev") is not None and not (found.group("pre") or found.group("post")):
        stage = (0, int(found.group("dev")))
    elif found.group("pre"):
        stage = (1, _STAGE[found.group("pre")], int(found.group("pren")))
    elif found.group("post"):
        stage = (3, int(found.group("post")))
    else:
        stage = (2,)
    return (numbers, stage)


def entries(changelog: str):
    """Every `## ` heading, newest first, as (release, rest, body).

    `release` is None where the heading is not one this gate can read;
    the caller reports that rather than skipping past it, because a
    heading that vanishes here reads downstream as an entry that was
    never written.
    """
    found = list(HEADING.finditer(changelog))
    out = []
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(changelog)
        body = changelog[match.end():end]
        parsed = ENTRY.match(match.group("text"))
        if parsed is None:
            out.append((None, match.group("text"), body))
        else:
            out.append((parsed.group("release"), parsed.group("rest"), body))
    return out


def problems_with(changelog: str, release: str):
    """Every way this changelog fails to record `release` as shipped."""
    said = entries(changelog)
    if not said:
        return ["the changelog carries no `## ` heading"]

    found = []
    for name, rest, _body in said:
        if name is None:
            found.append("this gate reads a heading as `## <release> — <date>`, "
                         "and cannot read %r" % rest)
        elif release_key(name) is None:
            found.append("%r is not a release number this gate can order" % name)
    if found:
        return found                      # nothing below can be trusted yet

    keys = [release_key(name) for name, _, _ in said]
    for older, newer in zip(keys[1:], keys[:-1]):
        if older >= newer:
            found.append("the entries are not in descending order: %s is not "
                         "older than %s" % (_name(said, older), _name(said, newer)))

    dates = [rest for name, rest, _ in said if DATE.match(rest)]
    for older, newer in zip(dates[1:], dates[:-1]):
        if older > newer:
            found.append("entry dated %s sits below one dated %s" % (older, newer))

    mine = release_key(release)
    if mine is None:
        return found + ["%r is not a release number this gate can order" % release]

    ours = [(name, rest, body) for name, rest, body in said if release_key(name) == mine]
    if not ours:
        found.append("the changelog carries no entry for %s" % release)
    else:
        _, rest, body = ours[0]
        if not DATE.match(rest):
            found.append("the entry for %s is headed %r; a release that ships "
                         "carries a date" % (release, rest))
        if not body.strip():
            found.append("the entry for %s says nothing under its heading" % release)

    for name, rest, _ in said:
        if release_key(name) <= mine and not DATE.match(rest):
            found.append("%s is at or below this release and is headed %r; it has "
                         "shipped, so it carries a date" % (name, rest))
    return found


def _name(said, key):
    for name, _, _ in said:
        if release_key(name) == key:
            return name
    return str(key)


# ---------------------------------------------------------------------------
# This repository
# ---------------------------------------------------------------------------

def test_pyproject_and_the_package_declare_the_same_release():
    found = re.search(r'(?m)^version *= *"([^"]+)"',
                      (ROOT / "pyproject.toml").read_text("utf-8"))
    assert found, "pyproject.toml no longer declares a version in the expected shape"
    assert found.group(1) == __version__, (
        "pyproject.toml says %s and iirds_validate.__version__ says %s"
        % (found.group(1), __version__))


def test_the_changelog_records_this_release():
    problems = problems_with((ROOT / "CHANGELOG.md").read_text("utf-8"), __version__)
    assert problems == [], "CHANGELOG.md, against %s:\n  %s" % (
        __version__, "\n  ".join(problems))


# ---------------------------------------------------------------------------
# The gate, run against changelogs that are wrong
#
# Every state below was accepted by the first version of this file. They are
# here because a gate is only known to work where it has been shown to fail.
# ---------------------------------------------------------------------------

GOOD = """# Changelog

## 0.5.0 — unreleased

### Added

- something not shipped yet.

## 0.4.2 — 2026-08-26

### Fixed

- something.

## 0.4.1 — 2026-08-25

### Fixed

- something older.
"""

BAD = {
    "a shipped release left undated":
        (GOOD.replace("## 0.4.1 — 2026-08-25", "## 0.4.1 — unreleased"),
         "has shipped"),
    "this release left undated":
        (GOOD.replace("## 0.4.2 — 2026-08-26", "## 0.4.2 — unreleased"),
         "carries a date"),
    "no entry for this release":
        (GOOD.replace("## 0.4.2 — 2026-08-26", "## 0.4.0 — 2026-08-26"),
         "no entry for 0.4.2"),
    "the entry says nothing":
        (GOOD.replace("### Fixed\n\n- something.\n", ""), "says nothing"),
    "the same release entered twice":
        (GOOD.replace("## 0.4.1 — 2026-08-25", "## 0.4.2 — 2026-08-26"),
         "descending order"),
    "a later release sits below this one":
        (GOOD.replace("## 0.4.1 — 2026-08-25", "## 0.6.0 — 2026-08-25"),
         "descending order"),
    "the dates run backwards":
        (GOOD.replace("## 0.4.2 — 2026-08-26", "## 0.4.2 — 1999-01-01"),
         "sits below one dated"),
    "a heading this gate cannot read":
        (GOOD.replace("## 0.4.1 — 2026-08-25", "## 0.4.1 (2026-08-25)"),
         "cannot read"),
    "a heading naming no release":
        (GOOD.replace("## 0.5.0 — unreleased", "## Unreleased — unreleased"),
         "can order"),
}


@pytest.mark.parametrize("state", sorted(BAD), ids=sorted(BAD))
def test_the_gate_refuses_a_changelog_that_is_wrong(state):
    changelog, expected = BAD[state]
    problems = problems_with(changelog, "0.4.2")
    assert problems, "accepted a changelog where %s" % state
    assert any(expected in problem for problem in problems), (
        "refused %r for the wrong reason: %s" % (state, problems))


def test_the_gate_accepts_the_shape_this_project_actually_uses():
    assert problems_with(GOOD, "0.4.2") == []


@pytest.mark.parametrize("release", ["0.4.2", "0.4.2rc1", "0.4.2b2", "0.4.2.post1"])
def test_a_release_python_can_publish_is_a_release_this_gate_can_order(release):
    """A gate that cannot read a release candidate is a gate that forbids
    cutting one. Refusing them would be a decision; crashing on the regex
    was not."""
    changelog = GOOD.replace("## 0.4.2 — 2026-08-26", "## %s — 2026-08-26" % release)
    assert problems_with(changelog, release) == []


@pytest.mark.parametrize("lower,higher", [
    ("0.9.0", "0.10.0"),
    ("0.4.3rc1", "0.4.3"),
    ("0.4.3a1", "0.4.3b1"),
    ("0.4.3b1", "0.4.3rc1"),
    ("0.4.3.dev1", "0.4.3rc1"),
    ("0.4.3", "0.4.3.post1"),
])
def test_releases_order_the_way_python_orders_them(lower, higher):
    assert release_key(lower) < release_key(higher)


@pytest.mark.parametrize("text", ["", "unreleased", "1.0+local", "v1.0", "1!1.0"])
def test_something_that_is_not_a_release_is_refused_rather_than_ordered(text):
    assert release_key(text) is None
