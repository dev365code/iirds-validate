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

import posixpath

from ..model import VARIANTS, VERSIONS, Violation
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


@rule("S4", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="iirds:iiRDSVersion must name a published version of the standard")
def s4_declared_version_exists(ctx):
    """A package that says it is iiRDS 9.9 cannot be validated as anything.

    Nothing in the catalogue constrains the value — M4 only counts how many
    times the property appears — so a package could declare a version that
    does not exist, be quietly checked against the newest one, and pass. The
    fallback is the right behaviour; doing it in silence is not.
    """
    if ctx.declared_version is None or ctx.declared_version in VERSIONS:
        return
    yield Violation("declared iiRDS version is not one this standard has published",
                    subject=ctx.declared_version,
                    detail="published versions: %s" % ", ".join(VERSIONS))


@rule("S5", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="iirds:formatRestriction must name a published profile")
def s5_declared_variant_exists(ctx):
    """An unrecognised profile silently switches off rules in both directions.

    Rules are filtered by variant, so a package declaring a profile that does
    not exist matches neither the unrestricted rules nor the handover ones: it
    skips both sets and reports clean. That is a one-line way to dodge
    validation entirely, and unlike the version case it produced no note at all.
    """
    if ctx.variant in VARIANTS:
        return
    yield Violation("declared iiRDS profile is not one this standard defines",
                    subject=ctx.variant,
                    detail="defined profiles: A, H, or no iirds:formatRestriction at all")


@rule("S6", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="every entry in the container must stay inside it")
def s6_entries_stay_inside_the_container(ctx):
    """An archive entry named `../../../etc/passwd` or `/tmp/x`.

    This validator never extracts anything, so it is not the one at risk — the
    consumer that unpacks the package is. Since the packages being checked
    arrive from suppliers, and since a build gate is the last thing that looks
    at them before something else does unpack them, it is worth failing on.

    No catalogued rule covers it: the specification constrains name characters
    and path length but says nothing about escaping the root, because it
    assumes good faith.
    """
    for name in ctx.package.names:
        if name.startswith("/") or name.startswith("\\") or ":" in name.split("/")[0]:
            yield Violation("container entry is an absolute path",
                            subject=name)
            continue
        if any(part == ".." for part in name.replace("\\", "/").split("/")):
            yield Violation("container entry escapes the package root",
                            subject=name,
                            detail="resolves to %s" % posixpath.normpath(name))


#: Section 5.2.2 states two requirements about the archive itself that no
#: catalogued rule covers. They are cheap to check and both are the kind of
#: thing a consumer discovers only when unpacking fails.
ZIP64_ENTRY_LIMIT = 65535
ZIP64_SIZE_LIMIT = 4 * 1024 ** 3


@rule("S7", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="the iiRDS ZIP archive must not be encrypted")
def s7_archive_is_not_encrypted(ctx):
    """"The iiRDS ZIP archive MUST NOT be encrypted." (section 5.2.2)

    Bit 0 of the general purpose flag. An encrypted entry cannot be read by a
    consumer that has only the package, which is every consumer.
    """
    if not ctx.package.is_archive:
        return
    for info in ctx.package.infos:
        if info.flag_bits & 0x1:
            yield Violation("archive entry is encrypted", subject=info.filename)


@rule("S8", kind="system", prio="MUST", versions=ALWAYS, variants=ALWAYS,
      title="large archives must use the ZIP64 extension")
def s8_zip64_where_required(ctx):
    """"The ZIP archive MUST use the ZIP64 extension if the file size is bigger
    than 4 GB or the package has more than 65536 file entries." (section 5.2.2)

    Without it the offsets wrap and the archive is unreadable past the limit —
    the classic way a large handover package arrives corrupt.
    """
    if not ctx.package.is_archive:
        return
    entries = len(ctx.package.infos)
    biggest = max((i.file_size for i in ctx.package.infos), default=0)
    if entries <= ZIP64_ENTRY_LIMIT and biggest <= ZIP64_SIZE_LIMIT:
        return
    # zipfile records the extension per entry; any entry needing it is enough.
    uses_zip64 = any(i.header_offset > 0xFFFFFFFF or i.file_size > 0xFFFFFFFF
                     or i.compress_size > 0xFFFFFFFF for i in ctx.package.infos)
    if not uses_zip64:
        yield Violation("archive exceeds the ZIP32 limits but does not use ZIP64",
                        detail="%d entries, largest file %d bytes" % (entries, biggest))
