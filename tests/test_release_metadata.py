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
run. Six of the nine states in it were accepted by the first version of
this file; the other three it already refused, and they are pinned so
that they stay refused.
"""
import re
from pathlib import Path

import pytest

from iirds_validate import __version__

ROOT = Path(__file__).resolve().parents[1]

#: Every `## ` line, whatever it says. Deliberately loose in three ways: a
#: heading this file cannot read has to reach an assertion that names it
#: rather than falling out of the search and reading as an entry nobody
#: wrote; CommonMark allows an ATX heading up to three spaces of indent, and
#: one indented that way rendered as a heading while this did not see it at
#: all; and a checkout with CRLF endings leaves a `\r` the anchor would
#: otherwise carry into the date.
HEADING = re.compile(r"^[ \t]{0,3}##[ \t]+(?P<text>.*?)[ \t\r]*$", re.M)

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
    numbers = [int(part) for part in found.group("numbers").split(".")]
    # 1.0 and 1.0.0 are one release, so trailing zeros go -- keeping at least
    # one component, because an empty tuple would sort below every release.
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    # Four independent components, because the three suffixes are independent:
    # 1.0rc1.post1 is not 1.0rc1, and a branch chain that stops at the first
    # one it finds gave them the same key -- which then reported one name
    # twice while complaining that two entries were out of order.
    if found.group("pre"):
        pre = (0, _STAGE[found.group("pre")], int(found.group("pren")))
    elif found.group("dev") is not None and found.group("post") is None:
        # A dev release of the final one comes before every pre-release of it:
        # 1.0.dev0 < 1.0a1 < 1.0 in PEP 440's own worked ordering.
        pre = (-1,)
    else:
        pre = (1,)
    post = int(found.group("post")) if found.group("post") else -1
    dev = int(found.group("dev")) if found.group("dev") else float("inf")
    return (tuple(numbers), pre, post, dev)


def _outside_fences(changelog: str) -> str:
    """The same text with fenced code blocks blanked out, line for line.

    A changelog that documents its own heading shape puts a `## ` line inside
    a fence, and reading it as an entry reports the file for saying what it
    is. Blanked rather than removed so that every offset still lines up.
    """
    out, fence = [], None
    for line in changelog.split("\n"):
        marker = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", line)
        blank = " " * len(line)          # same length, or the offsets shift
        if fence is None and marker:
            fence = marker.group(1)[0]
            out.append(blank)
            continue
        if fence is not None:
            out.append(blank)
            if marker and marker.group(1)[0] == fence:
                fence = None
            continue
        out.append(line)
    return "\n".join(out)


def entries(changelog: str):
    """Every `## ` heading, newest first, as (release, rest, body).

    `release` is None where the heading is not one this gate can read;
    the caller reports that rather than skipping past it, because a
    heading that vanishes here reads downstream as an entry that was
    never written.
    """
    found = list(HEADING.finditer(_outside_fences(changelog)))
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
        _, rest, _body = ours[0]
        if not DATE.match(rest):
            found.append("the entry for %s is headed %r; a release that ships "
                         "carries a date" % (release, rest))

    # Every entry, not only this release's: a heading with nothing under it is
    # a release whose notes were never written, and it stays that way for ever
    # once a later one is added above it.
    for name, _rest, body in said:
        if not body.strip():
            found.append("the entry for %s says nothing under its heading" % name)

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
# Six of the states below were accepted by the first version of this file;
# three it already refused. They are all here because a gate is only known to
# work where it has been shown to fail, and because a state it refuses today
# is a state it can stop refusing tomorrow.
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
    # And the same for one that shipped long ago: it stays empty for ever
    # once a later entry is added above it.
    "an older entry says nothing":
        (GOOD.replace("### Fixed\n\n- something older.\n", ""), "0.4.1 says nothing"),
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
    # CommonMark renders an ATX heading indented up to three spaces. One
    # indented that way was a heading to every reader and invisible here, so
    # a release left undated behind it read as a file with nothing wrong.
    "a shipped release left undated under an indented heading":
        (GOOD.replace("## 0.4.1 — 2026-08-25", "   ## 0.4.1 — unreleased"),
         "has shipped"),
    # PEP 440 makes 1.0 and 1.0.0 one release. Read as different ones, the
    # same release entered twice passed as two.
    "the same release entered twice under two spellings":
        (GOOD.replace("## 0.5.0 — unreleased",
                      "## 0.5.0 — unreleased\n\n- one.\n\n## 0.5 — unreleased"),
         "descending order"),
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
    ("0.4.3.dev1", "0.4.3a1"),
    ("0.4.3a1.dev1", "0.4.3a1"),
    ("0.4.3.dev1", "0.4.3a1.dev1"),
    ("0.4.3", "0.4.3.post1"),
    ("0.4.3.post1.dev1", "0.4.3.post1"),
    ("0.4.3rc1", "0.4.3rc1.post1"),
])
def test_releases_order_the_way_python_orders_them(lower, higher):
    """Cross-checked pair for pair against `packaging.version.Version` over
    every combination of these releases; `packaging` is not a dependency of
    this project, so what it agreed with is pinned here instead of imported.

    The three suffixes are independent, and a first version of this ordered
    by whichever one it found first -- so 1.0rc1.post1 and 1.0rc1 got the
    same key, and a file in perfect order was reported as out of order with
    one release named twice."""
    assert release_key(lower) < release_key(higher)


def test_a_release_documented_inside_a_code_fence_is_not_an_entry():
    """A changelog that shows its own heading shape puts a `## ` line in a
    fence. Read as an entry it reports the file for saying what it is."""
    documented = GOOD.replace(
        "### Added\n", "### Added\n\n```markdown\n## 9.9.9 — 2030-01-01\n```\n")
    assert problems_with(documented, "0.4.2") == []


def test_a_fence_does_not_disarm_the_checks_below_it():
    """The fence is blanked line for line so that the offsets still line up:
    the headings are found in the blanked text and the bodies are sliced out
    of the original. Dropping the characters instead of replacing them shifts
    every offset after the fence, and each entry's body becomes whatever text
    happens to sit that far along -- non-empty, so the check for an entry
    with nothing under it stops firing, quietly, for the whole file."""
    fenced = GOOD.replace(
        "### Added\n", "### Added\n\n```markdown\n## 9.9.9 — 2030-01-01\n```\n")
    hollow = fenced.replace("### Fixed\n\n- something older.\n", "")

    problems = problems_with(hollow, "0.4.2")
    assert any("0.4.1 says nothing" in problem for problem in problems), (
        "a fence above it hid the empty entry: %s" % problems)


@pytest.mark.parametrize("text", ["", "unreleased", "1.0+local", "v1.0", "1!1.0"])
def test_something_that_is_not_a_release_is_refused_rather_than_ordered(text):
    assert release_key(text) is None
