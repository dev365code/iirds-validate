"""System rules (S*) — the run itself failed, rather than the package.

These three were previously fabricated inside `runner.py`, which meant their
titles were written out twice and `iirdsv rules` reported system coverage as
0/3 for behaviour that already existed. Registering them puts their metadata
back in the catalogue with every other rule.

Two of them cannot be ordinary rules. S1 fires before there is anything to
validate, and S3 fires when another rule raises. Their bodies are empty and the
runner emits them; the registration exists so the rule is named and described
in one place.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule

#: Every kind of run, so a container that cannot be read is reported whether
#: the caller asked for conformance, interoperability, or both.
ALWAYS = ()


@rule("S1", versions=ALWAYS, variants=ALWAYS)
def s1_unreadable_container(ctx):
    """Emitted by `runner.run` when the file cannot be opened as a ZIP.

    There is no Context at that point, so there is nothing for a rule to
    inspect; this exists to give the finding a catalogued identity.
    """
    return ()


@rule("S2", versions=ALWAYS, variants=ALWAYS)
def s2_no_usable_metadata(ctx):
    """Nothing in META-INF parsed, so no graph rule could have run.

    Without this, `iirdsv lint` on a package with unreadable metadata reports
    no findings and exits 0 — every L rule looked at an empty graph and found
    nothing to complain about.
    """
    if ctx.sources:
        return
    detail = "; ".join(ctx.parse_errors) if ctx.parse_errors else "no metadata file present"
    yield Violation("container validation failed: no usable metadata, so no graph rule ran",
                    subject="META-INF", detail=detail)


@rule("S3", versions=ALWAYS, variants=ALWAYS)
def s3_rule_raised(ctx):
    """Emitted by `runner.run` when a rule raises.

    A rule that crashed is a rule that checked nothing, so it is reported
    rather than swallowed — and `tests/test_silent_pass.py` fails the suite if
    any fixture produces one.
    """
    return ()
