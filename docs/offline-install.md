# Running inside a closed network

Manufacturing sites are usually air-gapped, and technical documentation is
exactly the kind of material that is not allowed out. This tool is built so the
data never has to move.

## What it never does

- No network access at validation time. The iiRDS ontologies ship inside the
  package; nothing is fetched, resolved or phoned home.
- No telemetry, no update check, no license server.
- `tests/test_offline.py` disables `socket` entirely and runs a full validation,
  so a regression here fails the suite rather than surprising you on site.

## The shortest path in: one file

```sh
python tools/build_zipapp.py          # on a machine with a network
# copy dist/iirds-validate.pyz across by whatever means the site allows
python iirds-validate.pyz dist/       # on the machine without one
```

No pip, no index, no virtual environment, no rights to create one. Everything
is inside the archive, including `rdflib`, the `iirds` SDK and the ontologies,
and nothing in it
is compiled — the same file runs on Linux, macOS and Windows.

It is deliberately not a compiled binary. An unsigned executable is harder to
get past endpoint protection and impossible to read; a `.pyz` is a zip of
Python source that a reviewer can unpack and audit line by line. In an
environment where approval is the obstacle rather than installation, that is
the feature.

`python -m iirds_validate.ontology --verify` works from inside the archive too.

## Getting it in as a package

On a machine with a network:

```sh
pip download iirds-validate -d wheels/
```

That directory holds `iirds_validate`, `rdflib`, the `iirds` SDK and their
handful of dependencies. Copy it in by whatever means your site allows, then:

```sh
pip install --no-index --find-links wheels/ iirds-validate
iirdsv --version
```

If even pip is unavailable, the package is pure Python: unzip the wheel and put
`iirds_validate/` on `PYTHONPATH`. `rdflib` and `iirds` are the only things
you must bring along.

## Verifying what you carried in

```sh
python -m iirds_validate.ontology --verify
```

Checks the bundled ontology files against the SHA-256 sums recorded at build
time. Useful when the files crossed an air gap on removable media, and also the
guard against someone editing them — which would both break CC BY-ND and change
validation results silently.

```sh
python -m iirds_validate.ontology
# iiRDS 1.3: 78 classes, 70 properties, 2262 triples
```

## In a pipeline

```sh
#!/bin/sh
set -e
python build_packages.py
for pkg in dist/*.iirds; do
    iirdsv check "$pkg"      # non-zero exit stops the build
done
iirdsv lint dist/*.iirds --format json > reports/interop.json
```

`check` gates the build. `lint` is advisory — record it, review the trend, do
not block on it until the warnings are down to zero.

## Why "it runs in your browser" is not the same as "it never leaves"

The hosted validation tool processes files client-side and stores nothing on its
server. That is true of the code as published, and it is not the same guarantee
as never loading the page at all.

- **The code can change between visits.** A hosted single-page app is fetched
  fresh every time. What you audited last month is not necessarily what executes
  today, and there is no integrity pinning to notice the difference.
- **Nothing structurally prevents exfiltration.** Once the file is in the tab's
  memory, sending it anywhere is one `fetch()`. Only the current source code
  stands between the two, and see the previous point.
- **The dependency surface is large.** A Vue application pulls in hundreds of
  npm packages. Auditing that before every use is not realistic; auditing a
  pure-Python package with two pure-Python dependencies is.
- **Most sites will not approve it regardless.** "Open a browser tab to an
  external domain and feed it engineering documentation" is not a request that
  passes review at a manufacturer, and being technically safe does not make it
  approvable.

This tool takes the question off the table. There is no page to load, no server
to trust, and no version that changes underneath you: the wheel you carried in
is the code that runs.
