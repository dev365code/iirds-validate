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

Measured by `tools/crossvalidate.py` over the reference's own corpus:

- 64 of 66 fixtures it says must fail are failed here
- of the remaining silences: 32 where the reference's own assertion also
  passes, 9 malformed, 6 gated by version or variant, 3 invisible in RDF,
  2 mismatched, **0 unexplained**
- of the findings on fixtures it says pass: all trace to a row in this
  document, and none is an error-level finding this project cannot justify
