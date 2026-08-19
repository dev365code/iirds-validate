"""Read-only view of an .iirds container.

Everything the container rules need to know about the ZIP lives here, including
the things `zipfile` normally hides: entry order and per-entry compression.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import List, Optional


class PackageError(Exception):
    """The file could not be opened as a ZIP archive at all."""


class Package:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            raise PackageError(f"no such file: {self.path}")
        try:
            self._zip = zipfile.ZipFile(self.path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise PackageError(str(exc)) from exc
        self.infos: List[zipfile.ZipInfo] = self._zip.infolist()
        self.names: List[str] = [i.filename for i in self.infos]

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> Package:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._zip.close()

    # -- accessors ----------------------------------------------------------
    def has(self, name: str) -> bool:
        return name in self.names

    def read(self, name: str) -> bytes:
        return self._zip.read(name)

    def text(self, name: str, encoding: str = "utf-8") -> str:
        return self.read(name).decode(encoding, errors="replace")

    def info(self, name: str) -> Optional[zipfile.ZipInfo]:
        for i in self.infos:
            if i.filename == name:
                return i
        return None

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
        except Exception as exc:  # pragma: no cover - defensive
            return str(exc)
