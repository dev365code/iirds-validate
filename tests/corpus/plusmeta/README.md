# The reference corpus

130 RDF fixtures from [plusmeta/iirds-validation-tool][repo], at commit
`0bcf19dd` — the same revision `src/iirds_validate/data/rule-catalog.json` was
extracted from. MIT, Copyright 2020 plusmeta GmbH; their licence is in
`LICENSE` beside this file.

## Why it is here

This is the only external check this project has. Every rule here was written
from the specification by one reader, and a single reader cannot detect their
own misreading — running the same fixtures through both tools and diffing the
results is what turns a private reading into a claim someone can refute.

It was previously downloaded at run time from a moving branch, which meant the
numbers in `docs/divergences.md` were computed against an input nobody could
reproduce, including us. A figure nobody can re-derive is a figure, not
evidence, and this project's whole argument is that a validator should be able
to show its work. So: pinned, hashed, and here.

    python tools/vendor_corpus.py --check     # verify, offline
    make check                                # runs it, among everything else

`MANIFEST.json` records a SHA-256 for every file, and `tests/test_corpus_integrity.py`
checks them on every test run. Editing a fixture breaks the build, which is the
point — the moment these stop being upstream's bytes they stop being evidence.

## What is defective in it, and why none of it is repaired

    100  parse as they stand
     17  fragments: excerpts from the specification's numbered examples, which
          carry no <rdf:RDF> element because the surrounding prose declared the
          namespaces. Not breakage — material this project could be checking
          and currently is not.
     11  malformed XML
      2  zero-byte

Repairing any of them would replace upstream's bytes with our reading of what
upstream meant, and would contaminate the one oracle here that is not ours. The
defects are recorded by name in `MANIFEST.json` instead. Where a rule's only
fixture is in the malformed list, the honest position is "no comparison
possible" — see `docs/divergences.md`.

## Credit where it is due

This project's README is direct about where plusmeta's validator falls short,
and that criticism should not be read as diminishing what they published.
Mapping 157 rules to the specification sentences that justify them is the most
expensive artefact in this domain, and they released it, with the fixtures, for
anyone to use. This validator exists in the shape it does because that work was
open. Their tool is at <https://iirds.plusmeta.de/>.

[repo]: https://github.com/plusmeta/iirds-validation-tool
