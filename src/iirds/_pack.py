"""Writing a conformant container.

Written first as the checker's packer and moved here, because the container
rules people get wrong most — mimetype first and stored, stable bytes —
belong in the layer that every tool shares. `iirds_validate.cli` and
`iirds_validate.runner` import `pack` from here; there is one copy.
"""
from __future__ import annotations

import os
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import List, Optional

from ._package import METADATA_RDF

MIMETYPE_FILE = "mimetype"
MIMETYPE_VALUE = "application/iirds+zip"

#: A fixed timestamp for every entry, so packing the same directory twice
#: produces the same bytes. Override with SOURCE_DATE_EPOCH if a build
#: system wants its own.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


#: What a ZIP entry can carry. The format keeps the year as an offset from
#: 1980 in seven bits, so anything outside this is not a stamp it can hold --
#: and `SOURCE_DATE_EPOCH=0`, the commonest value a reproducible build is
#: given, is outside it. Clamping keeps the promise the variable makes (two
#: builds of one tree agree) where refusing would refuse to pack at all.
ZIP_EARLIEST = (1980, 1, 1, 0, 0, 0)
ZIP_LATEST = (2107, 12, 31, 23, 59, 58)


def _timestamp():
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        return FIXED_TIMESTAMP
    try:
        stamp = time.gmtime(int(epoch))[:6]
    except (ValueError, OSError, OverflowError):
        # OverflowError is neither of the other two and used to escape: a
        # value large enough gave a year in the millions, and the struct the
        # ZIP writes it into holds two bytes.
        return FIXED_TIMESTAMP
    return min(max(stamp, ZIP_EARLIEST), ZIP_LATEST)


#: Compressing these again wastes time and space for no gain.
ALREADY_COMPRESSED = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".m4v",
                      ".mp3", ".zip", ".iirds", ".woff", ".woff2")


class PackError(Exception):
    """The directory is not something that can be packed into a container."""


def _member_name(entry: Path, source: Path) -> str:
    """The name this file is stored under: one spelling, composed.

    A filesystem hands back whichever form the name was created in, and
    several macOS tools create the decomposed one. The metadata that refers to
    the file is written by a person in an editor and is composed, so the two
    are different byte strings and a lookup by the name in the RDF misses a
    file that is plainly there. Composed is what XML and RDF are written in,
    and choosing it means the archive says one thing rather than whatever the
    directory listing happened to say.
    """
    return unicodedata.normalize("NFC", entry.relative_to(source).as_posix())


def _symlinks(source: Path) -> List[Path]:
    """Links found anywhere under the source.

    `Path.is_file()` answers for the thing at the far end, so a link to a file
    outside the directory had those bytes read and written into the archive --
    whatever they were, and quietly. A link to a directory is the same silence
    facing the other way: rglob does not descend through one, so the author
    sees a folder in the source and finds nothing in the package.

    Neither is a decision this function may make on the author's behalf, so
    the rule is about links rather than about what they point at.
    """
    return sorted(p for p in source.rglob("*") if p.is_symlink())


def _entries(source: Path) -> List[Path]:
    files = sorted(p for p in source.rglob("*") if p.is_file())
    mimetype = source / MIMETYPE_FILE
    rest = [p for p in files if p != mimetype]
    return ([mimetype] if mimetype.exists() else []) + rest


def pack(source, output=None, *, overwrite: bool = False) -> Path:
    """Write `source` as a conformant .iirds archive and return its path.

    The mimetype file is created if missing — a directory with
    META-INF/metadata.rdf is plainly meant to be a package.
    """
    source = Path(source)
    if not source.is_dir():
        raise PackError("not a directory: %s" % source)
    # Asked of the names that will be written, not of the filesystem. On a
    # case-insensitive one -- macOS and Windows, where most authoring happens
    # -- `exists()` answers yes for `meta-inf/Metadata.rdf`, and the archive
    # then carries the spelling that was on disk. A ZIP member name is bytes,
    # so a reader looking for the spelling the standard names does not find
    # it: pack() wrote a package open() refuses, which is the one thing this
    # library promises it will not do.
    if METADATA_RDF not in {entry.relative_to(source).as_posix()
                            for entry in _entries(source)}:
        raise PackError("%s has no %s, so it is not an iiRDS container. A file "
                        "spelled another way does not count: the name goes into "
                        "the archive as it is written here, and a reader looks "
                        "for %s exactly."
                        % (source, METADATA_RDF, METADATA_RDF))

    output = Path(output) if output else source.with_suffix(".iirds")
    if output.suffix.lower() != ".iirds":
        output = output.with_suffix(".iirds")
    if output.exists() and not overwrite:
        raise PackError("%s exists; pass overwrite=True to replace it" % output)
    output.parent.mkdir(parents=True, exist_ok=True)

    seen: dict = {}
    for entry in _entries(source):
        seen.setdefault(_member_name(entry, source), []).append(entry)
    collisions = {name: paths for name, paths in seen.items() if len(paths) > 1}
    if collisions:
        name, paths = sorted(collisions.items())[0]
        raise PackError(
            "two files are stored under the same name once written composed: %s. "
            "An archive cannot hold both, and which one a reader would get is "
            "not something this should decide -- rename one."
            % ", ".join(sorted(str(path.relative_to(source)) for path in paths)))

    links = _symlinks(source)
    if links:
        raise PackError(
            "%s contains symbolic links, and a container is meant to be "
            "self-contained: %s. Replace each with the file it points at, or "
            "take it out of the directory being packed."
            % (source, ", ".join(link.relative_to(source).as_posix() for link in links[:5])))

    mimetype_content: Optional[bytes] = None
    if (source / MIMETYPE_FILE).exists():
        mimetype_content = (source / MIMETYPE_FILE).read_bytes()
        if mimetype_content != MIMETYPE_VALUE.encode("ascii"):
            raise PackError("%s does not contain %r; fix it rather than have this "
                            "overwrite it" % (MIMETYPE_FILE, MIMETYPE_VALUE))

    stamp = _timestamp()
    # Written beside the destination and moved into place, because opening the
    # destination for writing truncates it before a byte has been read. A
    # failure part-way -- a file that moved, a permission, a full disk -- then
    # destroyed whatever was there and left the part that had been written,
    # and that remainder is not obviously broken: the central directory is
    # still written on the way out, so it passes testzip() and opens and
    # reports its version while missing most of its content. The rename is one
    # step on every filesystem this runs on, so the destination is either the
    # package that was there or the one just built, and never a mixture.
    temporary = output.with_name(output.name + ".part-%d" % os.getpid())
    try:
        _write_archive(temporary, source, stamp, mimetype_content)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    return output


def _write_archive(path: Path, source: Path, stamp, mimetype_content: Optional[bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        # First entry, stored uncompressed — the rule every other tool gets
        # wrong, and it has to happen before anything else is written.
        info = zipfile.ZipInfo(MIMETYPE_FILE, date_time=stamp)
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, mimetype_content or MIMETYPE_VALUE.encode("ascii"))

        for entry in _entries(source):
            name = _member_name(entry, source)
            if name == MIMETYPE_FILE:
                continue
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = (zipfile.ZIP_STORED
                                  if name.lower().endswith(ALREADY_COMPRESSED)
                                  else zipfile.ZIP_DEFLATED)
            info.external_attr = 0o644 << 16
            archive.writestr(info, entry.read_bytes())
