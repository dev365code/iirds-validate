# The official sample packages, and what this tool says about them

iirds.org, the standard's site, lists one set of sample material on its
Materials page: the [iiRDS Sample Content](https://www.iirds.org/materials/sample-content),
which that page says was published on 17 October 2019. It is a ZIP behind free
registration, holding two packages and a description of them. The description
is © 2019 tekom e.V. and says the content is "not normative and … not part of
the iiRDS standard". The packages are built from the PI-Fan 1.1 documentation,
published under the MIT licence, and the description says that licence "must be
considered for further use of the iiRDS Sample Content Packages". Neither
package is copied into this repository. Each is named below by its SHA-256,
which the JSON report repeats as `packageDigest`, so a run can be matched to the
bytes it judged.

| Package | Declares | `iirds check` | `iirds lint` | Rules that fired |
|---|---|---|---|---|
| `iirds-sample-1.iirds` | iiRDS 1.0, iiRDS/A | exit 1 — 1 error, 6 warnings | exit 0 — 1 warning | M22.1 ×1, B10 ×6, L10 ×1 |
| `iirds-sample-2.iirds` | iiRDS 1.0, iiRDS/A | exit 1 — 1 error, 5 warnings | exit 0 — 1 warning, 5 info | M18 ×1, B10 ×5, L1 ×1, L8 ×5 |

Verdicts of version 0.9.1. `iirds all` runs both and reports their sum, and
exits `1` on each package. Exit `1` is at least one error and `0` none; a
warning moves it only under `-W`. Each package is judged against the edition it
declares: the rules that iiRDS 1.0 or iiRDS/A does not have stood down, and the
report's `notApplicable` lists them. The report also notes that this tool
bundles no ontology for iiRDS 1.0, so the class hierarchy it reads is 1.3's,
and a rule that depends on subclassing may differ from that edition.

Each error is a defect in the sample rather than in this reading.
[docs/divergences.md](divergences.md#the-consortiums-own-sample-packages-run-for-real)
quotes, from the 1.0 text the packages declare, the sentence each one breaks.
`tests/test_official_samples.py` holds every finding on this page, finding for
finding; it skips unless `IIRDS_SAMPLE_CONTENT` names the folder that holds
the two packages.

## `iirds-sample-1.iirds`

- In the Sample Content ZIP. 3,517,236 bytes, sha256 `9f5f90bfcdf9e9ff4babc2d3c5ad821070ed0b208283d028d60c243cf28e9bba`.
- The description: "An iiRDS/A package, containing all topics of PI-Fan for the X5-DH2 product variant in iiRDS XHTML5 format."
- Verdict, version 0.9.1: `iirds check` exit 1 — 1 error, 6 warnings; `iirds lint` exit 0 — 1 warning.

| Rule | Severity | Source | Reads from | Findings |
|---|---|---|---|---|
| M22.1 | error | catalogue | iiRDS 1.3 §6.2 Information Units, a MUST sentence | 1 |
| B10 | warning | this project | iiRDS 1.3 §B.6 Additional Semantic Tagging of Content | 6 |
| L10 | warning | this project | iiRDS 1.3 §A.1.1 Class Definitions | 1 |

## `iirds-sample-2.iirds`

- In the Sample Content ZIP. 2,713,076 bytes, sha256 `6a7d7fdff6c8ee7ba881fff19fa5dd8ae4caa3b753392902ac5732ef050846b0`.
- The description: "An iiRDS/A package, containing a collection of topics relevant for operation of the product."
- Verdict, version 0.9.1: `iirds check` exit 1 — 1 error, 5 warnings; `iirds lint` exit 0 — 1 warning, 5 info.

| Rule | Severity | Source | Reads from | Findings |
|---|---|---|---|---|
| M18 | error | catalogue | iiRDS 1.3 §6.2 Information Units, a MUST sentence | 1 |
| B10 | warning | this project | iiRDS 1.3 §B.6 Additional Semantic Tagging of Content | 5 |
| L1 | warning | this project | none — advice about what a consumer can resolve | 1 |
| L8 | info | this project | none — advice about what a consumer without network access cannot resolve | 5 |

**catalogue** is a rule catalogued by the reference tool, whose rule ids and
wording this project keeps ([THIRD_PARTY.md](../THIRD_PARTY.md)); **this
project** is this tool's own rule. The section is the one the rule links to in
the 1.3 text. `iirds rules <id> -v` prints any rule's source, the sentence it
reads and its remedy.

## Running it yourself

Register at iirds.org, download the Sample Content, unpack the ZIP, and run
the commands below from the folder that holds the two packages:

```
sha256sum iirds-sample-1.iirds iirds-sample-2.iirds
iirds check iirds-sample-1.iirds; echo $?
iirds lint iirds-sample-1.iirds; echo $?
iirds check iirds-sample-2.iirds; echo $?
iirds lint iirds-sample-2.iirds; echo $?
```

With this repository checked out, `IIRDS_SAMPLE_CONTENT=<that folder> python -m pytest tests/test_official_samples.py`
holds the same findings.
