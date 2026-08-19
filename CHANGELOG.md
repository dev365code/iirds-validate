# Changelog

## 0.1.0 — unreleased

First working version.

- `check` (conformance) and `lint` (interoperability) commands, JSON output,
  CI-friendly exit codes.
- Graph-based validation: RDF/XML and JSON-LD parse into the same graph, so
  results do not depend on how the metadata was serialised.
- 61 of the 157 catalogued rules implemented — 15/19 container, 46/135 schema.
- 8 interoperability rules with no counterpart in the specification.
- Fully offline: iiRDS 1.3 ontologies bundled verbatim, hash-verified, no
  network access at any point.
- A missing `iirds:iiRDSVersion` falls back to the newest version and is
  reported, instead of silently disabling every rule.
