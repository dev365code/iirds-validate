#!/usr/bin/env python3
"""Do the compatibility names own any file the `iirds` wheel owns?

`iirds-validate` and `iirds-sdk` exist so that the old names keep resolving.
They must carry nothing of the checker or the library, because two
distributions owning one file is how an uninstall of one breaks the other.
Asked of the installed metadata -- what pip will act on -- in an environment
where all three are installed.

    python tools/shim_overlap.py        # exit 1 and the paths, if any are shared
"""
from __future__ import annotations

import sys
from importlib import metadata

NAMES = ("iirds", "iirds-validate", "iirds-sdk")


def owned(name: str) -> set:
    """Every path a distribution's RECORD claims, its own metadata aside."""
    files = metadata.distribution(name).files or ()
    return {str(path) for path in files if ".dist-info/" not in str(path)}


def shared(owned_by: dict) -> dict:
    """{path: [distributions]} for every path two or more of them own."""
    claims: dict = {}
    for dist, paths in owned_by.items():
        for path in paths:
            claims.setdefault(path, []).append(dist)
    return {path: sorted(dists) for path, dists in claims.items() if len(dists) > 1}


def main() -> int:
    found = shared({name: owned(name) for name in NAMES})
    for path, dists in sorted(found.items()):
        print("%s is owned by %s" % (path, " and ".join(dists)))
    print("%d distributions, %d shared files" % (len(NAMES), len(found)))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
