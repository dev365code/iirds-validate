"""README.md is the PyPI page as well as the GitHub front page.

`pyproject.toml` names it as the distribution's readme, so PyPI renders the
same file -- and resolves a relative link against pypi.org, where
`docs/scope.md` is a 404. Every link a reader can follow from GitHub has to
be one they can follow from PyPI, which means an absolute one.
"""
from __future__ import annotations

import re
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def repository():
    """The address pyproject publishes, so that a rename reaches here too."""
    text = (README.parent / "pyproject.toml").read_text("utf-8")
    return re.search(r'^Homepage = "([^"]+)"', text, re.M).group(1)


REPOSITORY = repository()


def links():
    text = README.read_text("utf-8")
    # ](target) -- markdown links and images; a fenced block's parentheses
    # are not links, so fences are dropped first
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.findall(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", text)


def test_every_link_in_the_readme_can_be_followed_from_pypi():
    relative = [target for target in links()
                if not target.startswith(("http://", "https://", "#", "mailto:"))]
    assert relative == [], relative


def test_links_into_this_repository_point_at_the_tree_pypi_shows():
    """Absolute, and to the repository named in pyproject -- a link to a
    fork or to a renamed repository would survive the test above."""
    into = [target for target in links() if "/blob/main/" in target or "/tree/main/" in target]
    assert into, "the README no longer links into the repository at all"
    for target in into:
        assert target.startswith(REPOSITORY + "/"), target


def test_every_link_into_the_tree_names_something_that_is_there():
    """A file moved -- the per-edition inventory left docs/ for the package
    data today -- takes the links to it with it, silently."""
    root = README.parent
    into = [target for target in links() if "/blob/main/" in target or "/tree/main/" in target]
    missing = [target for target in into if not (root / target.split("/main/", 1)[1]).exists()]
    assert missing == [], missing
