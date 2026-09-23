| Axis | Now | 1.0 condition |
|---|---|---|
| Coverage | 172 of 280 obligations covered | at least 220 of 280 covered |
| Explanation | what, evidence, remedy | + a section for every rule, and the line |
| Report contract | schemaVersion 2, golden, exit codes | + a field-by-field schema page |
| Entrances | command line, library, single file | + GitHub Action, browser |
| Input safety | read budgets, advisories, mutation-tested | + lossless declared encodings |
| Upstream | pinned, checked weekly, a move shipped | met — a pin move has shipped |

**Explanation** — 3 of 5:
- what is wrong, in one sentence — done (`README.md`: "what is wrong")
- the evidence as read from the file — done (`README.md`: "the evidence as read from your file")
- a remedy, for every rule — done (`README.md`: "A rule without a prescription does not ship")
- the section of the specification each rule enforces — not yet
- the line in the file — not yet

**Report contract** — 3 of 4:
- schemaVersion in every report — done (`docs/golden-report.json`: ""schemaVersion": 2")
- a golden report held by a test — done (`tools/golden_report.py`: "--check")
- exit codes 0, 1, 2 and 64 under test — done (`README.md`: "`64` when the command line was the problem")
- a field-by-field schema page — not yet

**Entrances** — 3 of 5:
- command line — done (`pyproject.toml`: "[project.scripts]")
- Python library — done (`README.md`: "import iirds")
- single file, nothing to install — done (`README.md`: "one file, no install")
- GitHub Action — not yet
- browser, nothing installed — not yet

**Input safety** — 3 of 4:
- read budgets, per file and per run — done (`SECURITY.md`: "Every limit in the table above is a limit on")
- a security fix ships with an advisory — done (`SECURITY.md`: "A security fix that shipped in a release has a GitHub security advisory")
- tests verified against their own mutations — done (`README.md`: "verified against their own mutations")
- declared encodings read without loss — not yet

**Upstream** — 3 of 3:
- upstream catalogue pinned by commit — done (`README.md`: "catalogue taken from")
- checked weekly for change — done (`README.md`: "whether upstream still matches it is a weekly job")
- one pin move shipped — done (`CHANGELOG.md`: "taken from `f1119bea`, retrieved 2026-09-13, instead of `0bcf19dd`")
