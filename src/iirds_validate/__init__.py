"""Offline, graph-based validator and interoperability linter for iiRDS packages."""

__version__ = "0.6.0"

#: What `from iirds_validate import ...` offers, and the module each name lives
#: in. Resolved on first use rather than at import: the package used to pull in
#: the runner, and through it every module, the moment it was imported -- so
#: `python -m iirds_validate.ontology --verify`, the integrity check the
#: documentation hands a reviewer, found its module already imported and
#: opened with Python's warning about running one twice.
_EXPORTS = {
    "Finding": "model", "Rule": "model", "Severity": "model", "Violation": "model",
    "Package": "package", "PackageError": "package",
    "check": "runner", "lint": "runner", "load": "runner",
}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError("module %r has no attribute %r" % (__name__, name))
    from importlib import import_module

    value = getattr(import_module("." + module, __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))

#: The command's name, said once. Three console scripts point at the same
#: `main`, and every message the tool prints about itself opens with this --
#: the way `python3` answers `python`, `iirdsv` answers `iirds`.
PROGRAM = "iirds"
