# Where this validator disagrees with the reference tool

The README promises that results can be diffed against the [iiRDS Validation
Tool](https://github.com/plusmeta/iirds-validation-tool) rule by rule. That
promise is only worth anything if the places the two disagree are written down.
Every one is here, with the evidence.

`tools/crossvalidate.py` and `tools/explain_silence.py` reproduce all of it.

## How the reference tool was read

Not from its rule text — from its source. `src/config/validation/schema-rules.js`
holds the assertion for each rule, and `src/util/rules.js` the helpers. Several
rules do not do what their own wording says, which is the single most important
thing to know before comparing anything.

Worth knowing about the corpus this project leans on:

- fixture file names are offset from the rule ids they test — M10's failing
  fixture is named `metadata_iirds_sample-M11_false.rdf`, so only the
  `testFiles` field is authoritative
- two fixtures are committed as zero-byte files
- nine are not well-formed XML
- its unit test calls `validateSingleRule` directly, bypassing the version and
  variant filters the product itself applies
- the repository runs no tests in CI; its only workflow is a code review action

It is a useful oracle. It is not a certified one.

## Rules where the reference's implementation is not its own wording

Following the wording here would leave real checks missing, so this project
follows the implementation and records the wording.

| rule | wording says | reference checks | here |
|---|---|---|---|
| M19.1 | exactly one `has-identity-domain` | exactly one `identifier` | identifier |
| M19.3 | (same as M19.1) | exactly one `has-identity-domain` | domain |
| M21.4 | at most one `purpose` | at most one `dateOfStatus` | dateOfStatus |
| M21.5 | cardinality row for `purpose` | at most one `purpose` | purpose |
| M78–M93 | "not intended to be used directly" | element has an `rdf:about` | rdf:about |

The last row was the largest single error in this project's history. Sixteen
rules were implemented from the catalogue's category label, which produced
findings on tekom's own sample packages that no other tool reports. The
observation the label describes is real and useful, so it survives as **L10**, a
warning, labelled as this project's own reading rather than as a MUST.

`dateOfStatus` deserves a note: taking the wording for both M21.4 and M21.5
would mean checking `purpose` twice and never checking `dateOfStatus` at all.

## Rules where the reference's implementation is broken

Following it would mean implementing a bug.

| rule | reference assertion | why it cannot work |
|---|---|---|
| M12 | `!els.some(el => el.querySelectorAll("Selector"))` | `querySelectorAll` returns a NodeList, always truthy, so this fires whenever any element is selected |
| M16.2 | `els.filter(el => !el.querySelectorAll("has-event-type"))` | returns an array, and `[]` is truthy in JavaScript, so it never fails |
| M96.3 | `el.querySelector("classificationIdentifier").textContent` | throws when the property is absent, which is the case it exists to catch |

Each is implemented here from the specification text instead.

## Rules where this project is stricter, deliberately

| rule | difference | why |
|---|---|---|
| M15.10 | requires the InformationObject to relate to a Creator party | the reference checks `hasValidIdentity`, which is a different requirement; the wording is explicit and both handover fixtures fail it |
| M22.1 | counts roles on the party in the graph | the reference counts child elements, so a party written as several repeated `<iirds:Party rdf:about="…"/>` declarations is counted many times; both find the sample's role-less party, but only one of them says so once |
| M30 | only flags redeclared **iiRDS** terms | the reference rejects any `subClassOf`/`domain`/`range` element at all, which would forbid the proprietary subclasses section 7 explicitly permits |

## Rules where this project is more lenient, deliberately

Each of these was stricter until the reference's own fixtures showed the cost.

| rule | earlier behaviour | now | reason |
|---|---|---|---|
| M17, M18 | every externally referenced IRI had to be declared locally | fires only when a package references such a vocabulary and declares none of its own | the strict reading fails tekom's own external-product-ontology sample |
| M13.1, M13.2 | every Selector needed `rdf:value` and `dcterms:conformsTo` | RangeSelector exempt | a range is addressed by its start and end selectors, which M14.1 and M14.2 check |
| M19.4 | the identity domain had to be typed here | undescribed domains left to L1 | a reference out of the package is not a typing error |
| M15.7b/d, M15.8/9/10 | required a typed `vcard:Organization` | requires a stated `vcard:organization-name` | the reference's handover fixtures type the node `vcard:organization` — the property, lower case; the substance is that the party can be identified |
| "must have an IRI" family | required an **absolute** IRI | requires an identifier that is not a blank node and not the bare document base | absoluteness is M5's question, and M5 is RECOMMENDED. Conflating them turned one recommendation into sixty MUSTs |

## Differences that are not anybody's bug

**RDF collapses duplicate statements.** M2.7, M2.8 and M2.9 have fixtures that
repeat an element with an identical empty value. In RDF that is one statement,
so a graph-based validator cannot see two. Their fixtures and ours describe
byte-identical graphs — `tools/explain_silence.py` classifies these as
`invisible` by computing the diff. A package with two *different* values is
still caught.

**Malformed fixtures.** Nine fixtures are not well-formed XML. This validator
reports the parse failure (C16.1) and fails the package; a browser `DOMParser`
recovers a partial document and keeps going.

**Version and variant gating.** Six pairs name a rule that does not apply to
the fixture's declared version or profile — M8 is 1.1+ and the fixture declares
1.0. The reference's product applies the same filters; only its unit test does
not.

## Current agreement

Measured by `tools/crossvalidate.py` and `tools/explain_silence.py` over the
vendored corpus at `0bcf19dd` — the same revision the rule catalogue came from.
Both read `tests/corpus/plusmeta/`, so anyone can reproduce these offline:

```sh
make corpus            # the fixtures are still upstream's bytes
python tools/crossvalidate.py
python tools/explain_silence.py
```

The reference marks 113 rule/fixture pairs as "this fixture must fail this
rule". Ten of those name one of the two fixtures upstream committed as
zero-byte files, which nothing can test. Of the remaining **103 pairs, across
66 distinct fixtures**:

| | pairs | |
|---:|---|---|
| **46** | the expected rule fires here | |
| 35 | silent — and the reference's own assertion passes too | its unit tests call `validateSingleRule` directly, bypassing the version and variant filters its product applies, so a fixture can be listed against a rule that does not apply to it |
| 9 | silent — the fixture is malformed XML upstream | no comparison is possible; not repaired, see below |
| 6 | silent — gated by version or variant here | |
| 3 | silent — the defect exists only in the XML tree | two serialisations of one graph; there is nothing in the graph to report |
| 2 | silent — mismatched | the defect is reported, under a different rule id |
| 1 | silent — **ours** | reported here and not there; M22.2, below |
| 1 | silent — **unclassified** | M25, whose only fixture is one of the nine malformed |

Two findings fire on fixtures the reference says should pass, both M15.10, both
traceable to a row in this document.

### Three numbers, and why only one of them is the honest headline

The same measurement produces very different figures depending on what is
counted, and this document previously published the flattering one:

| | |
|---|---|
| 46 of 103 pairs (45%) | the expected rule fires |
| 44 of 66 fixtures (67%) | the expected rule fires somewhere on the fixture |
| 65 of 66 fixtures (98%) | **some** finding is produced on the fixture |

The last was published here as "64 of 66 fixtures it says must fail are failed
here". It is true, and it reads as a hit rate, and it is not one — producing
*a* finding on a file known to be defective is a much weaker thing than
producing the *right* one. It is the same error as reporting 157 of 157
catalogued rules as though it were coverage of the standard, and it was made
here for the same reason: the number that was easy to compute was allowed to
stand in for the number that mattered.

### Half the silence is one fixture

`metadata_iirds_sample_pass-M49_false.rdf` is listed upstream as the must-fail
fixture for **29 different rules** — M40, M43 through M76, and more. Its name
says M49, and M49 is the rule it actually violates. The other 28 pairs are a
file listed against rules it does not breach, which is why the reference's own
assertion passes on almost all of them.

That single fixture accounts for **51% of the 57 silent pairs**. Add the five
against `metadata_iirds_sample-M15_false.rdf` and the figure is decided, more
than anything else, by how loosely upstream filled in one metadata field. A
pair-level percentage computed over that distribution is not measuring this
validator, and quoting one without saying so would be the third version of the
same mistake this document already records twice.

The 45% is misleading in the other direction, because most of the silence is
accounted for: 35 pairs are cases where the reference does not report either,
and 9 are fixtures nobody can parse. Read the table above rather than any single
figure. What is actually unresolved is **four pairs** — the 2 mismatched, the 1
ours and the 1 unclassified.

### What the classifier behind that table cannot support

`tools/explain_silence.py` separates `ours` from `mismatched` by substring-
matching the first word of the catalogue's free-text `path` field. A short or
common value will match spuriously, and an absent one collapses the distinction
entirely. Earlier revisions of this document set **0 unexplained** in bold; the
classifier does not carry bold. Treat the last three rows as "needs a human",
which is what the divergence rows above are for.

