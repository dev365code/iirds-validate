"""The two names the checker and the library used to ship under.

`iirds-validate` and `iirds-sdk` stay on PyPI as compatibility packages: each
depends on `iirds` and carries nothing of it, so `pip install iirds-validate`
keeps resolving -- to `iirds` -- and no file is owned by two distributions,
which is how an uninstall of one breaks the other.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from iirds_validate import __version__

ROOT = Path(__file__).resolve().parents[1]
SHIMS = ("iirds-validate", "iirds-sdk")


def _pyproject(shim: str) -> str:
    return (ROOT / "shims" / shim / "pyproject.toml").read_text("utf-8")


@pytest.mark.parametrize("shim", SHIMS)
def test_a_shim_releases_in_lockstep(shim):
    found = re.search(r'(?m)^version = "([^"]+)"$', _pyproject(shim))
    assert found and found.group(1) == __version__, (shim, found and found.group(1))


@pytest.mark.parametrize("shim", SHIMS)
def test_a_shim_depends_on_iirds_alone_and_never_below_itself(shim):
    """A floor, not an exact pin, and the floor is the shim's own release: it
    never resolves to an `iirds` older than the one it was published beside,
    and never stands in the way of a newer one -- an exact pin would make
    `pip install -U iirds` a conflict on every machine that has the shim."""
    assert re.search(r'(?m)^dependencies = \["iirds>=%s"\]$' % re.escape(__version__),
                     _pyproject(shim)), "%s must depend on iirds>=%s and nothing else" % (shim, __version__)


def test_the_validator_shim_ships_no_package():
    """`iirds_validate` is in the `iirds` wheel. A second copy under the old
    name would be a file two distributions own."""
    assert re.search(r"(?m)^packages = \[\]$", _pyproject("iirds-validate"))
    assert not list((ROOT / "shims" / "iirds-validate").rglob("*.py"))


def test_the_sdk_shim_keeps_its_import_name():
    """`import iirds_sdk` was published; published names do not break."""
    module = ROOT / "shims" / "iirds-sdk" / "src" / "iirds_sdk" / "__init__.py"
    assert "from iirds import *" in module.read_text("utf-8")


@pytest.mark.parametrize("shim", SHIMS)
def test_a_shim_carries_the_licence_and_says_where_to_go(shim):
    here = ROOT / "shims" / shim
    assert (here / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    readme = (here / "README.md").read_text("utf-8")
    assert "pypi.org/project/iirds/" in readme
    assert "transferred to the iiRDS Consortium on request" in readme


def test_the_root_sdist_leaves_the_shims_out():
    """The shims are their own distributions, built from their own
    directories; the root sdist describing `iirds` must not carry them."""
    assert re.search(r"(?m)^prune shims$", (ROOT / "MANIFEST.in").read_text("utf-8"))


def test_the_overlap_check_names_a_shared_file():
    """`tools/shim_overlap.py` reads installed metadata, which a unit test
    cannot arrange; its judgement is a pure function, exercised here."""
    import shim_overlap

    assert shim_overlap.shared({"a": {"x/y.py"}, "b": {"x/y.py", "z.py"}}) == {"x/y.py": ["a", "b"]}
    assert shim_overlap.shared({"a": set(), "b": {"z.py"}}) == {}


#: The two commands the upgrade advice turns on, and the order it puts them in.
#: Stated on the compatibility package's PyPI page and on the front page, which
#: are read by different people at different moments: the page is what a
#: publisher sees, and the reader who has already run the upgrade is looking at
#: the repository, because the command that would have told them is the one
#: that stopped working.
RECOVERY = "pip install --force-reinstall --no-deps iirds"
UNINSTALL_FIRST = "pip uninstall -y iirds-validate"


def test_both_pages_give_the_same_upgrade_advice():
    """One hazard, two surfaces, and neither may drift from the other.

    Upgrading in place from 0.4.2 leaves the environment with no working
    command, and `pip list` and `pip check` both call it healthy -- the files
    are gone and the records are not, so nothing pip looks at is missing. The
    advice cannot be a rule; it is prose, on two pages, and this is what keeps
    the two saying one thing.
    """
    surfaces = {
        "README.md": ROOT / "README.md",
        "the shim's PyPI page": ROOT / "shims" / "iirds-validate" / "README.md",
        # A release body is a literal in the workflow rather than anything
        # derived, so the note reaches a release only by being here. It is the
        # surface a reader arrives at from a version tag.
        "the release notes": ROOT / ".github" / "workflows" / "release.yml",
    }
    for where, path in surfaces.items():
        text = " ".join(path.read_text("utf-8").replace("\\`", "`").split())
        for said in (RECOVERY, UNINSTALL_FIRST):
            assert said in text, "%s no longer says %r" % (where, said)


def test_the_front_page_says_which_versions_are_exposed():
    """A hazard with no boundary reads as "upgrading is unsafe", which is not
    true and is the kind of warning a reader learns to skip. The break needs
    both distributions to own one path, and the compatibility package has
    owned none since 0.5.0."""
    front = " ".join((ROOT / "README.md").read_text("utf-8").split())
    assert "0.4.2 or earlier" in front, "README.md no longer says who is exposed"
    assert "0.5.0 or later is unaffected" in front, "README.md no longer says who is not"
