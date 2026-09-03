# SHACL shapes for iiRDS 1.3

Machine-readable validation shapes for [iiRDS](https://iirds.org) packages —
the language-neutral encoding of the rules that
[iirds-validate](https://github.com/dev365code/iirds-validate) checks in
Python. [iirds-consortium/models#24](https://github.com/iirds-consortium/models/issues/24)
has had SHACL on its wishlist since April 2025; this is a working set for
edition 1.3, offered so a SHACL engine can validate iiRDS metadata without
this project's code. The shapes are written to SHACL Core and SHACL-AF
(`sh:sparql`) as the recommendation defines them, and **tested on pySHACL
0.40** — the differential gate below runs on that engine. Other engines
should agree for exactly that reason, but only pySHACL's agreement has been
demonstrated.

## The files

| file | needs | contains |
|---|---|---|
| `iirds-1.3/iirds-complete.ttl` | SHACL-AF engine | **start here**: core + SPARQL in one file, for any package that does not declare iiRDS/H |
| `iirds-1.3/iirds-handover-complete.ttl` | SHACL-AF | everything, base + handover, for packages declaring `formatRestriction` H |
| `iirds-1.3/iirds-core.ttl` | any SHACL Core engine | 112 shapes: cardinalities, required properties, IRI-kind, value lists, the navigation-chain locals |
| `iirds-1.3/iirds-sparql.ttl` | SHACL-AF (`sh:sparql`) | 15 shapes: graph-global checks (exactly one Package…), described-here exemptions, exact-typing prohibitions |
| `iirds-1.3/iirds-handover-core.ttl` | Core | 8 iiRDS/H additions — apply **only** under iiRDS/H |
| `iirds-1.3/iirds-handover-sparql.ttl` | SHACL-AF | 8 iiRDS/H additions (SPARQL): M15.11a, M15.7c, the five named-party MUSTs, and R4 |
| `MANIFEST.json` | — | every rule's disposition: shape IRI and file, or the verbatim reason it has no shape |

The `-complete` files exist because the pySHACL command line takes **one**
shapes file: passing the SPARQL file as a second `-s` or via `-e` does not
run it (`-e` adds to the *data* graph), and a quickstart that silently skips
fourteen shapes is worse than none. The split files are for engines or
pipelines that want Core only, or want to select the way the standard
selects rule sets: base files for every package, handover files added only
under iiRDS/H. There is no profile switch inside the shapes, because SHACL
has no notion of "the declared profile" — the caller chooses files, exactly
as a validator chooses rule sets.

## Running them

```sh
pip install "pyshacl==0.40.*"
python3 -m pyshacl -s iirds-1.3/iirds-complete.ttl -a metadata.rdf
```

(Run it from this directory, or spell out the paths — pySHACL exits 1 for
"file not found" and for "violations found" alike, so a wrong path in a
script reads as a failing package.) On pySHACL 0.40 the `sh:sparql` shapes
run with or without `-a`; the flag is kept because this is the invocation
the differential gate certifies, and engines differ on what they gate
behind SHACL-AF. Or in Python, which is also the honest way to handle the
base IRI:

```python
from rdflib import Graph
from pyshacl import validate

data = Graph().parse("META-INF/metadata.rdf", publicID="urn:iirds:package:")
ok, results, text = validate(data, shacl_graph="iirds-1.3/iirds-complete.ttl",
                             advanced=True, inference="none")
```

Three conventions matter.

**Base IRI.** The shapes name `<urn:iirds:package:>` where "this package"
has to be an IRI — that is what `publicID=` supplies above. `rdf:about=""`
resolves to the parsing base, so metadata using the empty `about` (both
official samples do) needs this convention to be checked rather than
blessed. The command line cannot set a base, and the gap is not one narrow
check: with a `file:` base, 23 of the 97 cleanly-parsing reference fixtures
report *fewer* violations than under the documented convention, across ten
rules. The Python API form above is the one the differential gate
certifies; treat CLI runs of `about=""` metadata as a smoke test.

**Inference off.** Leave RDFS/OWL inference disabled, as in both commands
above. SHACL's own semantics already walk `rdfs:subClassOf` in your data —
that is deliberate and correct: iiRDS section 7 lets a package declare
proprietary subclasses of iiRDS classes, and both these shapes and the
Python validator treat an instance of such a subclass as its iiRDS parent.
Full inference on top of that would additionally materialise the bundled
ontology's entailment hints and change what "described in this package"
means.

**One file, not the union.** These shapes validate the graph you hand
them — in practice `META-INF/metadata.rdf`. The CLI validates the *union*
of every metadata serialisation in the container (an `.iirds` may also
carry `metadata.jsonld`), so a package whose serialisations disagree can
validate differently here than there; the CLI's L9 reports that
disagreement itself, which no single-graph shape can see.

**Editions.** These shapes are the 1.3 reading, and they do not gate by
declared edition — a shapes file has no way to ask what the package
declares. Each shape carries `ivm:versions` listing the editions that state
its requirement; validating a 1.0-era package with the 1.3 shapes can
therefore fire rules that edition never stated (the differential gate pins
seven exactly such firings on the reference corpus). The Python validator
reads the declaration and gates; if you need that behaviour engine-side,
filter results whose `ivm:versions` excludes your package's declared
edition.

## Reading a result

Every violation points at its shape via `sh:sourceShape`, and every shape —
node shapes and their `…-p` property shapes alike — carries the machinery to
act on it: `sh:message` (what is wrong), `sh:description` (what to change —
the same remedy text the CLI prints), `sh:severity`, `ivm:ruleId`, and —
for every rule that cites a specification sentence — `dcterms:source`. Five
node shapes have no sentence to cite: L7, L10, S4 and S5 are this project's
own judgement calls, and M97.1's catalogue row carries no reference (its
sibling M97.2's does). A test pins that list. So the join back to the rule
catalogue is one lookup: **read `ivm:ruleId` off the source shape**,
whichever shape the engine attributed. (Property-shape IRIs are the node
shape's id plus `-p`, if you prefer string surgery; the annotation makes
that unnecessary.)

`sh:severity` mirrors the rule's declared severity. One divergence from the
CLI is deliberate: outside profile A the Python runner *demotes* certain
content-rule errors to warnings per package, a per-run decision a static
shapes file cannot make. The shapes always state the undemoted severity.

## Where these come from

The shapes are generated (`tools/emit_shacl.py` in the main repository) from
the same rule definitions the Python validator runs — the community rule
catalogue ([plusmeta's](https://github.com/plusmeta/iirds-validation-tool),
MIT, pinned at commit `0bcf19dd`) plus this project's own system, packaging
and lint rules — and CI byte-compares the committed files against the
generator, so what you read is what the generator says. Rule identifiers
come from that catalogue, and where a catalogue-sourced shape's `sh:message`
keeps the catalogue's rule wording, that text is MIT © plusmeta GmbH; the
remedy texts (`sh:description`) are this project's own throughout. See
`THIRD-PARTY-NOTICES.md` beside this file.

They are deliberately **not** derived from the RDF ontology: the ontology
carries no OWL axioms, its `rdfs:domain`/`range` are entailment hints rather
than constraints, and
[models' own open issues](https://github.com/iirds-consortium/models/issues)
document defects that ontology-derived shapes would faithfully encode.

**The caveat that matters: these shapes encode one documented reading of the
specification.** Where prose underdetermines a rule, the choice made here is
recorded — with the sentence, the alternative, and the evidence — in
[docs/divergences.md](../docs/divergences.md). Two of those questions are
currently before the Consortium.

## What is not here, exactly

57 of the 200 rules have no shape, in four honest categories,
each listed with its reason in `MANIFEST.json`:

- **45 not expressible** — 45 of the 200 rules are about ZIP bytes, content
  files, archive↔graph joins, or the validation run itself (S1–S3): entry
  order, the stored `mimetype`, path lengths, encryption bits, files present
  in the container. None of that
  exists in an RDF graph, **by nature, not omission**. A package can satisfy
  every shape here and still be unreadable to every consumer; full checking
  needs a container-aware validator, which is what the `iirds` checker is.
- **9 deferred** — expressible in principle, not yet written: the six
  lint rules whose exemption lists are long (L1, L3, L5, L6, L8 — and L4,
  which is itself MUST-level: directory-structure cycle detection); L13,
  which compares every name in the iiRDS namespaces with the vocabulary:
  `sh:closed` sees a node's predicates, but Core cannot keep the ones of a
  namespace and check them against a list it does not carry, and a
  `sh:sparql` constraint would carry the edition's term list as a VALUES
  block; and L14, whose test is how far a namespace is from iiRDS's — a
  string distance neither Core nor SPARQL has, though the half about the
  standard's own host is one `FILTER(STRSTARTS(...))`; and L15, which
  needs the per-edition term inventory beside the declared version — a
  `sh:sparql` constraint could carry each edition's names as a VALUES
  block, and the checker's inventory would be its generator. The
  five iiRDS/H MUSTs deferred at first release (M15.7b, M15.7d,
  M15.8–M15.10) have since landed as SPARQL shapes, softenings included:
  a party whose vCard this package does not describe passes those five,
  exactly as in the Python reading, and the pointer itself is reported
  once by R4 — which is a shape too, so both encodings say it.
- **2 out of edition** — M16.1 and M16.2 exist only in editions 1.0–1.1;
  a 1.3 shapes set has nothing to say about them.
- **1 no-op** — M96.4 is a MAY with nothing to violate; it is registered so
  `iirds rules` lists the whole catalogue.

## Why you can trust the translation

**These shapes are the iiRDS 1.3 rule set, and they carry no version gate.**
29 of them encode a rule that iiRDS 1.3 added or that only the 1.3 text
carries, so running them against a package that declares an older edition
reports rules that edition does not have. The Python validator gates on the
declared version and stays silent on those. Gating the shapes themselves would
put an inference about editions inside an artefact whose point is that a SHACL
engine can run it without this project's code, so the boundary is stated here
instead — and it is pinned by a test, which measures the divergence rather
than describing it.

Every emitted shape is **differentially tested against the 198-rule Python
validator**, on pySHACL 0.40: per-rule mutant packages (a defect and its
repair for each shape family, with severity equality asserted on every
one), a realistic conformant package that must stay silent in both
encodings, and the vendored reference corpus — 114 fixtures compared
rule-for-rule on fire-set equality (117 parse cleanly; the three rdflib's
RDF/XML reader rejects are pinned by name in the gate), plus a closing
check that every emitted shape has fired somewhere in the suite, so a shape
cannot pass by never engaging. The gate has caught real defects on
its own runs — an inverted navigation shape (M24.5), and a class-closure gap
in the Python validator itself (iiRDS section 7 subclasses, found as a
SHACL-only firing) — each recorded in the changelog.

Three engine realities are encoded rather than worked around, with comments
in the generator: SHACL-SPARQL forbids `VALUES` in constraints (membership
uses `FILTER IN`); pySHACL 0.40 ignores `sh:SPARQLTarget` (nothing here uses
it — a target an engine ignores is a rule that never fires); Turtle's
escape rules differ from SPARQL's (regex character classes are written to
need no escapes); and regex flavour is the engine's — pySHACL evaluates
`\s`/`\S` with Python-re breadth, XPath-strict engines are narrower, so
whitespace tolerance can differ at the Unicode margin (NBSP, exotic
spaces).

## Licence

Apache-2.0, © 2026 Wooyong Lee, with catalogue-sourced wording under MIT ©
plusmeta GmbH — both texts in `LICENSE` and `THIRD-PARTY-NOTICES.md` beside
this file, so a copy of this directory is self-contained. The shapes
reference iiRDS term IRIs (facts about the vocabulary) and copy no ontology
content — the files are independent of the CC BY-ND terms the ontology
carries, and a test enforces that no axiom or description prose leaks in.
Should the Consortium prefer different terms for an upstream home, the
author will relicense these files accordingly.

The `ivs:` / `ivm:` namespaces resolve through w3id.org permalinks
(registered via [perma-id/w3id.org#6584](https://github.com/perma-id/w3id.org/pull/6584)),
so the IRIs in these files survive any future change of hosting.
`MANIFEST.json` carries `_shapes_version`, which follows the main
project's release tags.
