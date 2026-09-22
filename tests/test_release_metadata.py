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
run. Most of the states in it were accepted by some earlier version of
this file; the rest it already refused, and they are pinned so that they
stay refused.
"""
import re
import subprocess
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


def published_releases() -> frozenset:
    """The releases this repository has published, read from its tags.

    This repository has two release lines. 0.6.1, 0.6.2 and 0.6.3 were cut
    from `release/0.6.x` and their version bumps never came back here, so
    `__version__` on the main line is behind them and three dated entries sit
    above it. "It has not shipped, so it is headed 'unreleased'" was this
    gate's sentence for that shape, and it stopped being true the day the
    second line existed. A tag is the record of what shipped, so a tag is what
    settles it.

    No tags at all does not switch this check off -- it refuses every dated
    entry above this release, which is noisy and points at the wrong thing.
    (Its converse, which wants a tag's entry to carry a date, does go quiet
    then: there is no tag for it to ask about.)
    `test_the_tags_are_visible_here` exists to say which thing: the checkout,
    not the file. `actions/checkout` fetches no tags unless it is asked.
    """
    try:
        done = subprocess.run(["git", "tag", "--list", "v*"],
                              cwd=str(ROOT), capture_output=True, text=True)
    except OSError:
        return frozenset()               # no git here: the test below says so
    if done.returncode != 0:
        return frozenset()
    keys = (release_key(line.strip()[1:]) for line in done.stdout.splitlines() if line.strip())
    return frozenset(k for k in keys if k is not None)


def problems_with(changelog: str, release: str, published=frozenset()):
    """Every way this changelog fails to record `release` as shipped.

    `published` is the set of release keys that have a tag. An entry above
    this release may carry a date only if it is one of them.
    """
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
        elif release_key(name) > mine and DATE.match(rest) \
                and release_key(name) not in published:
            found.append("%s is above this release, carries a date, and has no "
                         "v%s tag; it has not shipped, so it is headed "
                         "'unreleased'%s"
                         % (name, name,
                            "" if published else
                            " (and no v* tag is visible here at all, so this "
                            "may be the checkout rather than the file)"))
        elif release_key(name) > mine and not DATE.match(rest) \
                and release_key(name) in published:
            found.append("%s is above this release and is headed %r, and v%s is "
                         "tagged; it has shipped, so it carries a date"
                         % (name, rest, name))
    return found


def _name(said, key):
    for name, _, _ in said:
        if release_key(name) == key:
            return name
    return str(key)


# ---------------------------------------------------------------------------
# This repository
# ---------------------------------------------------------------------------

def version_in(text: str) -> str:
    found = re.search(r'(?m)^version *= *"([^"]+)"', text)
    assert found, "no version declared in the expected shape"
    return found.group(1)


def declared_versions() -> dict:
    """Every place this tree states its release, by name.

    Two packages ship from one distribution, so the library's `__version__`
    is this release too. A release stated in one place and not another is
    two releases, and `pip` and `--version` would disagree about which one
    a machine has.
    """
    import iirds

    return {"pyproject.toml": version_in((ROOT / "pyproject.toml").read_text("utf-8")),
            "iirds_validate.__version__": __version__,
            "iirds.__version__": iirds.__version__}


def test_the_version_is_one_number_everywhere_it_is_declared():
    said = declared_versions()
    assert len(set(said.values())) == 1, said


def test_the_changelog_records_this_release():
    published = published_releases()
    problems = problems_with((ROOT / "CHANGELOG.md").read_text("utf-8"), __version__,
                             published=published)
    if not published:
        # No tags visible: every dated entry above this release is refused for
        # that one reason, and saying so here as well would blame the file for
        # the checkout. `test_the_tags_are_visible_here` is the failure that
        # names the cause; this one keeps only what it can still judge, so a
        # real fault in the changelog is not hidden behind a missing tag.
        problems = [line for line in problems if "no v* tag is visible" not in line]
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
    # The tree keeps the last shipped number until the release commit, so an
    # entry above it is unshipped unless a tag says otherwise: dating one
    # without a tag claims a release that has not happened, and the version
    # bump would then find its notes already "shipped". The cases in this
    # table pass no `published` set, so no tag says otherwise here.
    "an entry above this release carries a date":
        (GOOD.replace("## 0.5.0 — unreleased", "## 0.5.0 — 2026-08-28"),
         "has not shipped"),
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


def test_the_tags_are_visible_here():
    """The gate above reads tags, so a checkout with none turns it off.

    `actions/checkout` fetches no tags unless asked, so this says plainly what
    a green run would otherwise hide. If this fails in CI, the checkout needs
    `fetch-tags: true` rather than this test needing a skip.
    """
    found = published_releases()
    assert found, ("no v* tags are visible, so every dated entry above this "
                   "release is refused as unshipped and the failures below "
                   "blame the file. A checkout fetches none unless asked: "
                   "ask for fetch-tags.")
    assert release_key("0.6.0") in found, sorted(found)


def test_a_dated_entry_above_this_release_with_no_tag_is_still_refused():
    """The line the repair must not cross. A second release line explains
    0.6.1 through 0.6.3; it explains nothing about a version nobody cut."""
    changelog = ("# Changelog\n\n## 0.6.9 — 2026-09-20\n\nSomething.\n\n"
                 "## 0.4.2 — 2026-08-26\n\nSomething else.\n")
    published = frozenset({release_key("0.4.2")})
    problems = problems_with(changelog, "0.4.2", published=published)
    assert any("0.6.9" in p and "no v0.6.9 tag" in p for p in problems), problems

    # and with the tag, the same changelog is accepted
    assert problems_with(changelog, "0.4.2",
                         published=published | {release_key("0.6.9")}) == []


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


# ---------------------------------------------------------------------------
# The library's own history
# ---------------------------------------------------------------------------

LIBRARY_CHANGELOG = ROOT / "docs" / "library-changelog.md"


def test_the_library_changelog_is_frozen_at_its_last_release():
    """The library shipped on its own as `iirds` 0.1.0 to 0.3.2, and that
    history is kept as it was published: complete up to its last release and
    closed. Nothing lands there now; what changes in the library is recorded
    in CHANGELOG.md beside what changes in the checker."""
    text = LIBRARY_CHANGELOG.read_text("utf-8")
    assert problems_with(text, "0.3.2") == []
    assert "unreleased" not in text.lower()


def test_the_release_notes_publish_the_coverage_that_was_measured():
    """The coverage figure is stated in three places — `docs/scope.md`, the
    README's front matter and the current release's notes — and only two were
    read. So the notes went on saying "81 of 280, of which 42 are held" after
    the tree had moved to 131 and 94, and the number a reader quotes from a
    release page would have been the one nobody checked.

    Read here, against the same measurement the other two are read against.
    """
    import re
    import sys

    sys.path.insert(0, str(ROOT / "tests"))
    from test_covers_is_earned import CLAIMED, held

    current = current_release_notes()
    if current is None:
        return                            # shipped, or no tags to say either way
    stated = re.search(r"Coverage of the standard is (\d+) of (\d+), of which (\d+) "
                       r"are held by a package", current)
    assert stated, "the current release's notes no longer state the coverage figure"
    assert int(stated.group(1)) == len(CLAIMED), stated.group(0)
    assert int(stated.group(3)) == len(held()), stated.group(0)

    scope = (ROOT / "docs" / "scope.md").read_text("utf-8")
    assert "Coverage of the standard is %s of %s." % (
        stated.group(1), stated.group(2)) in scope, (
        "the notes and docs/scope.md state different coverage")


def test_the_release_notes_count_the_rules_the_release_actually_adds():
    """"Ten new rules since the last release" is a number, and a number in
    prose goes stale the moment somebody adds an eleventh. It cannot be read
    off the tree alone — it is a difference between two — so it is read off
    the previous tag, and skipped where there is no git to ask.

    The coverage figure two lines above it was in exactly this state until it
    was wrong: stated in three places and read in two.
    """
    import re
    import subprocess

    import pytest

    current = current_release_notes()
    if current is None:
        return                            # shipped, or no tags to say either way
    stated = re.search(r"^(\w+) new rules", current, re.M)
    if stated is None:
        pytest.skip("the current notes do not count new rules")
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
             "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15}
    said = words.get(stated.group(1).lower())
    assert said is not None, "not a number this test can read: %r" % stated.group(1)

    # The whole file here, not the current section: the release before this
    # one is what the count is a difference against.
    dated = [name for name, rest, _ in entries((ROOT / "CHANGELOG.md")
                                               .read_text("utf-8"))
             if name is not None and DATE.match(rest)]
    previous = dated
    assert len(previous) >= 2, "there is no previous release to compare against"
    tag = "v" + previous[1]

    listed = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "--name-only",
                             "%s:src/iirds_validate/rules" % tag],
                            capture_output=True, text=True)
    if listed.returncode != 0:
        pytest.skip("no git checkout, or %s is not here" % tag)

    def ids(ref, names):
        found = set()
        for name in names:
            if not name.endswith(".py"):
                continue
            shown = subprocess.run(
                ["git", "-C", str(ROOT), "show",
                 "%s:src/iirds_validate/rules/%s" % (ref, name)],
                capture_output=True, text=True)
            found |= set(re.findall(r'@rule\(\s*"([^"]+)"', shown.stdout))
        return found

    here = sorted((ROOT / "src" / "iirds_validate" / "rules").glob("*.py"))
    before = ids(tag, listed.stdout.split())
    now = set()
    for path in here:
        now |= set(re.findall(r'@rule\(\s*"([^"]+)"', path.read_text("utf-8")))
    assert len(now - before) == said, (
        "the notes say %d new rules and the tree adds %d since %s: %s"
        % (said, len(now - before), tag, sorted(now - before)))


def current_release_notes():
    """The notes for this tree's version while no tag carries it, else None.

    A shipped section is the record of what the tool said when it shipped, and
    a gate that keeps rewriting those to today's measurement destroys the
    record it exists to protect -- the same reason
    `test_the_notes_still_being_written_state_the_count_that_was_measured`
    reads one section and not the file.

    Chosen by the version and by the tags, not by position. Reading the top
    section positionally was wrong twice over: it goes on reading these notes
    after their tag exists, so the first rule to land afterwards demands that
    a shipped record be edited to today's measurement; and opening the next
    entry above them moves the top section to one that states none of these
    figures, so every one of them reads as absent at once.
    """
    published = published_releases()
    if not published:
        return None                       # `test_the_tags_are_visible_here`
    mine = release_key(__version__)
    if mine in published:
        return None                       # shipped: it is a record now
    # Read through `entries`, which is what the rest of this file reads
    # headings with. Slicing on "\n## " and comparing the first word was a
    # second reader of the same file, and two readers of one file disagree:
    # that one saw nothing in `## 0.7 — …` (PEP 440 makes it this release),
    # nothing under two spaces after the hashes, and nothing under the
    # three-space indent CommonMark allows and `problems_with` has a named
    # case for. Each of those turned every figure gate off in silence.
    for name, _rest, body in entries((ROOT / "CHANGELOG.md").read_text("utf-8")):
        if name is not None and release_key(name) == mine:
            return body
    return None


def _rules_checked(path):
    from iirds_validate import runner

    return runner.check(path).checked


def _a_conformant_package(directory):
    """The package the notes' counts are about, built here.

    Not `fixtures/good.iirds`: `fixtures/` is ignored by git, so that path is
    a local artefact of `make tools` and is absent from a fresh clone and
    from a bare `pytest` run. A gate that reads it passes on the machine that
    built it and fails everywhere else -- which is what the first version of
    this did, reporting `1 rule checked` and an `S1` about an unreadable
    container. Built from the same generator the Makefile's rule calls, so it
    is the same package.
    """
    from make_fixture_package import build_package

    directory.mkdir(parents=True, exist_ok=True)
    return build_package(directory, "good.iirds")


def figures_the_notes_state(package):
    """`{what: (stated, measured)}` for every live figure in those notes.

    Live means "a number about this tree, which this tree can be asked".
    Figures about the past are not in here and are not gateable: what a
    release shipped is what its own section says.
    """
    from iirds_validate.registry import all_rules

    notes = current_release_notes()
    if notes is None:
        return {}                         # shipped, or no tags to say either way
    rules = list(all_rules())
    found = {}

    def stated(what, pattern, measured):
        # Every occurrence, not the first: a section that states a figure and
        # restates it differently lower down disagrees with itself, and
        # reading only the first match lets it.
        said = sorted({int(n) for n in re.findall(pattern, notes)})
        found[what] = (said or None, measured)

    stated("the size of the registry",
           r"the rule count goes to (\d+)", len(rules))
    stated("rules checked on a packed container",
           r"`iirds check` on a directory said `PASS,\s+(\d+)\s+rules checked`",
           _rules_checked(package))
    return found


def test_the_release_notes_state_figures_this_run_produces(tmp_path):
    """Every one of these was right when it was typed and wrong when it was
    published, because nothing read them again.

    Five were found at once in the notes for this release: the registry as
    233 when it is 236, two counts of rules checked each one behind, a count
    of commits that had grown by ten, and a transcript quoted as shipping in
    five releases that shipped in none. The README states the same figures
    and states them correctly, because `tools/gen_stable_section.py` writes
    them and `--check` refuses a stale one. This file had no such reader.

    The rule this draws: a figure about *this* tree, in the notes for *this*
    release, is measured here. A figure about a release that has shipped is
    not -- that is a record, and rewriting it to today's measurement is the
    defect, not the fix.
    """
    package = _a_conformant_package(tmp_path)
    wrong = ["%s: the notes say %s and this run gives %s"
             % (what, "nothing" if said is None else ", ".join(map(str, said)),
                measured)
             for what, (said, measured) in figures_the_notes_state(package).items()
             if said != [measured]]
    assert wrong == [], "\n".join(wrong)


def test_the_release_notes_state_the_count_an_unpacked_container_gives(tmp_path):
    """The other half of the same sentence, kept apart because measuring it
    costs an unpack: the notes say what the count moves *to* when the same
    package is checked as a directory."""
    import zipfile

    notes = current_release_notes()
    if notes is None:
        return                            # shipped, or no tags to say either way
    said = {(int(a), int(b))
            for a, b in re.findall(r"the count moves from (\d+) to (\d+)", notes)}
    assert said, "the notes no longer state the count an unpacked container gives"

    package = _a_conformant_package(tmp_path / "packed")
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(unpacked)
    assert said == {(_rules_checked(package), _rules_checked(unpacked))}, sorted(said)


def test_no_commit_that_changed_a_rule_moved_the_version():
    """The notes say so, so it is asked rather than remembered.

    `toolVersion` is the field a reader is told can say two runs had
    different rule *bodies*, and the claim behind that is this one. It was
    published as a count of commits, which grows with every rule change and
    would have to be edited by hand for ever; the property is what was meant
    and is what a machine can hold.

    Asked as "which commits moved the `__version__` line", not as "which
    commits touched both files" -- the first version of this gate asked the
    second and named two commits that edit a docstring in one file and a rule
    in the other, moving nothing.
    """
    notes = current_release_notes()
    if notes is not None:
        # A gate on a sentence has to check the sentence is still there. This
        # one had no such anchor, so the claim could be deleted, negated, or
        # turned back into the count it replaced with nothing noticing.
        assert re.search(r"no commit that changed\s+a?\s*rule file has ever "
                         r"moved it", notes), \
            "the notes no longer make the claim this gate holds"

    # A shallow checkout grafts its tip as a root commit, so `sha^` fails for
    # it and the "the first commit is excused" branch below swallows exactly
    # the commit this refuses. `actions/checkout` fetches depth 1 unless told
    # otherwise, so this gate was vacuous on every CI run while reading green.
    # It says which thing happened rather than passing.
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert shallow.stdout.strip() != "true", (
        "this checkout is shallow, so the history this reads is one commit "
        "deep and the question cannot be answered here; fetch the history")

    # Not a pattern over the diff. `^__version__ = ` was the first anchor and
    # one commit writing `__version__: str = "..."` retires it for ever;
    # `^__version__` is the same shape one step out, and `_RELEASE = "0.7.0"`
    # with `__version__ = _RELEASE` retires that. The claim is about the
    # value, so the value is read -- at both ends of every commit that touched
    # the file at all. Twelve commits have; this is cheap.
    touched_it = subprocess.run(["git", "log", "--format=%H", "--",
                                 "src/iirds_validate/__init__.py"],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
    if touched_it.returncode != 0:                          # pragma: no cover
        pytest.skip("no git history visible here")
    candidates = touched_it.stdout.split()
    assert candidates, "no commit here ever touched the version file"

    def version_at(ref):
        shown = subprocess.run(["git", "show",
                                "%s:src/iirds_validate/__init__.py" % ref],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
        if shown.returncode != 0:
            return None
        found = re.search(r"""__version__[^=\n]*=\s*["']([^"']+)["']""",
                          shown.stdout)
        return found.group(1) if found else None

    releases = []
    for sha in candidates:
        # The first commit created every file there is, so it moved the
        # version and wrote the rules in one breath without being an
        # instance of the thing this refuses.
        parent = subprocess.run(["git", "rev-parse", "--quiet", "--verify",
                                 sha + "^"], cwd=ROOT, capture_output=True)
        if parent.returncode != 0:
            continue
        if version_at(sha) != version_at(sha + "^"):
            releases.append(sha)
    assert releases, "no commit here ever moved the version, so this read nothing"

    both = []
    for sha in releases:
        names = subprocess.run(["git", "show", "--format=", "--name-only", sha],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
        if any(name.startswith("src/iirds_validate/rules/")
               for name in names.stdout.split()):
            both.append(sha)
    assert both == [], ("these commits moved the version and changed a rule "
                        "file together, so the notes' claim is no longer "
                        "true: %s" % ", ".join(sha[:8] for sha in both))
