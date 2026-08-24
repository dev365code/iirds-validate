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

import zipfile
from pathlib import Path
from typing import List, Optional

from .model import METADATA_RDF, MIMETYPE_FILE


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

    def read(self, name: str) -> bytes:
        return self._zip.read(name)

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

    def read(self, name: str) -> bytes:
        return (self.path / name).read_bytes()

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
