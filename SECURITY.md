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
| Path traversal ("zip-slip"): entries named `../…` escape the extraction directory, and in an unpacked container a link can lead out of it | S6 reports any entry that leaves the container: by every name it can be read as in an archive -- the one each record's bytes spell and the ones its Unicode Path extra fields give their readers, each up to a NUL -- by where it leads in a directory. In a directory, an entry that leads out is named and never read, and so is a chain of links too long to follow | `tests/test_silent_pass.py`, `tests/test_unpacked_links.py`, `tests/test_header_agreement.py` |
| Entity-expansion bombs in metadata or content (a 400-byte file that expands without bound) | any XML declaring entities is refused outright, and the refusal is itself a finding | `tests/test_content_hostile.py`, `tests/test_silent_pass.py` |
| Two metadata files whose blank nodes look alike: asking whether one repeats the other, and what each holds that the other lacks, was a search whose time grows faster than the files -- about a kilobyte of JSON-LD could hold a run for minutes | blank nodes that form trees are named by what hangs off them and compared in one pass, whatever their number and depth. What is left -- a blank node two blank nodes point at, or a cycle of them -- is named by trying every order of those nodes alone, which is exact, and is not tried past `MAX_COMPARED_BLANK_NODES` (eight) in a file: the second file is then left out of the merge, and C16.2 says so and names the limit. The same comparison checks what `write_metadata` writes, and refuses there by `ValueError` | `tests/test_bounded_comparison.py` |
| An archive whose two records of an entry disagree: the central directory, which `zipfile` and this tool read, describes one file, and the local file header, which a streaming consumer reads, describes another -- a package blessed on a benign prefix while a stream receives the rest | S10 compares the two records for every entry -- name, as each record's bit 11 reads it and as its bytes spell it, with each record's Unicode Path extra fields held to that name, method, the flags a reader acts on, crc-32 and sizes, from the local header or from the data descriptor it defers to -- and reports data that runs into the next entry | `tests/test_header_agreement.py`, one field of one record changed per fixture, and the archives stream writers and ZIP64 produce as the negatives |
| An archive whose central directory names one entry many times. `zipfile` resolves a name to the last record carrying it, so the earlier ones describe bytes no reader here opens -- and a pass that walks records rather than names does that entry's work once per record. Measured: 11,890 bytes on disk, fifty records over one entry declaring 8 MiB, 419,430,400 bytes decompressed in 0.23 s, and each repetition costs the sender a 46-byte record plus the name | the damage check behind C1 reads each name once, so what it costs is the entry's size rather than the record count, and S15 reports the duplication: how many records carry the name, that this run resolved it to the last of them, and, where the records give different offsets, that they describe different bytes -- two whole entries under one name, which is the case S10 cannot see because each record does agree with its own local header | `tests/test_duplicate_directory_records.py`, which measures what a whole run decompresses on the crafted archive and pins the duplication as a finding of its own |
| Oversized inputs, and an archive of no size at all that declares a great deal | metadata and content are read to 64 MiB per file and no further, and refused there. Across one run, what the content rules read is held to a total ceiling as well -- 512 MiB by default, `IIRDS_CONTENT_BUDGET` -- and past it a rendition is refused **without being read**, and named in the report as not examined rather than passed. So what the content rules read is that ceiling plus one per-file limit, once: a file's cost is not knowable without reading it, so one read may cross the ceiling and none after it. Both limits are on what comes back, not on the size the archive declares -- that field belongs to whoever built it, and a gate reading it is a gate the sender sets. **The ceiling does not bound what a whole run decompresses, and cannot**: asking whether an archive is damaged means opening the entries it can read, once per name, so a run reads what those declare however small the ceiling is. That pass asks for a bounded slice at a time and keeps none of it. A package that declares far more than it weighs therefore costs time in proportion to what it declares, not to its size | `tests/test_rendition_budget.py` for the ceiling, the environment variable and both package forms; `tests/test_content_hostile.py` for the reading bound and the damage pass; `tests/test_size_gates.py` |
| An archive of no size that declares a great deal in a compression method whose reads cannot be bounded | Every limit here is on what a read hands back. Python's zip reader passes the caller's length to the decompressor for deflate and for nothing else; stored has no decompressor to pass a length to and its read is bounded by the request; the two that do decompress and take no length hand the entry back whole and the result is sliced, so the slice is bounded and the allocation behind it is not. Measured: one 64 MiB entry, one 64 KiB read -- stored 79,898 bytes allocated, deflate 238,399, bzip2 71,530,984 from an archive of 189 bytes, lzma 79,972,634 from 9,657; lowering a ceiling does not touch it. So an entry in any method but stored and deflate is not opened: S14 reports it, and says it was not parsed and not checked for damage either, because answering that would mean decompressing it. Refusing is the only bound here that can be shown to hold -- driving the decompressors directly, with the length limit they do accept, means reimplementing the archive format's framing in the layer that opens files from strangers | `tests/test_compression_methods.py` |
| Metadata that sends the reader somewhere else: a JSON-LD `@context` can point outside the package, and a package is something a supplier hands you | every context reference is refused, whichever keyword names it and whether or not it carries a scheme. Inside a plant network that is a supplier choosing where a machine behind the firewall goes looking. **The refusal lives in the `iirds` reader and arrives with the release that carries it — this project's declared floor decides which packages of yours are covered.** | `tests/test_offline.py`, gated on the reader's version. The reader's own suite pins each construct and runs with rdflib's single context-fetch function sealed, so a construct nobody has enumerated turns it red too. |
| Supply-chain drift in what this tool itself bundles | the ontologies and the vendored corpus are verified against recorded SHA-256 digests on every run of the suite; the `.pyz` is byte-identical for one commit and one set of dependency versions built on one kind of system -- timestamps and entry order are pinned, the entry point is written as bytes rather than in the building system's line endings, the dependencies' console scripts carry the building machine's interpreter path and are dropped, and pip's record of its own installation is left out of the archive -- so the hash on a release page is the hash of the file carried across the air gap, and a rebuild can be compared against it. Three inputs are not pinned: what the index offers on the day and `SOURCE_DATE_EPOCH` if the builder sets one, both of which move the bytes, and the zlib the building Python compresses the entries with; what is measured is one runner building it twice (`.github/workflows/release.yml`), not two kinds of system against each other | `iirds_validate.ontology --verify`, `tests/test_corpus_integrity.py`, `tests/test_pack.py`, `tests/test_serve.py` |
| What runs in the jobs that build and publish a release: every `uses:` named a tag or a branch, so whoever owns that action decided, after this repository had been read, what would execute in the job that holds `id-token: write` and uploads under this project's name | every action is pinned to a full commit object, with the release it is written beside it, and the same action carries one commit everywhere it appears. The PyPI publisher, pinned so, still runs a container image it pulls from its registry by a tag, which its owner could push again. Pins are moved by hand: nothing here rewrites them, because a tool that did would be one more moving reference with write access to the file that decides what runs | `tests/test_workflow_supply_chain.py` |
| Anything at run time needing a network | validation opens no connection and needs no network; it is pure local computation. The one socket in the tool is `iirds serve`'s listener, which binds only to loopback and resolves a host name the operator gives in order to check that | `tests/test_offline.py`, `tests/test_serve.py` |

The tool never executes content, never extracts archives to disk, and reads
entries one at a time in memory.

The drop page, `iirds serve`, writes one thing to disk: the package it
receives. The upload is streamed into a file in a directory made for that
request under the system's temporary directory -- the alternative is holding
each package in memory for as long as it is checked -- and moved, under a safe
form of the name it was dropped with, into a second temporary directory while
it is checked. Both directories are removed before the answer is sent,
whichever way the request ends short of the process being killed, so by the
time the page shows a verdict the copy is gone. The other parts of a form are
read past, not written. `tests/test_drop_leaves_nothing.py` holds the removal,
which part is read, and the name the copy is kept under.

Every limit in the table above is a limit on **reading**. What a run holds after
it has read -- the renditions it has parsed, the graph it has built from the
metadata -- is not yet inside those limits, so a package can cost a run more
memory than the bytes it was allowed to read. That is an open limitation and
not a guarantee, written here so that it is not inferred from the rows above.

An unpacked container is a directory, and a directory can hold links, so there
the question is what this tool itself reads. Only what the container holds. A
name is resolved from the container's root downwards, one component at a time,
each link replaced by its own text where it stands and never a step outside,
and a name that a `..`, a `.` or a separator follows has to be a directory, or
the link leads nowhere -- on every system, though Windows would remove those by
their text and open something else -- so nothing out there is looked at to
decide -- not `stat`, not `readlink`. Four kinds of entry are named by S6 and
not opened: one that leads out, one written as an absolute path under neither
of the container's two names -- the one it was given and the one that resolves,
so a third spelling of the same place is reported rather than read -- one
passing through more links than a system will follow, and one pointing at
nothing. An absolute link under one of those names is walked like a relative
one. A name the listing does not hold is refused as the archive refuses it;
each read resolves the name again, so a file swapped after the listing for a
link that leads out is not read either, while one swapped for a link that stays
inside reads what it points at, as any link there does; and a directory the
check cannot list, or one holding an entry it cannot look up, refuses the
container rather than leaving part of it unlooked at. Both markers that make a
directory a container are found by name rather than by what they point at --
the directory a marker sits in is walked like any other name, and one that
leads out counts as the marker being there, for S6 to name -- so whether a file
somewhere else exists decides nothing about the report.

The same holds one layer up. Pointing at a directory searches it for packages,
and a `.iirds` name found there that leads out of the directory is refused by
name and not read; where the directory holds unpacked containers rather than
archives, a linked container is refused the same way. So is a subdirectory the
search cannot list, or a `.iirds` name in it the search cannot look up, named
as the argument was given; an unpacked container found there refuses what it
cannot read itself when it is opened, and the search asks no link what it
points at. The run exits 2 rather than checking less than it was asked to in
silence. A directory link found there is not searched through, and one that
leads out is named only when it sits directly in the directory and the search
finds no archive. The path named on the command line is followed wherever it
goes: that one is the operator's own choice.

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

Supported versions: the latest release. This project releases no fix for an
older one; a backport to a version you have frozen is professional support
(`SUPPORT.md`), not a release here. From the release after 0.7.1, a fix that
has to ship while main holds unreleased work is carried to the latest release's
own line and shipped as a patch there, as 0.6.1 to 0.6.3 were; the fix for
GHSA-qwv2-9vgj-vc2w was not, and shipped in 0.7.1 with the rest of that
release. For the single-file `.pyz`, upgrading
is copying one file.

## Advisories

From 0.6.1 on, a security fix that ships in a release has a GitHub security
advisory on this repository, naming the versions it reaches and the release
that fixes it. Security fixes in earlier releases -- this project's 0.4.2 and
the `iirds` library's 0.3.1 among them -- are recorded in their changelogs and
have no advisory.

- [GHSA-836f-9r66-gxcc](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-836f-9r66-gxcc):
  checking a directory could read files outside it and put parts of them in
  the report. `iirds-validate` 0.1.0 through 0.6.0, `iirds` and `iirds-sdk`
  0.5.0 through 0.6.0; fixed in 0.6.1.
- [GHSA-37j7-4w33-fr3w](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-37j7-4w33-fr3w):
  the content budget did not stop decompression. Renditions past the budget were
  still read in full before being refused, so a small archive could make one run
  decompress many times its budget. `iirds-validate` up to and including 0.6.1,
  `iirds` and `iirds-sdk` 0.5.0 through 0.6.1; fixed in 0.6.2.
- [GHSA-2p8x-2h66-4j7j](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-2p8x-2h66-4j7j):
  a bzip2- or lzma-compressed entry defeated every read limit. One bounded read
  could decompress the whole entry in memory, so a package of a few hundred bytes
  could exhaust the memory of the machine checking it. Same versions; fixed in
  0.6.2, which refuses such entries without opening them (S14).
- [GHSA-rf68-3wrj-h8jp](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-rf68-3wrj-h8jp):
  one entry was decompressed once per central-directory record that named it. A
  ZIP directory is a list of records rather than a set of names, and the check
  that asks whether an archive is damaged walked the records: an 11,890-byte
  archive with fifty records naming one 8 MiB entry made a run decompress
  419,431,868 bytes, and each repetition costs the sender a 46-byte record.
  `iirds-validate` up to and including 0.6.1, `iirds` and `iirds-sdk` 0.5.0
  through 0.6.1; fixed in 0.6.2, which walks the name table and reports the
  repetition (S15).
- [GHSA-ggjq-93h3-wfwj](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-ggjq-93h3-wfwj):
  one rendition nobody could decompress ended the content rules early. The rule
  that met it died, the cache it was filling was left truncated, and every
  content rule after it answered for a package it had seen part of -- while the
  report listed those rules among the ones it had checked. The verdict did not
  move; what was lost was the report's account of the other files.
  `iirds-validate` up to and including 0.6.2, `iirds` and `iirds-sdk` 0.5.0
  through 0.6.2; fixed in 0.6.3, which reports the read failure as a refusal
  (S16) and examines the rest.
- [GHSA-qwv2-9vgj-vc2w](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-qwv2-9vgj-vc2w):
  the search for a package's own ontology had no ceiling on what it read in
  total. Every entry under `META-INF/` that the standard does not name is read
  and parsed as RDF, each read was bounded per entry and nothing bounded their
  sum, and the constant meant to hold that sum was used by nothing. Measured: a
  524,395-byte archive carrying twenty 8 MiB entries made a run read back
  167,771,253 bytes and parse all of it, and the entry count is the sender's to
  choose. `iirds-validate` up to and including 0.6.3, `iirds` and `iirds-sdk`
  0.5.0 through 0.6.3; fixed in 0.7.1, where the scan stops at eight mebibytes
  and `S12` names the file it stopped on.
- [GHSA-gv27-g2mp-8ghv](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-gv27-g2mp-8ghv):
  an entry could be judged under a name its records do not give it. From
  Python 3.12, zipfile names an entry by an Info-ZIP Unicode Path extra field
  in the central directory where one holds, and libarchive names it by the one
  in the local header; the check compared only the names the two records'
  bytes spell, so an entry it judged under one name could reach another reader
  under another, one leading out of the package among them. `iirds-validate`
  0.1.0 through 0.7.1, `iirds` and `iirds-sdk` 0.5.0 through 0.7.1 -- for the
  directory's field when run on Python 3.12 or later, for the local header's
  on any interpreter; fixed in 0.7.2, where S10 holds every such field to its
  record's name and S6 checks every name an entry is read as.
- [GHSA-pj7w-78cj-j5h8](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-pj7w-78cj-j5h8):
  checking an unpacked container, or searching a directory, could look past
  it. The markers a container is recognised by were looked up through a link
  out of the directory, the listing and the search asked each link what it
  points at, and a link through a name that is not a directory was read as the
  file beside it. `iirds-validate` 0.1.0 through 0.7.1, `iirds` and
  `iirds-sdk` 0.5.0 through 0.7.1; fixed in 0.7.2, where each of these names
  is resolved inside the container and each entry is judged by itself rather
  than by what a link leads to.
- [GHSA-325m-q3mp-wx43](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-325m-q3mp-wx43):
  a directory that could not be read was left out without a word. A directory
  in an unpacked container that could be listed but not searched was checked
  without the files in it, and pointing at a directory of packages left out
  the ones in a subdirectory it could not read; the run passed on what it did
  find. `iirds-validate` 0.1.0 through 0.7.1, `iirds` and `iirds-sdk` 0.5.0
  through 0.7.1; fixed in 0.7.2, which refuses the container (S13) or the
  search (exit 2) and names what it could not read.
- [GHSA-8289-9w26-5w53](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-8289-9w26-5w53):
  the checks before the metadata parser read a document under the encoding it
  declared, while the parser reads it as UTF-8 whatever it declares; where the
  declaration made the two readings differ, a document the checks passed could
  declare XML entities for the parser to expand. `iirds` 0.3.2 through 0.7.2,
  `iirds-validate` and `iirds-sdk` 0.5.0 through 0.7.2; fixed in 0.7.3, where
  both checks also read the document as UTF-8.

- [GHSA-47q4-x239-rj3c](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-47q4-x239-rj3c):
  comparing a package's two metadata files, where it carries both, was a search
  whose time grew faster than the files wherever blank nodes looked alike -- a
  kilobyte of JSON-LD could hold a run for minutes. `iirds` 0.2.0 through 0.7.3,
  `iirds-validate` 0.1.0 through 0.7.3 and `iirds-sdk` 0.5.0 through 0.7.3; fixed
  in 0.7.4, where blank nodes that form trees are compared in one pass and the
  rest only up to eight of them.