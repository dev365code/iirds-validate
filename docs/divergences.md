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

## Found by the standard's own examples

### M30 was forbidding the extension mechanism it should permit

M30 keeps a package's metadata from restating the iiRDS schema. It decided that
on the subject alone, so any statement *about* an iiRDS term counted — including
`iirds:Component rdfs:subClassOf myCompany:ProductPart`, which is how the
standard writes equivalence to a proprietary class, RDFS having no
`owl:equivalentClass`. Example 43 is titled "Adding a proprietary class as an
equivalent class" and was reported as a violation of it.

It also contradicted **L5**, which asks authors to link proprietary classes to
the iiRDS vocabulary. One rule forbade what another recommended.

Now it fires only when both ends of the statement are the standard's own terms,
which is what "restating the schema" means. Worth recording where this came
from: no fixture in the reference corpus exercises it, and fixing it moved not
one figure in `docs/agreement.json`. Cross-validation against another
implementation could not have found it. The specification's own examples could,
and did, on the first run.

## Version scoping the reference got wrong

Every `versions` array in the catalogue came from the reference tool, and none
had ever been checked against anything. `tools/version_inventory.py` now does
it mechanically: fetch each tagged release of the ontology once, reduce it to
the set of term IRIs, and require that no rule declares itself applicable to a
version whose vocabulary lacks a term the rule names.

Five rules failed. **M96.1, M96.2, M96.3, M97.1 and M97.2** are dated from 1.0
in the catalogue and name `iirds:ExternalClassification`,
`iirds:classificationIdentifier` and `iirds:ClassificationDomain` — the whole
external classification vocabulary, which arrives in **1.2**. Eleven terms
appear between 1.1 and 1.2 and all of them belong to it. A rule cannot apply
before the class it is about exists, so the five are narrowed to 1.2 and 1.3
here.

The consequence of leaving it would have been small and entirely in the claim
rather than the output: on a 1.1 package those rules ran, matched nothing, and
reported clean. What was wrong was `iirdsv rules` saying they applied.

Four pairs in `docs/agreement.json` moved from `agree` to `silent` as a result,
and the movement is this project getting the answer right rather than wrong.
The reference's own fixtures for those rules — `M96-1_false.rdf` and its
siblings — declare `iiRDSVersion 1.1` while using `iirds:ExternalClassification`,
vocabulary that release did not have. Their unit tests call `validateSingleRule`
directly and bypass the version filter their product applies, so nothing on
their side would ever have noticed. This project honours the declared version,
so it now stands down where the fixture claims a release its own contents
contradict.

That the eleven terms appearing between 1.1 and 1.2 are, without exception, the
external classification vocabulary — `ExternalClassification`,
`ClassificationDomain`, `ClassificationType`, `classificationIdentifier`,
`classificationVersion`, `has-classification-domain`,
`has-classification-type`, `has-external-classification`, `CDD`,
`EclassCodedName`, `EclassIRDI` — is a coherent feature landing in one release
rather than a gap in the tagged ontology.

1.0 and 1.0.1 have no tagged ontology, so nothing is checked against them and
the inventory says so by name. If a term is absent in 1.1 it was absent in 1.0
as well — vocabularies do not get removed and reintroduced across a patch
release — so the narrowing above is safe in that direction too.

### M16.1 and M16.2, where the reference is right and its own link disagrees

The other direction, and the one worth checking first, because a scoping that
is too narrow turns a MUST off for versions people actually ship. Both rules
are dated 1.0 to 1.1, and both name `iirds:Event` and `iirds:has-event-code`,
which exist in every version including 1.3 — so the vocabulary check cannot
settle it and the specification has to.

iiRDS 1.3, section 6.6.1:

> Instances of the `iirds:Event` class **MAY** have the following properties

It was a MUST through 1.1 and is a MAY now. **The reference is right and this
project is right to stay silent on a 1.3 package.** The first of the 157
version arrays anybody has verified, and it held.

One loose end belongs to the reference rather than to us: the `spec` link it
gives for both rules points at the **1.3** document, where that sentence reads
MAY. A reader following it from `iirdsv rules -v M16.1` sees this validator
apparently contradicting the standard. It is not; the link is to a later
edition of a sentence that changed. These are the only two rules in the
catalogue whose spec link names an edition the rule does not apply to.

## Where the reference cannot settle it

Three rules whose disposition no amount of cross-validation will decide,
recorded so that "unresolved" does not quietly become "fine".

### M22.1 and M22.2 — one sentence, two checks, one fixture

> An `iirds:Party` MUST have a related `iirds:PartyRole` that is assigned by the
> property `iirds:has-party-role`.

The catalogue splits that into M22.1 (`path='Party'`) and M22.2
(`path='Party has-party-role'`), which reads as two obligations: the Party has
the property, and the thing the property points at is a PartyRole. The reference
implements both as the same check, so its M22.2 asks nothing its M22.1 does not.

Their only fixture for the pair, `Example 34 - Component with manufacturer-M33_false.rdf`,
carries an `iirds:Party` with no `has-party-role` at all. That is the first
obligation, and this project reports it — as M22.1. The reference lists the
fixture under both ids, so the pair (M22.2, that fixture) shows up here as a
silence.

It is not a disagreement. The defect is caught, under the other id. What is
true is that **the second half of the sentence is exercised by no fixture in
the corpus**: a `has-party-role` resolving to something that is not a PartyRole
is reported here and is not in their test material at all. So this is a gap in
the oracle, not a divergence in the rule, and cross-validation cannot tell the
two apart on its own.

`tools/explain_silence.py` classifies this pair as `ours`. That is wrong — it is
`mismatched` — and it is the concrete example behind the caveat further down:
the classifier decides between those two by substring-matching the first word
of a free-text field.

### M25 — no comparison is possible

> To model closed lists, the last node in a list level MUST have the property
> `iirds:has-next-sibling` relating to `iirds:nil`.

Its only fixture, `Example 38 - Table of contents-M36_false.rdf`, is one of the
eleven that do not parse — `mismatched tag` at line 27. There is nothing to run,
so the rule here is neither confirmed nor contradicted, and it is listed as
`unclassified` rather than folded into one of the explained categories.

Repairing the fixture would settle it by supplying our own reading of what the
file was meant to contain, which is the one thing an oracle must not be. The
honest disposition is "no comparison possible", and the way out is a mutation
of a package we control, not a repair of a package we do not.

## Content rules: three readings the specification does not settle

Appendix B has no counterpart in the reference tool — it reads only
`META-INF/metadata.rdf` and never opens a content file — so nothing here can be
cross-validated. These three are interpretation, and are recorded as such
rather than presented as findings the standard compels.

### B4 — the attribute whitelist is narrowed to scripting

Appendix B lists six permitted global attributes. tekom's own sample packages
carry `type` on `<link>`, which appears neither in that list nor in any
element-specific table. A strict whitelist therefore fails the standard's own
examples, which is strong evidence that the list is not meant to be read as
exhaustive.

So attribute checking is limited to event-handler attributes, where the
prohibition is not ambiguous. The cost is real: a genuinely stray attribute
goes unreported. The alternative cost was failing conformant packages on a
reading nobody else holds, which is worse.

### B8 — "only one" is scoped to a hazard statement, not to a file

> The `img` element MUST be a child of the signal word panel. Only one safety
> alert symbol MUST be included.

Both sentences sit inside the table describing **one** hazard statement, so
"only one" is read per statement. Under the per-file reading, a topic carrying a
correctly formed Warning and a correctly formed Danger notice would be a
violation — the rule would get stricter as the document got more careful, which
is the wrong direction for a safety check.

The per-file reading is available from the words alone. If tekom confirms it,
one line changes.

### B8 — a missing symbol is not reported

"MUST be included" is read as "at most one, where present". Absence is not
checked, so a Warning with no safety alert symbol passes.

This is a deliberate non-check rather than an oversight, and it is the least
comfortable row in this document. ANSI Z535 requires the symbol for WARNING and
DANGER; iiRDS does not say so in terms, and inferring a safety requirement from
a neighbouring standard is not something a validator should do silently. It is
recorded here instead, and it is the first of the questions to put to tekom.

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
| **42** | the expected rule fires here | |
| 34 | silent — and the reference's own assertion passes too | its unit tests call `validateSingleRule` directly, bypassing the version and variant filters its product applies, so a fixture can be listed against a rule that does not apply to it |
| 9 | silent — the fixture is malformed XML upstream | no comparison is possible; not repaired, see below |
| 11 | silent — gated by version or variant here | five of them because the fixture declares 1.1 while using vocabulary that arrives in 1.2; see above |
| 3 | silent — the defect exists only in the XML tree | two serialisations of one graph; there is nothing in the graph to report |
| 2 | silent — mismatched | the defect is reported, under a different rule id |
| 1 | silent — labelled **ours**, and mislabelled | M22.2: the defect *is* reported, as M22.1. See above — this is the worked example of what the classifier cannot do |
| 1 | silent — **unclassified** | M25, whose only fixture is one of the nine malformed |

Two findings fire on fixtures the reference says should pass, both M15.10, both
traceable to a row in this document.

### Three numbers, and why only one of them is the honest headline

The same measurement produces very different figures depending on what is
counted, and this document previously published the flattering one:

| | |
|---|---|
| 42 of 103 pairs (41%) | the expected rule fires |
| 40 of 66 fixtures (61%) | the expected rule fires somewhere on the fixture |
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

That single fixture accounts for **48% of the 61 silent pairs**. Add the five
against `metadata_iirds_sample-M15_false.rdf` and the figure is decided, more
than anything else, by how loosely upstream filled in one metadata field. A
pair-level percentage computed over that distribution is not measuring this
validator, and quoting one without saying so would be the third version of the
same mistake this document already records twice.

The 41% is misleading in the other direction, because almost all of the silence
is accounted for: 34 pairs are cases where the reference does not report
either, 11 are gated by a version or variant, and 9 are fixtures nobody can
parse. Read the table above rather than any single
figure. What is actually unresolved is **four pairs** — the 2 mismatched, the 1
ours and the 1 unclassified.

### What the classifier behind that table cannot support

`tools/explain_silence.py` separates `ours` from `mismatched` by substring-
matching the first word of the catalogue's free-text `path` field. A short or
common value will match spuriously, and an absent one collapses the distinction
entirely. Earlier revisions of this document set **0 unexplained** in bold; the
classifier does not carry bold. Treat the last three rows as "needs a human",
which is what the divergence rows above are for.

