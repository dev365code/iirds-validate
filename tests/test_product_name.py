"""One name, and where the old ones are allowed to remain.

The checker shipped as `iirds-validate` with `iirdsv` as its short command;
from 0.5.0 the distribution and the command are `iirds`. The old names live on
where they must -- as aliases, as the repository's address until it is
renamed, as a token stored reports carry, in the published shape namespace,
and in history -- and nowhere else. A sweep, so that a paragraph written from
habit does not put the old name back on the front page.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Where `iirds-validate` may still appear, and why.
OLD_DISTRIBUTION_ALLOWED = {
    "pyproject.toml": "the alias console script, and the repository's address",
    "README.md": "the badge address, the upgrade note, and the `source` token",
    "CHANGELOG.md": "history",
    "docs/library-changelog.md": "history",
    "docs/divergences.md": "an issue's address",
    "docs/offline-install.md": "the upgrade note",
    "src/iirds_validate/model.py": "the `source` token stored reports carry",
    "src/iirds_validate/cli.py": "the same token, in the rules listing",
    "src/iirds_validate/rules/system.py": "the issue tracker's address, in a remedy",
    "tests/test_registry.py": "pins that token",
    "tests/test_product_name.py": "this file",
    "tests/test_distribution.py": "the alias console script",
    "tests/test_shims.py": "the compatibility name",
    "tools/emit_shacl.py": "the published shape namespace and `ruleSource`",
    "tools/shim_overlap.py": "the compatibility name, asked of the installed metadata",
    "shapes/README.md": "the published shape namespace",
    "shapes/THIRD-PARTY-NOTICES.md": "the `ruleSource` token",
    "shapes/MANIFEST.json": "the published shape namespace",
    ".github/workflows/ci.yml": "the alias console script",
    ".github/workflows/release.yml": "the compatibility distribution",
    "NOTICE": "the name earlier releases were published under",
}
#: Where `iirdsv` may still appear, and why.
OLD_COMMAND_ALLOWED = {
    "pyproject.toml": "the alias console script",
    "README.md": "one sentence saying the alias still works",
    "CHANGELOG.md": "history",
    "src/iirds_validate/__init__.py": "the alias, explained beside the name",
    "src/iirds_validate/data/web/app.js": "a browser-storage key a page already wrote",
    "tests/test_distribution.py": "the alias console script",
    "tests/test_product_name.py": "this file",
    "tests/test_shims.py": "the alias",
    ".github/workflows/ci.yml": "the alias console script",
    ".github/workflows/release.yml": "the alias console script",
}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".txt", ".json", ".html", ".js", ".css", ".in", ""}


def tracked_text_files():
    listed = subprocess.run(["git", "ls-files"], cwd=str(ROOT), capture_output=True, text=True)
    if listed.returncode != 0:
        pytest.skip("not a git checkout")
    for line in listed.stdout.splitlines():
        path = ROOT / line
        if path.suffix in TEXT_SUFFIXES and path.is_file() and not line.startswith("shapes/") \
                and not line.startswith("tests/corpus/"):
            yield line, path


def _offenders(needle: str, allowed: dict):
    found = []
    for line, path in tracked_text_files():
        if line in allowed or line.startswith("shims/"):
            continue
        try:
            text = path.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        if needle in text:
            found.append(line)
    return sorted(found)


def test_the_old_distribution_name_appears_only_where_it_must():
    assert _offenders("iirds-validate", OLD_DISTRIBUTION_ALLOWED) == []


def test_the_old_short_command_appears_only_where_it_must():
    assert _offenders("iirdsv", OLD_COMMAND_ALLOWED) == []


def test_the_old_single_file_name_appears_nowhere():
    # Spelled in two halves so that this file is not its own first offender.
    assert _offenders("iirds-validate" + ".pyz", {}) == []


def test_the_front_page_installs_the_one_name():
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "pip install iirds\n" in readme
    assert "`iirds` for reading and writing packages" in readme or "## From Python" in readme
