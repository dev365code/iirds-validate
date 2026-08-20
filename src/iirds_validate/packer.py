"""Writing a container, because the requirements about the archive cannot be
checked before there is one.

Validating an unpacked directory leaves five requirements unanswerable: the
`.iirds` extension, `mimetype` being the first entry and stored uncompressed,
the archive not being encrypted, and ZIP64 past the size limits. Reporting them
as "not assessed" is honest and unhelpful — the person holding a directory
wants a package, not a caveat.

They are also the requirements people get wrong most often, and not through
carelessness. "First entry, stored uncompressed" is an OPC and EPUB convention
that `zip` can only manage with two invocations and the right flags, that most
graphical tools cannot express at all, and that `shutil.make_archive` gets
wrong every time. A validator that knows the rule and cannot apply it is
withholding the easy half of its knowledge.

So: pack it correctly, then validate the result. The five requirements stop
being unanswerable because they stop being in question.
"""
from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path
from typing import List, Optional

from .model import METADATA_RDF, MIMETYPE_FILE, MIMETYPE_VALUE

#: A fixed timestamp for every entry, so packing the same directory twice
#: produces the same bytes. That turns "this archive was built from that
#: directory" into something checkable with sha256 instead of something you
#: take on trust, and it costs a modification date nobody reads. Override with
#: SOURCE_DATE_EPOCH if a build system wants its own.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _timestamp():
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        return FIXED_TIMESTAMP
    try:
        return time.gmtime(int(epoch))[:6]
    except (ValueError, OSError):
        return FIXED_TIMESTAMP


#: Compressing these again wastes time and space for no gain.
ALREADY_COMPRESSED = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".m4v",
                      ".mp3", ".zip", ".iirds", ".woff", ".woff2")


class PackError(Exception):
    """The directory is not something that can be packed into a container."""


def _entries(source: Path) -> List[Path]:
    """Every file, with mimetype first and the rest in a stable order.

    Stable because two runs over the same directory should produce the same
    archive: a package you can rebuild and compare is a package you can trust
    someone else built the same way.
    """
    files = sorted(p for p in source.rglob("*") if p.is_file())
    mimetype = source / MIMETYPE_FILE
    rest = [p for p in files if p != mimetype]
    return ([mimetype] if mimetype.exists() else []) + rest


def pack(source, output=None, *, overwrite: bool = False) -> Path:
    """Write `source` as a conformant .iirds archive and return its path.

    The mimetype file is created if it is missing — a directory that has
    META-INF/metadata.rdf is plainly meant to be a package, and refusing over
    a twenty-one byte file nobody can remember the contents of helps nobody.
    """
    source = Path(source)
    if not source.is_dir():
        raise PackError("not a directory: %s" % source)
    if not (source / METADATA_RDF).exists():
        raise PackError("%s has no %s, so it is not an iiRDS container"
                        % (source, METADATA_RDF))

    output = Path(output) if output else source.with_suffix(".iirds")
    if output.suffix.lower() != ".iirds":
        output = output.with_suffix(".iirds")
    if output.exists() and not overwrite:
        raise PackError("%s exists; pass overwrite to replace it" % output)
    output.parent.mkdir(parents=True, exist_ok=True)

    mimetype_content: Optional[bytes] = None
    if (source / MIMETYPE_FILE).exists():
        mimetype_content = (source / MIMETYPE_FILE).read_bytes()
        if mimetype_content != MIMETYPE_VALUE.encode("ascii"):
            raise PackError("%s does not contain %r; fix it rather than have this "
                            "overwrite it" % (MIMETYPE_FILE, MIMETYPE_VALUE))

    stamp = _timestamp()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        # First entry, stored uncompressed. This is the one every other tool
        # gets wrong, and it has to happen before anything else is written.
        info = zipfile.ZipInfo(MIMETYPE_FILE, date_time=stamp)
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, mimetype_content or MIMETYPE_VALUE.encode("ascii"))

        for path in _entries(source):
            name = path.relative_to(source).as_posix()
            if name == MIMETYPE_FILE:
                continue
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = (zipfile.ZIP_STORED
                                  if name.lower().endswith(ALREADY_COMPRESSED)
                                  else zipfile.ZIP_DEFLATED)
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())

    return output
