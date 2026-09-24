# What this catches, and what it says when it does

Written by `tools/gen_what_it_catches.py`; every block is the output of
the command above it, captured on the run that wrote this file. Build the
containers and reproduce any of it with the commands each case names: one
that builds its container and one that checks it, two of each for the pair
that is not flagged.
It is arranged by the six things the picture on the front page draws, and
an axis with no case to show shows none.

The cases here are about this tool alone.

## Coverage

### `mimetype` with a trailing newline

    $ python3 tools/make_fixture_package.py fixtures/what-it-catches/mimetype.iirds --broken mimetype
    $ iirds check fixtures/what-it-catches/mimetype.iirds

    mimetype.iirds   iiRDS 1.3
      note: metadata read from META-INF/metadata.rdf

      ERROR C5        mimetype must contain exactly 'application/iirds+zip' with no line ending
                          mimetype
                          b'application/iirds+zip\n'
                        → Make the file contain exactly application/iirds+zip, ASCII, with no
                        → trailing newline and no byte order mark. Editors add both silently, so
                        → write it with a tool that does not.

      FAIL  1 error(s), 0 warning(s), 0 informational
      194 rules checked, 28 not applicable to this version/variant (26 for iiRDS/H, 2 for other editions)

Exit code 1.

**The standard says so.** The link below lands on these words, which are the
specification's own:

> It MUST contain ... application/iirds+zip

<https://iirds.org/fileadmin/iiRDS_specification/20231110-1.2-release/index.html#:~:text=It%20MUST%20contain,application/iirds%2Bzip>

`C5` states that obligation as: The mimetype file MUST contain the following
ASCII-encoded text in a single line, without any line delimiters such as CR or
LF: application/iirds+zip.

The finding prints the bytes it read, because an editor shows nothing wrong
with a file that ends in a newline.

### No `metadata.rdf`

    $ python3 tools/make_fixture_package.py fixtures/what-it-catches/no-metadata-rdf.iirds --broken jsonld-only
    $ iirds check fixtures/what-it-catches/no-metadata-rdf.iirds

    no-metadata-rdf.iirds   iiRDS 1.3
      note: metadata read from META-INF/metadata.jsonld

      ERROR C8        META-INF must contain metadata.rdf
                        → Add META-INF/metadata.rdf. It carries everything a consumer knows about
                        → the package; without it the content files are a folder of documents with
                        → no structure or meaning.

      FAIL  1 error(s), 0 warning(s), 0 informational
      194 rules checked, 28 not applicable to this version/variant (26 for iiRDS/H, 2 for other editions)

Exit code 1.

**The standard says so.** The link below lands on these words, which are the
specification's own:

> The META-INF directory MUST contain the file metadata.rdf containing all
metadata in RDF 1.1 XML syntax (see [rdf-syntax-grammar]).

<https://iirds.org/fileadmin/iiRDS_specification/20231110-1.2-release/index.html#:~:text=The%20META%2DINF%20directory%20MUST%20contain%20the%20file%20metadata.rdf%20containing%20all%20metadata%20in%20RDF%201.1%20XML%20syntax%20(see%20%5Brdf%2Dsyntax%2Dgrammar%5D).>

`C8` states that obligation as: The META-INF directory MUST contain the file
metadata.rdf.

A JSON-LD file alongside `metadata.rdf` is allowed; instead of it is not.

### A rendition with no format

    $ python3 tools/make_fixture_package.py fixtures/what-it-catches/no-format.iirds --broken missing-format
    $ iirds check fixtures/what-it-catches/no-format.iirds

    no-format.iirds   iiRDS 1.3
      note: metadata read from META-INF/metadata.rdf

      ERROR M11       Rendition must have exactly one iirds:format
                          urn:test:topic1 has-rendition
                          0 found
                        → Give the Rendition exactly one iirds:format, holding the media type of the
                        → file it points at, for example application/xhtml+xml or application/pdf.
                        → Add one if there is none; remove the extras if there are several.

      FAIL  1 error(s), 0 warning(s), 0 informational
      194 rules checked, 28 not applicable to this version/variant (26 for iiRDS/H, 2 for other editions)

Exit code 1.

**The standard says so.** The link below lands on these words, which are the
specification's own:

> An iirds:Rendition MUST also have the property iirds:format.

<https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#information-units:~:text=An%20iirds%3ARendition%20MUST%20also%20have%20the%20property%20iirds%3Aformat.>

`M11` states that obligation as: An iirds:Rendition MUST have the property
iirds:format.

The finding names the subject and how many were found. A rendition with an IRI
of its own is named by it; one written as a blank node, as here, is named by
the unit that has it, so two of those under one unit read alike.

### Metadata that points at a file the package does not carry

    $ python3 tools/make_fixture_package.py fixtures/what-it-catches/missing-content.iirds --broken missing-content
    $ iirds check fixtures/what-it-catches/missing-content.iirds

    missing-content.iirds   iiRDS 1.3
      note: metadata read from META-INF/metadata.rdf

      ERROR L2        iirds:source does not resolve to a file in the container
                          urn:test:topic1 has-rendition
                          content/topic1.xhtml
                        → Add the file to the container at exactly the path iirds:source names, or
                        → correct the path. Paths are relative to the container root,
                        → case-sensitive, and use forward slashes.

      FAIL  1 error(s), 0 warning(s), 0 informational
      194 rules checked, 28 not applicable to this version/variant (26 for iiRDS/H, 2 for other editions)

Exit code 1.

**This tool's own rule** (`L2`), no specification reference.

The graph is well-formed and no rule but `L2` has anything to say about it.
The package simply cannot be read by anyone, because the document it describes
is not in it. That is the half of the question the upstream catalogue has no
rule for.

### What it does not flag, and why

    $ python3 tools/make_fixture_package.py fixtures/what-it-catches/element-style.iirds
    $ python3 tools/make_fixture_package.py fixtures/what-it-catches/attribute-style.iirds --broken attribute-style

    $ iirds check fixtures/what-it-catches/element-style.iirds

    element-style.iirds   iiRDS 1.3
      note: metadata read from META-INF/metadata.rdf

      PASS  0 error(s), 0 warning(s), 0 informational
      194 rules checked, 28 not applicable to this version/variant (26 for iiRDS/H, 2 for other editions)

    $ iirds check fixtures/what-it-catches/attribute-style.iirds

    attribute-style.iirds   iiRDS 1.3
      note: metadata read from META-INF/metadata.rdf

      PASS  0 error(s), 0 warning(s), 0 informational
      194 rules checked, 28 not applicable to this version/variant (26 for iiRDS/H, 2 for other editions)

Both pass, and the two reports are the same document: every key identical
apart from the package's own path and digest, which is what a different
file is. One is written with typed elements and nested properties, the
other with the package's and the topic's literals as attributes, the
rendition as `rdf:parseType="Resource"` and every type as `rdf:type`;
the graph is the same graph -- this page is not written unless it is -- so
the answer is the same answer. `--broken` is only the name of the
generator's one switch; `attribute-style` is not a defect.

**Now.**

- 172 of 280 obligations covered

**Before 1.0.** at least 220 of 280 covered

## Explanation

A finding carries a link to the sentence of the standard it enforces when its
rule has one, and where a case on this page has one it quotes the words the
link lands on. Some rules claim an obligation of the standard without a link
to its sentence; a finding does not carry that claim, and `iirds rules <id>
-v` shows it. Some rules have neither -- this project's interoperability and
run rules among them, and a few from the upstream catalogue -- and for those
nothing yet says there is no section to give. Until every rule names its
section or says it has none, that item is not done.

**Now.**

- done -- what is wrong, in one sentence
- done -- the evidence as read from the file
- done -- a remedy, for every rule
- not yet -- every rule names its section, or says it has none
- not yet -- the line in the file

**Before 1.0.** + every rule names its section, the line

## Report contract

**Now.**

- done -- schemaVersion in every report
- done -- a golden report held by a test
- done -- exit codes 0, 1, 2 and 64 under test
- not yet -- a field-by-field schema page

**Before 1.0.** + a field-by-field schema page

## Entrances

**Now.**

- done -- command line
- done -- Python library
- done -- single file, nothing to install
- not yet -- GitHub Action
- not yet -- browser, nothing installed

**Before 1.0.** + GitHub Action, browser

## Input safety

### The container is not a container

    $ mkdir -p fixtures/what-it-catches && printf 'not a zip at all' > fixtures/what-it-catches/not-a-container.iirds
    $ iirds check fixtures/what-it-catches/not-a-container.iirds

    not-a-container.iirds   iiRDS not declared

      ERROR S13       cannot open container
                          fixtures/what-it-catches/not-a-container.iirds
                          File is not a zip file
                        → Rebuild the archive. An iiRDS container is an ordinary ZIP: `unzip -l` on
                        → it should list mimetype first. Nothing else here has run, because there
                        → was nothing to run against.

      FAIL  1 error(s), 0 warning(s), 0 informational
      1 rule checked, 221 not applicable to this version/variant (221 never put -- the container would not open)

Exit code 1.

**The standard states this obligation**, and `S13` claims it as
`dfn-iirds-package#1`; the rule carries no link to the sentence, so the page
has none to quote. `S13` states it as: the container could not be opened at
all

The standard describes a container, and a file that will not open is not one
yet. The last line is the point: the run says how many rules it never put,
rather than leaving a reader to assume they passed.

**Now.**

- done -- read budgets, per file and per run
- done -- from 0.6.1, a security fix ships with an advisory
- done -- tests verified against their own mutations
- not yet -- declared encodings read without loss

**Before 1.0.** + declared encodings read without loss

## Upstream

**Now.**

- done -- upstream catalogue pinned by commit
- done -- checked weekly for change
- done -- one pin move shipped

**Before 1.0.** met
