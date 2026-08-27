"""Read-only view of an iiRDS package, however it happens to be stored.

Two forms, one interface. A `.iirds` file is the delivery format, and everything
the container rules need to know about the ZIP lives here, including the things
`zipfile` normally hides: entry order and per-entry compression.

A directory is the form the package exists in while it is being built. Checking
it before zipping is the difference between finding a defect in the second you
made it and finding it in the artefact — and content rules in particular are
worth running on every save. Four requirements are about the archive rather
than the package and cannot be assessed on a directory; `is_archive` says so,
and the report says so too, rather than quietly passing them.
"""
from __future__ import annotations

import os
import posixpath
import zipfile
from pathlib import Path
from typing import List, Optional

from .model import METADATA_RDF, MIMETYPE_FILE, MIMETYPE_VALUE

#: Read in pieces this big. Large enough that a normal entry costs one or
#: two calls, small enough that a hostile one cannot make the first call
#: expensive.
_CHUNK = 1 << 16

#: The ceiling on any single entry read without one being asked for. Both
#: gates above this layer refuse at 64 MiB, so nothing legitimate needs more,
#: and a caller that cares about the boundary asks with `read_bounded`.
MAX_ENTRY_BYTES = 64 * 1024 * 1024

#: The ceiling on what one run will decompress in total. Per-entry limits
#: bound each rendition and nothing bounded their sum, so an archive that
#: compresses to nothing could make a run decompress as much as it declared:
#: measured, forty one-megabyte renditions in a package of no size at all made
#: the run read a hundred and sixty. Reads past this raise, and the rule that
#: reports it names the number rather than letting memory run out first.
MAX_CONTENT_TOTAL_BYTES = int(os.environ.get("IIRDS_CONTENT_BUDGET") or 512 * 1024 * 1024)
#: Read once at import, and named in S9's remedy: a delivery larger than the
#: default is not wrong, it is large, and the person checking it decides
#: what their machine can hold rather than this module deciding for them.


class ContentBudgetExceeded(Exception):
    """A run asked to decompress more than MAX_CONTENT_TOTAL_BYTES."""

    def __init__(self, read_so_far: int, limit: int):
        super().__init__("%d bytes decompressed against a ceiling of %d" % (read_so_far, limit))
        self.read_so_far, self.limit = read_so_far, limit


#: What `iirds:source` names, decided once.
#:
#: Three layers used to decide it separately and disagreed, which is worse
#: than any one of them being wrong: a value could be *present* to the rule
#: that reports missing files and *absent* to the rules that would open it, so
#: a topic carrying a script drew no finding at all while a consumer holding
#: the same package read the file without trouble. The verdict has to be about
#: the package a consumer gets.
#:
#: The specification calls the value a URL -- "iirds:source MUST relate the
#: rendition to the URL of the physical file" -- so it is parsed as one and
#: percent-decoded: a space in a filename is written `%20` and means a space.
#: Backslashes fold to slashes because that is what a reader does with them,
#: and a Windows-shaped path naming a file that is plainly in the container
#: should be judged on what it contains rather than only on how it is spelled.
#: A value that still points outside after normalising names nothing here.


#: Why `entry_named` answered None. Three different things to tell a reader,
#: and L2 told them all the same one until a value carrying a colon started
#: arriving here rather than resolving to a name nothing would match.
ELSEWHERE = "elsewhere"        # names a place outside this container entirely
NOTHING = "nothing"            # names nothing at all
ESCAPES = "escapes"            # climbs out of the container


def entry_named(source: str) -> Optional[str]:
    """The container entry this `iirds:source` names, or None.

    None means "not a name in this container": an absolute URL, an empty
    value, or a path that climbs out of the package. The caller decides what
    to say about that -- this answers only what the value points at. Which of
    the three it met is `entry_or_reason`.
    """
    return entry_or_reason(source)[0]


def entry_or_reason(source: str):
    """`(entry, None)` where the value names one, `(None, reason)` where it
    does not -- one of ELSEWHERE, NOTHING or ESCAPES.

    One resolution with the reason carried out of it, rather than a second
    one written beside it to work out why the first said no.
    """
    from urllib.parse import unquote

    # Query and fragment cut by hand rather than through a URL parser: a
    # parser reads `//content/a` as an authority named `content`, which turns
    # that value into `a` -- a different file, silently. That leaves `//`
    # read as a path where the rest is read as a URL; docs/divergences.md
    # records the whole reading and that deliberate seam in it.
    path = source.split("#", 1)[0].split("?", 1)[0]
    # Decode before folding: `%5c` is a backslash, and posixpath.normpath
    # leaves `..\..\` intact, so the oldest zip-slip spelling walks straight
    # out of anything that folds too early or not at all.
    path = unquote(path).replace("\\", "/")
    if ":" in path:
        return None, ELSEWHERE   # section 5.1.3: not a character a name carries
    # lstrip takes a character set rather than a prefix, so a leading dot
    # would be eaten: ".config/a.xhtml" must not become "config/a.xhtml".
    name = posixpath.normpath(path.lstrip("/"))
    if not path or name == ".":
        return None, NOTHING
    if name == ".." or name.startswith("../"):
        return None, ESCAPES
    return name, None


class PackageError(Exception):
    """The path is neither a readable archive nor a package directory."""


class UnreadablePath(PackageError):
    """Nothing could be read from the path at all: absent, or not permitted.

    Separate from a corrupt archive because the two are different problems for
    whoever is holding the package. A missing file is a mistake in the command;
    a corrupt one arrived that way, and the person who sent it needs to know.
    The catalogue has an identifier for each — S1 and C1 — and collapsing them
    into one meant S1 could never fire.
    """


class Package:
    """An .iirds archive."""

    is_archive = True

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            raise UnreadablePath("no such file: %s" % self.path)
        try:
            self._zip = zipfile.ZipFile(self.path)
        except zipfile.BadZipFile as exc:
            raise PackageError(str(exc)) from exc
        except OSError as exc:
            raise UnreadablePath(str(exc)) from exc
        except Exception as exc:
            # Everything else the central directory can do to a reader. An
            # entry name whose bytes are not the encoding its flag declares
            # raises UnicodeDecodeError from inside zipfile, and a supplier
            # sets that flag, not us. This class promises the caller two
            # exception types and the runner turns exactly those into
            # findings, so a third ends the run before any rule exists to
            # report it -- which is the failure this class was written to
            # prevent, arriving through the one door it does not watch.
            raise PackageError("%s: %s" % (type(exc).__name__, exc)) from exc
        self.infos: List[zipfile.ZipInfo] = self._zip.infolist()
        self.names: List[str] = [i.filename for i in self.infos]
        # Lookup tables. `info()` was a linear scan and `has()` a list
        # membership test, each called once per file per content rule — on a
        # 20,000-topic package that multiplied out to 35,000 scans over 20,000
        # entries and made validation quadratic: 0.5s at 1,000 topics, 36s at
        # 20,000. Same zipfile semantics: for a duplicated name the last entry
        # wins, which is what ZipFile.getinfo does.
        self._by_name = {i.filename: i for i in self.infos}
        self._name_set = frozenset(self.names)

    def __enter__(self) -> Package:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._zip.close()

    def has(self, name: str) -> bool:
        return name in self._name_set

    def read(self, name: str, limit: int = MAX_ENTRY_BYTES) -> bytes:
        return self.read_bounded(name, limit)[0]

    def read_bounded(self, name: str, limit: int):
        """The entry's bytes, and whether there were more than `limit` of them.

        Never an unbounded read. `ZipFile.read()` with no size decompresses
        the whole member in a single call and only then truncates it to the
        size the central directory declares -- a field the sender writes. An
        entry declaring a hundred bytes over a hundred megabytes of deflate
        therefore cost the hundred megabytes, resident, before the hundred
        bytes came back: 100 KB of archive for 450 MB, on a package the
        report then passed. Reading in chunks costs the chunk.

        The limit is on what is read, not on what is claimed, so a declared
        size cannot switch a gate off in either direction.

        What it does not fix, and what a first draft of this sentence claimed
        it did: `zipfile` truncates to the size in the *central directory*,
        and a consumer that streams the archive reads the *local* header
        instead. Where the two disagree the two see different documents, and
        this sees the shorter one -- so a member can be blessed here and
        arrive longer somewhere else. Refusing that is a rule about the
        archive rather than a bound on a read, and there is no rule for it
        yet; docs/scope.md carries it as open.
        """
        out = bytearray()
        with self._zip.open(name) as handle:
            while len(out) <= limit:
                chunk = handle.read(min(_CHUNK, limit + 1 - len(out)))
                if not chunk:
                    break
                out += chunk
        return bytes(out), len(out) > limit

    def charge(self, count: int) -> None:
        """Add `count` to the run's content-decompression total and stop past
        the ceiling.

        Called by the content rules and by nothing else. A first version
        charged every read inside `read_bounded`, which counted the metadata
        too -- so with a small ceiling the run died reading metadata.rdf, and
        the death surfaced as a parse error on the metadata rather than as
        the budget it was. Metadata and mimetype have their own gates; the
        ceiling is on content, and only content pays into it.
        """
        self.content_read = getattr(self, "content_read", 0) + count
        if self.content_read > MAX_CONTENT_TOTAL_BYTES:
            raise ContentBudgetExceeded(self.content_read, MAX_CONTENT_TOTAL_BYTES)

    def text(self, name: str, encoding: str = "utf-8") -> str:
        return self.read(name).decode(encoding, errors="replace")

    def info(self, name: str) -> Optional[zipfile.ZipInfo]:
        return self._by_name.get(name)

    @property
    def first_entry(self) -> Optional[zipfile.ZipInfo]:
        return self.infos[0] if self.infos else None

    @property
    def files(self) -> List[str]:
        """Entries that are files, not directory markers."""
        return [i.filename for i in self.infos if not i.is_dir()]

    def testzip(self) -> Optional[str]:
        """Name of the first corrupt entry, or None."""
        try:
            return self._zip.testzip()
        except Exception as exc:                       # pragma: no cover - defensive
            return str(exc)


class _FileInfo:
    """The one thing a directory can honestly answer about an entry: its size.

    Deliberately tiny and deliberately not a ZipInfo. Rules that need ZIP
    facts (entry order, compression) check `is_archive` and stand down; the
    size gates need only `file_size`, and while `DirectoryPackage.info()`
    answered None they were silently disabled for the unpacked form — the
    same oversized document an archive refuses was read and parsed whole
    when checked before zipping.
    """

    __slots__ = ("file_size",)

    def __init__(self, file_size: int):
        self.file_size = file_size


class DirectoryPackage:
    """An unpacked container: the shape a package has while you are building it.

    Presents the same interface as `Package` so no rule has to know which it is
    looking at. What it cannot present is a ZIP: there is no entry order, no
    compression mode, no encryption flag. Rules about those check `is_archive`
    and stand down.
    """

    is_archive = False

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_dir():
            raise PackageError("not a directory: %s" % self.path)
        if not (self.path / METADATA_RDF).exists() and not (self.path / MIMETYPE_FILE).exists():
            raise PackageError(
                "%s is not an unpacked iiRDS container: no %s and no %s"
                % (self.path, MIMETYPE_FILE, METADATA_RDF))
        self.names: List[str] = sorted(
            p.relative_to(self.path).as_posix()
            for p in self.path.rglob("*") if p.is_file())
        self.infos: List = []
        self._name_set = frozenset(self.names)

    def __enter__(self) -> DirectoryPackage:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        pass

    def has(self, name: str) -> bool:
        return name in self._name_set

    def read(self, name: str, limit: int = MAX_ENTRY_BYTES) -> bytes:
        return self.read_bounded(name, limit)[0]

    def charge(self, count: int) -> None:
        """The same budget as the archive form, kept in step by hand.

        The two package types share no base class, and the first version of
        the budget gave `charge` to the archive only -- so an unpacked
        container raised where a zipped one refused, and the two forms of one
        package stopped giving the same answer. tests/test_paths.py holds
        them to it.
        """
        self.content_read = getattr(self, "content_read", 0) + count
        if self.content_read > MAX_CONTENT_TOTAL_BYTES:
            raise ContentBudgetExceeded(self.content_read, MAX_CONTENT_TOTAL_BYTES)

    def read_bounded(self, name: str, limit: int):
        """Same contract as the archive form, and for the same reason.

        Nothing here is lying about a size -- a file on disk is as long as it
        is -- but the two forms have to answer alike or a gate is on in one
        and off in the other, which is how both size gates came to be
        silently disabled for the unpacked form once before.
        """
        with (self.path / name).open("rb") as handle:
            data = handle.read(limit + 1)
        return data, len(data) > limit

    def text(self, name: str, encoding: str = "utf-8") -> str:
        return self.read(name).decode(encoding, errors="replace")

    def info(self, name: str):
        if name not in self._name_set:
            return None
        return _FileInfo((self.path / name).stat().st_size)

    @property
    def first_entry(self):
        return None

    @property
    def files(self) -> List[str]:
        return list(self.names)

    def testzip(self):
        return None


#: §5.2: "The file name of the iiRDS ZIP archive MUST feature the file name
#: extension .iirds".
CONTAINER_SUFFIX = ".iirds"

#: A ZIP local file header is thirty fixed bytes, then the name, then the extra
#: field, then the data. The fields read here: the signature, the compression
#: method at 8, the compressed size at 18, the name length at 26 and the extra
#: length at 28.
_LOCAL_HEADER = b"PK\x03\x04"
_HEADER_FIXED = 30
_STORED = 0


def _u16(raw: bytes, at: int) -> int:
    return int.from_bytes(raw[at:at + 2], "little")


def _u32(raw: bytes, at: int) -> int:
    return int.from_bytes(raw[at:at + 4], "little")


def _opens_like_a_container(head: bytes, more) -> bool:
    """Does this begin the way §5.2 says an iiRDS ZIP archive begins?

    "the root directory of the ZIP file MUST contain a file named mimetype. It
    MUST contain the following ASCII-encoded text in a single line, without any
    line delimiters such as CR or LF: application/iirds+zip. The file MUST be
    the first entry in the ZIP file and it MUST be stored uncompressed."

    Every clause of that is a discriminator, and the name is not one of them:
    a file called nested.iirds holding any twenty-eight bytes would otherwise
    answer the question a nesting rule asks. Read from the first *local*
    header rather than from the central directory, because the directory is
    written by whoever built the archive and a consumer streaming the file
    reads the local one; where they disagree this sees what a stream sees.

    `more` is called with the number of bytes needed when the extra field
    pushes the payload past what was already read.
    """
    if len(head) < _HEADER_FIXED or head[:4] != _LOCAL_HEADER:
        return False
    if _u16(head, 8) != _STORED:
        return False
    name_len, extra_len = _u16(head, 26), _u16(head, 28)
    payload = MIMETYPE_VALUE.encode("ascii")
    if name_len != len(MIMETYPE_FILE) or _u32(head, 18) != len(payload):
        return False
    if head[_HEADER_FIXED:_HEADER_FIXED + name_len] != MIMETYPE_FILE.encode("ascii"):
        return False
    start = _HEADER_FIXED + name_len + extra_len
    raw = head if len(head) >= start + len(payload) else more(start + len(payload))
    return raw[start:start + len(payload)] == payload


def nested_containers(package) -> List[str]:
    """Every entry that is a nested iiRDS container, in a fixed order.

    The evidence the metadata cannot give. A document that declares a nested
    package and a document that *is* the nested package are the same graph --
    §6.2 says a conformant package's own instance is not a member of another
    package, so the only metadata evidence for either reading is the relation
    under dispute. The archive is outside that circle: §5.3 says nested
    packages "are stored as iiRDS ZIP archives", §5.1.2 lists them among the
    content files below the root directory, and §6.3.3 says all of them "MUST
    be included side by side in the iiRDS ZIP archive of the highest level
    iiRDS package".

    Sorted because entry order is the sender's choice and a report is not.
    """
    found = []
    for name in sorted(package.files):
        if not name.endswith(CONTAINER_SUFFIX):
            continue
        try:
            head = package.read_bounded(name, _HEADER_FIXED + 256)[0]
            if _opens_like_a_container(
                    head, lambda n, _name=name: package.read_bounded(_name, n)[0]):
                found.append(name)
        except Exception:                     # unreadable is not nested
            continue
    return found


def looks_like_a_container(path: Path) -> bool:
    return (path / MIMETYPE_FILE).exists() or (path / METADATA_RDF).exists()


def open_package(path):
    """Open whichever of the two forms is at `path`."""
    path = Path(path)
    if path.is_dir():
        return DirectoryPackage(path)
    return Package(path)


def discover(path, recursive: bool = True) -> List[Path]:
    """Every package under `path`, in a stable order.

    A `.iirds` file is itself. A directory that is an unpacked container is
    itself. Any other directory is searched for `.iirds` files, so pointing at
    a build output directory does the obvious thing.
    """
    path = Path(path)
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    if looks_like_a_container(path):
        return [path]
    pattern = "**/*.iirds" if recursive else "*.iirds"
    found = sorted(p for p in path.glob(pattern) if p.is_file())
    if found:
        return found
    # No archives: perhaps a directory of unpacked containers.
    return sorted(p for p in path.iterdir() if p.is_dir() and looks_like_a_container(p))
