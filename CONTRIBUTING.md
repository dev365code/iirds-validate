# Contributing

## Certify your commits (DCO)

Every commit needs a sign-off line:

```
Signed-off-by: Your Name <you@example.com>
```

`git commit -s` writes it for you; `git commit --amend -s` repairs a
forgotten one. The line certifies the [Developer Certificate of
Origin 1.1](https://developercertificate.org/) — that you wrote the change
or otherwise have the right to submit it under this project's licence. That
is the whole deal: you keep your copyright, your contribution arrives under
Apache-2.0 like everything here (inbound = outbound), and the project keeps
a provenance trail it can show anyone who asks — which, for a tool courting
a standards body, someone eventually will. There is no CLA and no paperwork;
a certificate of origin is a statement of fact, not a transfer of rights.

Pull requests are checked for the line automatically.

The certificate, verbatim:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## Adding a rule

Catalogued rules (`C*`, `M*`) inherit their priority, applicable versions,
variants and specification link from `data/rule-catalog.json`, so a rule is just
its implementation:

```python
@rule("M21.5")
def m21_5(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.purpose, "iirds:purpose")
```

Interoperability rules (`L*`) are not in the catalogue and carry their own
metadata:

```python
@_lint("L9", "what a reader would want to know", prio="RECOMMENDED")
def l9_something(ctx):
    ...
```

Rules yield `Violation`s and return nothing. A rule that raises is reported as a
finding rather than taking the run down, so a bug in one rule cannot hide the
other 60.

## Rules of the road

1. **Never spell a term inline.** Add it to `terms.py` with bracket syntax.
   `tests/test_terms.py` will confirm it exists in the ontology.
2. **Ask the graph, not the document.** No string matching on RDF/XML, ever.
   If a rule would behave differently on JSON-LD, it is wrong.
3. **Add a fixture both ways.** A new rule needs a package that violates it and
   one that does not. `tests/conftest.py` builds containers in memory.
4. **Do not touch `data/ontologies/`.** Verbatim redistribution is a licence
   condition; `tests/test_offline.py` checks the hashes.

## Cross-checking against plusmeta

Rule identifiers match the [iiRDS Validation
Tool](https://iirds-validation.plusmeta.de/), which is the most useful review
available: run a package through both and compare. A disagreement is worth
understanding before either side is called wrong — the answer has so far been
interesting every time.

## Read this first

[docs/scope.md](docs/scope.md). One page. It says what belongs here and what
does not, which saves proposing something that will be turned down for reasons
nobody had written anywhere.

## Running the tests

```sh
pip install -e ".[dev]"
pytest
```

`pytest` is not everything CI runs, and the difference has turned a good commit
red twice — over import order, which the test suite cannot see. `make check`
runs the lot: ruff at the version CI pins, the tests, the ontology hashes, and
the serialisation equivalence proof against a container with a known defect.

```sh
make dev      # ruff and pytest
make check    # every gate CI's lint and test jobs run
make fix      # the formatting ruff can correct itself
```

One thing that check will not let you do is prove the equivalence claim against
a clean package. Four identical empty reports agree with each other however
badly the tool is broken, so `serialisation_equivalence.py` treats a package
with no findings as a failed run unless you pass `--allow-clean`. The same
reasoning applies to any test you add here: compare reports that say something.
