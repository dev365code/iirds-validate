```
    _ _ ____  ____  _____
   (_|_) __ \/ __ \/ ___/                 ___    __     __
  / / / /_/ / / / /\__ \       _  _____ _/ (_)__/ /__ _/ /____
 / / / _, _/ /_/ /___/ /      | |/ / _ `/ / / _  / _ `/ __/ -_)
/_/_/_/ |_/_____//____/       |___/\_,_/_/_/\_,_/\_,_/\__/\__/
```

**A package can satisfy every rule in the [iiRDS](https://iirds.org)
specification and still be unreadable to whoever receives it.** This checks for
both, from the command line, on a machine with no internet connection, as a step
in a build.

```console
$ iirdsv dist/manual.iirds
manual.iirds   iiRDS 1.3
  ERROR M11       Rendition must have exactly one iirds:format
                      urn:example:rendition/7
  WARN  L1        relation points at an IRI that is never described in this package
                      urn:example:event/al-204
  FAIL  1 error(s), 1 warning(s)
$ echo $?
1
```

The error is a specification violation. The warning is not — nothing in the
standard forbids pointing at an IRI you never describe, and a consumer reading
that package silently loses the data. It happens in one of tekom's own sample
packages.

---

## Start here

**Nothing to install.** Copy one file in and run it:

```sh
python iirds-validate.pyz dist/
```

850 KB, contains `rdflib` and the iiRDS ontologies, compiles nothing, so the
same file runs on Linux, macOS and Windows. It is an ordinary zip: whoever has
to approve software entering the network can open it and read every line, which
is usually the hard part. Build it with `python tools/build_zipapp.py`.

**Or on the path:** `pip install iirds-validate`. One runtime dependency. For an
air-gapped install see [docs/offline-install.md](docs/offline-install.md).

**Then point it at something:**

```sh
iirdsv dist/manual.iirds      # a package
iirdsv build/manual/          # the same package before it was zipped
iirdsv dist/                  # every package under a directory
```

A path means "check it". No subcommand needed.

---

## The commands

| | |
|---|---|
| `iirdsv <path>` | check **and** lint — what you want most of the time |
| `iirdsv check <path>` | **does it conform?** container, metadata graph, content |
| `iirdsv lint <path>` | **will anyone else be able to read it?** |
| `iirdsv pack <dir>` | write a directory as a conformant `.iirds`, then check that |
| `iirdsv rules` | every rule, its priority, its versions, its source |

### In a build

```sh
iirdsv check dist/ || exit 1            # fail the build on any error
iirdsv dist/ --format json > report.json
iirdsv check dist/ -W                   # warnings fail it too
iirdsv check dist/ -q                   # exit code only
```

Exit codes: `0` clean, `1` findings, `2` could not run.

### From Python

```python
from iirds_validate import check, lint

report = check("manual.iirds")
for finding in report.findings:
    print(finding.id, finding.severity, finding.violation.message)
```

`report.as_dict()` is what `--format json` prints. Every finding carries
`source`, which is `catalogue` or `iirds-validate`, so a stored report stays
unambiguous even if the catalogue later mints an identifier this project
already uses.

### Flags

| | |
|---|---|
| `--format json` | machine-readable; the banner never appears in it |
| `--iirds-version 1.2` | validate against a version other than the declared one |
| `-W` | warnings fail the run |
| `-q` | exit code only |
| `-v` | print the specification link behind each finding |

---

## What makes it different

The [iiRDS Validation Tool](https://github.com/plusmeta/iirds-validation-tool)
by plusmeta is good and actively maintained, and its rule catalogue is the
foundation this project is built on — the rule identifiers here are deliberately
the same so results can be compared rule by rule. Use it to look at one package
by hand; that is what it is for. Everywhere the two disagree is written down,
with evidence, in [docs/divergences.md](docs/divergences.md).

Four things here are different.

**It asks whether the package will work, not only whether it conforms.** Ten
rules with no counterpart in the specification, because a conformant package
can still be undeliverable:

| | |
|---|---|
| L1 | a relation points at an IRI the package never describes |
| L2 | `iirds:source` names a file that was not packed |
| L3 | a directory node unreachable from any root — invisible in every viewer |
| L4 | a cycle in the navigation structure |
| L5 | a proprietary class not linked to any iiRDS class |
| L6 | a metadata value with no label a consumer could display or match |
| L7 | an information unit with no title |
| L8 | references out to vocabularies an offline consumer cannot resolve |
| L9 | the RDF/XML and JSON-LD metadata describe different graphs |
| L10 | an abstract iiRDS class used to type an instance directly |
| L11 | content named `.xhtml` but declared as another media type, so nothing checked it |
| L12 | two entries differing only in case, so one is lost when the package is unpacked |

**It checks the content.** Appendix B states 25 absolute requirements about
iiRDS XHTML5 — no scripting, no forms, no `<svg>`, a fixed element list, a
hazard-statement vocabulary — and no tool checked any of them. Every rule in the
reference catalogue reads `META-INF/metadata.rdf` and never opens a content
file, so a package can pass every conformance check that exists while its
documents cannot be rendered.

**It reads the graph, not the document.** iiRDS metadata is RDF, and RDF/XML is
not a canonical way of writing it down. These are the same statement:

```xml
<iirds:Document rdf:about="urn:d1"/>

<rdf:Description rdf:about="urn:d1">
  <rdf:type rdf:resource="http://iirds.tekom.de/iirds#Document"/>
</rdf:Description>
```

A validator that walks the XML tree sees the shape its own generator emits and
silently reports a clean package for the others.
`tools/serialisation_equivalence.py` takes a real package, rewrites its metadata
four ways and checks the findings are identical. The same property is what makes
`META-INF/metadata.jsonld` work at all.

**It runs where the packages are.** Unattended, in CI, behind an air gap, from a
single file that needs no installation. Exit codes, JSON, a library API. That
the alternative validates client-side is true and is not the same as never
loading the page: a hosted application is fetched fresh every visit, and "open a
browser tab to an external domain and feed it engineering documentation" is not
a request that passes review at a manufacturer.

---

## What it checks

```console
$ iirdsv rules
container  19/19    the ZIP and its layout
schema     135/135  the metadata graph  +2 of its own
system     3/3      the run itself  +5 of its own
content    -        iiRDS XHTML5 (Appendix B)  +8 of its own
lint       -        will a consumer be able to use it  +12 of its own
```

157 of 157 catalogued rules, plus 27 of this project's own.

| kind | catalogued | this project |
|---|---|---|
| container (C\*) | 19 / 19 | — |
| schema (M\*) | 135 / 135 | 2 |
| system (S\*) | 3 / 3 | 5 |
| content (B\*) | — | 8 |
| interoperability (L\*) | — | 12 |

Coverage of the catalogue is not coverage of the standard. The specification
states **314 absolute obligations**, counted by
[`tools/extract_requirements.py`](tools/extract_requirements.py) and listed in
[docs/requirements.json](docs/requirements.json) — 254 marked with an RFC 2119
keyword and 60 more stated as `0..1` in the property tables, which carry no
keyword at all and are obligations regardless. This README said 254 for months
with nothing behind it; the figure was right about what it counted and counted
the wrong thing.

That is the denominator, not a score. One rule can cover several statements and
several rules one statement, and some requirements are not machine-checkable at
all. Mapping the 314 to rules is not done, so **this tool cannot tell you what
share of the standard it checks**, and "no findings" must not be read as
"conformant". `iirdsv rules -v` prints the specification link behind each rule. Three of
the 157 are aliases of rules with identical wording, one is a `MAY` with nothing
to violate, and two are conditions the runner reports rather than rules it
evaluates.

### Versions and profiles

iiRDS 1.0, 1.0.1, 1.1, 1.2 and 1.3, and the unrestricted, `A` and `H` profiles.
The axes are independent — a rule can be 1.3-only, iiRDS/H-only, or both — and
every combination is exercised by the suite.

An `iirds:iiRDSVersion` the standard never published is a finding, not something
quietly rounded to the newest version, and an `iirds:formatRestriction` matching
no profile is a finding rather than a way to switch both rule sets off at once.
Only the 1.3 ontology is bundled, so validating against an earlier version
borrows its class hierarchy; the report says so when it happens.

---

## Directories, and packing one

A package spends most of its life as a directory, and checking it there finds a
defect in the thing you just made rather than in the artefact.

Five requirements are about the archive rather than the package — the `.iirds`
extension, `mimetype` first and stored uncompressed, no encryption, ZIP64 past
the limits — and cannot be assessed before there is one. The report says which,
rather than passing them in silence. `iirdsv pack` closes that:

```sh
iirdsv pack build/manual/ -o dist/manual.iirds
```

It writes the archive the way the specification requires, then validates what it
wrote. "First entry, stored uncompressed" is the requirement people get wrong
most often, and not through carelessness: `zip` manages it only with two
invocations and the right flags, most graphical tools cannot express it, and
`shutil.make_archive` gets it wrong every time. Packing the same directory twice
produces the same bytes, so "this archive came from that directory" is checkable
with `sha256` rather than taken on trust.

---

## Trusting the answer

the defect register is the register of every defect this
project has found in itself, and which instrument found it. It is the argument
for why there is twice as much test and tool code here as validator.

[docs/scope.md](docs/scope.md) is the map: what this is, what it deliberately is
not, where each thing lives, the four ways a validator can be wrong and which
instrument here finds which — and the list of what is still unresolved.


A validator's whole product is its verdict, and a wrong verdict is invisible
from the inside: it prints `PASS` and you learn nothing. So the evidence lives in
the repository.

- **Cross-validation, against a corpus that is in the repository.** The
  reference tool's own fixtures are vendored at the revision its rule catalogue
  came from, with a SHA-256 for each, so `tools/crossvalidate.py` and
  `tools/explain_silence.py` run offline and anyone can re-derive what is
  claimed below. Of the 103 rule/fixture pairs it says must fail, the expected
  rule fires here on 42; 34 more are cases where the reference does not report
  either, 11 are gated by version or variant, 9 are fixtures nobody can parse,
  and **4 are genuinely unresolved**.
  The full table, and why "65 of 66 fixtures produce some finding" is the
  flattering way to say this rather than the honest one, are in
  [docs/divergences.md](docs/divergences.md).
- **Every finding says what to do about it.** All 184 rules carry one imperative
  sentence naming the change, and `tests/test_remediation.py` refuses a rule
  that does not. A validator that names a defect and not the remedy has told
  you that something is wrong and left you the specification to search, which
  is most of the work and all of the expertise.
- **Every rule has been watched fire.** The suite records which rule ids
  actually produce a finding, and 183 of the 184 have — the remaining one is a
  `MAY` with nothing to violate. It began at 63. A rule that fires nowhere is
  not known to work: S8 spent months exactly backwards, able to fire only on
  archives that were correct, and no test would have caught it because no test
  made it fire. Line coverage would not have helped; its body ran and returned
  the wrong answer.
- **Deterministic output**, byte-identical across `PYTHONHASHSEED` values, so two
  runs can be diffed.
- **No network, tested rather than asserted.** A JSON-LD `@context` may be a URL
  and the parser will dereference it, so remote contexts are refused — inside a
  plant network that is not only a broken promise but a supplier choosing which
  host a machine behind the firewall connects to.
- **Integrity.** The bundled ontologies are checked against recorded SHA-256
  digests; `python -m iirds_validate.ontology --verify` does it from the
  installed copy.
- **CI.** Python 3.9 to 3.13, Windows, rdflib 6 and 7, the wheel installed into
  a clean environment, and the single-file form run with `python -S` so anything
  that works came out of the archive.

**What is not established.** The 23 rules this project invented have no second
implementation anywhere to be compared against. They have tests in both
directions, and those tests were checked by breaking each rule in turn, which is
weaker evidence than the catalogued rules have.
[docs/divergences.md](docs/divergences.md) records where this project is
deliberately stricter than the reference and why. Anything derived from this
project's own reading rather than a literal `MUST` is a warning, never an error.

If it reports an error on a package you believe is conformant, that is the most
valuable bug report this project can receive. Please open an issue with the
package or a reduced case.

---

## Contributing

A rule is its implementation and two tests; the metadata comes from the
catalogue. See [CONTRIBUTING.md](CONTRIBUTING.md). Four rules of the road, each
of which exists because it was broken once:

1. Never spell an iiRDS term inline. Add it to `terms.py`, where a test confirms
   it exists in the ontology.
2. Ask the graph, not the document. A rule that behaves differently on JSON-LD
   is wrong.
3. Every rule needs a package that violates it and one that does not.
4. Do not edit `data/ontologies/`. Verbatim redistribution is a licence
   condition and the hashes are checked.

## Licence

Apache-2.0 — see [LICENSE](LICENSE).

The bundled iiRDS ontologies are © tekom Deutschland e.V. / iiRDS Consortium
under **CC BY-ND 4.0** and are redistributed verbatim; the rule catalogue is
derived from plusmeta's MIT-licensed tool. CC BY-ND is not an OSI-approved
licence, so this distribution is not wholly open source even though the code is
— [docs/licensing.md](docs/licensing.md) explains what that means for you and
what would fix it. Provenance in [NOTICE](NOTICE) and
[THIRD_PARTY.md](THIRD_PARTY.md).

Not affiliated with, endorsed by, or certified by the iiRDS Consortium, tekom
Deutschland e.V., plusmeta GmbH or Quanos Solutions GmbH. "iiRDS" is used
descriptively to name the standard this tool validates against.
