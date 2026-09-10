"""Read-only view of an iiRDS package, however it happens to be stored.

Two forms, one interface. A `.iirds` file is the delivery format, and everything
the container rules need to know about the ZIP lives here, including the things
`zipfile` normally hides: entry order and per-entry compression.

A directory is the form the package exists in while it is being built. Checking
it before zipping is the difference between finding a defect in the second you
made it and finding it in the artefact — and content rules in particular are
worth running on every save. Six requirements are about the archive rather
than the package and cannot be assessed on a directory; `is_archive` says so,
and the report says so too, rather than quietly passing them.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import posixpath
import stat
import zipfile
from pathlib import Path
from typing import Iterator, List, NamedTuple, Optional, Tuple

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

#: The ceiling on what a run reads from META-INF looking for a package's own
#: ontology. A second budget, deliberately: `charge` below is the ceiling on
#: *content* and only content pays into it, because a first version counted
#: metadata too and a run died reading metadata.rdf with the death surfacing
#: as a parse error rather than as the budget it was. A reader asking what a
#: run will read in total needs both numbers, which is why each says so.
#:
#: Eight mebibytes is fifty times `iirds-core.rdf`, the ontology the standard
#: itself publishes, and twenty-five times the whole bundled set. A package's
#: own extension is smaller than the standard's; past this it is not an
#: ontology, it is something else in the same directory.
MAX_SIDE_BYTES = 8 * 1024 * 1024

#: Read size while checking that every entry decompresses. The check reads the
#: whole archive by construction -- that is what it is -- so the only thing to
#: choose is whether an entry arrives in memory whole. It does not.
_INTEGRITY_CHUNK = 1 << 16


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


def file_digest(path):
    """(sha256 of the file, its size, or None and why not).

    Streamed, because a container may be a quarter of a gigabyte and this runs
    on every check. What it answers is one question and only that one: the
    same bytes, or different bytes. It is **not** the identity of a package --
    recompressing the same content changes it while the verdict does not -- so
    nothing may read it as "a different package".

    A directory has no single file to hash, and an unreadable path has no
    bytes at all. Both come back as None with the reason said, rather than as
    a digest of nothing.
    """
    path = Path(path)
    if path.is_dir():
        return None, None, "an unpacked container is not one file, so it has no digest"
    running = hashlib.sha256()
    size = 0
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(_INTEGRITY_CHUNK)
                if not chunk:
                    break
                running.update(chunk)
                size += len(chunk)
    except OSError as exc:                        # noqa: BLE001 -- reported, not raised
        return None, None, "the bytes could not be read (%s)" % type(exc).__name__
    return "sha256:" + running.hexdigest(), size, None


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
    #: An entry is its bytes, whatever its mode says, and nothing here follows
    #: one. The unpacked form fills these in; S6 reads them from both.
    outward_links: Tuple[str, ...] = ()
    chained_links: Tuple[str, ...] = ()
    dangling_links: Tuple[str, ...] = ()
    absolute_links: Tuple[str, ...] = ()

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

    def local_headers(self) -> Iterator[Tuple[zipfile.ZipInfo, Optional[LocalHeader], bytes]]:
        """Every entry's local file header, read where the directory says it is.

        `(info, header, descriptor)` per directory entry, in directory order,
        the file opened once. `header` is None where the offset holds no
        local file header -- past the end of the file, negative after a
        broken ZIP64 end record, or bytes that do not start with the
        signature. `descriptor` is the 24 bytes following the
        data, as the directory's compressed size places them, for an entry
        whose local header sets bit 3; empty otherwise. Reads are bounded by
        the format itself: thirty bytes, then two 16-bit lengths' worth, then
        twenty-four. `infos` carries the offsets `zipfile` already corrected
        for anything prepended to the archive.
        """
        with open(self.path, "rb") as handle:
            for info in self.infos:
                header = None
                descriptor = b""
                # Negative after a broken ZIP64 end record: `zipfile` corrects
                # every offset by the shift it measures, and a record that
                # lies about the directory's position makes the shift negative.
                # One more offset that holds no local file header.
                head = b""
                if info.header_offset >= 0:
                    handle.seek(info.header_offset)
                    head = handle.read(_HEADER_FIXED)
                if len(head) == _HEADER_FIXED and head[:4] == _LOCAL_HEADER:
                    rest = handle.read(_u16(head, 26) + _u16(head, 28))
                    header = parse_local_header(head + rest, info.header_offset)
                if header is not None and header.flag_bits & 0x8:
                    handle.seek(header.data_start + info.compress_size)
                    descriptor = handle.read(_DESCRIPTOR_BYTES)
                yield info, header, descriptor

    @property
    def directory_offset(self) -> int:
        """Where the central directory begins, as `zipfile` found it."""
        return self._zip.start_dir

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
        this sees the shorter one -- so a member could be blessed here and
        arrive longer somewhere else. Refusing that is a rule about the
        archive rather than a bound on a read: S10 compares the two records
        for every entry, through `local_headers` below.
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

        The search for a package's own ontology under META-INF has its own,
        `MAX_SIDE_BYTES`, for that reason and not by oversight. Two ceilings,
        and what a run will read in total is their sum.
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
        """Name of the first entry that will not come back out, or None.

        Not `ZipFile.testzip`, which returns that name for one kind of damage
        and raises for the other: a CRC that does not match is returned, a
        deflate stream that will not decode is raised, and the two are the
        same fact about the same file. The raise used to be caught here and
        returned in the name's place, so C1 reported

            ZIP archive is corrupt: Error -3 while decompressing data

        naming no file, on an archive of any size. A flipped byte inside
        compressed data is the ordinary way an archive is damaged, so that
        was the ordinary reading -- the branch that produced it was marked
        as defensive.
        """
        for info in self._zip.infolist():
            try:
                with self._zip.open(info) as handle:
                    while handle.read(_INTEGRITY_CHUNK):
                        pass
            except Exception:
                return info.filename
        return None


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


#: FILE_ATTRIBUTE_REPARSE_POINT: what Windows sets on a name that stands for
#: somewhere else -- a junction, a symbolic link, and a few things that are
#: neither, such as a file a cloud client has not downloaded yet. Asked for by
#: attribute rather than by tag: `st_reparse_tag` is not on every build, and
#: `os.path.islink` says no to a junction.
_REPARSE_POINT = 0x400


#: How many links one name may be followed through before this gives up: the
#: smallest of the limits the systems this runs on enforce. Measured -- macOS
#: refuses the thirty-third with ELOOP, Linux allows forty. Asking the system
#: instead is worse than useless: `pathconf("PC_SYMLINK_MAX")` answers 255 on
#: the machine whose kernel stops at 32. Reading further than the number here
#: would judge a package on entries a consumer cannot open by name, which is
#: the opposite of what this rule is for, and a number that moved with the
#: machine would make one package two verdicts.
MAX_LINK_HOPS = 32

#: What `_resolve` answers. Four facts about a name, because they are four
#: different things to tell a reader: it resolves, it leads out, it is a chain
#: nothing will follow to the end, or it is written as an absolute path -- which
#: this cannot show to be inside the container without walking out of it, and
#: which is not how a package names its own files.
INSIDE, LEAVES, CHAINED, ABSOLUTE = "inside", "leaves", "chained", "absolute"


def _under(child: str, top: str) -> bool:
    """Whether a path is `top` or spelled beneath it -- as text, on purpose.

    Asking the filesystem is the thing being avoided: `os.path.realpath` walks
    a path to answer, and what it finds out there -- whether a directory
    exists, whether it may be searched -- would then be readable off the
    report. Every path compared here is a link's own text against a root this
    tool was handed.
    """
    top = os.path.normcase(os.path.normpath(top))
    child = os.path.normcase(os.path.normpath(child))
    return child == top or child.startswith(top + os.sep)


def _is_link(path: str) -> bool:
    """Whether this name stands for somewhere else rather than holding bytes.

    A junction is one and `os.path.islink` says it is not, so Windows is asked
    for the attribute instead -- and then for the target, because a name can
    carry that attribute and be no kind of link: a file a cloud client has not
    fetched yet is one, and reading it is reading a file, not following it.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    if not getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
        return False
    try:
        os.readlink(path)
    except OSError:                                     # standing for nothing this can follow
        return False
    return True


def _split(text: str) -> List[str]:
    """A link's own text, cut into components on this platform's separators."""
    if os.altsep:
        text = text.replace(os.altsep, os.sep)
    return text.split(os.sep)


def _absolute(text: str) -> bool:
    """Whether a link's text starts somewhere other than at the link.

    `os.path.isabs` is not enough on Windows, where a name that begins with a
    separator starts at the current drive's root and 3.13 stopped calling that
    absolute.
    """
    return (os.path.isabs(text) or bool(os.path.splitdrive(text)[0])
            or text[:1] == os.sep or (bool(os.altsep) and text[:1] == os.altsep))


#: What Windows puts in front of a target it hands back for a junction, and
#: sometimes for a symbolic link. It names the same directory; left on, every
#: junction inside a container reads as one leading out of it.
_EXTENDED = "\\\\?\\"


def _rooted(target: str, roots: Tuple[str, ...]) -> Optional[List[str]]:
    """An absolute target as components under the container, or None.

    Two spellings of the root, because a container reached through a link has
    two: the one the operator named and the one it resolves to. On macOS
    `/tmp` and `/private/tmp` are that pair, and an absolute link inside a
    package is written in whichever of them its author had.
    """
    if target.startswith(_EXTENDED):
        target = target[len(_EXTENDED):]
        if target[:4].upper() == "UNC" + os.sep:
            target = os.sep + os.sep + target[4:]
    for root in roots:
        if root and _under(target, root):
            return [part for part in _split(os.path.relpath(target, root))
                    if part and part != os.curdir]
    return None


def _resolve(roots: Tuple[str, ...], parts) -> Tuple[str, Optional[str]]:
    """Where a name in a container leads: one component at a time, from the
    root down, and never a step outside it.

    A path is resolved the way the kernel resolves one, because the kernel is
    what opens it. Reading a link's text and judging the whole joined string
    was not that: `os.readlink` looks at the last component only, so a link to
    `b/secret` was judged inside while `b` itself was a link out of the
    container, and `os.path.normpath` folded `sub/link/..` textually while the
    kernel followed the link first and went somewhere else entirely. Both put
    a file from outside into a report.

    So each component is joined to what has been resolved so far, and if that
    is a link its own text is walked in its place; `..` is applied to what is
    already resolved rather than to the text. Every path touched is under the
    root when it is touched, so nothing out there is looked at -- not `stat`,
    not `readlink` -- and the answer cannot depend on what happens to be
    there. Three answers, because a name can be three things: it resolves
    (`INSIDE`, with the file to open), it leads out (`LEAVES`), or it passes
    through more links than a reader would follow (`CHAINED`).
    """
    top = roots[0]
    pending = [part for part in reversed(list(parts)) if part and part != os.curdir]
    done: List[str] = []
    hops = 0
    while pending:
        part = pending.pop()
        if not part or part == os.curdir:
            continue
        if part == os.pardir:
            if not done:
                return LEAVES, None                     # a step above the root
            done.pop()
            continue
        here = os.path.join(top, *done, part)
        if _is_link(here):
            hops += 1
            if hops > MAX_LINK_HOPS:
                return CHAINED, None
            try:
                target = os.readlink(here)
            except OSError:                             # not ours to follow
                return LEAVES, None
            if _absolute(target):
                inner = _rooted(target, roots)
                if inner is None:
                    # It may well be inside: a container reached by one of its
                    # names holds links written with the other. Saying it leads
                    # out would be a claim this did not check -- checking it
                    # means resolving a path outside the container, which is
                    # the thing that put files from out there into reports.
                    return ABSOLUTE, None
                done = []
                pending.extend(reversed(inner))
            else:
                pending.extend(reversed([p for p in _split(target)
                                         if p and p != os.curdir] or [os.curdir]))
            continue
        done.append(part)
    return INSIDE, os.path.join(top, *done)


class Unlistable(PackageError):
    """A directory in the container that could not be listed.

    Not a finding about a package: what is in there was not looked at, and a
    check that quietly covers less than the container holds is the one thing
    this tool must not do. `os.walk` skips such a directory in silence, and a
    package can make one -- so the container is refused instead, by name.
    """


def _walk(roots: Tuple[str, ...]) -> Tuple[List[str], Tuple[str, ...], Tuple[str, ...],
                                           Tuple[str, ...], Tuple[str, ...]]:
    """The files of an unpacked container, and the links that are not files.

    `rglob` and `is_file()` answered this before, and `is_file()` answers for
    the far end of a link. So a link to any file the user running the check
    could read was listed, read and judged: a container whose metadata was a
    link to somebody else's passed on a file it does not contain, and one
    whose `mimetype` was a link to a private key had the first bytes of that
    key quoted into the report.

    Every link is resolved here instead (`_resolve`), and a link that is not a
    file inside the container becomes a name S6 reports rather than a name any
    rule can read.

    A directory that is a link is not walked through, in or out, which is what
    `rglob` did too. A junction is not walked through either, and that is the
    one listing this changes for a container holding one: `rglob` walked
    through those, because a junction is not what `islink` calls a link.
    """
    top = roots[0]
    names: List[str] = []
    leaving: List[str] = []
    chained: List[str] = []
    dangling: List[str] = []
    absolute: List[str] = []

    def refuse(error: OSError) -> None:
        where = error.filename or top
        with contextlib.suppress(ValueError):           # another drive: named as given
            where = os.path.relpath(where, top).replace(os.sep, "/")
        raise Unlistable("a directory in the container could not be listed: %s (%s)"
                         % (where, error.strerror or error))

    for here, directories, files in os.walk(top, followlinks=False, onerror=refuse):
        relative = os.path.relpath(here, top)
        prefix = "" if relative == os.curdir else relative.replace(os.sep, "/") + "/"
        for name in list(directories):
            full = os.path.join(here, name)
            if _is_link(full):
                directories.remove(name)
                verdict, _target = _resolve(roots, (prefix + name).split("/"))
                if verdict == LEAVES:
                    leaving.append(prefix + name)
                elif verdict == CHAINED:
                    chained.append(prefix + name)
                elif verdict == ABSOLUTE:
                    absolute.append(prefix + name)
        for name in files:
            entry = prefix + name
            full = os.path.join(here, name)
            if _is_link(full):
                verdict, target = _resolve(roots, entry.split("/"))
                if verdict == LEAVES:
                    leaving.append(entry)
                elif verdict == CHAINED:
                    chained.append(entry)
                elif verdict == ABSOLUTE:
                    absolute.append(entry)
                elif os.path.isfile(target):
                    names.append(entry)
                elif not os.path.lexists(target):
                    dangling.append(entry)
            elif os.path.isfile(full):
                names.append(entry)
    return (sorted(names), tuple(sorted(leaving)), tuple(sorted(chained)),
            tuple(sorted(dangling)), tuple(sorted(absolute)))


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
        if not (os.path.lexists(str(self.path / METADATA_RDF))
                or os.path.lexists(str(self.path / MIMETYPE_FILE))):
            raise PackageError(
                "%s is not an unpacked iiRDS container: no %s and no %s"
                % (self.path, MIMETYPE_FILE, METADATA_RDF))
        self._top = os.path.realpath(str(self.path))
        #: Both spellings of the root: the one that was named and the one it
        #: resolves to. An absolute link inside a package is written in one of
        #: them, and on macOS every path under `/tmp` has both.
        self._roots = (self._top, os.path.abspath(str(self.path)))
        self.names: List[str]
        (self.names, self.outward_links, self.chained_links,
         self.dangling_links, self.absolute_links) = _walk(self._roots)
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
        if name not in self._name_set:
            # What `zipfile` raises for a name the archive does not hold. Every
            # rule asks `has()` first, so none has come this way; it was the
            # one path by which a caller could open a file the listing never
            # offered, `../` and all.
            raise KeyError("There is no item named %r in the container" % name)
        where = self._entry(name)
        with open(where, "rb") as handle:
            data = handle.read(limit + 1)
        return data, len(data) > limit

    def text(self, name: str, encoding: str = "utf-8") -> str:
        return self.read(name).decode(encoding, errors="replace")

    def _entry(self, name: str) -> str:
        """The file to open for a listed name, followed again at the read.

        The listing is taken when the container is opened and the rules read
        it later, so the question is asked twice on purpose: a name that was a
        file when it was listed and is a link out of the container now is one
        the directory changed under the check, and it is refused rather than
        read.
        """
        verdict, where = _resolve(self._roots, name.split("/"))
        if verdict != INSIDE:
            raise PackageError("%s changed while it was being checked" % name)
        return where

    def info(self, name: str):
        if name not in self._name_set:
            return None
        return _FileInfo(os.stat(self._entry(name)).st_size)

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
#: A data descriptor (APPNOTE 4.3.9): an optional signature, crc-32, then the
#: two sizes at four bytes each or, for ZIP64, eight. Twenty-four bytes cover
#: the longest form.
_DATA_DESCRIPTOR = b"PK\x07\x08"
_DESCRIPTOR_BYTES = 24
_ZIP64_EXTRA = 0x0001
_PLACEHOLDER = 0xFFFFFFFF


class LocalHeader(NamedTuple):
    """The fields of a local file header (APPNOTE 4.3.7) a reader acts on,
    with the ZIP64 sizes (4.5.3) already read in for the placeholders."""
    offset: int
    name: bytes
    flag_bits: int
    compress_type: int
    crc: int
    compress_size: int
    file_size: int
    data_start: int


def parse_local_header(raw: bytes, offset: int) -> Optional[LocalHeader]:
    """The local file header at the start of `raw`, or None where there is none."""
    if len(raw) < _HEADER_FIXED or raw[:4] != _LOCAL_HEADER:
        return None
    name_len, extra_len = _u16(raw, 26), _u16(raw, 28)
    if len(raw) < _HEADER_FIXED + name_len + extra_len:
        return None
    name = raw[_HEADER_FIXED:_HEADER_FIXED + name_len]
    extra = raw[_HEADER_FIXED + name_len:_HEADER_FIXED + name_len + extra_len]
    compress_size, file_size = _zip64_sizes(extra, _u32(raw, 18), _u32(raw, 22))
    return LocalHeader(offset, name, _u16(raw, 6), _u16(raw, 8), _u32(raw, 14),
                       compress_size, file_size, offset + _HEADER_FIXED + name_len + extra_len)


def _zip64_sizes(extra: bytes, compress_size: int, file_size: int):
    """4.5.3: the ZIP64 extra carries, in this order, only the sizes whose
    32-bit field holds the placeholder."""
    at = 0
    while at + 4 <= len(extra):
        tag, size = _u16(extra, at), _u16(extra, at + 2)
        body = extra[at + 4:at + 4 + size]
        if tag == _ZIP64_EXTRA:
            cursor = 0
            if file_size == _PLACEHOLDER and cursor + 8 <= len(body):
                file_size = int.from_bytes(body[cursor:cursor + 8], "little")
                cursor += 8
            if compress_size == _PLACEHOLDER and cursor + 8 <= len(body):
                compress_size = int.from_bytes(body[cursor:cursor + 8], "little")
            break
        at += 4 + size
    return compress_size, file_size


def descriptor_readings(descriptor: bytes):
    """Every (crc, compressed size, uncompressed size) a data descriptor's
    bytes can be read as: with or without the signature (4.3.9.3), with
    four-byte or eight-byte sizes (ZIP64)."""
    for skip in (4, 0) if descriptor.startswith(_DATA_DESCRIPTOR) else (0,):
        for width in (4, 8):
            end = skip + 4 + 2 * width
            if len(descriptor) >= end:
                yield (_u32(descriptor, skip),
                       int.from_bytes(descriptor[skip + 4:skip + 4 + width], "little"),
                       int.from_bytes(descriptor[skip + 4 + width:end], "little"))


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
    """Whether either marker is there -- as a name, not as a far end.

    `exists()` answers for what a link points at, so a directory whose
    `META-INF/metadata.rdf` was a link out of it was a container when the file
    at the far end happened to be there and was not one when it was not. That
    is one bit about a path of the sender's choosing, read off the verdict.
    """
    return (os.path.lexists(str(path / MIMETYPE_FILE))
            or os.path.lexists(str(path / METADATA_RDF)))


def open_package(path):
    """Open whichever of the two forms is at `path`."""
    path = Path(path)
    if path.is_dir():
        return DirectoryPackage(path)
    return Package(path)


def search(path, recursive: bool = True) -> Tuple[List[Path], List[Path]]:
    """Every package under `path`, and every name under it that leads out.

    A `.iirds` file is itself. A directory that is an unpacked container is
    itself. Any other directory is searched for `.iirds` files, so pointing at
    a build output directory does the obvious thing.

    The path named on the command line is followed wherever it goes: it is the
    operator's own choice. A name *found* under it is not, and this followed
    those too -- a directory holding `x.iirds -> ~/.ssh/id_ed25519` put that
    file's digest and its size in the report, and one holding a link to
    somebody else's package had that package's metadata quoted in it. They
    come back in the second list, to be refused out loud rather than skipped
    in silence.
    """
    path = Path(path)
    if path.is_file():
        return [path], []
    if not path.is_dir():
        return [], []
    if looks_like_a_container(path):
        return [path], []
    # Both spellings again, and every candidate judged by the same walk from
    # the root down: a name found under a directory link was judged on its own
    # text before, so `build/x.iirds -> b/theirs.iirds`, with `b` a link out,
    # read somebody else's package and said nothing.
    roots = (os.path.realpath(str(path)), os.path.abspath(str(path)))
    pattern = "**/*.iirds" if recursive else "*.iirds"
    found: List[Path] = []
    leaving: List[Path] = []
    for candidate in sorted(path.glob(pattern)):
        verdict, where = _resolve(roots, candidate.relative_to(path).parts)
        if verdict != INSIDE:
            leaving.append(candidate)
        elif os.path.isfile(where):
            found.append(candidate)
    if found or leaving:
        return found, leaving
    # No archives: perhaps a directory of unpacked containers.
    for candidate in sorted(path.iterdir()):
        verdict, where = _resolve(roots, (candidate.name,))
        if verdict != INSIDE:
            leaving.append(candidate)
        elif os.path.isdir(where) and looks_like_a_container(candidate):
            found.append(candidate)
    return found, leaving


def discover(path, recursive: bool = True) -> List[Path]:
    """The packages `search` finds, for a caller with nothing to say about
    the names it refused."""
    return search(path, recursive)[0]
