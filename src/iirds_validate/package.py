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

import posixpath
import zipfile
from pathlib import Path
from typing import List, Optional

from .model import METADATA_RDF, MIMETYPE_FILE

#: Read in pieces this big. Large enough that a normal entry costs one or
#: two calls, small enough that a hostile one cannot make the first call
#: expensive.
_CHUNK = 1 << 16

#: The ceiling on any single entry read without one being asked for. Both
#: gates above this layer refuse at 64 MiB, so nothing legitimate needs more,
#: and a caller that cares about the boundary asks with `read_bounded`.
MAX_ENTRY_BYTES = 64 * 1024 * 1024


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


def entry_named(source: str) -> Optional[str]:
    """The container entry this `iirds:source` names, or None.

    None means "not a name in this container": an absolute URL, an empty
    value, or a path that climbs out of the package. The caller decides what
    to say about that -- this answers only what the value points at.
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
        return None       # section 5.1.3: not a character a file name carries
    # lstrip takes a character set rather than a prefix, so a leading dot
    # would be eaten: ".config/a.xhtml" must not become "config/a.xhtml".
    name = posixpath.normpath(path.lstrip("/"))
    if not path or name in (".", "..") or name.startswith("../"):
        return None
    return name


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
