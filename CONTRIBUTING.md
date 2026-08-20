# Contributing

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
make check    # everything CI runs
make fix      # the formatting ruff can correct itself
```

One thing that check will not let you do is prove the equivalence claim against
a clean package. Four identical empty reports agree with each other however
badly the tool is broken, so `serialisation_equivalence.py` treats a package
with no findings as a failed run unless you pass `--allow-clean`. The same
reasoning applies to any test you add here: compare reports that say something.
