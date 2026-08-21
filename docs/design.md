# Why a graph, not a tree

RDF is a graph. RDF/XML is one way of writing that graph down, and it is not a
canonical one. These four documents are the same three triples:

```xml
<!-- 1: typed element, nested child -->
<iirds:Topic rdf:about="urn:t1">
  <iirds:relates-to-event><iirds:Event rdf:about="urn:e1"/></iirds:relates-to-event>
</iirds:Topic>

<!-- 2: typed element, reference -->
<iirds:Topic rdf:about="urn:t1">
  <iirds:relates-to-event rdf:resource="urn:e1"/>
</iirds:Topic>
<iirds:Event rdf:about="urn:e1"/>

<!-- 3: rdf:Description with explicit rdf:type -->
<rdf:Description rdf:about="urn:t1">
  <rdf:type rdf:resource="http://iirds.tekom.de/iirds#Topic"/>
  <iirds:relates-to-event rdf:resource="urn:e1"/>
</rdf:Description>

<!-- 4: a different prefix for the same namespace -->
<ii:Topic rdf:about="urn:t1">
  <ii:relates-to-event rdf:resource="urn:e1"/>
</ii:Topic>
```

Plus `META-INF/metadata.jsonld`, which iiRDS 1.3 accepts as an alternative
serialisation of the same graph.

Any tool that reads the XML tree has to handle each of these shapes explicitly,
and in practice tools handle the shape their own generator emits. The failure is
quiet: a selector that matches nothing produces no error, just no findings. A
validator reports a clean package; a reader loses the data; both sides are
conformant and neither knows.

Parsing into a graph collapses all four into the same set of triples before any
rule runs. Rules ask "which subjects are typed `iirds:Topic`" instead of "which
elements are named `Topic`", and the question has one answer regardless of how
the document was written. That is the whole architectural difference between
this tool and the alternatives, and `tests/test_serialisation_blindness.py`
exists to keep it true.

## What a graph cannot do

Half the specification is not about the graph at all:

- the ZIP entry order and the compression mode of `mimetype`
- path lengths, forbidden characters, where content files may live
- whether the file named by `iirds:source` is actually in the archive
- XHTML5 conformance of the content itself

None of that is expressible in SHACL either, which is worth saying because
"generate SHACL shapes and you are done" is a tempting shortcut. Container rules
are ordinary Python over `zipfile`, and they catch the majority of real defects.

## Why the rules are hand-written and not generated from the ontology

The obvious idea is to derive constraints from the ontology automatically — the
cardinalities are in there, after all, stuffed into `iirds:description` strings
like `"Cardinality: http://iirds.tekom.de/iirds#InformationUnit [0..1]"`.
[iirds-consortium/models#24](https://github.com/iirds-consortium/models/issues/24)
proposes exactly that.

The problem is the source material. The same repository carries two dozen open
issues against the ontology: properties with no range, `rdfs:Literal` used as a
class, `domainIncludes` without `domain`. Generating shapes from it encodes
those defects as rules. So the catalogue extracted from the specification is
treated as authoritative, and the ontology is used for what it is reliable
about: the class hierarchy.

## Terms come from the ontology, not from rule prose

Two failure modes produced silently-passing rules during development, and both
are now guarded by tests:

`rdflib.Namespace` subclasses `str`, so `IIRDS.format` returns `str.format` — a
bound method — rather than the property. rdflib patches some names (`title`) and
not others, so the breakage is inconsistent. Every term is declared once in
`terms.py` using bracket syntax.

The prose of a rule is not the name of a property. plusmeta's text for M16 reads
"Instances of the iirds:Event class MUST have property iirds:eventCode"; the
ontology defines `iirds:has-event-code`. `tests/test_terms.py` asserts every
term in `terms.py` is really defined in the bundled ontology, which turns a
guess into a failing test.


## The banner

`iirdsv` with no arguments prints a logo, the version and how to start. Nothing
else does — `check`, `lint` and `all` write into a build log or a pipe, and
`--format json` writes a document another program parses. A banner in front of
that is not noise, it is corruption, so `tests/test_cli.py` asserts it never
appears there.

It is plain ASCII rather than block-drawing characters. Those look better in a
modern terminal and turn into rubbish in a Windows console or over a serial
link, and the machines this tool exists for are the ones with the old fonts.


## Working rule: adversarial review before delivery

Self-review of the SHACL deliverable was run first, against a sealed list of
findings from two independent adversarial passes. Score: five of the issues
found, the two worst missed — a quickstart whose flags silently skipped every
SPARQL shape, and a licence header whose central claim ("wording is this
project's own") was false for 85 of 133 shapes. Both were the kind of error an
author cannot see: one requires *distrusting the documentation you wrote*, the
other *re-deriving a fact you already believe*.

So the rule, standing: before anything is delivered — a release, a submission,
a claim in a README — an adversarial pass by a reviewer that did not write the
material runs against it, and the review's findings become regression tests,
not just fixes. The gate that never catches anything is indistinguishable from
no gate; the reviewer that shares the author's beliefs is indistinguishable
from the author.
