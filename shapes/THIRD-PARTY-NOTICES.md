# Third-party notices for the shapes directory

These notices make a copy of this directory self-contained: everything it
carries from elsewhere, and the terms it arrived under. The shapes files
themselves are Apache-2.0, © 2026 Wooyong Lee (`LICENSE` beside this file).

## Rule identifiers and wording — plusmeta rule catalogue (MIT)

Rule identifiers (`ivm:ruleId`) derive from the iiRDS Validation Tool's
rule catalogue, and where a catalogue-sourced shape's `sh:message` /
`rdfs:label` keeps the catalogue's rule wording, that wording does too.
The remedy texts (`sh:description`) are this project's own throughout:

    iiRDS Validation Tool
    https://github.com/plusmeta/iirds-validation-tool
    Copyright 2020 plusmeta GmbH
    Pinned at commit 0bcf19dd

Shapes whose `ivm:ruleSource` is `"iirds-validate"` are this project's own
wording. The SHACL constraint logic in every shape is this project's
independent work; the original is a browser application operating on an XML
DOM and contains no SHACL.

The MIT License:

    MIT License

    Copyright (c) 2020 plusmeta GmbH

    Permission is hereby granted, free of charge, to any person obtaining a
    copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction, including
    without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to
    permit persons to whom the Software is furnished to do so, subject to
    the following conditions:

    The above copyright notice and this permission notice shall be included
    in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
    OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
    TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
    SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## What is deliberately absent — the iiRDS ontologies (CC BY-ND 4.0)

The iiRDS RDF ontologies are © tekom Deutschland e.V., CC BY-ND 4.0, and are
**not** in this directory in any form. The shapes reference iiRDS term IRIs —
facts about the vocabulary — and copy no ontology content: no class or
property definitions, no `rdfs:subClassOf`/`domain`/`range` axioms, no
description prose. A test in the main repository enforces that boundary.

"iiRDS" is a standard of the iiRDS Consortium, hosted by tekom Deutschland
e.V.; the name is used descriptively. This project is not affiliated with,
endorsed by, or certified by the iiRDS Consortium, tekom Deutschland e.V.,
or plusmeta GmbH.
