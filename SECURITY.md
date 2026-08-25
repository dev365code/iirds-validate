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
| Oversized inputs | metadata and content are read to 64 MiB and no further, and refused there. The limit is on what comes back, not on the size the archive declares -- that field belongs to whoever built it, and a gate reading it is a gate the sender sets | `tests/test_content_hostile.py`, `tests/test_size_gates.py` |
| Metadata that sends the reader somewhere else: a JSON-LD `@context` naming a URL makes the parser phone home, and a `@context` naming no scheme at all is worse — it is resolved against the directory the tool was run from and read off your disk, with no socket involved | every context reference is refused, whichever keyword names it (`@context` itself, an `@import`, a scoped context on a term) and whether or not it carries a scheme. Inside a plant network the first is a supplier choosing which host a machine behind the firewall reaches; the second is a supplier choosing which of your files it reads. **The refusal lives in the `iirds` reader and arrives with the release that carries it — this project's declared floor decides which packages of yours are covered.** | `tests/test_offline.py`, where a package naming a context by bare name is watched failing to read a decoy out of the working directory -- gated on the reader's version, because the refusal is the reader's and arrives with the release that carries it. The reader's own suite pins each construct and runs with rdflib's single context-fetch function sealed, so a construct nobody has enumerated turns it red too. |
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
most serious bug this project can have; the register in
the defect register shows that such reports get fixed, tested
and credited rather than argued with.

Supported versions: the latest release. There is no backporting; upgrading is
copying one file.
