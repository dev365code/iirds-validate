| Axis | Now | 1.0 condition |
|---|---|---|
| Coverage | 172 of 280 obligations covered | at least 220 of 280 covered |
| Explanation | what, evidence, remedy | + every rule names its section, the line |
| Report contract | schemaVersion, golden, exit codes | + a field-by-field schema page |
| Entrances | command line, library, single file | + GitHub Action, browser |
| Input safety | read budgets, advisory, mutations | + declared encodings read without loss |
| Upstream | pinned, checked weekly, one pin move shipped | met |

**Explanation** — 3 of 5:
- what is wrong, in one sentence — done (`README.md`: "what is wrong")
- the evidence as read from the file — done (`README.md`: "the evidence as read from your file")
- a remedy, for every rule — done (`README.md`: "A rule without a prescription does not ship")
- every rule names its section, or says it has none — not yet
- the line in the file — not yet

**Report contract** — 3 of 4:
- schemaVersion in every report — done (`README.md`: "The report is a document with a `schemaVersion`")
- a golden report held by a CI check — done (`.github/workflows/ci.yml`: "the stored report is the one this tree produces")
- exit codes 0, 1, 2 and 64 under test — done (`README.md`: "`64` when the argument parser rejected the command line")
- a field-by-field schema page — not yet

**Entrances** — 3 of 5:
- command line — done (`pyproject.toml`: "iirds = "iirds_validate.cli:main"")
- Python library — done (`README.md`: "import iirds, iirds_validate")
- single file, nothing to install but Python — done (`README.md`: "one file, no install")
- GitHub Action — not yet
- browser, nothing installed — not yet

**Input safety** — 3 of 4:
- read budgets per file, and per run for content — done (`SECURITY.md`: "Across one run, what the content rules read is held to a total ceiling")
- from 0.6.1, a shipped security fix has an advisory — done (`SECURITY.md`: "a security fix that ships in a release has a GitHub security advisory")
- tests of named gates verified against mutations — done (`.github/workflows/ci.yml`: "python tools/mutation_table.py --run")
- declared encodings read without loss — not yet

**Upstream** — 3 of 3:
- upstream catalogue pinned by commit — done (`README.md`: "catalogue taken from")
- checked weekly for change — done (`README.md`: "whether upstream still matches it is a weekly job")
- one pin move shipped — done (`CHANGELOG.md`: "The vendored rule catalogue and the reference corpus move to a newer upstream commit")

Before it calls a release 1.0, this project asks of itself — Coverage: at least 220 of 280 covered; Explanation: what is wrong, in one sentence · the evidence as read from the file · a remedy, for every rule · every rule names its section, or says it has none · the line in the file; Report contract: schemaVersion in every report · a golden report held by a CI check · exit codes 0, 1, 2 and 64 under test · a field-by-field schema page; Entrances: command line · Python library · single file, nothing to install but Python · GitHub Action · browser, nothing installed; Input safety: read budgets per file, and per run for content · from 0.6.1, a shipped security fix has an advisory · tests of named gates verified against mutations · declared encodings read without loss; Upstream: upstream catalogue pinned by commit · checked weekly for change · one pin move shipped.
