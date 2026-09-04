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
| M24.5 | root MUST have a structure type | non-root MUST NOT have one | non-root |
| M78–M93 | "not intended to be used directly" | element has an `rdf:about` | rdf:about |

The last row was the largest single error in this project's history. Sixteen
rules were implemented from the catalogue's category label, which produced
findings on tekom's own sample packages that no other tool reports. The
observation the label describes is real and useful, so it survives as **L10**, a
warning, labelled as this project's own reading rather than as a MUST.

**M15.10** is not in that table, because the table's middle column is what the
reference checks and this project cannot read the reference's source — only its
fixtures, which say the opposite of its catalogue wording. What follows is a
disagreement with the *catalogue*, settled from the specification.

Its catalogue wording asks an `iirds:InformationObject` for
`iirds:relates-to-Party` with role Creator. Section 8.3.2 asks something else:
"at least one `iirds:has-identity` relating to an `iirds:Identity` with an
`iirds:IdentityDomain`. The `iirds:IdentityDomain` MUST relate to an
`iirds:Party` with `iirds:has-party-role` `iirds:Creator`". The party hangs off
the domain, which is the shape M15.7b and M15.7d already follow for the
manufacturer, while the Package and Document bullets put a party on the subject
itself and those are M15.9 and M15.8 — the only two that still do. Four more
things agree: `relates-to-Party`
appears exactly twice in those mandatory lists, for the Package's Creator and
the Document's Author; section 6.8.3 permits — MAY, not MUST — a party on
`iirds:InformationUnit`, `iirds:ContentLifecycleStatus`, `iirds:Component`,
`iirds:ProductVariant` or `iirds:IdentityDomain`, and `iirds:InformationObject`
is none of those, being a subclass of `iirds:iirdsDomainEntity`. Appendix A
settles it without needing the permission read at all: `iirds:relates-to-party`
is declared with **Has Domain** `iirds:Component`, `iirds:IdentityDomain`,
`iirds:ClassificationDomain`, `iirds:InformationUnit`,
`iirds:ContentLifeCycleStatus`, `iirds:ProductVariant` — the property does not
reach an information object at all. And the material agrees: *both* fixtures the
catalogue lists as passing for M15.10 have an information object carrying an
identity and no party of its own, as does **Example 63**, the specification's
own iiRDS/H package with mandatory metadata. This rule reported a MUST-level
error on all three.

Two of the three are silent now. Example 63 is not, and not because of this
rule: the example declares its creator party at `http://iirds.org/example/…`
while the identity domain points at `https://iirds.org/example/…`, so the party
the domain names is a resource the package never describes. Reconcile the two
schemes and it goes quiet; the author party carries the same typo the other way
round. The example stays in view because a specification's own worked example
is the cheapest oracle a validator has, and because the claim that this rule no
longer fires on it was written before anyone ran it.

The class this belongs to was enumerated, and the first enumeration was
wrong in a way worth recording. Sweeping the 1.3 text for a MUST whose subject
is "**The** *Class*" following a line that introduces one — the construction
that makes a requirement existential — finds four, all about
`iirds:IdentityDomain`: the two identity types (M15.7a's second half and
M15.7c) and the two parties (M15.7b and M15.7d for the manufacturer, this rule
for the creator). The sweep looked for the article and missed the
demonstrative. The fifth is the shell the other four sit inside: "**This**
`iirds:ProductVariant` MUST relate to an `iirds:Identity` with an
`iirds:IdentityDomain`", under "at least one
`iirds:relates-to-product-variant` relating to an `iirds:ProductVariant`" —
and that one fixes the population as well as the quantifier. Read over every
`iirds:ProductVariant` in the graph, M15.7b, M15.7c and M15.7d failed a
package for carrying a model it documents elsewhere; they read the variants a
document names now, and name the document, which is the shape M15.7a always
had. A test holds the closure by adding a further identity of each kind, and a
further variant, to a conformant handover package and requiring that nothing
turns it away.

One identity is enough. "at least one `iirds:has-identity` …" introduces the
domain the next sentence speaks of, and section 6.8.1 says instances of
`iirds:InformationObject` "MAY have `iirds:has-identity` relations" — plural,
and 6.2.2 says an information object "MAY be related to additional
identifications via the `iirds:has-identity` property" —
so an object may carry a second identity, an internal number naming nobody,
which a reading over every domain would fail. The finding names the object
rather than a domain: which domain to mend is the author's, and two objects
sharing one unmended domain are two failures.

Correcting it moved `docs/agreement.json` by exactly two pairs, both of them
`M15.10` against a fixture the catalogue marks as passing, and both classified
`extra` — the category for a finding this project reports and the reference
does not. The file now records none: 113 pairs, `agree` 42, `silent` 61,
`untestable` 10. Cross-validation did not find this, because a rule can be
wrong about the standard while both implementations are wrong together; what
found it was reading section 8.3.2 and then noticing that the reference's own
passing fixture was one this rule failed.

M24.5 deserves the same note as `dateOfStatus`, with one correction to it.
Its title is section 6.9.1's positive sentence, "The root node of a directory
structure MUST have one property `iirds:has-directory-structure-type`", and the
rule checks the sentence immediately after, "Only root nodes of a directory
structure MUST have" it. What the row cost was not the check but the remedy:
the remedy followed the title and told a reader whose *child* node was reported
to add the property to the root, which leaves the finding where it was. A
remedy is printed under a finding and has to resolve that finding; it now says
to remove the property from the node named.

The correction is that **M24.6 does not cover the title's sentence either**, so
that sentence is unchecked. M24.6 asks whether *a* root with the property
exists — one existential check for the whole graph — while 6.9.1's first
sentence binds every root. A package with two directory structures, the second
of whose roots carries no structure type, is reported by nothing: M24.5 is
silent because that node is not reachable from another, M24.6 is satisfied by
the first root, and L3 says something adjacent but is a lint and does not run
under `check`. It is recorded here rather than fixed, because the fix is a
rule about what a root is, and this project has one already — `_linked_nodes`
computes exactly the set — but a new MUST is not something to add inside a
commit about a remedy.

`dateOfStatus` deserves a note: taking the wording for both M21.4 and M21.5
would mean checking `purpose` twice and never checking `dateOfStatus` at all.

## Catalogue titles that name a term the ontology does not define

Rule titles are the catalogue's wording, reproduced character for character
so results stay diffable against the reference tool rule by rule. Eight of
them name a property or class that does not exist under the spelling given.
Correcting them here would break that comparison, so they are recorded
rather than edited — and a gate skips exactly these when it checks that a
rule's *own* prose names real terms.

| the title says | the ontology defines | rules |
|---|---|---|
| `iirds:eventCode` | `iirds:has-event-code` | M16.1 |
| `iirds:eventType` | `iirds:has-event-type` | M16.2 |
| `iirds:relates-to-Party` | `iirds:relates-to-party` — capitalisation only | M15.8, M15.9, M15.10 |
| `iirds:ContentLifecyleStatus` | `iirds:ContentLifeCycleStatus` — "Lifecyle" is a typo for "LifeCycle" | M21.1 |
| `iirds:ContentLifecyleStatusValue` | `iirds:ContentLifeCycleStatusValue`, same typo | M21.1 |
| `iirds:DocumentTypes` | `iirds:DocumentType` — plural | M15.1 |
| `iirds:first-child` | `iirds:has-first-child` | M24.6 |
| `iirds:next-sibling` | `iirds:has-next-sibling` | M24.6 |

The first two were already noted where the Consortium's own samples are
discussed, because the 1.0 prose uses them too and the 1.0 *schema* does
not — a discrepancy between one edition's document and its own vocabulary,
not a tool's mistake. The other six are the catalogue's alone. None of them
affects what any rule checks: every term a rule *evaluates* comes from
`terms.py`, where a test resolves it against the bundled ontology. What is
affected is what a reader is told, which is why they are listed rather than
left to be rediscovered.

## Rules where the reference's implementation is broken

Following it would mean implementing a bug.

| rule | reference assertion | why it cannot work |
|---|---|---|
| M12 | `!els.some(el => el.querySelectorAll("Selector"))` | `querySelectorAll` returns a NodeList, always truthy, so this fires whenever any element is selected |
| M16.2 | `els.filter(el => !el.querySelectorAll("has-event-type"))` | returns an array, and `[]` is truthy in JavaScript, so it never fails |
| M96.3 | `el.querySelector("classificationIdentifier").textContent` | throws when the property is absent, which is the case it exists to catch |

Each is implemented here from the specification text instead.

## Rules where this project is stricter, deliberately

This table had a third row, for M15.10, claiming that the reference's
`hasValidIdentity` was "a different requirement" and that the catalogue's
wording was "explicit". The wording was explicit and it was not the
specification's; both of the reference's handover fixtures failed this rule
because the rule was wrong, and one of them is marked as passing. The row
above, in the wording table, records what section 8.3.2 actually says. Being
stricter than the reference is a position this project takes on purpose and
has to defend from the specification; when the defence is the catalogue's own
sentence, there is no defence.

| rule | difference | why |
|---|---|---|
| M22.1 | counts roles on the party in the graph | the reference counts child elements, so a party written as several repeated `<iirds:Party rdf:about="…"/>` declarations is counted many times; both find the sample's role-less party, but only one of them says so once |
| M30 | only flags redeclared **iiRDS** terms | the reference rejects any `subClassOf`/`domain`/`range` element at all, which would forbid the proprietary subclasses section 7 explicitly permits |

## Rules where this project is more lenient, deliberately

Each of these was stricter until the reference's own fixtures showed the cost —
or, for C9, until the grammar the obligation cites was read.

| rule | earlier behaviour | now | reason |
|---|---|---|---|
| M17, M18 | every externally referenced IRI had to be declared locally | fires only when a package references such a vocabulary and declares none of its own | the strict reading fails tekom's own external-product-ontology sample |
| M13.1, M13.2 | every Selector needed `rdf:value` and `dcterms:conformsTo` | RangeSelector exempt | a range is addressed by its start and end selectors, which M14.1 and M14.2 check |
| M19.4 | the identity domain had to be typed here | undescribed domains left to L1 | a reference out of the package is not a typing error |
| M15.7b/d, M15.8/9/10 | required the class `vcard:Organization` | accepts `vcard:Organization` **or** `vcard:organization` — the vcard *property* IRI used where the class belongs — and still requires a stated `vcard:organization-name` | every handover fixture the reference ships writes the lower-case spelling; both say "organisation" and one is a misspelling of the other |
| "must have an IRI" family | required an **absolute** IRI | requires an identifier that is not a blank node and not the bare document base | absoluteness is M5's question, and M5 is RECOMMENDED. Conflating them turned one recommendation into sixty MUSTs |
| C9 | the document element had to be `rdf:RDF` | `rdf:RDF`, or a single node element in its place | the RDF 1.1 XML grammar the obligation cites starts with production *doc* or *nodeElement* (§7.2.1); §2.6: "When there is only one top-level node element inside rdf:RDF, the rdf:RDF can be omitted although any XML namespaces must still be declared." rdflib reads the form; the rule did not |

**What a row here does to a coverage claim.** "More lenient" covers three
different things, and only one of them costs a claim. The `claim` column says
which each row is; `tests/test_covers_is_earned.py` reads that column, because
a table nothing runs is how the M25 paragraph below came to be contradicted by
the code it describes.

| rule | kind of leniency | claim |
|---|---|---|
| M17, M18 | **narrows the sentence** — the rule asks something else and the difference is unreported | withdrawn |
| M15.7b, M15.7d, M15.8, M15.9, M15.10, R12 | **a spelling** — `vcard:organization` is a case-slip of the class the sentence names, and no term of the vCard vocabulary at all | kept |
| M13.1, M13.2 | **not a leniency** — Example 13 shows a `RangeSelector` carrying neither property and its two fragment selectors carrying both, which these rules check | kept |
| M19.4 | **narrows the sentence** | never claimed |
| M2.1, R1, R2 (the "must have an IRI" family) | **not a leniency** — appendix A says `IRI: REQUIRED`, and a relative IRI is an IRI; the earlier rule enforced M5's RECOMMENDED absoluteness on top | kept |
| C9 | **not a leniency** — the earlier rule enforced the shape most files have rather than the grammar the obligation cites | kept |
| B6 | **a spelling** — the extension is compared case-insensitively, so `.XHTML` passes where B.3 writes `.xhtml` | kept |

So the rule, stated in `docs/scope.md`: a claim survives a documented
difference only where the difference is about *how* the sentence is spelled,
or where what is called leniency is really the correction of a strictness the
sentence never asked for. Where the rule genuinely checks less than the
sentence says, the claim goes with it.

**Which claims stand is not stated in this document.** It was, in a paragraph
here that named two rules and described the state of their citations; both had
moved by the time anyone read it again. The paragraph further down about
section 6.9.1 went the same way, in this file, three days apart. A sentence of
prose about what the code claims is a copy of the code, and copies drift.

So the record lives in two places a test reads. A withdrawal is a
`# not <requirement id>: <reason>` comment on the rule that refused it, pinned
as rule-and-obligation pairs in `tests/test_covers_is_earned.py`; a claim is
`covers=` on the rule, and every one of them is either held by a package there
or named in that file's UNAUDITED list. The table above says which rows of it
keep a claim, and a test reads the column. This document explains *why* a
reading was chosen. It no longer says what the code does.

What is worth keeping from that paragraph is the part about withdrawals
themselves. A withdrawal is cheaper than a wrong claim and it is not free: it
says a sentence cannot be checked. Twice that was a statement about the
afternoon rather than about the sentence — "it would need the vCard vocabulary
bundled" needed six IRIs, and "the rule asks whether the file parses" was true
of the rule and is a thing a rule can be taught. Ask a withdrawal for its
evidence the way a claim is asked for a package.

**C9, in more detail.** Section 5.1.1 asks for "RDF 1.1 XML syntax (see
[rdf-syntax-grammar])", and the rule enforced the shape most files have
rather than the grammar: a file whose one top-level element was
`<iirds:Package rdf:about="…">` — three statements to every RDF parser — was
reported as not an RDF document, with a remedy claiming no parser would read
a statement from it. The criterion is the grammar's now: the document element
is `rdf:RDF`, or it is a node element, which §7.2.5 defines as any absolute
IRI outside the eleven reserved names (the core syntax terms, `rdf:li`, the
old terms). Two consequences follow and are pinned by tests. An element with
no namespace, `<manual>`, is still C9: its name is not an IRI, so it is not a
node element, however happily rdflib turns it into a class. And an XHTML file
saved as metadata.rdf is *not* C9: its document element, `html` in the XHTML
namespace, is a node element to the grammar, so the file is RDF/XML that is
not about iiRDS, and the graph rules say what is missing (no package) while
lint says whose the classes are (nobody's — rdflib types the node with the
namespace and the element name run together, `…/1999/xhtmlhtml`, and drops
the text inside `title`, which §7.2.11 gives no place to). Only the document
element is judged; what the body does with the grammar is the parser's to
say, and rdflib says nothing.

The judgement is the reader's, not this checker's: `iirds.parse_metadata`
refuses the document on the bytes it parses, after the byte order mark has
decided the encoding. Judged before the decode, a UTF-32 `<manual>` showed
no element at all to the judge and two triples to the parser.

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

## The Consortium's own sample packages, run for real

The iiRDS Sample Content (2019-10-31, behind free registration at iirds.org)
contains the only two complete packages the standard's authors have published:
`iirds-sample-1.iirds` and `iirds-sample-2.iirds`, both declaring iiRDS 1.0,
variant A. The first genuine 1.0 material this project has seen — 159 rules
ran, 29 correctly stood down for the version and profile.

Every error was verified against the 1.0 specification text (2018-04-18)
before being called a defect:

| finding | verdict | the sentence, from the edition the package declares |
|---|---|---|
| sample 1, **M22.1** (error) | **defect in the official sample** | "An iirds:Party MUST have a related iirds:Role that is assigned by the property iirds:has-party-role" — the reviewer Party carries only a vcard |
| sample 2, **M18** (error) | **defect in the official sample** | "As product variants are a proprietary iiRDS extension, they MUST be present in the metadata.rdf of the iiRDS package" — verbatim in 1.0 and 1.3; the package relates to `pifan#X5-DH2` and declares no ProductVariant |
| both samples, B10 (warning ×11) | correct observation | eleven hazard statements at caution or warning level carry a triangular ISO warning sign — in five of them the safety alert symbol itself — and tag none of them, so a consumer cannot tell the alert symbol from the flammable-materials sign beside it. The packages provide the symbols; the `data-role` that identifies one is what is absent. Six in sample 1, five in sample 2; the four notices carry a blue circle and are left alone |
| sample 1, L10 (warning) | correct observation | the package types `mch:EnvironmentalProtectionInstruction` directly as `iirds:InformationSubject`; tekom's own 1.3 machinery vocabulary types that term as an instance of `iirds:Safety` — the warning's advice is the vocabulary's current position |
| sample 2, L1 (warning) | correct observation | `relates-to-party` names a UUID described only in sample 1; a consumer holding sample 2 alone cannot resolve it |
| sample 2, L8 ×5 (info) | as designed | references into the external `pifan` vocabulary, which an offline consumer cannot fetch |

Sample 1 passes M17/M18 because it declares its externally-identified
components inline; sample 2 references without declaring. The pair lands
exactly on the line those rules draw, which is unplanned and reassuring.

`tests/test_official_samples.py` pins all of this, finding for finding; it
skips unless `IIRDS_SAMPLE_CONTENT` points at the directory, because the
packages are registration-gated and are not redistributed here.

One caveat this exercise surfaced was settled the same day, by fetching the
Consortium's own published 1.0 schema: the 1.0 *prose* names the Event
properties `iirds:eventCode` and `iirds:eventType`, but the 1.0 *ontology*
already says `has-event-code` and `has-event-type` — so M16.1/M16.2 check the
right names for every edition, and the discrepancy is between the 1.0 document
and the 1.0 schema, not in any tool. The same fetch showed the sample's L10
warning holds against the package's own era: `mch:EnvironmentalProtectionInstruction`
is typed `iirds:Safety` in the 1.0 machinery vocabulary too.

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
reported clean. What was wrong was `iirds rules` saying they applied.

Four pairs in `docs/agreement.json` moved from `agree` to `silent` as a result,
and the movement is this project getting the answer right rather than wrong.
The reference's own fixtures for those rules — `M96-1_false.rdf` and its
siblings — declare `iiRDSVersion 1.1` while using `iirds:ExternalClassification`,
vocabulary that release did not have. Their unit tests call `validateSingleRule`
directly and bypass the version filter their product applies. This project
honours the declared version, so it now stands down where the fixture claims
a release its own contents contradict -- and, since L15, says so: run over
the reference corpus, those eight fixtures are exactly the files on which it
reports names from a later edition than the one declared.

That the eleven terms appearing between 1.1 and 1.2 are, without exception, the
external classification vocabulary — `ExternalClassification`,
`ClassificationDomain`, `ClassificationType`, `classificationIdentifier`,
`classificationVersion`, `has-classification-domain`,
`has-classification-type`, `has-external-classification`, `CDD`,
`EclassCodedName`, `EclassIRDI` — is a coherent feature landing in one release
rather than a gap in the tagged ontology.

The inventory initially covered 1.1 onward, because the GitHub tags carry
nothing older; the Consortium's site publishes every edition's schemas, and
extending the inventory to 1.0 and 1.0.1 immediately found two more: **M49**
names `iirds:IdentityType` and **M76** names `mch:ProtectiveEquipment`, both
declared from 1.0 in the catalogue and both arriving in 1.1 — with the whole
identity-type system (ArticleCode, SerialNumber, GTIN, EAN, ObjectInstanceURI,
ProductType) and the protective-equipment family beside them, a coherent
release rather than a gap in the data. Both are narrowed to 1.1 onward, making
seven catalogue version arrays corrected in all.

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
MAY. A reader following it from `iirds rules -v M16.1` sees this validator
apparently contradicting the standard. It is not; the link is to a later
edition of a sentence that changed. These are the only two rules in the
catalogue whose spec link names an edition the rule does not apply to.

## Where the reference cannot settle it

Three rules whose disposition no amount of cross-validation will decide,
recorded so that "unresolved" does not quietly become "fine".

### `is-part-of-package` pointing at its own subject — nesting, or nothing?

Two sentences decide who the container is.

> The corresponding `iirds:Package` instance of an iiRDS package MUST NOT be a
> member of **another** iiRDS package expressed by the property
> `iirds:is-part-of-package`. (§6.2, and the same sentence in 1.0)

> In the `metadata.rdf` file of the parent iiRDS container, the referenced
> parent iiRDS container MUST NOT have any outgoing `iirds:is-part-of-package`
> relations. (§6.3.3, 1.3 only)

A package naming *itself* is not a member of another package, so the first
sentence does not make it a nested child. This project reads it that way: **a
package is a nested child when it is part of a different package.** Before
that, the bare presence of the predicate meant nesting, and one triple a
package cannot legally carry bought the exemption §6.3 grants to children.
Measured: an `iirds:Package` carrying `iirds:has-rendition` reported `M8`; the
same package plus `<iirds:is-part-of-package rdf:resource="…itself"/>` reported
nothing. A MUST NOT was switched off by a statement that cannot be true. The
same reading hid M3 as well — one self-looping package beside one genuine
container drew no "more than one package represents this container".

**This reverses the paragraph that stood here one commit ago.** It said the
named parent was deliberately not required to be present — "a nested child
delivered on its own is still a child, and asking for its parent would report
it for being delivered alone". The premise is wrong.

What settles it is normative and does not need the example. §6.3.3 asks the
child's package to "reference exactly one `iirds:Package`", Appendix A gives
`iirds:is-part-of-package` the range `iirds:Package`, and §6.2 forbids the
container's own instance from being "a member of another iiRDS package
expressed by the property `iirds:is-part-of-package`" — which, read per
document, is broken by a standalone child whose own metadata carries the
triple.

Example 16 corroborates and is **not** the argument: §1 puts examples outside
the normative text. It prints *two* files. In the parent's `metadata.rdf` the nested
package carries `<iirds:is-part-of-package rdf:resource="…iiRDS-parent"/>`
beside the parent's own `iirds:Package`. In **the nested child's own**
`metadata.rdf` the same package appears with `iiRDSVersion` and
`formatRestriction` and **no `iirds:is-part-of-package` at all**. A child
delivered alone is not supposed to carry the triple, so refusing to require
the parent was protecting a document the specification does not describe.

Two sentences say why. §5.3: "A nested iiRDS package MUST NOT contain metadata
about the outer iiRDS package." And §6.2, about the container being validated:
"The corresponding `iirds:Package` instance of an iiRDS package MUST NOT be a
member of another iiRDS package expressed by the property
`iirds:is-part-of-package`."

Two of §6.3.3's four MUSTs are scoped to one document — "In the
`metadata.rdf` file of the parent iiRDS container" — which is where the
nesting triple belongs. A scope clause does not by itself forbid the triple
elsewhere; §6.2 is what does that. (§6.3.3's first MUST is about the *child's*
`iirds:Package` being present in the parent's metadata, not the parent's, and
is not evidence here.)

So: **a package is a nested child when it is part of a different package that
this graph describes as an `iirds:Package`.** An IRI nothing describes, a node
typed `iirds:Topic`, a plain literal, an anonymous blank node — none of them
makes one, and each of them used to. The fifth shape re-opened the self-loop
bypass closed the commit before, by pairing the self-loop with any one of the
other four.

What this does **not** do is report the child that carries the triple. §5.3's
two prohibitions are `x5-3-nested-iirds-packages#2` and `#3`, and both were
gaps when this was written. They are no longer the same kind of thing.

`#3` — "An iiRDS package that contains a nested iiRDS package MUST NOT contain
metadata about the content of the nested iiRDS package" — is **R6**. It reports
a subject that is not an `iirds:Package` and that names a package this document
declares nested. Every reading of such a document breaks something: the parent's
reading breaks §5.3, the child's own breaks §6.2 ("MUST NOT be a member of
*another* iiRDS package"), and a reading in which neither package is this
container's breaks §5.1.1, which gives `META-INF` to "metadata on the iiRDS
package and its contents" exclusively. So the finding needs no decision about
which container is in hand — which is what separates it from a heuristic.

**R6 sees one triple pattern, and §5.3's sentence is wider.** A parent that
copies the child's units into its own `metadata.rdf` and omits the
`iirds:is-part-of-package` relations is describing the child's content and is
not reported. Measured: such a package draws nothing from R6. "Metadata about
the content" has no other graph form this could key on without guessing which
units belong to whom, so the rest of the sentence stays uncovered rather than
approximated.

A package nested inside a nested package is content too — §6.2 lists
`iirds:Package` among the subclasses of `iirds:InformationUnit` — but R5
already reports that shape under §6.3.3, and one triple should not draw two
findings under two requirement ids.

**What the archive settles, and what it costs.** The metadata cannot say which
container this is, but the archive can weigh in: §5.3 says nested packages "are
stored as iiRDS ZIP archives", §5.1.2 lists them among the content files below
the root directory, and §6.3.3 says "All nested iiRDS containers MUST be
included side by side in the iiRDS ZIP archive of the highest level iiRDS
package". So a document that declares a nested package while the archive
carries no nested container is broken whichever container it is: the parent's
reading breaks §6.3.3, the child's breaks §5.3. **R8** reports that, and its
evidence is §5.2's own description of an iiRDS ZIP archive read out of the
first local header — the extension alone is not the test, because a file named
`nested.iirds` holding sixteen bytes of anything would otherwise answer the
question and read as evidence.

The cost, named. "Side by side … of the **highest level** iiRDS package" can be
read as *flattening*: in P ⊃ C ⊃ G, both `C.iirds` and `G.iirds` sit at one
level inside `P.iirds`, and `C.iirds` on its own then legitimately carries no
nested archive. §8.3.1.2's "by nesting iiRDS ZIP archives **in each other**"
reads the other way, and this takes that one. Under the flattening reading R8
has one false report: a middle container in a chain three deep, validated on
its own. Nothing in reach has three levels — no corpus fixture, neither
official sample, no example in the specification — so the reading is a choice
made without a witness, which is why it is written here rather than assumed.

`#2` — "A nested iiRDS package MUST NOT contain metadata about the outer iiRDS
package" — is recorded as **undecidable from one container**, in a list kept
separate from the one for obligations addressed to reading applications. Its
antecedent is "a nested iiRDS package"; §6.2 says a conformant package's own
instance is not a member of another package, so a document declaring itself
nested is either the child breaching that sentence or a parent describing its
child, and the metadata does not distinguish them. Other sentences weigh
without settling it — §6.3 says the enclosing package is the subject of no
rendition, which is M8 — and so does the archive, which is a different
question. Neither list counts toward coverage and both are gated. What the archive
settles is a different sentence, not this one: R8 answers §6.3.3's "must be in
the archive", and knowing that a document is wrong somewhere is not knowing
that it is the nested package.

**The shapes are the 1.3 rule set and carry no version gate.** Twenty-nine
emitted shapes encode a rule that only iiRDS 1.3 carries, so running
`shapes/iirds-1.3/` against a package declaring an older edition reports rules
that edition does not have; the Python rules gate on the declared version and
stay silent on those. Gating the shapes would put an inference about editions
inside an artefact whose point is that a SHACL engine runs it without this
project's code, so the boundary is stated rather than papered over — and the
differential gate now measures it on a concrete graph instead of only ever
feeding itself 1.3 documents, which is why it had never seen this.

**What is left open, and why it is left.** The profile and the version are read
off the package this container is about, and a package the metadata says is
nested does not set them — the reason is written in the rule that does the
reading, and it is the false-reject direction: a nested child declaring the
handover profile would otherwise switch seventeen handover MUSTs on against a
container that never claimed to be one.

That reading has a residual, and it is not closed here. A container whose own
package declares the handover profile *and* declares itself nested inside an
outer package described in the same file is judged unrestricted. Three states
of that document are now separated:

| the archive carries | verdict |
|---|---|
| no nested container | R8 — a declared nested package that is not here |
| a file named `*.iirds` that is not one | R8, because the name is not the test |
| a real nested iiRDS container | no finding |

The third row passes, and this project does not claim to know how to close it.
At that point the container is, in everything observable from outside, a parent
carrying a child; the handover claim sits on a package the metadata says is
inside it rather than on this container, and §6.3.3 Example 16 puts a child's
own restriction in the child's own `metadata.rdf` — a file this validator does
not open. Widening the profile reading to elect the nested package instead
would not change that row either, and it would trade a certainty for an
inference in the one place where an inference is silent: the choice of profile
happens before any rule runs and produces no finding to disagree with.

The cost, named: a parent's `metadata.rdf` that misspells its own package's
IRI in the child's reference now draws M8 **and M3** on the child — M3 because
two packages are then representing this container. That graph already breaks
§6.3.3's "MUST reference exactly one `iirds:Package`" — it references zero —
so the defect is real and only the rule ids are approximate. A rule for that
sentence would retire the approximation; there is none yet, and §6.3.3 is at
1 of 4.

What does *not* accompany it: `iirds check` runs the conformance rules only,
and L1 — "relation points at an IRI that is never described in this package" —
is a lint rule. Under `iirds lint` it reports the dangling reference; under
the default subcommand nothing does.

The population is the graph's own subclass closure, not the ontology's,
because SHACL's `sh:class` sees only the data graph — the two encodings have
to be asking about the same nodes.

**What the standard leaves to §6.3.3, R5 now says.** §6.2 forbids only
membership in another package, so it does not make a self-loop a violation.
§6.3.3 does: "the referenced parent iiRDS container MUST NOT have any outgoing
`iirds:is-part-of-package` relations", and a package naming itself is its own
referenced parent with an outgoing relation. That sentence
(`x6-3-3-metadata-of-nested-iirds-packages#4`) had no rule here and none in the
reference catalogue, so a self-loop was for one release neither exempt from
anything nor reported by anything. It is reported now, under the id of the
sentence that says it, and the same rule catches a chain of three and two
packages each inside the other. It is version-gated to 1.3, because §6.3.3
exists in the cached 1.3 and not in the cached 1.0, and 1.1 and 1.2 are not on
hand to check.

The corpus carries exactly one such package,
`tests/corpus/plusmeta/files/metadata_iirds_sample-M5_false.rdf`. Its verdict
is unchanged in both directions: it is the only package in the file, it
carries no `iirds:has-rendition`, and it declares iiRDS 1.0, where M8 does not
apply. No catalogue pair names that file, so `docs/agreement.json` does not
move.

M8's shape stays SHACL Core, by counting rather than comparing. Core cannot
ask whether a value node differs from the focus node it hangs off — the
comparison components all compare one path's values against another path's at
the same focus. It does not have to: the value nodes of a **zero-or-one** path
are the focus node and its direct parents, they are a set so a self-loop does
not double it, and `sh:qualifiedValueShape [ sh:class iirds:Package ]` with
`sh:qualifiedMinCount 2` says exactly "there is a Package-valued parent other
than me".

Zero-or-*more* is wrong here, and only one graph in the suite can tell them
apart: a focus whose parent is an `iirds:Topic` that is itself part of a real
Package. The chain walk finds two Packages among the value nodes and exempts
the focus; §6.3.3 asks the child to reference an `iirds:Package`, one hop, not
a chain. That graph is pinned.

An earlier attempt moved the rule to `sh:sparql` on the belief that Core could
not express any of this, which would have cost a Core-only engine a MUST NOT
for nothing. M3 reads the same predicate through `sh:sparql`, and both of its
`FILTER NOT EXISTS` blocks carry the class test now — without it the two
encodings disagreed on every one of the five shapes above.

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
> `iirds:has-next-sibling` relating to an instance of the class `iirds:nil`.

"An instance of the class" is the sentence's own wording and `iirds:nil` is
declared `rdfs:Class`, so a package that mints its own terminator and types it
`iirds:nil` has done what the sentence asks; the sample packages instead point
straight at the class IRI. Both close a level here.

The rule does not claim `covers=x6-9-1-directory-nodes#3`, because it does not
cover all of it. A node nothing points at is a root, and M25 exempts roots --
tekom's own `iirds-sample-1` has twenty-seven directory nodes, exactly one
root, and that root carries no `iirds:has-next-sibling` at all, in every one
of the fifty-one fixtures built from it. A reading that made the requirement
reach the root would fail the Consortium's own sample, so the exemption stays
and the citation would be an overclaim.

Which cuts against the specification's own worked examples, and the tension is
worth stating rather than smoothing. Example 47 tells a consumer to *find* the
root by querying for the node whose `iirds:has-next-sibling` relates to
`iirds:nil`, and Example 48 says outright: "As the root directory node has no
following sibling on the same hierarchy level, it forms a linked list with only
one member. To close the linked list with only one element, the root directory
node has `iirds:nil` as the next sibling." On that reading a root is the last
node of the top level and the sentence reaches it. Against that: the sentence
opens "To model closed lists", which is purposive rather than unconditional,
and the Consortium ships packages that do not do it. Firing on tekom's own
sample needs better evidence than a reading, so the rule stays where it is and
the disagreement is recorded here instead of resolved in silence.

This paragraph was written before a mapping pass added the very claim it
refuses, and nothing read it — a document is not a gate. It is one now:
`tests/test_covers_is_earned.py` reads this file for the phrase "does not
claim `covers=…`" and fails if any rule claims what a paragraph here says it
does not.

Its only fixture, `Example 38 - Table of contents-M36_false.rdf`, is one of the
eleven that do not parse — `mismatched tag` at line 27. There is nothing to run,
so the rule here is neither confirmed nor contradicted, and it is listed as
`unclassified` rather than folded into one of the explained categories.

Repairing the fixture would settle it by supplying our own reading of what the
file was meant to contain, which is the one thing an oracle must not be. The
honest disposition is "no comparison possible", and the way out is a mutation
of a package we control, not a repair of a package we do not.

## M2.6 — one title, or one title per language? (open, raised from outside)

[iirds-validate#1](https://github.com/dev365code/iirds-validate/issues/1),
opened 2026-08-22 by Vladimir Alexiev, is the first defect report this project
has had from anyone else. It is a real one.

The shape and the Python rule both cap `iirds:title` at one value, and both
carried a remedy telling authors to write one title per language with
`xml:lang`. In RDF those are distinct terms, so the advice asked for precisely
what the constraint rejects. Both encodings agreed with each other and
contradicted their own sentence, which is exactly why the differential gate
between them stayed silent: it compares constraints, and this was prose.

The remedy is corrected. **Which half was wrong is not settled**, so the reading
is published here rather than decided.

**Read one way, the constraint is faithful.** Appendix A.1.1 gives
`0..1 iirds:title` for `iirds:InformationUnit`, and the ontology repeats it as
`Cardinality: iirds:InformationUnit [0..1]`. Section 6.10.1 models multilingual
content as one information unit per document language, each relating to the same
`iirds:InformationObject`; 6.10.2 relates those units with
`iirds:is-translation-of`. That machinery operates on units, not on titles, and
would be redundant if a unit could simply carry a title per language.

**Read the other way, the constraint is too strict.** `iirds:language` is
`0..*` on the same class, so an information unit is not modelled as monolingual.
Section 6.10.1 is a MAY, and it is about *content* language: a package whose
content is English only has no mechanism at all for carrying a German title for
a German-speaking consumer. And `iirds:title` is `rdfs:subPropertyOf
dcterms:title` with range `rdfs:Literal`, which includes `rdf:langString`. On
this reading `0..1` was written without language tags in mind.

Nothing in the specification says whether `0..1` counts RDF terms or titles, so
the question goes to tekom. Until it is answered the constraint stays: relaxing
it would make these shapes more permissive than the standard on a reading the
standard does not state, and the rule here is that a reading of ours is
published, not shipped as a MUST.

If the answer is that language variants count as one title, the shape the issue
proposes is the one to adopt — `sh:uniqueLang true` together with
`sh:qualifiedValueShape [ sh:datatype xsd:string ] ; sh:qualifiedMaxCount 1`.
The second half is the part that is easy to miss: `rdf:langString` and
`xsd:string` are different datatypes, so `sh:uniqueLang` alone leaves an
untagged literal uncapped.

## L13 — a name in the iiRDS namespace the standard does not define (open, warning)

Section 7.3 lists the conditions a proprietary extension MUST fulfil, and the
first is that proprietary classes, instances and properties *are registered to
the namespace of the defining party*. A name in one of the four iiRDS
namespaces that no iiRDS vocabulary defines is therefore one of two things: a
misspelling of a term the standard has, or a proprietary term registered to
the wrong party's namespace. Either way a consumer that looks it up finds no
class, no property and no label. Until this rule no rule asked the bundled
vocabulary whether an arbitrary iiRDS name exists — `is_iirds_term` tests the prefix,
which is what most rules want, and `is_defined` was applied to iiRDS IRIs
nowhere — so `iirds:relates-to-componnet` passed every rule, in the standard's
own namespace, where a reader has the least reason to doubt it.

**Why it is a warning and not the error the sentence would support.** Run
over the reference corpus, the rule names exactly two terms. One is the
corpus author's own negative fixture, `iirds:ThisIsNotAStandardizedDocumentType`,
which is the rule working. The other is
`iirds:EnvironmentalProtectionInstruction`, named in the core namespace by
fifty-one files — seven of them fixtures the catalogue marks as passing — where
the standard defines that term under `iirds/domain/machinery#`. The IRIs differ,
so the core spelling resolves to nothing in the published vocabularies; but
this is not a proprietary term in the wrong namespace, it is the standard's
own term under the standard's sibling namespace, and a widely used reference
implementation treats it as fine. Whether the four iiRDS namespaces are one
vocabulary for the purpose of resolving a name is the standard's editors'
question, not this project's, and it is on the list of questions to put to
them. Until it is answered the rule reports and does not fail a build; if the
answer is that a name resolves only in the namespace that defines it, L13
becomes a conformance rule covering that condition of section 7.3.

**What the rule does not do.** It does not judge names outside the four
iiRDS namespaces (L5 asks whether those are linked in), and it does not
check a term against the edition the package declares — every edition's
vocabulary is never smaller than the one before, 281 terms in 1.0 to 327 in
1.3 with nothing removed, so a name defined in any edition is defined in 1.3;
a term used ahead of the edition that introduced it is a separate reading.

**Measured.** The two sample packages the iiRDS Consortium publishes name
nothing this rule reports. The 1.3 specification's own Example 53 does:
`iirds:vdi2770` for the classification type the vocabulary spells `VDI2770`,
which the rule reports with that correction.

**What it cannot see.** A datatype IRI (`rdf:datatype="…iirds#Revison"`) is
inside a literal, not a term of the graph; and a JSON-LD key that no context
maps is dropped by the processor before any graph exists. Both are the
parser's, and both are below this rule.

## Where severity currently outruns the reading

The README's rule is that anything resting on this project's own reading is a
warning. Two places do not yet honour it, named here so the promise stays
checkable rather than aspirational:

- **L4** (navigation cycles) is reported as an error on this project's own
  authority: no specification sentence names cycles, but no consumer walking
  a cyclic structure terminates, and a defect that hangs the reader did not
  seem to belong at warning level. If tekom's answer to the open questions
  below settles it otherwise, it moves.
- ~~The Appendix B entry condition~~ **Corrected**: content findings now
  report as errors under iiRDS/A — whose whole point is restricting content to
  iiRDS XHTML5 — and demote to warnings under every other profile, where the
  standard permits any content and the entry condition is this project's
  reading. The rule keeps its MUST priority (the sentences are MUSTs); the
  *runner* assigns the severity, because only it knows the profile. So the
  list above is one item long: L4.

## `iirds:source` — a URL or a path? The standard says both, normatively


This is the reading behind `package.entry_named()`, which every rule that
looks for a file in the container goes through. It is a choice between two
normative sentences, and it costs something either way, so it is written
down here rather than left in a docstring.

**For "URL".** §6.3, the only place the standard says what the value *is*,
says it twice in one sentence, both MUSTs:

> To identify the physical file, the property `iirds:source` MUST relate the
> rendition to the **URL** of the physical file. The **URL** MUST be relative
> to the root folder of the iiRDS package.

And iiRDS 1.0 wrote two of its own examples as
`<iirds:source rdf:resource="rendition/intro.mpeg"/>`. `rdf:resource` holds
an RDF URI reference, so there the standard is putting the value in IRI
space itself — where a space in a file name has to be `%20`, because a
literal space cannot appear there at all. Both forms are gone from 1.3,
without comment.

**For "path".** Appendix A is normative too — §1 exempts only §2 and §4 —
and it defines the same property as the

> relative **path** of a file in an iiRDS package that contains the content
> of a rendition

with `Has Range: rdfs:Literal`. §5.1.3 calls the same object a path again.
A plain literal has no encoding layer: a producer with a file named
`a b.xhtml` writes `a b.xhtml`, because nothing in literal syntax asks for
anything else.

**What the corpus says: nothing.** Across the 97 that parse of the 130
vendored metadata documents, plus the three packages under `fixtures/`,
**1,395 `iirds:source` values carry no `%`, `#`, `?`, space or backslash** — and neither do the spec's own
examples in either release. Every real value available is spelled the same
under both readings. The corpus cannot decide this and neither can
cross-validation: the reference tool never resolves the value against an
archive at all.

**The reading taken here is "URL"**, on the strength of §6.3 being the only
sentence that says what the value is. So the value is percent-decoded and
its fragment and query are cut before it is matched against the container.

**What that costs.** §5.1.3 lists the characters a file or directory name
may not contain — `/,”*:<>\` — and `%` and `#` are not among them. So:

| character | legal in a name? | consequence of the URL reading |
|---|---|---|
| `:` | no | refusing a value that still holds one costs nothing |
| `\` | no | folding backslashes costs nothing |
| `%` | **yes** | a file named `a%20b.xhtml` cannot be addressed |
| `#` | **yes** | a file named `a#b.xhtml` cannot be addressed |
| `?` | yes as written | same, though the list is plainly a garbled Windows-reserved set and `?` is likely meant to be in it |

The quietest case is a directory legally named `%2e%2e`: the value
`content/%2e%2e/topic.xhtml` decodes to `content/../topic.xhtml` and names
a *different* file without complaining. `iirds`'s own test suite records
these three costs so they are not discovered by a user.

**What the fragment cut is not.** A rendition that addresses part of a file
does not put a fragment in `iirds:source`. §6.3.1 gives it
`iirds:has-selector`, and the worked example (1.3 Example 15, 1.0
Example 12) carries a whole-file `iirds:source` beside an
`iirds:FragmentSelector` holding `xpointer(...)`. The fragment is cut
because a URL's fragment is not part of its path, and for no other reason.

**One place this is neither reading.** A value beginning `//` is treated as
a path: `//content/a.xhtml` names `content/a.xhtml`. Under the URL reading
`//content` is an authority and the value would name `a.xhtml` — a
different file, silently. The authority is cut by hand rather than through
a URL parser precisely to avoid that, so the value is read as a URL
everywhere except the one place where doing so would resolve to the wrong
file.

**Not a security boundary.** Refusing a decoded `%2e%2e` escape aligns the
guard with the reading; it closes nothing. `iirds.Package.open()` tests
membership in the archive's entry list, and `DirectoryPackage` tests
membership in a set built by walking under its own root, so a value that
escapes never reaches a filesystem join in either project — encoded or not.

## Content rules: two readings the specification does not settle, and one it does

Appendix B has no counterpart in the reference tool — it reads only
`META-INF/metadata.rdf` and never opens a content file — so nothing here can be
cross-validated, which is why every entry below is recorded rather than
assumed. B4 and B8 are interpretation and are recorded as such rather than
presented as findings the standard compels. B10 is the opposite case and is in
this section because it used to be one of the three: the specification does
settle it, this document said otherwise, and the entry now says so. What
remains interpretation there is the exemption it grants, not the finding it
makes.

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

### B6 — the file extension is compared without regard to case

> The iiRDS XHTML5 content filename MUST use the file extension `.xhtml`.

B.3 writes the extension in lower case and section 5.1.3 says file names are
case-sensitive, so `.XHTML` is arguably a different extension and a breach.
The rule lower-cases before comparing, and therefore accepts it.

The reason is which mistake costs more. A package whose files end in `.XHTML`
is readable by every consumer that matches extensions the way every operating
system tool does; reporting it would fail a package nothing else objects to,
over the shift key. A package that genuinely uses the wrong extension --
`.html`, `.htm` -- is still reported, which is the case the sentence is about.

This is a spelling, so the claim on the sentence stands. It is one call to
`.lower()` if the Consortium reads it the other way.

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

### B1 — what counts as declaring an entity, and what an external DTD is

B.3 asks that content be a well-formed XML document, and a document declaring
entities is refused before it is parsed rather than reported after: the
billion-laughs shape has nothing invalid about it, so no rule would reject it
on its merits and the parser has to not meet it at all.

Two readings sit under that, and both are this project's.

**A declaration is what the grammar calls a declaration.** The refusal used to
search the whole document for the token, which the grammar permits in one
place only -- inside a doctype's internal subset. iiRDS is a documentation
standard, so a topic explaining XML syntax is an ordinary file, and a passage
quoting a declaration in a CDATA section or a comment was read as the thing it
described. Under iiRDS/A that is an error, so a package failed on a topic
documenting the format it ships in. The question is now put to the parser,
which decides the encoding without being told and knows where a declaration
may sit; the guard and the parser cannot disagree because they are the same
parser.

**An external DTD is not a declaration.** `<!DOCTYPE html SYSTEM "x.dtd">` may
name a file that declares entities, and this project does not refuse it. The
parser does not fetch it, so nothing can expand; and a parser that did fetch
would be reaching outside the package, which is a different promise with its
own rule. Refusing it would report a document for something that cannot
happen here. If a reader is ever met that resolves external DTDs, this is the
row to revisit.

### B10 — a missing *tag* is reported, and it is not an error

This entry used to say the opposite, on a false premise: that iiRDS does not
require the symbol in terms and that reporting its absence would mean importing
a requirement from ANSI Z535. iiRDS does say so in terms, in both editions this
project has read, one paragraph above the table B8 was already built from:

> If an iiRDS package contains content with hazard statements, then the iiRDS
> package MUST always provide the applicable safety alert symbols and signal
> words.

and immediately before the table, in 1.0 and 1.3 alike:

> A hazard statement consists of a safety alert symbol, a signal word, a
> message panel, and a symbol panel.

B9 reports a hazard statement with no signal word: nothing in it provides one,
which is the sentence, and it is silent on every piece of official material.

B10 is the other half, and it does not carry a MUST, because the sentence and
the check are not the same fact. The subject of the requirement is *the iiRDS
package* and the verb is *provide*. Both Consortium packages provide the
symbols — open the files and five of the eleven flagged statements hold the
yellow triangle with the exclamation mark, the rest another triangular ISO
sign. What is absent is the `data-role` saying which picture that is. Turning
"provide" into "tag it as a child of the signal word panel" rests on the note
above the table and the tagging example below it, and section 1 of both
editions puts notes and examples outside the normative text — the same rule
`tools/extract_requirements.py` applies when it counts obligations. So B10
reports at warning: the observation is real and useful, and it is a reading of
ours, which this document publishes rather than ships as a MUST.

**The narrowing.** B10 leaves `notice` alone, on iiRDS's own definitions rather
than a neighbouring standard's. The bundled ontology defines danger, warning
and caution each by personal injury, and notice as a "message that contains
information considered important but not related to personal injury" — so no
safety alert symbol is *applicable* to it, in the requirement's own word. The
sample packages draw the same line: a triangle on the eleven, a blue circle on
the four. The hazard level is read from the `data-role` value, never from the
signal word's text, which is written in the content's language.

**What this costs.** Eleven warnings on the Consortium's own packages — six in
sample 1, five in sample 2 — and no failures. An earlier version of this entry
shipped them as errors on the reading above, and the message it printed was
untrue of the packages it printed on: it said the symbol was missing where the
symbol was in the file, one `div` away. The cheapest way to clear that error
was to delete every `data-role` in the package, which is conformant, since the
attribute is a MAY — a remedy that destroys the machine-readable safety
tagging the rule exists to protect. A finding that can be answered by removing
information is pointed the wrong way, and that is the argument for warning.

The specification's own material passes: Example 43 in 1.0 and Example 46 in
1.3 are the same markup, and both put the tagged `img` inside the signal word
panel with an untagged picture in the symbol panel beside it. That example is
the one piece of iiRDS XHTML5 the authors of Appendix B wrote themselves, and
`tests/test_spec_examples.py` runs every B rule against it.

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
| 32 | silent — and the reference's own assertion passes too | its unit tests call `validateSingleRule` directly, bypassing the version and variant filters its product applies, so a fixture can be listed against a rule that does not apply to it |
| 9 | silent — the fixture does not parse | 9 pairs, whose fixtures are among the corpus's 11 malformed files; no comparison is possible, and none is repaired — see below |
| 13 | silent — gated by version or variant here | five of them because the fixture declares 1.1 while using vocabulary that arrives in 1.2; see above |
| 3 | silent — the defect exists only in the XML tree | two serialisations of one graph; there is nothing in the graph to report |
| 2 | silent — mismatched | the defect is reported, under a different rule id |
| 1 | silent — labelled **ours**, and mislabelled | M22.2: the defect *is* reported, as M22.1. See above — this is the worked example of what the classifier cannot do |
| 1 | silent — **unclassified** | M25, whose only fixture is one of the nine malformed |

No finding fires on a fixture the reference says should pass. Two did, both
M15.10, and both were this project's error rather than the reference's: the
rule asked an information object for a party section 8.3.2 hangs on its
identity domain. Correcting it emptied that category, which had existed since
the measurement began.

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

