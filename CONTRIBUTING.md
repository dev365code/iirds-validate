# Contributing

## Certify your commits (DCO)

Every non-merge commit in a pull request needs a sign-off line:

```
Signed-off-by: Your Name <you@example.com>
```

`git commit -s` writes it for you; `git commit --amend -s` repairs a
forgotten one on the last commit, and `git rebase --signoff <base>` on every
commit after `<base>`. The line certifies the [Developer Certificate of
Origin 1.1](https://developercertificate.org/) — that you wrote the change
or otherwise have the right to submit it under this project's licence. That
is the whole deal: you keep your copyright, your contribution arrives under
Apache-2.0 like the project's own code (inbound = outbound; the bundled
ontologies and the rule catalogue keep their own licences, as `NOTICE` says),
and the project keeps
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

Catalogued rules (`C*`, `M*`, and `S1` to `S3`) inherit from
`src/iirds_validate/data/rule-catalog.json` whatever priority, applicable
versions, variants and specification link they do not pass themselves --
several pass their own where the catalogue's was wrong. The catalogue carries no remedy,
so every rule still passes its own `fix=`, which `tests/test_remediation.py`
requires:

```python
@rule("M21.5", fix="What to change so the package meets it.")
def m21_5(ctx):
    yield from _at_most_one(ctx, T.ContentLifeCycleStatus, T.purpose, "iirds:purpose")
```

Interoperability rules (`L*`) are not in the catalogue and carry their own
metadata:

```python
@_lint("L9", "what a reader would want to know", prio="RECOMMENDED",
       fix="What to change so the package meets it.")
def l9_something(ctx):
    ...
```

Rules yield `Violation`s and return nothing. A rule that raises is reported as a
finding rather than taking the run down, so a bug in one rule cannot hide what
the other rules find.

## Rules of the road

1. **Never spell a term inline** -- R1, R2 and L16 still do, and are the
   exceptions to remove rather than to follow. Add it to `terms.py` with
   bracket syntax.
   `tests/test_terms.py` will confirm it exists in the ontology, as long as it
   is defined above the `TERMS` snapshot at the end of the term list.
2. **Ask the graph, not the document.** No string matching on RDF/XML in a rule, ever.
   If a rule would behave differently on JSON-LD, it is wrong.
3. **Add a fixture both ways.** A new rule needs a package that violates it and
   one that does not. `tests/conftest.py` builds containers in memory.
4. **Do not touch `src/iirds_validate/data/ontologies/`.** Verbatim redistribution is a licence
   condition; `tests/test_offline.py` checks the hashes.

## Cross-checking against plusmeta

The catalogued rules' identifiers (`C*`, `M*`, `S1` to `S3`) match the [iiRDS
Validation Tool](https://iirds-validation.plusmeta.de/)'s -- `B*`, `L*`, `R*`
and `S4` onward are this project's own -- and it is the most useful review
available: run a package through both and compare. A disagreement is worth
understanding before either side is called wrong.

## Read this first

[docs/scope.md](docs/scope.md). It says what belongs here and what
does not, which saves proposing something that will be turned down for reasons
nobody had written anywhere.

## Running the tests

```sh
pip install -e ".[dev]"
pytest
```

`pytest` is not everything CI runs: import order, for one, is ruff's to see
and not the test suite's. `make check` runs, among its other checks, ruff (the one installed -- `.[dev]`
and `make dev` install the version CI pins), the tests with the pySHACL
differential gate required, the ontology hashes, the serialisation equivalence
proof against a container with a known defect, and the specification checks,
which fail unless `.spec-cache/` holds the specification (`python
tools/extract_requirements.py --refresh`; `make check IIRDS_REQUIRE_SPEC_CACHE=`
skips them, as the release workflow does).

```sh
make dev      # ruff, pytest and pySHACL: what make check needs
make check    # CI's lint and test gates except the .pyz build
make fix      # the lint findings ruff can fix itself (ruff check --fix)
```

One thing that check will not let you do is prove the equivalence claim against
a clean package. Four identical empty reports agree with each other however
badly the tool is broken, so `serialisation_equivalence.py` treats a package
with no findings as a failed run unless you pass `--allow-clean`. The same
reasoning applies to any test you add here: compare reports that say something.

## Cutting a release

The release is one number in eight places. Seven of them are yours to
change: `pyproject.toml`, `src/iirds_validate/__init__.py`,
`src/iirds/__init__.py`, and the two compatibility packages under `shims/`,
which carry it twice each -- their `version` and their `iirds>=` floor. The
eighth is `shapes/MANIFEST.json`, which you do not edit: run `python
tools/emit_shacl.py` and the manifest follows the version by itself. Give the
top entry of `CHANGELOG.md` its date in the same commit, then `make check` --
each of the eight fails a test if it is left behind (`pyproject.toml` and the
two `__init__.py` files share one; each shim line and the manifest have their
own), and the changelog fails one if the date and the number are not in one commit. The tag
is `v` and the number.

Look at the action pins before you tag. Every `uses:` in
`.github/workflows/` names a commit rather than a tag, so no action's code
moves on its own or picks up the fix its owner published last month -- though
the PyPI publisher, at that commit, runs a container image pulled from its
registry by a tag, which its owner could push again;
`tests/test_workflow_supply_chain.py` says why that trade was made. Moving a pin is reading the action's releases since the
one in the comment, taking the commit that release resolves to, and
changing every place that action appears -- a test refuses a pin that
disagrees with itself across the three files. Do it here, before a tag,
rather than during one: `release.yml`'s build job can be run by hand, but its
publish jobs run only on a tag push, so the first run of a changed publisher
is a real release.
