# Changelog

The `iirds` library shipped on its own as 0.1.0 to 0.3.2; that history is in
[docs/library-changelog.md](docs/library-changelog.md). From here on, what
changes in the library is recorded beside what changes in the checker.

## 0.7.0 — unreleased

**A relation carrying text where a reference belongs (L16).** In RDF/XML the
two forms differ by one attribute: `<iirds:relates-to-party
rdf:resource="urn:x:party1"/>` points at a party, and
`<iirds:relates-to-party>party1</iirds:relates-to-party>` puts the string
"party1" in the graph and points at nothing. The relation is present, so the
rules asking whether it is there are satisfied, and the rules asking about its
target find a literal and step over it.

Twelve rules already say this about thirteen of the forty-six relations —
R10, R12, M17, M18, M22.2, M26, M94 and the five below — each as a MUST,
because for those the standard states the range obligation in a sentence of its
own. L16 is the same observation about the other thirty-three, where it states
none. Seven of the thirteen were seven when L16 was written; the number is
measured rather than listed, so adding those five moved it by itself. It is a
warning and claims no obligation: `rdfs:range` in RDF is an inference and not a
constraint, and the one general-looking range MUST, section 7.3.3's, is about a
proprietary property complying with the iiRDS property it refines. Coverage is
unchanged, which is the point of keeping "claimed" and "held" apart.

The rule reads the ontology's own word for what a relation is rather than a
list or a proxy. Every property the standard declares descends from
`iirds:iirdsRelationConcept` or from `iirds:iirdsAttribute`; the two sets are
disjoint and between them they are all of it. `iirds:title` and
`iirds:revision` are attributes and are left alone.

It reports against the edition the package is read as. Only the newest
ontology ships, so the forty-six are the same list whatever a package
declares — but eight of them are absent from iiRDS 1.0 and three from 1.2, and
a name the declared edition does not have is not one of its relations at all.
That is L15's sentence, and L15 reports it.

Over the corpus this repository vendors it finds ten, in nine files. Seven of
the ten are an empty element rather than a misspelt reference, so the rule says
which of the two a reader is looking at: "carries text where a reference
belongs" against "is empty, so it points at nothing", with a different repair
for each. A value with a datatype or a language keeps it in the finding —
`xsd:anyURI` is the one literal form that does carry a resolvable identifier.

**`iirds:ForeseeableMisuse` is no longer reported as a grouping class (L10).**
The ontology marks a class that should not be instantiated directly with a
sentence of its own, and this rule found it by looking for "not int".
`iirds:ForeseeableMisuse` is concrete, and its description is ordinary prose
beginning "Use of a product in a manner **not intended** by the producer or
supplier". The advice was impossible to follow — the class has no subclasses,
so the finding told the reader to retype the instance and could only offer
"define a proprietary subclass".

The marker is now the phrase every spelling shares. The ontology writes the
same sentence four ways — "Not intended", "Not intented", "Not indented" and
"No intended" — so the old substring read two of the four while matching prose
that negates something else; `iirds:iirdsRelationConcept` and
`iirds:relates-to-functional-metadata` were the two it missed. The shapes read
the corrected set from the rule instead of computing it beside it.

**Four sentences that name a class and a property now have both their rules
(R19–R21, R23).** A helper in this codebase says the shape out loud: *"MUST
have an X which is assigned by property P" — the X half. Three sentences of
chapter 6 have this shape and each needs two rules: one to count the property,
one to ask what it points at.* Three is what somebody found by reading.

The sharpest is the document type. A `iirds:Document` with no document type
fails; the same document naming its type as the string "OperatingInstructions"
**passed**. Writing text was better than leaving it out, which is the opposite
of what the sentence says. The other three are not verdict flips — a neighbour
reports those packages for another reason — but the finding a reader saw named
a sentence they had not broken and offered the repair for it.

**A fifth was drafted and withdrawn: `iirds:has-identity-domain` already had
its second rule.** M19.4 has been asking what that property points at all
along. The measurement that found this family probed with a literal, and M19.4
exempted any node the package does not describe — a literal carries no
statements, so a rule doing the job read as a rule that was missing, and a
second one was written beside it that fired on the same triple. What the probe
found was not a missing rule but two branches M19.4 was letting past: a
literal, and a term the ontology defines that is not a domain. Those belong to
M19.4, which now uses the family's shared helper instead of being a fourth
hand-written copy of it.

**Two exemptions were letting real defects through, in both encodings.** A name
in the standard's own namespace that the standard does not define — nobody
mints one by accident — was treated as a pointer at nothing and left to L1.
The reference corpus's own designated counterexample for the document-type
sentence points `iirds:has-document-type` at
`iirds:ThisIsNotAStandardizedDocumentType`, and the rule written to catch a
document type that is not a standardised one was silent on it. And a blank node
with no statements went to L1 too, which looks at IRIs only, so it was reported
by nothing at all.

**Coverage of the standard is 131 of 280, of which 96 are held by a package.**
Unchanged and up from 94: these rules claim nothing. Each was drafted claiming
the sentence it seemed to answer, and every one of those claims turned out
unearned — the reasons are recorded beside the rules, because each is a
distinct way of misreading a sentence that names a class and a property. What
did move is the audit: two cardinality sentences, "MUST point to exactly one
domain by the property", are now held by the package that has two domains.
They were briefly held by a package pointing at one domain of the wrong class,
which has exactly one and breaks the sentence after it rather than that one.

## 0.6.0 — 2026-09-05

Ten new rules, and a coverage figure that means something it did not mean
before.

**What the checker now reads that it did not.** Section 8.3.2 states six
product-variant sentences twice, once for `iirds:Package` and once for
`iirds:Document`; only the Document half had rules, so a handover package
could omit everything the Package list asks for and pass (R13–R16, one builder
read twice, so the two halves cannot drift). Section 6.8.2's "an X **which is
assigned by** P" was checked for the property and not for the type (R10).
Section 6.8.3's second limb — what a party's `iirds:relates-to-vcard` points
*at* — was unchecked (R12). Appendix A gives `iirds:IdentityDomain` at most one
`iirds:has-identity-type`, and a domain declaring two answered two of section
8.3.2's four questions with one party (R17). Section 7.1 requires a proprietary
extension used in a package to be *in* metadata.rdf, including when it is in a
side ontology under META-INF that section 5.1.1 tells consumers to ignore
(R11, R18). And appendix B forbids scripting in three ways, of which two were
checked: a URL whose scheme is a script is the third (B11).

**Coverage of the standard is 131 of 280, of which 94 are held by a package.**
The last release said 25 of 314. Those numbers moved for three reasons and
they are worth separating. The denominator is the published one now — 280
distinct obligations rather than 314 raw statements. The numerator grew
because the rules did. And fifty of it was there all along: appendix A states,
per class, that instances must have an IRI, and the generated table in
`src/iirds_validate/rules/schema_tables.py` — written *from that appendix* —
had never been told which of its rows each rule was answering. Those fifty are
claimed now, and each one is held by a package that breaks it rather than by a
name that matches. The second figure is the one to weigh. A `covers=` claim used to
be made by reading a sentence and a rule side by side; it is now made by
building the package that breaks the sentence and watching what happens, and
`tests/test_covers_is_earned.py` refuses a claim that has neither a
counterexample nor a place on the unaudited list.

**Two encodings, one answer.** The SHACL shapes and the Python rules are
compared package by package, and that comparison now includes how many
findings each reports: four graph-global checks were reporting one fact once
per participating node in SHACL and once in total in Python, so a consumer
counting errors was told a different number about the same package.

**Fixed.** A vcard reference that pointed at a name from a vocabulary drew two
findings from two rules, one of which told the reader to describe
`iirds:Topic` in their package. A finding from a rule that runs in every
profile announced itself as `iiRDS/H:`. `iirds:identifier` and
`iirds:classificationIdentifier` are declared `rdfs:range rdfs:Literal` by the
ontology and both encodings accepted an IRI in either. Two packages naming
each other as parent left the container with no corresponding
`iirds:Package` and nothing said so.

## 0.5.0 — 2026-09-03

The first release in which the checker and the library ship as one
distribution: `pip install iirds` installs both. The command is `iirds`;
`iirds-validate` and `iirdsv` are kept as aliases of it. The renaming changed
no rule, no rule identifier and not the `source` token a report carries;
three remedies that told a reader to run `iirdsv pack`, or to report a rule
that crashed, now spell the command's name and the issue tracker's address.
Four rules are new. L13, L14 and L15 are warnings: a package that passed
0.4.2 still exits 0 unless `-W` asks warnings to fail the run. S10 is an
error, about an archive no tool writes and one edit produces: it fails a
package only where the archive describes an entry two ways. One rule
reports less: C9 no longer fails an RDF/XML document
written without the `rdf:RDF` element, a form the grammar permits (see
*Fixed*).
The single-file form is `iirds.pyz`. `iirds-validate` and `iirds-sdk` stay on
PyPI as compatibility packages that depend on `iirds` at no less than their
own release — a floor now, where the alias used to pin one exact version, so
a later `pip install -U iirds` never conflicts with them. `iirds-validate`
installs nothing of its own; `iirds-sdk` keeps the `iirds_sdk` module it
published, which re-exports `iirds`. Tools that install by executable, such
as pipx and `uv tool`, want the name that has one: `iirds`.

**Upgrading from `iirds-validate` 0.4.x:** uninstall it first, then install
the new name with `-U` — `pip uninstall -y iirds-validate`, then
`pip install -U iirds`. Without `-U` the `iirds` library already present
satisfies the request and nothing new is installed. The order matters: pip
records each distribution's files separately and does not notice when two
records claim one path, so installing the new name first and uninstalling the
old one afterwards deletes files the new one had just written. If that has
already happened, `pip install --force-reinstall --no-deps iirds` restores
them.

### Added

- **An archive whose two records of an entry disagree is reported (S10).**
  A ZIP describes every entry twice, in a local file header before its data
  and in the central directory at the end. `zipfile` reads the directory,
  so that is the document every rule here judged; a consumer that reads
  the archive as a stream -- libarchive, Java's stream reader, anything
  fed from a pipe -- reads the local header instead, and `unzip` takes the
  checksum and the method from it. Where the two disagreed, this tool
  blessed the entry the directory described and a stream received the one
  the local header described, and nothing said so: seven bytes here, seven
  hundred there, every existing rule silent. S10 reads the local header
  where the directory says it is and reports the entry whose name, method,
  encryption or data-descriptor flag, crc-32 or sizes differ between the
  two records -- from the local header, or from the data descriptor it
  defers to -- and the entry whose data, as the directory describes it,
  runs into the next entry's header or the directory itself. What writers
  legitimately do differently is not a disagreement: the extra fields and
  timestamps, a data descriptor with or without its signature, ZIP64 sizes
  in an extra field or in an eight-byte descriptor, an archive with
  something prepended. The archives Python's stream writer, ZIP64 and a
  prefixed stub produce are the rule's negatives and stay silent, as do
  the Consortium's own sample packages.

- **A namespace that is nearly, but not, an iiRDS namespace is reported
  (L14).** `iirds/` for `iirds#`, `https` for `http`, `www.` in front: to
  every consumer a different vocabulary, so every name under it resolved to
  nothing -- and the package was reported as a set of proprietary classes
  not linked into iiRDS and a container declaring no package. True, and the
  wrong place to look. The finding names the namespace once, says how many
  names sit under it and how many of them the standard has, and which
  namespace was meant. Written the way the standard's own prose writes it,
  without the `#` -- so that every name runs into the namespace,
  `iirdsPackage` -- the namespace is reported as written and the names
  under it decide which one was meant, since by letters `handover#` is as
  near to `.../domain/machinery` as `machinery#` is; where several of the
  standard's namespaces begin with the one written -- the host alone, or
  `.../domain/` -- the names under it pick the one that defines them, and
  where none does all are offered rather than the shortest. `iirds#/` --
  one character past the separator -- is this finding, not eight unknown
  names under a namespace a prefix test
  took for the standard's; and the standard's host or vocabulary IRI on its
  own is not a name under anything. Anything on the standard's own host
  that is not one of its four namespaces is reported whatever its distance;
  the nearest legitimate foreign namespace in the reference corpus, read
  off the corpus in the test, scores below 0.6 against a line at 0.85.

- **The report says which layer a problem is in.** Metadata that names no
  iiRDS name at all -- the namespace misspelled, or a document that is not
  about iiRDS -- gets one note before every other, saying so and naming the
  namespace to check, before the findings that describe the absence and
  before the note that no version was declared, which is true of such a
  package and the wrong thing to read first. The footer's "21 not
  applicable" now says for what: "19 for iiRDS/H, 2 for other editions", or
  on a handover package "1 for packages that are not iiRDS/H"; `-v` lists
  them by rule, and `--format json` carries them under `notApplicable`.
  Read off the rules, not typed, and worded in the standard's profile names.

- **A name from a later edition of iiRDS than the package declares is
  reported (L15).** Only the newest ontology ships, so every package is
  judged against the 1.3 vocabulary whatever it declares: a package
  declaring 1.0 that uses `iirds:is-based-on` (1.3) passed every rule,
  since the standard does define the name -- and a consumer reading the
  package as 1.0 has no definition for it. The finding names the edition
  the name arrived in, once per name; forty-six names arrived after 1.0,
  fifteen in 1.1, eleven in 1.2, twenty in 1.3, and every one is pinned
  as an anachronism against a 1.0 declaration. The names are held to the
  edition the run validates against -- the declared one, or the one
  `--iirds-version` asked for, as with every version-scoped rule -- and
  the detail says which when they differ. A domain name is named with its
  domain: `Operation` is a core name since 1.0 and a handover name since
  1.3, and the finding about the second does not read as a claim about
  the first. The per-edition inventory, read off the Consortium's
  published schemas by `tools/version_inventory.py`, moves into the
  package for this, from `docs/`; no edition has ever dropped a name,
  which is what makes "defined from 1.2 on" one edition rather than a
  list, and a test holds the newest edition's list to the bundled
  vocabulary. A name no edition has stays L13's. What the rule cannot see
  is a value that is a literal: the profile `H`, which 1.3 introduced, is
  declared as one.

- **A name in the iiRDS namespace that the standard does not define is
  reported (L13).** The namespace was trusted and the name never was:
  `is_iirds_term` tests a prefix, and no rule asked the bundled vocabulary
  whether the name behind an arbitrary iiRDS IRI exists. So
  `iirds:relates-to-componnet`, a class spelled `iirds:Componentt` beside a
  real one, and a document type the
  standard does not have all passed every rule, in the standard's own
  namespace, where a consumer has the least reason to doubt them -- and
  found no class, no property and no label when it looked them up. The
  finding names the term once however often it occurs and, where a defined
  term is close enough, says which one was probably meant, as the whole IRI:
  the commonest case is not a misspelling but a term the standard defines in
  one of its domain vocabularies, named in core. The suggestion is measured:
  every defined term, mutated the ways names get mutated, is answered with
  the original or with nothing, never with another term -- a test holds
  that -- and the remedy fits the position the name stood in.

  A warning, not an error, on purpose. Fifty-one files of the reference
  corpus -- seven of them fixtures the catalogue marks as passing -- name
  `iirds:EnvironmentalProtectionInstruction` in core, where the standard
  defines it under machinery, and the 1.3 specification's own Example 53
  writes `iirds:vdi2770` for `VDI2770`. Whether section 7 forbids that is a question
  for the standard's editors, recorded in `docs/divergences.md`; the two
  sample packages the iiRDS Consortium publishes name nothing this rule
  reports.

### Fixed

- **A metadata.rdf written without the `rdf:RDF` element was rejected
  (C9).** The RDF 1.1 XML grammar, which the obligation C9 covers cites,
  lets a document start with `rdf:RDF` or with a single node element (§7.2.1;
  §2.6: "the rdf:RDF can be omitted although any XML namespaces must still be
  declared"). A file whose one top-level element was the package itself --
  three statements to every RDF parser, and the shape most of the standard's
  own examples are written in (with the namespace declarations the examples
  leave out) -- was reported as not an RDF document, with a remedy claiming
  no parser would read a statement from it. The rule now judges by
  the grammar: the document element is `rdf:RDF`, or its name is an absolute
  IRI outside the eleven names the grammar reserves. `<manual>` is still not
  RDF/XML -- a name with no namespace is not an IRI -- and says so with a
  remedy that is true.

- **Findings that only followed from a document not being RDF/XML were
  reported as the package's own.** rdflib reads `<manual>` as a class named
  `manual`, and the graph rules ran on that: "declares no iirds:Package",
  "proprietary class not linked into iiRDS" -- every finding true, every
  one a consequence of C9, and the note beside them said the graph rules
  could not run. The reader now refuses a document the grammar does not
  define, judged on the bytes it parses -- after the byte order mark has
  been honoured, so a UTF-16 or UTF-32 `<manual>` is refused like a UTF-8
  one -- and the report is C9 and S2, with the reader's reason in S2's
  detail. The same holds where the XML itself did not parse -- S2 says no
  metadata was usable, and "declares no iirds:Package" no longer fires on
  the empty graph beside it. `lint`, which runs no container rule, reports
  C9 the way it reports a parse failure, so a package nobody could read no
  longer lints clean. A document element the grammar reserves (`rdf:li`)
  is C9 as well, named as such, rather than a parse error in rdflib's
  words.

- **Links on the PyPI page led nowhere.** The README is the PyPI page too,
  and its nineteen links into the repository were relative -- `docs/scope.md`
  -- which PyPI resolves against itself, to a 404. They are absolute now,
  held so by a test, which also refuses a link to a file that is no longer
  where the link says.

- **Which package the version and the profile were read off.** That pair
  chooses the ontology and the applicable rules, so reading it from the wrong
  node changes what "valid" means for the whole run — before any rule runs.

  A package typed with a subclass it declares itself was not seen as a package
  at all, so it had no version and no profile, and every handover rule stood
  down: a package that fails one of them was reported clean. Section 7 permits
  exactly that typing and asks a consumer to treat the instance as its parent
  class, which the rules themselves already do.

  A package *inside* the package set the container's profile — a nested child
  declaring the handover profile switched seventeen handover MUSTs on against
  a container that never claimed to be one. That holds however deep the
  nesting goes: where a document carries a child and its parent but not the
  grandparent, the root of what is present answers, not whichever package
  sorts first.

  And the answer changed between runs. Graph order is not stable across
  processes, so the same bytes were judged against two different rule sets
  depending on the run. The version and the profile were also accumulated
  separately, so a run could answer with a pair no package in the container
  had ever declared. Both properties now come off one package, chosen under a
  fixed order.

- **Two blank nodes that said different things could be given one name.** The
  name is a digest of what the node says, and the digest joined its parts with
  a separator — so a value holding that separator and the text of a plausible
  neighbour spelled the end of its own field. Two packages then tied, and a
  tie left them in graph order, which is the order the naming exists to
  escape. The digest also left blank-node objects out entirely, so a package
  reaching a blank node and a package reaching nothing were one name too. A
  report could complain of two packages and name one of them twice.

- **A package declared part of itself claimed the exemption meant for nested
  children.** §6.3 says the package representing the enclosing container must
  not be the subject of `iirds:has-rendition`, and a package inside another
  package is exempt because it is content. That exemption was granted on the
  bare presence of `iirds:is-part-of-package`, so adding one triple pointing
  at the package's own identifier made the finding disappear — a MUST NOT
  switched off by a statement that cannot be true. §6.2 draws the line with a
  word: the container's instance must not be a member of *another* package.
  A package is a nested child when it is part of a different one now, and the
  same reading gives M3 back the case it was missing, where a self-looping
  package sits beside a genuine container.

  A parent has to be one. The exemption was granted on the bare presence of
  `iirds:is-part-of-package`, so an IRI nothing describes, a node typed
  `iirds:Topic`, a plain literal or an anonymous blank node each bought it —
  and one of those beside the self-loop re-opened the bypass the paragraph
  above closes. §6.3.3 asks the nested child's package to "reference exactly
  one `iirds:Package`", and both of its MUSTs are scoped to the parent
  container's own `metadata.rdf`, where the parent is required to exist. So a
  package is a nested child when it is part of a different package this graph
  describes as one. `docs/divergences.md` carries the reading, what it costs,
  and the fact that it reverses what that file said one release ago.

  M8's shape follows the same reading and stays SHACL Core. Core cannot
  compare a value node with the focus node it hangs off, but it does not need
  to: the value nodes of a zero-or-one path are the focus node and its direct
  parents, they are a set so a self-loop does not double them, and counting
  the Packages among them says "there is a Package-valued parent other than
  me". M3 reads the same predicate and moved with it.

- **L7 took its exemption away from the packages that use section 7.** A
  package is exempt from "every information unit should have a title", and the
  exemption was claimed by comparing types — so a package typed with a
  subclass it declares itself lost it and was reported for having no title,
  while the published shapes stayed silent.

- **L11 could not find the file every other rule found.** It reports a file
  named `.xhtml` that no content rule examined, and it resolved
  `iirds:source` its own way, so a spelling the other rules resolve was, to
  L11, a name matching no entry. It went quiet on exactly the packages it
  exists for.

- **A nesting chain, a cycle and a package inside itself are reported.** §6.3.3
  says the package a child names as its parent "MUST NOT have any outgoing
  `iirds:is-part-of-package` relations" — nesting in the parent container's
  metadata is one level deep. No rule here implemented that sentence and the
  reference catalogue has none for it, so all three shapes read as ordinary
  nesting and drew nothing. **R5** says it, under the id of the requirement,
  gated to 1.3 because that is the only edition on hand that carries §6.3.3.

- **A document that declares a nested package may not describe that package's
  content.** §5.3 carries two prohibitions on what a container may say about
  a package nested inside it, and both were recorded as checkable and
  unchecked. **R6** implements the second one. Its finding is compelled under
  every reading of an ambiguous document, which is what lets it be reported
  without deciding which container is in hand: read the file as the parent's
  and §5.3 is broken; read it as the nested child's own and §6.2 is broken
  instead, because a package's own instance must not be a member of *another*
  package; read it as describing a pair held somewhere else and §5.1.1 is,
  which gives `META-INF` to "metadata on the iiRDS package and its contents"
  exclusively. The shape is SHACL Core: keeping a package that names *itself*
  out of the nested set means comparing a value node with the focus node,
  which Core cannot do — but it can count instead, and two Packages among the
  values of a zero-or-one path is exactly "a Package parent other than me".

  **What it does not see.** R6 reports one triple pattern: a subject that is
  not a package, naming a package this document declares nested. A parent that
  copies the child's units into its own metadata and omits those relations is
  describing the child's content and draws nothing. The rest of §5.3's
  sentence stays uncovered rather than approximated, and `docs/divergences.md`
  says so. R6 is also version-gated to 1.3, the only edition on hand carrying
  the sentence, so a 1.1 or 1.2 document with the same defect passes in
  silence; what is known about those editions is that they had the nesting
  mechanism, not that they carried this prohibition.

- **A container that says it is inside another package is reported.** §6.2:
  "The corresponding `iirds:Package` instance of an iiRDS package MUST NOT be
  a member of another iiRDS package expressed by the property
  `iirds:is-part-of-package`." The sentence stands word for word since 1.0 and
  no rule here claimed it, so the commonest spelling of the nesting defect —
  a child container handed over on its own, still naming the parent it was
  packed inside — passed with **no findings at all**. **R7** reports it, on
  every edition. A package whose named parent is described in the same
  metadata is a nested child declared the way §6.3.3 asks and stays silent;
  so does a package naming itself, which is not another package and which R5
  already reports under the sentence that names that shape.

- **A declared nested package that is not in the archive is reported.** §6.3.3:
  "All nested iiRDS containers MUST be included side by side in the iiRDS ZIP
  archive of the highest level iiRDS package." **R8** is the one nesting
  question the metadata cannot answer and the archive can, and it needs no
  decision about which container is in hand either: a document declaring a
  nested package while the archive carries none is broken under the parent's
  reading (§6.3.3) and under the child's (§5.3). The evidence is §5.2's own
  description of an iiRDS ZIP archive, read out of the first local header —
  the file name alone is not the test, because a file called `nested.iirds`
  holding any sixteen bytes would otherwise answer it and read as evidence.
  The cost of one reading of "highest level" is named in
  `docs/divergences.md`.

- **A handover package that nests is refused.** Two sentences said it and no
  rule claimed either: "an iiRDS/H package MUST NOT contain another iiRDS ZIP
  archive" (§8.3.1.2) and "iiRDS/H packages MUST use this variant of hierarchy
  formation and MUST NOT contain nested packages" (§6.7.3). **R9** reports
  both sides this validator can see — a nested container in the archive, and a
  nested package declared in the metadata — because a package can breach
  either alone. Unrestricted packages are untouched: §8.3.1.2 opens by
  permitting nesting for them by name.
  193 rules, 142 SHACL shapes. Coverage of the standard: 25 of 314.

- **The sentence no single container can decide is recorded as such.** The
  other §5.3 prohibition — a nested package must not carry metadata about the
  outer one — cannot be decided from the metadata of one container. Its
  antecedent is "a nested iiRDS package", and §6.2 says a conformant package's
  own instance is not a member of *another* package, so a document declaring
  itself nested is either the child breaching that sentence or a parent
  describing its child, and the metadata does not distinguish them. Other
  sentences weigh without settling it — §6.3 says the enclosing package is the
  subject of no rendition, which is the rule M8 — and so does the archive. It
  moves to a second recorded-with-a-reason list, kept apart from the one for
  obligations addressed to reading applications so that "hard to check"
  cannot hide inside "not about the package". Neither list counts toward
  coverage and both are gated. Coverage of the standard: 21 of 314.

- **A hand-edited sentence in the published requirement index passed the whole
  suite.** `docs/requirements.json` is the enumeration the coverage figure is
  a fraction of and the thing every rule's `covers=` points at, so a wrong
  sentence there misattributes an obligation rather than merely reading badly.
  The re-derivation compared ids and counts and not the sentences, and the
  test named "the index records the fingerprint of its source" measured that
  fingerprint's *length* and compared it with nothing — so the index could
  name a source it had not been built from, which is the one thing a
  fingerprint is for. Both are closed, and both forgeries now fail. Because
  the specification is not redistributable and CI has no copy, `make check`
  refuses to skip these when the cache is absent, the way it already refuses
  to skip the differential gate.

- **`iirds serve` — a drop page on the machine you are already on.** The
  report has only ever existed as text on a terminal, and the people who build
  iiRDS packages are technical writers rather than people who read one. This
  serves one page on the loopback interface, takes a dropped `.iirds`, and
  shows the verdict `iirds <path>` would have printed. Literally that string:
  the handler calls the same renderer on the same report object in the same
  process, so there is no second implementation to keep in step and nothing to
  prove agreement about. Three things differ by construction and are now
  stated wherever the claim is: the page renders into a string and so never
  carries terminal colour; where a finding quotes the container's own path it
  quotes the handler's copy; and on Windows the command line's line endings
  are the platform's while the page's are `\n` — which the equivalence test
  found on a machine none of the reading had happened on. Flags — `-v`, `-q`, `-W`, `--format json`,
  `--fragment`, directories, several packages — belong to the command line.

  It refuses to bind to any address that is not loopback, refuses a POST that
  came from another page, logs nothing by default because a request line
  carries the name of somebody's document, and serves exactly one path.
  (An earlier version of this entry said the stdlib's default handler would
  have served the working directory. It would not: `BaseHTTPRequestHandler`
  has no `do_GET` at all — that is `SimpleHTTPRequestHandler`, which this
  deliberately is not. Without the check the page simply answers everywhere,
  which is a lie about what is there rather than a disclosure.)
  The name the browser sends is
  carried through verbatim, because the rule about the `.iirds` extension
  reads the container's file name and a handler that renamed the copy would
  decide that rule for every package it was handed.

- **The drop page speaks five languages and has a light/dark switch, and its
  parts live in one folder.** English, German, Korean, Japanese and Chinese
  for the page's own words, following the browser until the reader chooses;
  system, light or dark following the operating system until the reader
  disagrees with it; both remembered in that browser and nowhere else. **The
  report is not translated** — it is the command line's output word for word,
  and each language says so in its own words rather than leaving a reader to
  work it out. `data/web/` holds the page, the stylesheet, the script and the
  strings; they are assembled into the single response at request time, so
  splitting them for editing did not add a path to the server.

- **Fixed in the drop page, found by review**: a body whose declared multipart
  boundary appears nowhere in it crashed the request thread and printed a
  traceback — reachable from any page the reader had open, because that
  content type needs no preflight; a POST from another origin was answered
  instead of refused; a lying `Content-Length` parked a thread for ever with
  nothing to reap it; the upload limit bounded the body and not the memory,
  where the parse costs about eleven times what it reads; the policy header
  permitted inline code in general instead of naming this page's own; the
  banner volunteered the version; and a name whose trailing space matters
  reached the extension rule stripped — the page passed a package the command
  line fails, from the transport's own tidying rather than from the document.

- **A report died halfway through on a console that could not show one of its
  characters.** The remedy lines are marked with an arrow, and writing U+2192
  to a stream encoded in a legacy code page raises rather than degrades — so
  on a Windows machine outside an English locale the report stopped at the
  first remedy, mid-run, with a traceback where the rest of the findings
  should have been. The exit code was still 1, so a build reading only that
  saw nothing wrong, and a redirected report was silently truncated. The
  marker is now chosen by what the stream can encode: the arrow where it can
  be shown, two characters where it cannot. Reproduced with
  `PYTHONIOENCODING=cp1252` before it was fixed.

- **A dropped file no longer costs the process eleven times its size.** The
  upload was read whole and handed to a MIME parser that copied it several
  times over; measured, a sixteen-megabyte body moved the process's peak by
  a hundred and eighty. The body is streamed to disk as it arrives now, the
  part headers read and then the payload copied chunk by chunk up to the
  closing boundary — which can straddle two chunks, so a tail the length of
  the delimiter is held back from each flush and the scanner is tested at
  every offset around the chunk edge, byte for byte. The same body now moves
  the peak by one megabyte. The upload limit, which had been lowered to
  thirty-two megabytes as a bandage over the parse, is back at a quarter
  gigabyte.

- **The drop page checks a bounded number of files at once.** A thread per
  request with nothing above it: measured, thirty-two posts left forty-six
  threads standing, each a whole validation run. The same-origin check keeps
  other pages out, but the page's own reader can drop a folder of files, and
  a folder is not an attack. Four run at a time now and the rest wait for a
  slot — their bodies are already on disk, which is cheap, and the reader
  asked for them. A checker that crashes gives its slot back, which is stated
  as a test rather than trusted: the quiet alternative was one bad drop
  eating a slot for the life of the process.

- **A rendition is decompressed once per run, and a run states a ceiling on
  what it will decompress in total.** Measured: one rendition was read four
  times — once to refuse or accept it, once to parse it, and the same pair
  again by a second rule, because the bytes were never kept after the first
  look. Forty one-megabyte renditions in an archive that compresses to
  nothing made the run read a hundred and sixty megabytes. The bytes are
  memoised on the run now, and per-entry limits are joined by a total —
  half a gigabyte by default, `IIRDS_CONTENT_BUDGET` to change it. **S9**
  reports the first rendition the ceiling stopped at, with the numbers, and
  says that the renditions from there on were not examined; a report that
  fell silent on them would have read as a pass. 194 rules.

### Changed

- **Where two packages both represent the container, the one declaring the
  newer version answers.** M3 reports the pair either way, so the package does
  not pass — what the choice decided was whether the *other* defects in it
  were looked for, and taking whichever sorted first let a package declaring
  1.0 win an alphabetical tie-break and stand every 1.1+ rule down. A plain
  §6.3 violation beside it went unreported. A package declaring nothing ranks
  as the newest, because that is already what a missing version means.

- **A package declaring two versions is judged against the newest of them**,
  not the lowest. M4 reports the pair either way; what the newer reading keeps
  is the finding. A 1.3 package breaking a 1.1+ MUST could otherwise silence
  that finding by declaring 1.0 beside its own version, and a missing version
  already falls back to the newest for the same reason — nothing passes by
  silence. Versions are compared as numbers rather than as text.

- **L2 says which of three silences it met.** A source naming somewhere
  outside the container, one naming nothing, and one climbing out of the
  package are different things, and all three were reported as "escapes the
  package root". L2 now stays quiet about the first — that is M9's finding,
  and it is not a path that went wrong — and names the other two.

- One vendored fixture is now reported with no declared version instead of
  `1.0`. Its first package deliberately omits the property — its own comment
  says so — and the `1.0` came from a second package beside it. The findings
  are the same at either version.

### Fixed in the library

- **`pack()` refused to run under the convention it exists to support.**
  `SOURCE_DATE_EPOCH=0` is the commonest value a reproducible build is given,
  and a ZIP cannot carry a date before 1980, so the packer raised instead of
  packing. A value large enough for `OverflowError` escaped the guard
  entirely and reached the archive as a year in the millions. The stamp is
  clamped to what the format can hold, which keeps the promise the variable
  makes — two builds of one tree agree — where refusing kept nothing.

- **A metadata document was refused on a size nobody had measured.** The gate
  read the uncompressed size out of the ZIP directory, which is written by
  whoever built the archive: a few hundred bytes could be announced as a
  gigabyte and turned away, and the message named a limit and a length that
  had never been read. The read is bounded and the bytes are counted now, and
  where the directory disagrees with what is there the refusal says that
  instead — a directory that does not describe its contents is the defect,
  not an oversized document.

- **Writing the metadata for an ordinary manual took most of a minute, and
  nearly all of it was the self-check.** The bytes are parsed back and
  compared against the graph they came from, which is what makes the write
  trustworthy; the comparison asked rdflib whether the two graphs were
  isomorphic, and that is priced for the general case. iiRDS nests a
  rendition inside every information unit, so a few hundred topics is a few
  hundred blank nodes: doubling the topic count multiplied the time by four
  to six, reaching about forty-three seconds at eight hundred topics — by
  which point the check was ninety-seven per cent of what writing cost.

  Where the blank nodes form a forest — none shared, none in a cycle, which
  is every metadata document in the vendored corpus — the same answer comes
  from naming each blank node by a digest of the subtree hanging off it and
  comparing the triples with those digests standing in for the labels. Under
  that condition the two comparisons agree by construction, and where it does
  not hold the graph goes to the general check unchanged. The self-check is
  not weakened and is not optional; the same eight hundred topics now write
  in well under a second.

- **`iirds:source` is now read as the URL §6.3 calls it.** That section says
  twice, normatively, that the property relates a rendition "to the URL of
  the physical file" and that "the URL MUST be relative to the root folder".
  Read as a literal path instead, a file named `a b.xhtml` and referred to
  as `a%20b.xhtml` answered "no such entry" while sitting right there. The
  value is now percent-decoded and its fragment and query cut before it is
  matched.

  This is a choice, not a fact: Appendix A calls the same value a "relative
  path of a file" with range `rdfs:Literal`, and §5.1.3 permits `%` and `#`
  in a file name — so a package naming a file `a%20b.xhtml` or `a#b.xhtml`
  is entitled to, and this reading cannot reach it. `iirds-validate`'s
  `docs/divergences.md` carries the evidence on both sides, and tests here
  record the cost rather than leaving it to be discovered.

  §5.1.3 settles the cheaper half outright: a colon may not appear in a file
  name, so a value still holding one after decoding names nothing in this
  container. `http://…`, `mailto:…` and `urn:uuid:…` answer `None` instead of
  a path assembled out of the URL. `open()` now distinguishes the three
  silences that answer `None` — no source, an empty one, and one naming
  something that is not an entry here — instead of reporting a missing
  declaration that is not missing.

  `source_of()` resolves case for case with `iirds-validate`, which the
  docstring claimed while several readings differed.

- **`pack()` could write a package `open()` refuses.** The check for metadata
  asked the filesystem, and a case-insensitive one answers yes for a file
  spelled another way; the archive then carried the spelling from disk, which
  a reader looking for the name the standard gives does not find. The question
  is put to the names about to be written instead.

- **A file whose name was stored decomposed did not match the metadata that
  refers to it.** Several tools create names in that form, and the RDF beside
  them is composed, so one file had two byte strings and a lookup by the name
  in the metadata missed it. Members are stored composed; two names that would
  collide once composed are refused rather than silently reduced to one.

- **A failed pack destroyed the package it was replacing.** The archive was
  opened for writing before anything had been read, so a failure part-way
  through left the part already written — and that remainder is not obviously
  broken: it carries a central directory, passes an integrity check, opens,
  and reports its version while missing most of its content. It is written
  beside the destination now and moved into place only once it is whole.

- **A symbolic link in the packed directory put bytes from outside the
  package into the delivery.** `is_file()` answers for the far end of a link,
  so whatever it pointed at was read and written into the archive, quietly. A
  link to a directory was the same silence facing the other way: the walk does
  not descend through one, so a folder present in the source was absent from
  the package. Links are refused now, naming the ones found — following or
  skipping are both decisions about the delivery that belong to its author.

- **The dependency allowlist swept one directory, not the package.** The
  check that keeps this package's third-party dependencies down to rdflib
  walked `src/iirds/*.py`, which reaches every module only because the
  package is one flat directory today. The first subpackage would have
  carried any import at all past the allowlist with nothing to say so. It
  walks the tree now, and the walk itself is tested against a tree that has a
  subpackage, which the real one does not.

### Changed in the library

- **`parse_metadata` refuses a well-formed XML document that is not
  RDF/XML.** The grammar's document starts with `rdf:RDF` or with a single
  node element (RDF 1.1 XML Syntax §7.2.1, §2.6); rdflib reads anything
  else -- `<manual>`, an element in a namespace that is not an IRI, a root
  the grammar reserves -- into a graph nobody wrote. The reader now returns
  `(None, "<name>: not an RDF/XML document: <why>")`, judged on the decoded
  bytes so that the encoding cannot hide the document element, and
  `Package.parse_errors` and `metadata_sources` say so; `Package.graph`
  raises as it does for every refusal. The category is exported as
  `NOT_RDFXML`, the judgement as `is_rdfxml_document_element()`, and the
  scheme test both use as `is_absolute_name()`. A validator built on the
  library reports the same document the same way this one does.

- **A warning from this package's own code fails the suite.** Warnings were
  collected and printed at the end of a run, where one that means something
  is indistinguishable from the eleven that do not. They are errors now, with
  one exception scoped to rdflib, whose JSON-LD parser warns about its own
  deprecated internals on every parse — scoped to where the warning comes
  from rather than to its wording, so the dependency rephrasing its message
  does not turn this suite red. Expected failures are strict and unregistered
  marks are refused, both for the same reason: a test that silently applies
  to nothing is worse than no test. The settings are checked by tests that
  provoke the behaviour, because a configuration table is the one part of a
  suite that nothing else exercises.

## 0.4.2 — 2026-08-26

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

- **A file the container is judged to contain is now a file the content rules
  read.** Two layers resolved `iirds:source` separately and disagreed, so one
  value could be present to the rule that reports missing files and absent to
  the rules that would open it — a topic carrying a script drew no finding at
  all, while a reader holding the same package opened the file without
  trouble. One resolution answers for both. It follows the specification in
  calling the value a URL, so percent-encoding means what it says; it folds
  backslashes, because that is what a reader does with them; and it no longer
  reads `//content/a.xhtml` as naming a host called `content`, which had been
  resolving that value to a different file.

- **A document that described an entity declaration is no longer refused for
  making one.** The refusal matched the token anywhere in the bytes, and the
  grammar allows a declaration in one place only, so a topic explaining XML
  syntax -- an ordinary file in a documentation standard -- was turned away,
  and under iiRDS/A that is an error. The question is now put to the parser,
  which decides the encoding without being told and knows where a declaration
  may sit. A doctype naming an external DTD passes: nothing fetches it, so
  nothing can expand. docs/divergences.md carries both readings.

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
