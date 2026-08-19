# Changelog

## 0.1.0 — unreleased

First working version.

- `check` (conformance) and `lint` (interoperability) commands, JSON output,
  CI-friendly exit codes.
- Graph-based validation: RDF/XML and JSON-LD parse into the same graph, so
  results do not depend on how the metadata was serialised.
- 119 of the 157 catalogued rules implemented — 15/19 container, 104/135 schema.
- 8 interoperability rules with no counterpart in the specification.
- Fully offline: iiRDS 1.3 ontologies bundled verbatim, hash-verified, no
  network access at any point.
- A missing `iirds:iiRDSVersion` falls back to the newest version and is
  reported, instead of silently disabling every rule.

### Fixed before release

Three ways this tool did the thing it criticises the alternative for —
reporting a clean package when its rules had not run — found in review and
each now pinned by a test in `tests/test_silent_pass.py`:

- A corrupt `META-INF/metadata.jsonld` in an ordinary 1.3 package was parsed,
  failed, and discarded: `C16.2` was gated to the handover profile, where the
  file is *mandatory*, but the file is *permitted* anywhere from 1.3.
- `iirds lint` on a package whose metadata did not parse reported no findings
  and exited 0. Container rules do not run under `lint`, so nothing was left to
  notice the graph was empty; the report said so in a note, and notes do not
  affect the exit status.
- A 600-byte `metadata.rdf` of nested XML entities occupied the parser
  indefinitely. Metadata declaring entities is now refused, and metadata above
  64 MiB uncompressed is rejected before it is read.

And three defects that produced wrong answers:

- `L4` walked the navigation structure recursively. `iirds:has-next-sibling` is
  a linked list, so a 1000-entry table of contents — an ordinary manual —
  exhausted the stack and was reported as a MUST violation naming a Python
  exception. Now iterative, sharing edge traversal with `L3`.
- `L2` used `str.lstrip("./")`, which strips a character set rather than a
  prefix, so any path whose first segment began with a dot was reported as a
  missing content file.
- The `L*` rules carried a private copy of the version list, so adding a future
  iiRDS version to `model.VERSIONS` would have stopped all of them applying to
  it, silently.

Also: the ZIP handle is now closed, `terms.py` takes one type-filtered snapshot
instead of two positional ones (a term added below the first was never checked
by its own guard test), a missing file exits 2 rather than 1, and the JSON
report carries `schemaVersion` and `validatedAgainst`.
