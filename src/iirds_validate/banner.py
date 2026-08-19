"""The thing you see when you type `iirdsv` and nothing else.

Deliberately not printed by `check`, `lint` or `all`. Those write to a build
log or into a pipe, and `--format json` writes a document another program
parses; a banner in front of either is somewhere between noise and corruption.

Plain ASCII on purpose. Block-drawing characters look better in a modern
terminal and turn into rubbish in a Windows console or over a serial link, and
the machines this tool is built for are exactly the ones with the old fonts.
"""
from __future__ import annotations

from . import __version__

#: figlet, "slant". 25 columns, which leaves room on an 80-column terminal for
#: the version to sit on the baseline.
LOGO = r"""    _ _ ____  ____  _____
   (_|_) __ \/ __ \/ ___/
  / / / /_/ / / / /\__ \
 / / / _, _/ /_/ /___/ /
/_/_/_/ |_/_____//____/"""

TAGLINE = "conformance and interoperability checking for iiRDS packages, offline"

COMMANDS = (
    ("check <package.iirds>", "does it conform to the specification?"),
    ("lint  <package.iirds>", "will anyone else be able to read it?"),
    ("all   <package.iirds>", "both"),
    ("rules", "every rule this tool checks, and its source"),
)


def banner(coverage=None) -> str:
    """The logo, the version on the baseline, and how to start."""
    lines = LOGO.splitlines()
    lines[-1] = "%-26s validate %s" % (lines[-1], __version__)
    out = ["", "\n".join(lines), "", "  " + TAGLINE, ""]
    for command, purpose in COMMANDS:
        out.append("  iirdsv %-24s %s" % (command, purpose))
    out.append("")
    if coverage:
        out.append("  " + coverage)
        out.append("")
    return "\n".join(out)
