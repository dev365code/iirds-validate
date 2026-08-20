# What this is, what it is not, and where everything lives

One page, because the repository has grown a verification apparatus twice the
size of the thing being verified, and that is easy to mistake for the project
being complicated. It is not. The validator is 2,069 lines of code across 244
functions with a median length of five, and no duplicated block anywhere in it.
What is large is the evidence, and the evidence is the product.

## The purpose

> A person building an iiRDS package on an air-gapped network points at one
> path and learns two things, with no internet and nothing installed: **does it
> conform**, and **will anyone else be able to read it**.

Everything here should be traceable to that sentence. Where it is not, it is
either a mistake or an unstated goal, and both are worth catching.

Three properties follow, and they are the ones to defend when a change is
proposed:

- **Offline.** Not "works offline too" — offline is the reason the project
  exists. The only iiRDS validator in the world is a web application, and the
  industry that most needs one does not put its documentation on the internet.
- **Nothing installed.** A `.pyz` and a Python. Not pip, not an index, not a
  virtual environment, not rights to create one.
- **Reads the graph, never the XML tree.** RDF/XML has many legal
  serialisations of the same graph. A validator that walks the tree sees one of
  them, which is how a package can satisfy every rule and still be rejected.

## What it is not

Written down because each of these was, at some point, about to be built.

- **Not a certifier.** There is no iiRDS conformance authority, and that is not
  a vacancy this project may fill. It reports findings. It does not attest,
  certify, or issue a record that a package conforms — and could not honestly,
  while the share of the specification it checks is unmeasured. See "the
  unresolved list" below.
- **Not an authoring tool.** `iirdsv pack` exists because five container
  requirements cannot be assessed on an unpacked directory, and for no other
  reason. It is subordinate to checking, not a second product.
- **Not a fixer.** No `--fix`. Deciding what a package was meant to say is the
  author's job; this reports what it does say — and says, for every rule, what
  change would settle it. Naming the remedy is part of reporting. Applying it
  is not.
- **Not a CCMS integration.** Not now.

## Where things live

| | |
|---|---|
| `src/iirds_validate/rules/` | the 180 rules — `container.py` C\*, `schema.py` M\*, `system.py` S\*, `content.py` B\*, `lint.py` L\*, `schema_tables.py` generated |
| `src/iirds_validate/context.py` | parses metadata into **one graph**; every rule reads this and nothing else |
| `src/iirds_validate/terms.py` | every iiRDS term, in one place, checked against the ontology by a test |
| `src/iirds_validate/data/` | what ships: the rule catalogue and the vendored ontologies |
| `tests/corpus/plusmeta/` | the reference corpus, verbatim and hashed — the only external check |
| `tools/` | nothing a user runs. Extraction, cross-validation, vendoring, packaging |
| `docs/agreement.json` | per-pair agreement with the reference; CI fails if it moves |
| `docs/divergences.md` | every place this project and the reference differ, and why |

## How this project knows it is right

There are four ways a validator can be wrong, and no single instrument finds
more than two of them. This is the whole reason the apparatus is large.

| | **1** a requirement with no rule | **2** a rule that misreads its sentence | **3** fires on a conformant package | **4** correct but never fires |
|---|---|---|---|---|
| The requirement map *(half built: `docs/requirements.json` enumerates, nothing maps yet)* | **only method** | review aid | — | — |
| Mutation testing *(partial: the generated table, the cardinality family, iiRDS/H)* | — | **cannot, by construction** | strong | **only method** |
| The reference corpus | — | partial | strong | partial |
| tekom's own samples and examples *(`tests/test_spec_examples.py`)* | — | one direction only | **strong** | — |

Two things about that table are worth internalising.

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

## The unresolved list

Kept short and kept honest. If one of these is quietly dropped, something has
gone wrong.

1. **Coverage of the standard is unmeasured.** 157 of 157 catalogued rules is
   coverage of plusmeta's catalogue, not of iiRDS. The denominator now exists —
   314 absolute obligations, derived in `docs/requirements.json` — but nothing
   maps them to rules yet, so the numerator does not. Until it does, "no
   findings" must never be presented as "conformant".
2. **Four rule/fixture pairs are unresolved**, each with a row in
   `docs/divergences.md` saying why.
3. **Three Appendix B rules rest on readings the specification does not
   settle**, also recorded there. They are the questions to put to tekom.
4. **The catalogue couples this project to plusmeta.** Rule ids, priorities,
   version arrays and spec links all come from their file. The version arrays
   are now checked against the vocabulary each release actually carried, which
   found five wrong; the rest of the coupling stands. `THIRD_PARTY.md` records
   the policy; the requirement map is the way out.
5. **iiRDS 1.0 and 1.0.1 have never met a real package**, and have no tagged
   ontology either, so the version check above cannot reach them. Self-made
   fixtures are circular.

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
