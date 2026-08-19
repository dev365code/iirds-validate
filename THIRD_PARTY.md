# Third-party material and provenance

Everything bundled here, where it came from, and what you may do with it.

| Component | Origin | Licence | Modified? |
|---|---|---|---|
| Rule ids, priorities, spec links, rule wording | [plusmeta/iirds-validation-tool](https://github.com/plusmeta/iirds-validation-tool) | MIT | Reformatted to JSON; wording unchanged |
| Rule implementations | this project | Apache-2.0 | n/a — written from scratch |
| `iirds-core.rdf`, `iirds-machinery.rdf`, `iirds-software.rdf`, `iirds-handover.rdf`, `iirds-skos.rdf` | [iiRDS 1.3 release](https://www.iirds.org/materials/version-13) | CC BY-ND 4.0, © tekom Deutschland e.V. | **No — byte-for-byte verbatim** |
| `rdflib` | [RDFLib](https://github.com/RDFLib/rdflib) | BSD-3-Clause | No (runtime dependency) |

## Why the ontologies are not converted

CC BY-ND forbids *sharing* adapted material. Redistributing a Turtle or JSON-LD
conversion of `iirds-core.rdf` would be sharing an adaptation. Reading the file
and converting it in memory at run time is not. So the shipped bytes are the
original bytes, and `sha256sums.txt` lets anyone verify that.

## Why plusmeta's rule ids are kept

Reproducing the mapping from 157 rules to the specification sentences that
justify them is the single most expensive artefact in this domain. plusmeta
published it under MIT. Reusing it — with attribution — is the licence working
as intended. Keeping the identifiers also means a package can be run through
both tools and the results diffed rule by rule, which is how this project
verifies itself.

## What is *not* reused

No plusmeta source code. Their validator walks an XML DOM with CSS selectors;
this one operates on an RDF graph. See `docs/design.md` for why that difference
matters.
