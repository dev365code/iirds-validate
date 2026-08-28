"""Offline, graph-based validator and interoperability linter for iiRDS packages."""

__version__ = "0.4.2"

from .model import Finding, Rule, Severity, Violation  # noqa: F401
from .package import Package, PackageError  # noqa: F401
from .runner import check, lint, load  # noqa: F401

#: The command's name, said once. Three console scripts point at the same
#: `main`, and every message the tool prints about itself opens with this --
#: the way `python3` answers `python`, `iirdsv` answers `iirds`.
PROGRAM = "iirds"
