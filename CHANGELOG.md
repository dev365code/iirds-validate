# Changelog

## 0.3.0 — 2026-08-22

- **The five deferred iiRDS/H MUSTs land as shapes** (M15.7b, M15.7d,
  M15.8–M15.10): the named-party chains, softenings included — a party
  whose vCard the package does not describe passes (the dangling
  reference is L1's finding, once), a described-but-nameless vCard fails.
  138 shapes; the deferred bucket is down to the six long-exemption lint
  rules. The differential gate caught a SPARQL scoping trap on the way in
  (a UNION branch evaluates independently, so a filter-only branch saw
  its variable unbound) — recorded in the generator's comments.
- The `ivs:`/`ivm:` namespaces resolve through w3id.org permalinks
  (perma-id/w3id.org#6584).
- **A package shipping both metadata serialisations no longer double-counts
  its blank nodes**: two isomorphic sources now merge as one graph, so an
  inline IdentityDomain is one domain, not "2 domains". Genuinely divergent
  sources still union — their disagreement is L9's finding, and hiding
  either side would hide the evidence. Found by the round-4 adversarial
  pass, where the single-file SHACL shapes were the side that was right.
- **`--fragment`**: validate a bare metadata file — a spec example, a
  snippet under an editor's hands — inside a throwaway container, with the
  four rules a fragment cannot satisfy (M3, M4, L2, S6) suspended and named
  in a note. The wrapping this project offered the specification's CI in
  iirds-consortium/specification#34, shipped as a flag.

## 0.2.0 — 2026-08-21

- **SHACL shapes** (`shapes/`): 133 shapes for iiRDS 1.3 — the
  language-neutral encoding of the rules, generated from the same sources,
  differentially tested against the Python validator — fire-set equality
  over the entire reference corpus, severity equality on every mutant
  and provocation fixture — with a closing check that every emitted shape fires somewhere
  in the suite. Single-file
  `iirds-complete.ttl` / `iirds-handover-complete.ttl` forms for the pySHACL
  command line; remedy text, severity, spec link, `ivm:ruleId` and
  `ivm:versions` on every shape, node and property shapes alike; graph-global
  checks name the offending node in `sh:value` where one exists ("no
  package is declared" has none — that one result points at the shape's
  own IRI, the engine's convention for a nodeless failure). The 52 rules without a shape
  are accounted for by category in the README and manifest — 38 that no RDF
  graph can express, 11 deferred (five iiRDS/H MUSTs among them, named), 2
  out of edition, 1 no-op. Answers iirds-consortium/models#24.
- **iiRDS §7 fixes in the validator itself, found by the shapes gate**:
  instances typed with a package-declared subclass of an iiRDS class are now
  seen by every rule — including two (M15.5, M22.2) that had private
  exact-typing tests bypassing the shared closure. SHACL's `sh:targetClass`
  had these semantics by definition; the differential gate refused to let
  the two encodings differ, and the Python side was the one corrected. The
  seventeen nodekind rules M78–M94 also shed titles that were accidentally
  the ontology's description prose, for constraint-describing ones.
- Interpretation choices, where prose underdetermines a rule, remain
  documented in [docs/divergences.md](docs/divergences.md).
- pySHACL rides as a dev-only extra (`.[shacl]`); the runtime stays
  rdflib-only and the `.pyz` is unchanged.

## 0.1.0 — 2026-08-20

First public release.

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
- Profile-aware severity: the Appendix B content rules are errors under
  iiRDS/A and warnings elsewhere, because outside A the standard permits any
  content and "which files count as iiRDS XHTML5" is this project's reading.
- iiRDS 1.0, 1.0.1, 1.1, 1.2, 1.3; unrestricted, A and H profiles. An
  undeclared version falls back to the newest *and says so*; an unpublished
  version or profile is a finding, not a silent default.

### What was found while building it

The evidence lives in the repository rather than in this file:
[docs/findings.md](docs/findings.md) is the register of every defect the
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
