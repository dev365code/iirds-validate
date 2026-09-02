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
| Path traversal ("zip-slip"): entries named `../…` escape the extraction directory | S6 reports any entry that leaves the container | `tests/test_system_and_container.py` |
| Entity-expansion bombs in metadata or content (a 400-byte file that expands without bound) | any XML declaring entities is refused outright, and the refusal is itself a finding | `tests/test_content_hostile.py`, `tests/test_silent_pass.py` |
| An archive whose two records of an entry disagree: the central directory, which `zipfile` and this tool read, describes one file, and the local file header, which a streaming consumer reads, describes another -- a package blessed on a benign prefix while a stream receives the rest | S10 compares the two records for every entry -- name, method, the flags a reader acts on, crc-32 and sizes, from the local header or from the data descriptor it defers to -- and reports data that runs into the next entry | `tests/test_header_agreement.py`, one field of one record changed per fixture, and the archives stream writers and ZIP64 produce as the negatives |
| Oversized inputs | metadata and content are read to 64 MiB and no further, and refused there. The limit is on what comes back, not on the size the archive declares -- that field belongs to whoever built it, and a gate reading it is a gate the sender sets | `tests/test_content_hostile.py`, `tests/test_size_gates.py` |
| Metadata that sends the reader somewhere else: a JSON-LD `@context` can point outside the package, and a package is something a supplier hands you | every context reference is refused, whichever keyword names it and whether or not it carries a scheme. Inside a plant network that is a supplier choosing where a machine behind the firewall goes looking. **The refusal lives in the `iirds` reader and arrives with the release that carries it — this project's declared floor decides which packages of yours are covered.** | `tests/test_offline.py`, gated on the reader's version. The reader's own suite pins each construct and runs with rdflib's single context-fetch function sealed, so a construct nobody has enumerated turns it red too. |
| Supply-chain drift in what this tool itself bundles | the ontologies and the vendored corpus are verified against recorded SHA-256 digests on every run of the suite; the `.pyz` is bit-for-bit reproducible so the hash on a release page is the hash of the file carried across the air gap | `iirds_validate.ontology --verify`, `tests/test_corpus_integrity.py`, `tools/build_zipapp.py` |
| Anything at run time needing a network | there is no network code path at all; validation is pure local computation | `tests/test_offline.py` |

The tool never executes content, never extracts archives to disk, and reads
entries one at a time in memory.

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
