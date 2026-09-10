# Security

## Why this file is not boilerplate

This tool's job is to open archives that arrive from outside — a supplier's
handover package is exactly the kind of file people are told not to open — and
it is built to be the *last* thing standing between such a file and whatever
unpacks it next, on networks where nothing else gets a look. So hostile input
is not an edge case here; it is the working assumption.

## What is already defended, and where the proof lives

| threat | defence | pinned by |
|---|---|---|
| Path traversal ("zip-slip"): entries named `../…` escape the extraction directory, and in an unpacked container a link can lead out of it | S6 reports any entry that leaves the container: by its name in an archive, by where it leads in a directory. In a directory, an entry that leads out is named and never read, and so is a chain of links too long to follow | `tests/test_silent_pass.py`, `tests/test_unpacked_links.py` |
| Entity-expansion bombs in metadata or content (a 400-byte file that expands without bound) | any XML declaring entities is refused outright, and the refusal is itself a finding | `tests/test_content_hostile.py`, `tests/test_silent_pass.py` |
| An archive whose two records of an entry disagree: the central directory, which `zipfile` and this tool read, describes one file, and the local file header, which a streaming consumer reads, describes another -- a package blessed on a benign prefix while a stream receives the rest | S10 compares the two records for every entry -- name, method, the flags a reader acts on, crc-32 and sizes, from the local header or from the data descriptor it defers to -- and reports data that runs into the next entry | `tests/test_header_agreement.py`, one field of one record changed per fixture, and the archives stream writers and ZIP64 produce as the negatives |
| Oversized inputs | metadata and content are read to 64 MiB and no further, and refused there. The limit is on what comes back, not on the size the archive declares -- that field belongs to whoever built it, and a gate reading it is a gate the sender sets | `tests/test_content_hostile.py`, `tests/test_size_gates.py` |
| Metadata that sends the reader somewhere else: a JSON-LD `@context` can point outside the package, and a package is something a supplier hands you | every context reference is refused, whichever keyword names it and whether or not it carries a scheme. Inside a plant network that is a supplier choosing where a machine behind the firewall goes looking. **The refusal lives in the `iirds` reader and arrives with the release that carries it — this project's declared floor decides which packages of yours are covered.** | `tests/test_offline.py`, gated on the reader's version. The reader's own suite pins each construct and runs with rdflib's single context-fetch function sealed, so a construct nobody has enumerated turns it red too. |
| Supply-chain drift in what this tool itself bundles | the ontologies and the vendored corpus are verified against recorded SHA-256 digests on every run of the suite; the `.pyz` is bit-for-bit reproducible so the hash on a release page is the hash of the file carried across the air gap | `iirds_validate.ontology --verify`, `tests/test_corpus_integrity.py`, `tools/build_zipapp.py` |
| Anything at run time needing a network | there is no network code path at all; validation is pure local computation | `tests/test_offline.py` |

The tool never executes content, never extracts archives to disk, and reads
entries one at a time in memory.

An unpacked container is a directory, and a directory can hold links, so there
the question is what this tool itself reads. Only what the container holds. A
name is resolved from the container's root downwards, one component at a time,
each link replaced by its own text where it stands and never a step outside, so
nothing out there is looked at to decide -- not `stat`, not `readlink`. Four
kinds of entry are named by S6 and not opened: one that leads out, one written
as an absolute path, one passing through more links than a system will follow,
and one pointing at nothing. An absolute link is judged against the container's
two names -- the one it was given and the one that resolves -- so one written
in a third spelling of the same place is reported rather than read. A name the
listing does not hold is refused as the archive refuses it; each read resolves
the name again, so a file swapped for a link after the listing is not read
either; and a directory the check cannot list refuses the container rather than
leaving part of it unlooked at. Both markers that make a directory a container
are found by name rather than by what they point at, so whether a file
somewhere else exists decides nothing about the report.

The same holds one layer up. Pointing at a directory searches it for packages,
and a `.iirds` name found there that leads out of the directory is refused by
name and not read; where the directory holds unpacked containers rather than
archives, a linked container is refused the same way. The run exits 2 rather
than checking less than it was asked to in silence. The path named on the
command line is followed wherever it goes: that one is the operator's own
choice.

Three things are outside what that can see. A hard link is the file itself to
any directory listing, and is read as one. A directory somebody else is
changing while it is being checked can race any check made from outside it.
And an archive entry whose mode marks it as a symbolic link is, to this tool, a
file holding the link's text -- S6 reads its name, not where that text points;
an extractor that restores links, as Info-ZIP `unzip` does, turns such an
archive into exactly the directory described above, and that directory is what
the paragraph above covers.

## Reporting a vulnerability

If you find a way to make this tool misbehave on a hostile package — crash,
hang, over-read, or worst of all *pass something silently* — please use
GitHub's private vulnerability reporting on this repository ("Security" →
"Report a vulnerability") rather than a public issue, and it will be handled
with priority over everything else. A silent pass on hostile input is the
most serious bug this project can have; the changelog shows that such reports
get fixed, tested and credited rather than argued with.

Supported versions: the latest release. There is no backporting; upgrading is
copying one file.
