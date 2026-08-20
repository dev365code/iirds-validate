# Licensing, honestly

This distribution is not under a single licence, and the difference matters to
some people who will want to use it. Here is the whole position.

## What is under what

| | Licence | OSI-approved? |
|---|---|---|
| Source code, tests, tools, docs | Apache-2.0 | yes |
| Rule catalogue (`data/rule-catalog.json`) | MIT, © plusmeta GmbH | yes |
| iiRDS ontologies (`data/ontologies/`) | **CC BY-ND 4.0**, © tekom Deutschland e.V. | **no** |
| Reference corpus (`tests/corpus/plusmeta/`) | MIT, © plusmeta GmbH | yes |
| The iiRDS specification itself (quoted, not bundled) | **CC BY 4.0**, © the document editors | yes |

The last two rows are the ones people get wrong, this project included. iiRDS
is licensed at two tiers: the **specification text is CC BY 4.0** — attribution
only, derivatives and commercial use both permitted — while the **ontology
files are CC BY-ND 4.0**, which forbids sharing an adapted version. So quoting
a requirement sentence is free, and converting `iirds-core.rdf` to Turtle and
publishing it is not.

Two consequences worth stating, because both were assumed the other way here
before anyone checked. Mapping the specification's requirements sentence by
sentence may quote those sentences in full, with attribution; it does not need
hashes and 60-character excerpts to stay lawful. And a secondary claim that
iiRDS is CC BY-**NC**-ND — which appears in plusmeta's 2020 licence file —
matches neither current source, so nothing here treats iiRDS as
non-commercial.

## Bundling the ontologies is permitted

Section 2(a)(1) of CC BY-ND 4.0 grants the right to

> reproduce and Share the Licensed Material, in whole or in part

The NoDerivatives condition restricts *Sharing Adapted Material* — material in
which the licensed work is "translated, altered, arranged, transformed, or
otherwise modified". Shipping the files unchanged is not that. So the files are
here byte-for-byte, with their own copyright headers intact, and
`tools/`-generated SHA-256 digests prove it:

```sh
python -m iirds_validate.ontology --verify
```

A consequence worth stating plainly: **the ontologies are never converted in
anything that gets redistributed.** rdflib parses them into memory at run time,
which is use, not Sharing. If you fork this project, do not commit a Turtle or
JSON-LD conversion of them.

Attribution under Section 3(a)(1) is in [NOTICE](../NOTICE): creator,
copyright notice, licence notice, warranty-disclaimer notice, a link to the
Licensed Material, and a statement that nothing was modified.
`tests/test_licensing.py` checks each of those is still there.

## The part that is not open source

CC BY-ND is **not** an OSI-approved licence and is **not** DFSG-free: the
no-derivatives condition fails both definitions. Legally we are fine. But it
means:

- This wheel cannot go into Debian `main` or Fedora as-is.
- Some corporate open-source review processes reject ND-licensed content
  outright, regardless of what it is.
- Anyone forking this project inherits the restriction on those files.

None of that is hidden by calling the project Apache-2.0, which is why this
page exists. The Apache licence covers what we wrote; it does not and cannot
relicense tekom's material, and Section 2(a)(5) of CC BY-ND forbids imposing
different terms on it anyway.

## Why we bundle anyway

The tool exists to run inside networks that have no route to the internet. An
ontology fetched at validation time is not an option — it is the whole problem
the project was built to avoid. The choice is between bundling and not
existing.

## What would fix it

A permissive licence on the **machine-readable schema files only** — the RDF
ontologies, not the specification text. That is a distinction standards bodies
make routinely: the prose stays ND so nobody publishes a mangled "iiRDS
specification", while the schema every implementation has to load ships freely.

There is precedent inside the consortium itself: `iirds-consortium/dita-ot-plugin`
is Apache-2.0. And `iirds-consortium/models`, which publishes four of these same
RDF files, currently carries **no licence file at all** — so the same bytes are
CC BY-ND from iirds.org and unlicensed from GitHub. That inconsistency is worth
resolving in either direction.

[`licence-request.md`](licence-request.md) is a draft of that request. It has
not been sent.

## Before you publish a fork

If your copy of this project came out of client work, the licence questions
above are the easy half. Check first whether you are allowed to publish
anything derived from that engagement at all, and keep client data, vocabulary
mappings and configuration out of the repository entirely — not merely
gitignored.
