"""One name, and where the old ones are allowed to remain -- and how often.

The checker shipped as `iirds-validate` with `iirdsv` as its short command;
from 0.5.0 the distribution and the command are `iirds`. The old names live on
where they must -- as aliases, as the repository's address until it is
renamed, as a token stored reports carry, in the published shape namespace,
and in history -- and nowhere else. Each file on the list is held to the
number of mentions it is allowed, so a paragraph written from habit cannot
put the old name back on a page that already carries it for a good reason;
history alone is uncounted. This file names the paths it allows, so it is
the one file the sweep does not read.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OLD_DISTRIBUTION = "iirds-" + "validate"
OLD_COMMAND = "iirds" + "v"
OLD_SINGLE_FILE = OLD_DISTRIBUTION + ".pyz"

#: path -> (mentions allowed, why); None = history, uncounted.
OLD_DISTRIBUTION_ALLOWED = {
    ".github/workflows/ci.yml": (4, "the alias console script and the compatibility package"),
    ".github/workflows/release.yml": (9, "the compatibility package and the alias console script"),
    "CHANGELOG.md": (None, "history"),
    "NOTICE": (1, "the name earlier releases were published under"),
    "README.md": (7, "the badge address, the alias sentence, the upgrade note, the `source` token"),
    "docs/divergences.md": (2, "an issue's address"),
    "docs/library-changelog.md": (None, "history"),
    "pyproject.toml": (5, "the alias console script, and the repository's address"),
    "shapes/README.md": (2, "the repository's address, as a link"),
    "shapes/THIRD-PARTY-NOTICES.md": (1, "the `ruleSource` token"),
    "shims/iirds-sdk/pyproject.toml": (1, "the repository's address"),
    "shims/iirds-validate/README.md": (4, "the compatibility package's own page"),
    "shims/iirds-validate/pyproject.toml": (3, "the compatibility package's own name"),
    "src/iirds_validate/cli.py": (1, "the same token, in the rules listing"),
    "src/iirds_validate/model.py": (1, "the `source` token stored reports carry"),
    "src/iirds_validate/rules/system.py": (1, "the issue tracker's address, in a remedy"),
    "tests/test_distribution.py": (2, "the alias console script"),
    "tests/test_registry.py": (1, "pins the `source` token"),
    "tests/test_shims.py": (5, "the compatibility name"),
    "tools/emit_shacl.py": (4, "the published shape namespace, `ruleSource`, and the artefact header"),
    "tools/shim_overlap.py": (2, "the compatibility name, asked of the installed metadata"),
}
OLD_COMMAND_ALLOWED = {
    ".github/workflows/ci.yml": (1, "the alias console script"),
    ".github/workflows/release.yml": (1, "the alias console script"),
    "CHANGELOG.md": (None, "history"),
    "README.md": (1, "one sentence saying the alias still works"),
    "pyproject.toml": (1, "the alias console script"),
    "shims/iirds-validate/README.md": (1, "the compatibility package's own page"),
    "src/iirds_validate/__init__.py": (1, "the alias, explained beside the name"),
    "src/iirds_validate/data/web/app.js": (1, "a browser-storage key a page already wrote"),
    "tests/test_distribution.py": (1, "the alias console script"),
}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".txt", ".json", ".html", ".js", ".css", ".in", ""}


def tracked_text_files():
    listed = subprocess.run(["git", "ls-files"], cwd=str(ROOT), capture_output=True, text=True)
    if listed.returncode != 0:
        pytest.skip("not a git checkout")
    for line in listed.stdout.splitlines():
        path = ROOT / line
        if path.suffix not in TEXT_SUFFIXES or not path.is_file() or line.startswith("tests/corpus/"):
            continue
        if line == "tests/test_product_name.py":
            continue
        # The shapes themselves and their manifest carry the published
        # namespace IRI in every shape; the prose beside them is read.
        if line.startswith("shapes/") and not line.endswith(".md"):
            continue
        yield line, path


def _mentions(needle: str) -> dict:
    found = {}
    for line, path in tracked_text_files():
        try:
            text = path.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        count = text.count(needle)
        if count:
            found[line] = count
    return found


def _offences(needle: str, allowed: dict) -> dict:
    """{path: (found, allowed)} wherever the count is not the allowed one."""
    found = _mentions(needle)
    bad = {}
    for path, count in found.items():
        cap = allowed.get(path, (0, None))[0]
        if cap is not None and count != cap:
            bad[path] = (count, cap)
    for path, (cap, _why) in allowed.items():
        if cap and path not in found:
            bad[path] = (0, cap)          # the allowance outlived the mention
    return bad


def test_the_old_distribution_name_appears_only_where_it_must_and_only_as_often():
    assert _offences(OLD_DISTRIBUTION, OLD_DISTRIBUTION_ALLOWED) == {}


def test_the_old_short_command_appears_only_where_it_must_and_only_as_often():
    assert _offences(OLD_COMMAND, OLD_COMMAND_ALLOWED) == {}


def test_the_old_single_file_name_appears_nowhere():
    assert _mentions(OLD_SINGLE_FILE) == {}


def test_the_front_page_installs_the_one_name():
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "pip install iirds\n" in readme
    assert "## Reading and writing packages from Python" in readme


def test_the_sweep_would_notice_one_mention_too_many():
    """A count that is not held is a list; this holds the holding."""
    allowed = {"README.md": (1, "one")}
    assert _offences.__name__ == "_offences"
    # A file allowed once but mentioning twice, and one not allowed at all.
    found = {"README.md": 2, "docs/new.md": 1}
    bad = {p: (c, allowed.get(p, (0, None))[0]) for p, c in found.items()
           if allowed.get(p, (0, None))[0] is not None and c != allowed.get(p, (0, None))[0]}
    assert bad == {"README.md": (2, 1), "docs/new.md": (1, 0)}
