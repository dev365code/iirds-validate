# Changelog

## 0.1.0 — unreleased

First version. Everything below describes the state at the first public tag.

### What it does

- `check` (conformance), `lint` (interoperability), `all`, `pack`, `rules`;
  JSON output; CI-friendly exit codes (`0` clean, warnings alone stay `0`
  unless `-W`; `1` errors; `2` could not run).
- **185 rules**: all 157 of the reference catalogue, plus 28 of this project's
  own — 8 content rules for iiRDS XHTML5 (Appendix B, checked by no other
  tool), 12 interoperability rules, 5 system guards, and 3 rules (R1–R3) for
  specification requirements the catalogue has no identifier for.
- Graph-based: RDF/XML and JSON-LD parse into one graph, so results do not
  depend on how the metadata was serialised. Deterministic output, ordered
  for a reader: causes first, consequences last.
- Every finding carries a remedy — what to change, where it goes, and what a
  consumer loses without it.
- Fully offline: iiRDS 1.0–1.3 term inventories and the 1.3 ontologies
  bundled verbatim and hash-verified; remote JSON-LD contexts refused; XML
  entity declarations refused; hostile archives (zip-slip, oversized
  metadata) rejected. Ships as a reproducible single-file `.pyz`.
- iiRDS 1.0, 1.0.1, 1.1, 1.2, 1.3; unrestricted, A and H profiles. An
  undeclared version falls back to the newest *and says so*; an unpublished
  version or profile is a finding, not a silent default.

### What was found while building it

The evidence lives in the repository rather than in this file:
the defect register is the register of every defect the
apparatus caught in its own rules — including a rule that was backwards from
the day it was written and one no input could reach — and
[docs/divergences.md](docs/divergences.md) records every disagreement with the
reference implementation, with the specification text beside each. Seven of
the catalogue's version arrays were corrected against the Consortium's own
published schemas. Both of the Consortium's official sample packages fail
their own specification; every error this tool reports on them survived
verification against the 1.0 text they declare.

### Known limits

Coverage of the standard itself is measured and small: the specification
states 314 absolute obligations, and the mapping from those to rules has only
begun (`tools/requirement_coverage.py` prints the honest number). "No
findings" is not "certified conformant" — nothing can certify that, and this
tool says so rather than implying otherwise.
