# What this is, what it is not, and where everything lives

One page, because the repository has grown a verification apparatus larger
than the thing being verified, and that is easy to mistake for the project
being complicated. It is not: the validator itself is a few thousand lines of
short functions. What is large is the evidence, and the evidence is the product.

## The purpose

> A person building an iiRDS package on an air-gapped network points at one
> path and learns two things, with no internet and nothing installed: **does it
> conform**, and **will anyone else be able to read it**.

Everything here should be traceable to that sentence. Where it is not, it is
either a mistake or an unstated goal, and both are worth catching.

Three properties follow, and they are the ones to defend when a change is
proposed:

- **Offline.** Not "works offline too" — offline is the reason the project
  exists. The validation tool the Consortium's own site points at runs in a web
  page, and the purpose above is a machine with no internet. Whether some other offline validator exists is not
  something this project has surveyed, so that is not the claim here; the
  claim is about the route a reader is most likely to be sent down.
- **Nothing installed.** A `.pyz` and a Python. Not pip, not an index, not a
  virtual environment, not rights to create one.
- **Reads the graph, never the XML tree.** RDF/XML has many legal
  serialisations of the same graph. A validator that walks the tree sees one of
  them, which is how a package can satisfy every rule and still be rejected.

## What it is not

Written down so that none of these gets built by drift.

- **Not a certifier.** There is no iiRDS conformance authority, and that is not
  a vacancy this project may fill. It reports findings. It does not attest,
  certify, or issue a record that a package conforms — and could not honestly,
  while the share of the specification it checks is only partly measured:
  "the unresolved list" below gives the share that is mapped, and the rest is
  unmapped rather than known to be unchecked.
- **Not an authoring tool.** `iirds pack` exists because the requirements about
  the ZIP archive itself -- the ones an unpacked check names -- cannot be
  assessed on a directory; the same writer stages what `check --fragment`
  checks, and the `iirds` library offers it as its writer. It is subordinate to checking, not a second product.
- **Not a fixer.** No `--fix`. Deciding what a package was meant to say is the
  author's job; this reports what it does say — and says, for every rule, what
  change would settle it. Naming the remedy is part of reporting. Applying it
  is not.
- **Not a CCMS integration.** Not now.
- **Not a counter of every repeat.** Where a JSON-LD file's graphs hold nodes
  without names that form no tree, or one deeper than forty, and one graph could
  repeat another, L9 does not compare the metadata files, and the report's
  notes say so.

## Where things live

| | |
|---|---|
| `src/iirds_validate/rules/` | the rules — `container.py` C\*, `schema.py` M\*, `system.py` S\*, `content.py` B\*, `lint.py` L\*, `requirements.py` R\*, `schema_tables.py` generated |
| `docs/requirements.json` | what the standard requires, enumerated from the specification |
| `src/iirds_validate/context.py` | parses metadata into **one graph**, which every metadata rule reads instead of the XML; container, system and content rules read the archive and its files |
| `src/iirds_validate/terms.py` | the iiRDS terms the hand-written rules name, checked against the ontology by a test; the table-driven rules in `src/iirds_validate/rules/schema_tables.py` name theirs in its tables, which `tests/test_schema_tables.py` checks against the ontology too, and three hand-written rules (R1, R2, L16) build theirs where they use them |
| `src/iirds_validate/data/` | what ships: the rule catalogue and the vendored ontologies |
| `src/iirds/` | the container layer the checker is built on — open a package, read its metadata as a graph, write a conformant container — shipped in the same distribution and never importing the checker |
| `tests/corpus/plusmeta/` | the reference corpus, verbatim and hashed — the one external check that ships with the repository and runs in CI; the Consortium's sample packages are checked by `tests/test_official_samples.py` where they are supplied |
| `tools/` | development and release machinery: extraction, cross-validation, vendoring, and the `.pyz` build a user may run once |
| `docs/agreement.json` | per-pair agreement with the reference; CI fails if it moves |
| `docs/silence.json` | why this validator is silent on each pair the reference reports; CI fails if it moves |
| `docs/divergences.md` | where this project reads a rule both tools have differently from the reference, and why -- and the argument for some of the rules only this project has |
| `docs/what-it-catches.md` | cases that each show the finding they are about, and a pair that draws none; under each `iirds check` is what it printed — written by `tools/gen_what_it_catches.py`, so a case whose verdict moves stops the build rather than going stale on the page |

## How this project knows it is right

There are four ways a validator can be wrong, and no single instrument finds
all four. This is the whole reason the apparatus is large.

| | **1** a requirement with no rule | **2** a rule that misreads its sentence | **3** fires on a conformant package | **4** correct but never fires |
|---|---|---|---|---|
| The requirement map *(part built: `docs/requirements.json` enumerates, and `covers=` maps part of it)* | **only method** | review aid | — | — |
| Mutation testing *(partial: the generated table, the cardinality family, iiRDS/H)* | — | **cannot, by construction** | strong | strong |
| The reference corpus | — | partial | strong | partial |
| tekom's own samples and examples *(`tests/test_spec_examples.py`)* | — | one direction only | **strong** | — |

Two things about that table are worth internalising.

The SHACL differential gate is another instrument, and it hunts a fifth
failure mode the table above has no column for: **translation errors** —
places where a second encoding of the same reading says something different.
It caught an inverted shape on its own first run.

**Mutation testing cannot detect a misreading.** The mutations are derived from
our own reading, so the mutant and the rule are two encodings of one belief;
their agreement carries no information about whether the belief is right. Its
value is in the other assertions — that the unmutated package comes back clean,
and that no unexpected rule fires.

The specification's examples are the sharpest of these and cost the least: they
are conformant material written by the people who wrote the requirements, so a
finding on one means a rule is too broad. That has now happened four times —
B4, M17/M18, M78–M93, and M30, which contradicted L5 outright and which the
reference corpus could not have found, because fixing it moved no agreement
figure at all.

**Failure mode 2 is the least covered, and cannot be closed by one reader.**
That is not a gap in the plan; it is why `docs/divergences.md` exists.
Publishing a reading is the only way a single author can make it refutable.

Whether that apparatus earns its size is answered by the changelog and the
regression tests, which record every defect it has caught and how.

## The unresolved list

Kept short and kept honest. If one of these is quietly dropped, something has
gone wrong.

1. **Coverage of the standard is 172 of 280.** 137 of the 172 are held by a
   package. The second number is the one to weigh, and it is the smaller one
   for a reason worth stating plainly: a `covers=` claim used to be made by
   reading a sentence and a rule side by side and judging them to be about the
   same thing. Ten claims made that way turned out to be wrong — a sentence
   asking for a `vcard:Organization` claimed by rules that deliberately did
   not check the class, two sentences naming a class and a property claimed by
   rules that counted the property, a conditional obligation claimed by a rule
   triggering on a different condition, a sentence about what a file contains
   claimed by a rule that asks whether the file parses, and one claimed over a
   paragraph of `docs/divergences.md` that said in those words that it must
   not be. Five were withdrawn, five were earned by fixing the rule or by
   giving the sentence to a rule that could already see it. An eleventh claim
   had been withdrawn and should not have been: `iirds:RangeSelector` is
   exempt from M13.1 and M13.2 because the specification's own Example 13 is
   a range selector carrying neither property, and the two fragment selectors
   it points at carry both — which those rules do check. What separates the
   groups is not a better reading; it is that somebody built the package that
   breaks the sentence and watched what happened.

   So the criterion is written down, and it is one sentence: **a rule covers
   an obligation when every package violating that obligation's sentence is
   reported by that rule or by another rule claiming the same id.** Reporting
   more than the sentence asks does not disqualify a claim; reporting less
   does, and a documented divergence that narrows a check withdraws the claim
   with it — keeping both is exactly how a documented exemption becomes an
   undocumented hole. `tests/test_covers_is_earned.py` holds the criterion,
   names the 137 claims a package stands behind, and names the other 35 in a
   list called UNAUDITED. Every one of those 35 may be perfectly good; none
   is *known* to be, and the ten that were not looked just like them.

   **A claim says a violation is reported. It does not say the package
   fails.** Ten of the 172 are appendix B's obligations about iiRDS XHTML5
   content, claimed by content rules alone, and outside profile iiRDS/A the runner demotes content findings to
   warnings — so a package breaching one of those ten is reported, prints
   `PASS` and exits 0 -- except where no content rule got a parsed
   document for the file at all, the container having refused to hand it over
   or this tool having refused to parse it, which `ERROR S16` reports as the
   run's own business rather than the profile's. With `-W` it prints `FAIL` and exits 1: that gate is the
   caller's policy rather than the standard's, and the report records which one
   it was judged by. The demotion is deliberate and
   argued under "Content rules" in `docs/divergences.md`. It is repeated here
   because the coverage figure is the sentence a reader is most likely to
   quote out of this page, and "checked" and "enforced" are not the same word.

   The iiRDS XHTML5 content rules look at the files the metadata declares as XHTML renditions, and —
   in an iiRDS/H package — the content list. The second half of that sentence
   is new. Section 8.3.1.1 forbids referencing the content list in the
   metadata, so in a package that obeys it the content list is never a
   declared rendition, and for as long as the population was "what the
   metadata declares" these rules had never looked at it there: a content list built from scripts, forms and iframes drew no content
   finding at all. The prohibition made the blind spot.

   Some detail on the denominator. It is derived in
   `docs/requirements.json`; the parse finds 314 absolute obligations and the
   same file names why 34 of those are not further obligations — four are
   the keywords named in the sentence that defines them, which no package can
   satisfy or breach, and thirty are one obligation counted twice, appendix A
   stating each property's cardinality in the class's own table and again in
   the overview table. The figure was 314 until those were derived rather
   than assumed; the numerator is the union of the `covers=`
   declarations on the rules, printed by `tools/requirement_coverage.py`. The
   figure is small because the mapping is only part done, not because the
   rules check almost nothing — 157 catalogued rules do a great deal that is
   simply not yet mapped to a requirement id. Which is the point of measuring
   it while it is embarrassing: a number that starts honest can be watched.
   "157 of 157" was never embarrassing and was never coverage of the standard.
   Until this rises, "no findings" must never be presented as "conformant".
   One claim was withdrawn while the map was being read against the
   specification: C16.2 said it checked "If metadata is provided in the JSON-LD
   1.1 syntax, the META-INF directory MUST contain the file metadata.jsonld",
   and it does not — it asks whether an iiRDS/H package has that file and
   whether the file parses. A package carrying JSON-LD metadata at
   `META-INF/metadata.json` was built and run: nothing reads it as metadata
   and nothing reports it. The obligation is named as a gap in
   `tests/test_requirement_coverage.py` with what it would take, which is a
   rule about the other files in META-INF — and section 5.1.1 recommends that
   consumers ignore those, so the reading wants settling before the rule.
   L12's claim on "file names ... MUST be unique within their parent
   directories" went with it: that sentence begins "File names are
   case-sensitive", which is the thing L12 reports, and C15 holds the
   obligation itself.

   Three obligations sit outside the numerator with a reason rather than a
   gap. Two are addressed to reading applications rather than to packages: no
   artefact can satisfy or breach them. The third — a nested package must not
   carry metadata about the outer one — is about the package, and a validator
   holding one container cannot decide it. Its antecedent is "a nested iiRDS
   package", and §6.2 says a conformant package's own instance is not a member
   of another package, so a document that declares itself nested is either the
   child breaching that sentence or a parent describing its child; the
   metadata does not distinguish them. Other sentences weigh without settling
   it — §6.3 says the enclosing package is the subject of no rendition, which
   is the rule M8 — and so does the archive.

   Twenty-six more are the word inside a vocabulary table. Appendix A describes
   each term in a "Definition:" and a "Description:" cell, and the
   specification's own markup calls a word inside twenty-nine of those an RFC
   2119 keyword: "Physical items **REQUIRED** for the running of a
   manufacturing production", "period of time **REQUIRED** for a specific
   task", "documentation that the supplier **SHALL** provide to the purchaser
   according to the purchase order". Twenty-six describe a thing in the world
   or bind somebody in it, and no container can satisfy or breach one. They
   stay in the denominator — the specification marks them, and dropping them
   would be this project deciding the standard is wrong about its own markup —
   but the report names them rather than leaving them in the remainder.

   The other three of the twenty-nine say something about the metadata and stay
   where the work is: the range-selector sentence, stated once per property,
   and §6.8.4's classification-domain sentence restated in the appendix. Both
   sides are listed by name, because the first attempt drew the line at the
   cell's label and split one term's two adjacent rows.

   All three lists are in the source and all three are gated; "hard to check"
   is on none of them.
2. **Four rule/fixture pairs are unresolved**, each with a row in
   `docs/divergences.md` saying why.
3. **Two rules rest on readings the specification does not
   settle**: one name the vocabulary does not define
   that the reference corpus uses in fifty-one files (L13, recorded there too), and whether a
   name from a later edition than the package declares is a defect or a
   warning (L15 says warning). They are the questions to put to tekom.
   Another used to sit beside them on a false premise -- that iiRDS never
   requires a safety alert symbol in terms. It does, in 1.0 and 1.3 alike, and
   B10 reports a hazard statement in which no picture is tagged as one; what remains a reading of ours there is the
   exemption for NOTICE, which reports less rather than more.
4. **The catalogue couples this project to plusmeta.** For the catalogue's rules,
   ids and priorities come from their file, and so do version arrays and spec
   links except where a rule overrides them. The version arrays
   are now checked against the vocabulary each release actually carried, which
   found five wrong; the rest of the coupling stands. `THIRD_PARTY.md` records
   the policy; the requirement map is the way out.
5. ~~iiRDS 1.0 has never met a real package~~ **Closed**: the Consortium's
   own sample packages declare 1.0 and were validated on 2026-08-20 — both
   fail their own specification, every error verified against the 1.0 text
   ([divergences.md](divergences.md)). Their schemas now feed the version
   inventory too, so no edition's vocabulary is unchecked. **1.0.1 still has
   not**: no real package declaring it has been validated.

6. ~~The archive's own index is taken at its word~~ **Closed**: S10 reads
   every entry's local file header where the central directory says it is
   and reports the entry where the two describe different files -- name,
   as each record's bit 11 reads it and as its bytes spell it, method, the
   flags a reader acts on, checksum and sizes, and data that runs into the
   next entry. The extra fields and timestamps writers put in the two
   records differ legitimately and are not compared; a Unicode Path field,
   which a reader takes the name from, is held to its own record's name.
   Nothing in the
   specification addresses the case; a consumer reading the archive as a
   stream does.

## Checking any of this yourself

Nothing above is asserted where it could be run.

```sh
make check      # everything CI runs: lint, generated tables, corpus, tests, equivalence
make corpus     # the reference fixtures are still upstream's bytes, and agreement has not moved
```

If a claim in this repository cannot be re-derived by someone who is not us,
it is not evidence, and it should be deleted or made checkable. That standard
is the reason for the size of `tools/`, and it is not negotiable — a validator
asking to be trusted about other people's packages has to be able to show its
own work.
