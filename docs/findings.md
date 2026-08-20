# What the apparatus has caught

This repository carries twice as much test and tool code as validator, and the
fair question about that is whether it earns its keep. This is the evidence:
every defect found in this project *by* this project, and which instrument
found it.

Read as an argument, it says one thing repeatedly. **Almost nothing here was
found by reading the code.** It was found by making a rule fire, by comparing
one enumeration against another, or by running material somebody else wrote.
Each row is a defect that a passing test suite did not notice.

## The instruments, ranked by what they caught

| instrument | found | the kind of thing only it finds |
|---|---:|---|
| Making every rule fire once | 6 | rules that are dead, unreachable, or the inverse of their title |
| Enumerating the standard independently | 3 | requirements nothing covers, and denominators that count the wrong thing |
| Writing the *second* half of a test | 4 | assertions that pass on every input, including empty ones |
| The specification's own examples | 1 | rules too broad, at the authority of the people who wrote the requirement |
| Cross-validating against another tool | 2 | disagreements neither side can settle alone |
| Auditing the process itself | 3 | gates that exist in one place and not the other |
| Reading the code | 3 | pinning mistakes, and claims that outran what was implemented |

## The findings

### Rules that could not do their job

| | what was wrong | how it surfaced |
|---|---|---|
| **S8** | Compared entry count against the ZIP32 limit, then inferred ZIP64 from per-entry offsets — so it failed every correctly built 70,000-entry archive and could never fire on a defective one. Backwards for months. | writing the first test that made it fire |
| **S1** | Unreachable. Its docstring said "emitted by runner.run when the file cannot be opened as a ZIP"; the runner emitted C1 there, for both cases. | writing the first test that made it fire |
| **M8** | The title reads "the package must not be part of itself" and the rule is the opposite: `is-part-of-package` is the *exemption*. A test written from the title would have asserted the inverse and passed. | writing the first test that made it fire |
| **M30** | Forbade `iirds:Component rdfs:subClassOf myCompany:ProductPart` — the standard's own way of declaring equivalence to a proprietary class, and the exact link **L5 recommends**. One rule forbade what another asked for. | the specification's Example 43 |
| **M96.1–3, M97.1–2** | Declared applicable from 1.0 while naming vocabulary that arrives in 1.2. They ran, matched nothing, reported clean; what was wrong was the claim. | comparing each rule's terms against the ontology of each release |
| **118 of 182 rules** | Had never produced a finding anywhere in 1,067 tests. Not broken — but from the inside, unexercised and dead are indistinguishable, and S8 shows what can be hiding there. | instrumenting the suite to record which ids fire |

### Silent passes: defective packages reported clean

| | what got through | how it surfaced |
|---|---|---|
| **Content declared `text/html`** | A `.xhtml` file with `<script>`, `<blink>` and a bad `<link rel>` — all eight content rules skipped, `ok=True`. One word in the metadata. | reading the content-rule entry condition |
| **`; charset=utf-8`** | The same eight rules skipped for any package declaring its encoding, which is good practice. The most conscientious authors got the least checking. | reading the entry condition |
| **Case-only collisions** | `Fig1.png` and `fig1.png` — valid, distinct ZIP entries, one file on Windows and macOS. The archive validated; the unpacked directory was missing a file. | writing C15's first test |
| **A 410-byte content file** | Nested entity declarations expanding until the run died, reported as no findings. | a hostile-input review |

### Claims that were not true

| | the claim | what it actually was |
|---|---|---|
| **Determinism** | "byte-identical across runs", in the README | rdflib mints fresh blank-node ids per parse, so three runs gave three reports, and RDF/XML and JSON-LD of one graph disagreed |
| **"64 of 66 fixtures failed here"** | reads as a hit rate | counted fixtures producing *some* finding. The expected rule fires on 42 of 103 pairs |
| **"254 absolute requirements"** | in the README for months, `grep` found one hit and no source | right about what it counted. Sixty more obligations are stated as `0..1` with no RFC 2119 keyword at all — 314 |
| **"0 unexplained"**, in bold | the silence classifier | decides two of its categories by substring-matching the first word of a free-text field |
| **Cross-validation figures** | reproducible | the corpus was fetched from `master` while the rules were pinned to a commit |
| **C13, C15 remediation** | written the same day | described a 255-character limit where the constant is 260, and a case collision the rule does not check. Written from the requirement's prose without reading the code |

### Tests that could not fail

| | |
|---|---|
| **`test_element_style_and_description_style_agree`** | Named for the project's central claim; compared two empty lists. It would have passed had the tool reported nothing for any input. The fixture it used was documented as "the same graph" and is not — it replaces a blank node with an IRI, which `rdflib.compare.isomorphic` denies. |
| **The 61 generated rules** | Two tests guarded the table: that each row names a real class, and that each id is catalogued. Neither asked whether *that* class belonged to *that* rule. Swapping two left both true. The catalogue's own `path` field was the answer, sitting unused. |
| **`serialisation_equivalence.py`** | Four identical empty reports agree with each other however badly the tool is broken. It now refuses a clean package. |

### The process itself

| | |
|---|---|
| **A stray `git checkout`** | Discarded source changes between running the tests and committing, so a green local run was pushed as a red build. "The tests passed" and "what was committed is what passed" are different statements. |
| **`make check` had a hole** | Created to stop local and CI drifting; within a day two gates existed in it that CI did not run. A gate only in CI is noisy and gets fixed. A gate only in the Makefile means CI is not checking something everybody believes it checks. |
| **A generated file edited directly** | A regex touched 59 call sites, two of them in a file written by a generator. The output was correct and no longer matched what the generator would produce. |

### Answers that were true and useless

Not defects in what the tool detects — defects in what it says about it.

| | |
|---|---|
| **A package zipped one directory too high** | Four errors: add a mimetype, create a META-INF, add a metadata.rdf. The author had all three, one level down. Nothing said what had happened. Now **R3**. |
| **Report order** | Registry order — kind, then rule id — is an order about the code. It put R3 fourth of six, so the reader met three misleading findings before the true one. Causes now come first and consequences last. |
| **Findings with no remedy** | Every rule named a defect and stopped there, which is fine for somebody who already knows iiRDS and useless for everybody else. All 185 now say what to change. |

### Requirements nothing checks

Found by mapping a chapter of the specification against the rules, end to end.
Chapter 5 has 21 absolute obligations: sixteen have a rule, two are addressed
to consumers rather than to packages, and three are checkable and unchecked.

| | |
|---|---|
| `dfn-iirds-container#1` | "An iiRDS container MUST have a single root directory." — now **R3**. Zipping the package folder instead of its contents produced four errors telling the author to add a mimetype, a META-INF and a metadata.rdf, all of which they had one level down, and nothing saying what happened. |
| `dfn-iirds-zip-archive#10` | "A nested iiRDS package MUST NOT contain metadata about the outer iiRDS package." |
| `dfn-iirds-zip-archive#11` | "An iiRDS package that contains a nested iiRDS package MUST NOT contain metadata about the content of the nested iiRDS package." |

Two classes had the same shape earlier: Appendix A states `IRI: REQUIRED` for
56 of them and 54 had a rule, so `iirds:ClassificationType` and
`iirdsHov:DocumentCategory` became R1 and R2.

None of these is remarkable on its own. What they have in common is that they
were invisible while coverage was measured against another tool's catalogue,
and that each cost one comparison once the standard had been enumerated
separately.

### A limitation of the index itself

C14 enforces "The length of file names is limited to 255 characters", which is
a real obligation and carries no RFC 2119 keyword and no cardinality notation.
It is stated as plain declarative prose, so the extractor does not see it and
it has no requirement id to cite. How much else is stated that way is not
known. The denominator is therefore a floor rather than a total, which is the
right direction for it to be wrong in but is worth saying out loud.

## What this does not say

Not one of these was found by a user, because there are none yet. The list is
what the project could find about itself, and its shape is the honest limit:
**every instrument here checks fidelity to a reading, and none can check the
reading.** Whether a rule means what its sentence in the specification means is
the one question no single author can answer, and it is why
[divergences.md](divergences.md) exists and why the letter to tekom matters
more than any of this.
