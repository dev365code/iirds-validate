"""The three places this project states its own release, held together.

A release whose changelog entry is still headed "unreleased" ships notes
that promise rather than record, and a `pyproject.toml` that disagrees
with `__version__` ships a wheel whose metadata contradicts the package
inside it. Nothing else in the suite reads these three together, so
nothing else notices when a bump lands in two of them and not the third.

The invariant is deliberately not "the top heading is this release":
writing the entry as the work lands, under an undated heading, and dating
it at the release is a working style this project's sibling uses. What
cannot happen is shipping under that undated heading. So: the newest
*dated* entry is this release, and anything above it names a later one.
"""
import re
from pathlib import Path

from conftest import version_tuple
from iirds_validate import __version__

ROOT = Path(__file__).resolve().parents[1]

# `## 0.4.2 — 2026-08-26`, or `## 0.3.3 — unreleased`. What follows the
# dash is captured whatever it says, so an undated heading reaches the
# assertions rather than failing the search and reading as a missing entry.
HEADING = re.compile(r"^## +(?P<release>\S+)(?: +[—-] +(?P<rest>.+?))? *$", re.M)
RELEASE = re.compile(r"^[0-9]+(?:\.[0-9]+)+$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def headings():
    """Every `## ` heading in the changelog, newest first, as (release, rest)."""
    found = [(m.group("release"), m.group("rest") or "")
             for m in HEADING.finditer((ROOT / "CHANGELOG.md").read_text("utf-8"))]
    assert found, "CHANGELOG.md carries no `## ` heading"
    return found


def test_pyproject_and_the_package_declare_the_same_release():
    found = re.search(r'(?m)^version *= *"([^"]+)"',
                      (ROOT / "pyproject.toml").read_text("utf-8"))
    assert found, "pyproject.toml no longer declares a version in the expected shape"
    assert found.group(1) == __version__, (
        "pyproject.toml says %s and iirds_validate.__version__ says %s"
        % (found.group(1), __version__))


def test_every_changelog_heading_names_a_release():
    for release, _ in headings():
        assert RELEASE.match(release), (
            "changelog heading %r is not a release number; the entries this "
            "gate reads are addressed by version" % release)


def test_this_release_has_a_dated_changelog_entry():
    """The one that bites at a tag: `__version__` moved and the entry that
    heads it still says "unreleased", so the release ships undated notes."""
    dated = [r for r, rest in headings() if DATE.match(rest)]
    assert dated, "no changelog entry is dated; none of them records a release"
    assert dated[0] == __version__, (
        "this is %s and the newest dated changelog entry is %s -- either the "
        "entry for %s is missing, or it is still headed undated"
        % (__version__, dated[0], __version__))


def test_nothing_undated_sits_below_this_release():
    """An undated heading is work not yet shipped, so it names something
    newer. Naming something older leaves a shipped release undated."""
    mine = version_tuple(__version__)
    for release, rest in headings():
        if DATE.match(rest):
            break
        assert version_tuple(release) > mine, (
            "changelog entry %s is headed %r, and %s is not newer than this "
            "release (%s); a shipped release carries a date"
            % (release, rest, release, __version__))
