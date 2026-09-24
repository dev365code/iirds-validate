# Running inside a closed network

Many manufacturing sites run air-gapped networks, and technical documentation
is the kind of material that is often not allowed out. This tool is built so the
data never has to move.

## What it never does

- No network access at validation time. The iiRDS ontologies ship inside the
  package; nothing is fetched, resolved or phoned home.
- No telemetry, no update check, no license server.
- `tests/test_offline.py` runs a full validation with the socket functions that
  open a connection made to fail -- `socket.socket` and `create_connection`, and
  in a second test `create_connection`, `getaddrinfo` and `connect` -- so a
  regression here fails the suite rather than surprising you on site.

## The shortest path in: one file

```sh
python tools/build_zipapp.py          # on a machine with a network
# copy dist/iirds.pyz across by whatever means the site allows
python iirds.pyz dist/                # on the machine without one
```

No pip, no index, no virtual environment, no rights to create one. Everything
is inside the archive, including `rdflib`, the `iirds` library and the ontologies,
and nothing in it
is compiled -- the build refuses a platform-specific wheel -- so the one file is
meant to run on Linux, macOS and Windows alike; CI runs it on Linux.

It is deliberately not a compiled binary. An unsigned executable is harder to
get past endpoint protection and impossible to read; a `.pyz` is a zip of
Python source that a reviewer can unpack and audit line by line. In an
environment where approval is the obstacle rather than installation, that is
the feature.

The ontology check shown under *Verifying what you carried in* runs from
inside the archive as
`PYTHONPATH=iirds.pyz python -S -m iirds_validate.ontology --verify`.

## Getting it in as a package

On a machine with a network:

```sh
pip download iirds -d wheels/
```

That directory holds this project's wheel — `iirds_validate` and the `iirds`
library it is built on — plus `rdflib` and the dependencies it declares for the
Python that ran `pip download` (`isodate` only below 3.11), so download with the
Python version the closed machine runs. Copy it in by whatever means your site
allows, then:

```sh
pip install --no-index --find-links wheels/ iirds
iirds --version
```

If even pip is unavailable, the package is pure Python: unzip the wheel into a
directory and put that directory -- the one holding `iirds_validate/` and
`iirds/` -- on `PYTHONPATH`, with `rdflib` and what it
needs — `pyparsing`, and `isodate` below Python 3.11.

## Verifying what you carried in

```sh
grep ' iirds.pyz$' SHA256SUMS | shasum -a 256 -c -
python -m iirds_validate.ontology --verify
```

`SHA256SUMS` is a release asset, so carry it across beside the file you want.
It names every other asset the release carries, and `shasum -c` on the whole of
it fails on each one you did not bring -- hence asking it about the one line.

**A mismatch means the file is not the one that was published.** It does not
say why. An innocent difference and a tampered file look the same here, which
is the reason to run it at all.

If you built the `.pyz` yourself with `python tools/build_zipapp.py` instead of
downloading it, there is no `SHA256SUMS` on the machine and the sum to compare
against is the one on the release page. A build of the tagged commit is
expected to match it when the dependency versions match, `SOURCE_DATE_EPOCH` is
unset as it is for the release, and it is built the way the release is: on
Linux, with the zlib the release runner's Python carries. What the release
workflow measures is one runner building it twice, not two kinds of system
against each other. The versions the release bundled are named by the
`*.dist-info` directories inside the archive itself, which is a weaker thing to
rely on than a record published beside it.

`python -m iirds_validate.ontology --verify` checks the bundled ontology files
against the SHA-256 sums in `sha256sums.txt`, which is committed beside them and
ships in the same package. Useful when the files crossed an air gap on removable
media, and it catches an edit to them that leaves `sha256sums.txt` alone — an
edit that would both break CC BY-ND and change validation results silently. An
edit to both files passes it; that is what the release's `SHA256SUMS` is for.

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
    iirds check "$pkg"      # non-zero exit stops the build
done
iirds lint dist/*.iirds --format json > reports/interop.json
```

`check` gates the build. `lint` is advisory for its warnings, which leave the
exit code alone unless `-W` is given; an error-level finding makes it exit 1 --
L4, a cycle in the directory structure, is one `check` does not run -- so under
`set -e` the lint line above stops the build unless it ends in `|| true`.

## Why "it runs in your browser" is not the same as "it never leaves"

The hosted validation tool is described as processing files client-side and
storing nothing on its server. Even where that holds of the code as published,
it is not the same guarantee as never loading the page at all.

- **The code can change between visits.** A hosted single-page app can be
  fetched anew on any visit. What you audited last month is not necessarily what executes
  today, and there is no integrity pinning to notice the difference.
- **Nothing structurally prevents exfiltration.** Once the file is in the tab's
  memory, sending it anywhere is one `fetch()`. Only the current source code
  stands between the two, and see the previous point.
- **The dependency surface is large.** A Vue application is built from a large
  npm dependency tree. Auditing that before every use is not realistic; auditing
  a pure-Python package whose one declared dependency, `rdflib`, brings
  `pyparsing` and, below Python 3.11, `isodate` -- all pure Python -- is.
- **Many sites will not approve it regardless.** "Open a browser tab to an
  external domain and feed it engineering documentation" is not a request that
  passes review at a manufacturer, and being technically safe does not make it
  approvable.

This tool takes the question off the table. There is no remote page to load, no
server but your own to trust, and no version that changes underneath you: the
wheel or `.pyz` you carried in is the code that runs.

`iirds serve` does not reopen it. It is a page served by the command you just
ran, on the loopback interface of the machine you ran it on, from the code you
carried in — the same wheel, the same rules, the same renderer. There is no
origin to approve, no fetch that could leave, and no version that changes
between uses, because the version is the one you installed. It exists so that
somebody who writes documentation for a living can drop a file on a page
instead of typing a path into a terminal, which is a different problem from
the one above and has a different answer.
