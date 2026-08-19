# iirds-validate

Validate [iiRDS](https://iirds.org) packages from the command line, on a machine
with no internet connection, as a step in a build.

```console
$ iirdsv check build/manual.iirds
manual.iirds   iiRDS 1.3
  ERROR M11       iirds:Rendition must have iirds:format
                      urn:example:rendition/7
  PASS  1 error(s), 0 warning(s), 0 note(s)
$ echo $?
1
```

Two commands, because there are two different questions:

| | asks |
|---|---|
| `iirdsv check` | **is this package conformant?** container structure and the metadata graph, against the rules in the specification |
| `iirdsv lint` | **can anyone else read it?** dangling references, missing content files, orphaned navigation, values with no label |

A package can pass `check` and fail `lint`. That combination is not a
contradiction — it is the most common way an iiRDS handover goes wrong, and it
is why the second command exists.

## Install

```sh
pip install iirds-validate
```

Offline, which is the case this tool is built for:

```sh
# on a machine with a network
pip download iirds-validate -d wheels/

# on the machine without one
pip install --no-index --find-links wheels/ iirds-validate
```

One runtime dependency (`rdflib`). The iiRDS ontologies are bundled, so nothing
is fetched at validation time — see [docs/offline-install.md](docs/offline-install.md).

## Use it in a build

```sh
iirdsv check dist/*.iirds || exit 1                 # fail the build
iirdsv all pkg.iirds --format json > report.json    # machine-readable
iirdsv check pkg.iirds -W                           # warnings are errors too
```

Exit codes: `0` clean, `1` findings, `2` could not run.

```python
from iirds_validate import check, lint

report = check("manual.iirds")
if not report.ok:
    for finding in report.findings:
        print(finding.id, finding.violation.message)
```

## Why not the existing tool

The [iiRDS Validation Tool](https://github.com/plusmeta/iirds-validation-tool)
by plusmeta is good and actively maintained. Use it for interactive checking —
it is the right tool for looking at one package by hand. Its rule catalogue is the
foundation this project is built on, and the rule identifiers here are
deliberately the same so results can be compared.

It is a browser application, and that has consequences this project addresses:

**It cannot be a build step.** Someone has to open a page and drop a file on it.
There is no exit code, no JSON, no library. You can build the app and carry the
static files into a closed network, but a human still has to click.

**It reads the XML tree, not the graph.** Its assertions run
`document.querySelectorAll("Document, Topic, Fragment, Package")` over
`META-INF/metadata.rdf`. RDF/XML has several legal ways to say the same thing,
and a CSS selector only sees one of them:

```xml
<iirds:Document rdf:about="urn:d1"/>                       <!-- matched -->

<rdf:Description rdf:about="urn:d1">                       <!-- not matched -->
  <rdf:type rdf:resource="http://iirds.tekom.de/iirds#Document"/>
</rdf:Description>
```

Both are conformant iiRDS. A package written the second way passes with no
information-unit rule having run at all. `tests/test_serialisation_blindness.py`
pins the behaviour this project guarantees instead: the same package written
three ways — element style, description style, JSON-LD — produces byte-identical
results.

**JSON-LD is barely checked.** iiRDS 1.3 accepts `META-INF/metadata.jsonld`. The
existing tool confirms the file parses and stops; all 135 schema rules read
`metadata.rdf` and skip a JSON-LD package entirely. Here both serialisations
parse into the same graph and get the same rules.

Every place the two tools disagree is recorded, with evidence, in
[docs/divergences.md](docs/divergences.md) — including the places where the
reference tool's implementation does not match its own rule text, and the
places where this project was wrong until its corpus said so.

**A missing version declaration passes silently.** Rules are filtered by the
declared `iirds:iiRDSVersion`; when it is absent the filter matches nothing, no
rules run, and the report is clean. This tool falls back to the newest version,
records the assumption in the report, and reports the omission as a finding.

## Coverage

Honest numbers, printed by `iirdsv rules`:

| kind | implemented |
|---|---|
| container (C\*) | 19 / 19 |
| schema (M\*) | 135 / 135 |
| system (S\*) | 3 / 3 |
| **catalogue total** | **157 / 157** |
| interoperability (L\*) | 9 — this project only |

All 157 catalogued rules are implemented. That is coverage of the catalogue,
not a certificate: three of them are aliases of rules with identical wording,
one is a MAY with nothing to violate, and two are conditions the runner reports
rather than rules it evaluates. `iirdsv rules` lists every one, and
`tools/serialisation_equivalence.py` is the check that matters more than the
count — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Interoperability rules

These have no counterpart in the specification. They exist because valid
packages still fail in practice.

| id | what it catches |
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

L1 is the one that started this. RDF lets the same fact be written inline or as
a reference; both are conformant; a reader that handles only one of them loses
data without any error. No conformance checker will ever report it, because no
rule is broken.

## Versions and profiles

iiRDS 1.0, 1.0.1, 1.1, 1.2 and 1.3 are supported, and the version and profile
axes are independent — a rule can be 1.3-only, iiRDS/H-only, or both. Everything
1.3 added to the rule set belongs to the handover profile (iiRDS/H), so on an
unrestricted package 1.2 and 1.3 check identically. Override detection with
`--iirds-version 1.2` when you need to.

## Licence

Apache-2.0 — see [LICENSE](LICENSE).

The bundled iiRDS ontologies are © tekom Deutschland e.V. / iiRDS Consortium
under **CC BY-ND 4.0** and are redistributed verbatim; the rule catalogue is
derived from plusmeta's MIT-licensed tool. CC BY-ND is not an OSI-approved
licence, so this distribution is not wholly open source even though the code
is — [docs/licensing.md](docs/licensing.md) explains what that means for you
and what would fix it. Provenance in [NOTICE](NOTICE) and
[THIRD_PARTY.md](THIRD_PARTY.md).

Not affiliated with, endorsed by, or certified by the iiRDS Consortium, tekom,
plusmeta GmbH or Quanos Solutions GmbH. "iiRDS" is used descriptively to name
the standard this tool validates against.
