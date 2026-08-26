# Changelog

## 0.4.2 — unreleased

### Security

- **A JSON-LD `@context` could send the reader outside the package.** The
  refusal is the reader's and arrives with `iirds` 0.3.1; this release
  carries the reporting half — C16.2 stops calling a refused document
  invalid, SECURITY.md states the threat, and a version-gated test watches a
  package fail to reach anything outside its own container.

### Added

- **Three rules.** R4 reports an iiRDS/H party pointing at a vCard the package
  never describes — five MUSTs about naming an organisation deliberately stay
  quiet about that pointer so it does not arrive five times, and it used to be
  left to a rule outside the conformance run, so a handover package whose
  manufacturer, author and creator all pointed at nothing passed in silence.
  B9 reports a hazard statement with no signal word. B10 reports, as a
  warning, a hazard statement at caution, warning or danger level where no
  image is tagged as the safety alert symbol. 185 rules to 188.

### Changed

- **Rules about a class now see the subclasses a package declares**, where
  Appendix A says instances of that class need an IRI. Section 7 permits such
  a subclass and requires a consumer to process the instance as the parent, so
  a package could put an anonymous instance past a rule by naming its own
  type. Fifty-six rules changed population; the five whose classes the
  specification never asks for an IRI did not. M15.11a and M19.4 changed the
  same way. A package that passed 0.4.1 can report new findings for this
  reason.

- **M25 checks that a level closes**, not merely that the property is present:
  a last node pointing at something that is neither another directory node nor
  a terminator left the list open and passed. It also stops reporting the
  terminator itself when a package declares one.

- **The same package now produces the same report, every run.** It did not.
  A blank node has no identifier of its own -- the one it appears to have is
  minted afresh each time the file is read -- and three places let that reach
  the page: the fallback name for an unlabelled node, the digest meant to
  replace it, and rules that listed values or walked references in whatever
  order the store offered. One of the Consortium's own sample packages gave
  three different reports from three runs of 0.4.1, and two rules named a
  different real thing each time. A blank node is named from what it says
  now, nested nodes included, and every listing that reaches a report is
  ordered by that name. Details that mentioned a blank node will read
  differently from 0.4.1, and identically to each other.

### Fixed

- **One rule could produce a finding per element with nothing bounding the
  listing.** 20,000 repetitions of one violation in a 51 KB archive made
  17 MB of JSON and 143 MB resident. Findings now enter a report through
  one gateway that lists at most 100 per rule and counts all of them, so
  the summary, `ok` and the exit code are exactly what they were; the
  report and the JSON say how many were left out.

- The container boundary joins the parse boundary: an entry name whose bytes
  are not the encoding its flag declares raised out of `zipfile` and ended the
  run with a traceback. It is a C1 finding now, like every other way an
  archive can be unusable.
- A reader that breaks its contract no longer ends a run before any rule has
  looked at the package. This project declares a dependency floor rather than
  a pin, so it will be paired with readers it was never tested against.
- Eleven remedies named terms the standard does not have — six machinery
  classes spelled `iirds:` rather than `iirdsMch:`, `iirds:relates-to-Party`
  for `relates-to-party`, a handover property that does not exist, and a
  relation that never existed. A gate resolves every iiRDS term a remedy names.
- M2.6's remedy asked authors to write what its own shape rejects, reported
  from outside in this project's first issue. The constraint is unchanged and
  the open question is recorded in `docs/divergences.md`.
- C16.1, C16.2 and S3 stop describing the wrong failure: a refused document is
  not invalid syntax, and a rule that crashed is not a metadata parse error.

## 0.4.1 — 2026-08-25

- **The `iirds` dependency loses its upper bound** (`>=0.2.0,<0.3` →
  `>=0.2.0`). The cap was reflexive 0.x caution against a dependency
  this project authors, releases and tests in the same breath, and it
  contradicted the SDK's own published promise that what it publishes is
  intended not to break. Worse, it split one shared container layer in
  two: nobody could install this validator and the SDK's newer features
  together. An upper bound on a library is a prediction that pip cannot
  recover from when it turns out wrong; the honest moment to add one is
  when an incompatibility is known, not before. Only 0.2-era API is used
  here, the pair is exercised on every push, and CI still runs the floor
  (`iirds==0.2.0`) exactly. No behaviour changes.

## 0.4.0 — 2026-08-24

- **The container layer is shared with the [`iirds`](https://github.com/dev365code/iirds)
  SDK, in both directions.** `pack()` moved to the SDK (same bytes, same
  refusals — the eleven packing tests pass against it unedited), and the
  metadata reader — the hardening guards, the parser, the
  isomorphic-once merge — is imported back from it, so the SDK's answer
  can never contradict the validator's. The seam is pinned by object
  identity, not equality: a fork of either side fails loudly. Two
  runtime dependencies now, both pure Python: rdflib and
  `iirds>=0.2.0,<0.3`, each exercised at its floor in CI.
- **Both size gates were disabled for directory packages.**
  `DirectoryPackage.info()` answered `None`, so a 64 MiB+ document that
  an archive refuses was read and parsed whole in the
  check-before-you-zip form — and neither gate, in either form, had
  ever been observed firing by any test. Four tests now watch both;
  this entry records the silent pass.
- The section-7 class closure's data half is now literally the SDK's
  `subclasses_of`: "the SDK's answer is a subset of the validator's"
  became a property of the code rather than a claim about it.
- The `.pyz` build script reads its bundle list from `pyproject.toml`
  instead of hard-coding it, and the smoke test proves self-containment
  for every bundled dependency (887 KB with the SDK inside).
- The CLI's pack error wording is owned by the CLI: the SDK speaks API
  ("pass overwrite=True"), the terminal speaks flags ("pass
  --overwrite"), and the boundary translates.
- **The offline claim became a gate**: CI seals the network at the
  socket layer and runs every rule against a real container; "touches
  no network" is now enforced, not asserted.
- Four spec links on dcterms-backed rules stopped quoting a sentence
  about the wrong class.

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
  either side would hide the evidence. Found before release, where the
  single-file SHACL shapes were the side that was right.
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

The evidence lives in the repository rather than in this file: the regression
tests cover every defect the apparatus caught in its own rules — including a
rule that was backwards from the day it was written and one no input could
reach — and
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
