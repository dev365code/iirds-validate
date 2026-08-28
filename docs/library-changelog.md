# Changelog of the `iirds` library, up to 0.3.2

The library shipped on its own as `iirds` 0.1.0 to 0.3.2, and this is its
history as it was published. From 0.5.0 it ships with the checker: what
changed in it since 0.3.2 is in the *library* sections of the 0.5.0 entry in
[CHANGELOG.md](../CHANGELOG.md), and later changes are recorded there.

## 0.3.2 — 2026-08-26

### Fixed

- **A document that described an entity declaration was refused for making
  one.** The guard matched the token anywhere in the bytes, and the grammar
  allows a declaration in one place only. Metadata that quotes the vocabulary
  it is written in -- in a CDATA section, in a comment -- was turned away. The
  question is now put to the parser, which is the thing that would do the
  expanding: it knows the encoding without being told and it knows where a
  declaration may sit. A doctype naming an external DTD passes, because
  nothing fetches it and so nothing can expand.

- **A decoded document could come back changed.** Removing the encoding
  declaration after a decode is right -- it would contradict the bytes -- but
  the pattern was not anchored to the front, and a declaration may only sit
  there. Where the real one named no encoding, the first match was in the
  body, so a passage quoting a declaration reached the graph with a piece
  missing. Reading is meant to be faithful; this was not.

## 0.3.1 — 2026-08-26

### Security

- **XML entity declarations could reach the parser in an encoding the guard
  did not read.** The refusal and the parser disagreed about what the bytes
  said. They are decided the same way now, before any guard reads them, and
  the gate is written as a property rather than a list of encodings: a parser
  that grows one turns the suite red until the guard follows it.

- **A JSON-LD `@context` could send the reader outside the package.** The
  guard covered some of the ways a context is named and not others. Refusal
  is positional now rather than lexical -- a string in context position is a
  reference and is refused, wherever it appears and whatever names it.

  Held by two gates, because an enumeration cannot assert its own
  completeness: each shape is pinned, and the suite runs with rdflib's
  context fetch sealed, so anything that would leave the package turns a test
  red whatever turns out to be responsible.


## 0.3.0 — 2026-08-25

### Added
- `source_of(graph, node)` / `Package.source_of(node)`: a Rendition's
  `iirds:source` resolved to the entry it names. The core normalisation
  (leading slash stripped, `./` and internal `../` collapsed) is the
  validator's reading verbatim; folding backslashes and refusing a path
  that escapes the package are the SDK's own added strictness (the
  validator does the equivalent one layer up, in its container check).
  Resolution deliberately does not judge existence.
- `Package.open(node)`: a readable stream over the resolved entry,
  raising when the node names nothing or names an absent entry.
- `write_metadata(graph, destination=None)`: metadata.rdf out,
  self-verified — the bytes are parsed back through the same guarded
  reader and compared isomorphically before being handed over.
  Byte-stable across repeated writes of the same Graph object, and
  documented as no more than that. Serialisation drops any base on the
  graph, so a subject built on `PACKAGE_BASE` is written as an absolute
  `rdf:about` (the whole ecosystem reads against that base anyway); a
  graph carrying genuinely relative IRIs writes them relative.

## 0.2.0 — 2026-08-24

The hardening release: `open()` now treats metadata as what it is —
untrusted input from a supplier — with the same guards, the same error
strings and the same merge semantics as
[iirds-validate](https://github.com/dev365code/iirds-validate), from
shared code the validator imports as its own next release.

### Changed
- **`Package.version` and `Package.variant` read the Package node only**
  (or a section-7 subclass of it). 0.1.0 scanned any subject carrying
  the property; a version literal on some other node is noise, not the
  declaration. Conformant packages — declaration on the Package node —
  are unaffected.
- `Package.graph` raises `IirdsError` when no metadata source could be
  read at all (hostile or unparsable), instead of escaping with a raw
  parser exception. Empty is what a sparse package looks like, so
  "unreadable" must not answer "empty".

### Added
- Query surface with section-7 semantics: `instances_of`,
  `is_instance`, `subclasses_of`, `label_of` — the subclass closure
  walks the package's own declarations (the 1.3 core declares no
  concrete subclasses, so this is the whole answer, not an
  approximation).
- `META-INF/metadata.jsonld` is read and merged beside `metadata.rdf`;
  isomorphic sources count once (blank nodes double under naive union),
  divergent sources still union. `metadata_sources`, `metadata_graphs`
  and `parse_errors` expose what parsed, which document said what, and
  what was refused.
- Hardening, ported from the validator: XML entity declarations
  refused; metadata above 64 MiB uncompressed refused before being
  read; a remote JSON-LD `@context` refused wherever it nests; byte
  order marks honoured (UTF-8/16/32).
- `parse_metadata()` and `merge_sources()` as standalone functions.
- The import set is pinned by test — rdflib and the standard library,
  nothing else — and CI runs the suite against rdflib 6.0.0 exactly,
  the floor `rdflib>=6` promises.

## 0.1.0 — 2026-08-21

First release: `open()`, `pack()` (mimetype first and stored,
byte-identical repacks), and the stewardship pledge — the name
transfers to the iiRDS Consortium on request.
