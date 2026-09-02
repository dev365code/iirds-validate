"""Reading the bundled data, whether it is on disk or inside a zipapp.

`Path(__file__).parent / "data"` is the obvious way and it stops working the
moment the package is run from a single-file archive — which is the way this
tool most wants to be delivered, because a closed network can accept a file
copied in and cannot accept `pip install`.

`importlib.resources` reads the same bytes either way.
"""
from __future__ import annotations

import functools
import json
from importlib import resources
from typing import Dict, FrozenSet, List


def _data():
    return resources.files("iirds_validate") / "data"


def read_bytes(*parts: str) -> bytes:
    target = _data()
    for part in parts:
        target = target / part
    return target.read_bytes()


def read_text(*parts: str, encoding: str = "utf-8") -> str:
    return read_bytes(*parts).decode(encoding)


def _resolve(*parts: str):
    target = _data()
    for part in parts:
        target = target / part
    return target


def exists(*parts: str) -> bool:
    """Whether the entry is there, asked in a way a zip answers honestly.

    `zipfile.Path.is_file()` returns True for a path that is not in the archive
    at all, so a plain is_file()/is_dir() test reports a bundled ontology for a
    version that was never bundled — and the substitution that should have
    happened does not, and the read fails much later with a KeyError. Listing
    the parent is the reliable question.
    """
    if not parts:
        return True
    target = _resolve(*parts)
    try:
        if target.is_dir():
            return True
    except Exception:
        pass
    try:
        return parts[-1] in {entry.name for entry in _resolve(*parts[:-1]).iterdir()}
    except Exception:
        return False


def listdir(*parts: str) -> List[str]:
    target = _data()
    for part in parts:
        target = target / part
    try:
        return sorted(entry.name for entry in target.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return []


@functools.lru_cache(maxsize=1)
def version_terms() -> Dict[str, FrozenSet[str]]:
    """Which term IRIs each published edition of iiRDS defines.

    Written by `tools/version_inventory.py --refresh` off the Consortium's
    published schema files (1.3 from the bundled ontologies), and checked
    offline by the same tool. Only the newest ontology ships, so this list
    is the only thing that knows a 1.3 name is not a 1.0 name.
    """
    data = json.loads(read_text("version-terms.json"))
    return {edition: frozenset(terms) for edition, terms in data["terms"].items()}
