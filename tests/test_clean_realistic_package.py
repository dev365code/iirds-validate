"""The calibration anchor: an ordinary, correct package must report nothing.

Every fixture in this suite before this one was minimal — a blank-node
Rendition, one topic, no navigation — so the rules were never confronted with
what `iirds pack` users actually produce: renditions with IRIs, identities
with domains, parties with vcards, a table of contents. The audit built such a
package and got thirty identical warnings on a correct result, which is the
"too strict" half of the oscillation this project keeps falling into.

This package is the standing answer. It is built the way the specification's
own examples build things, it is correct on purpose, and the gate is **zero
findings of any severity**. Every future rule change runs into it: a rule that
fires here is wrong until the fixture is shown to be wrong, and tightening the
fixture is a reviewed decision, not a side effect.

(The other half of the oscillation — too loose — is held by the corpus, the
spec examples and the mutation tests, which insist defects ARE reported.)
"""
from __future__ import annotations

from conftest import build_package
from iirds_validate import runner

XHTML = ('<?xml version="1.0" encoding="utf-8"?>'
         '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title></head>'
         '<body><h1>%s</h1><p>Ordinary body text.</p></body></html>')

IIRDS = "http://iirds.tekom.de/iirds#"

METADATA = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:vcard="http://www.w3.org/2006/vcard/ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">

  <iirds:Package rdf:about="urn:acme:pkg">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:title>Fan 3000 documentation</iirds:title>
  </iirds:Package>

  <iirds:Document rdf:about="urn:acme:doc">
    <iirds:title>Operating instructions</iirds:title>
    <iirds:language>en</iirds:language>
    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>
    <iirds:is-version-of rdf:resource="urn:acme:io"/>
    <iirds:has-identity rdf:resource="urn:acme:identity"/>
    <iirds:has-content-lifecycle-status rdf:resource="urn:acme:status"/>
    <iirds:relates-to-party rdf:resource="urn:acme:party"/>
    <iirds:has-rendition rdf:resource="urn:acme:rendition-doc"/>
  </iirds:Document>
  <iirds:Rendition rdf:about="urn:acme:rendition-doc">
    <iirds:format>application/xhtml+xml</iirds:format>
    <iirds:source>content/doc.xhtml</iirds:source>
  </iirds:Rendition>

  <iirds:InformationObject rdf:about="urn:acme:io">
    <iirds:title>Operating instructions</iirds:title>
  </iirds:InformationObject>

  <iirds:Topic rdf:about="urn:acme:t1">
    <iirds:title>Safety</iirds:title>
    <iirds:has-rendition rdf:resource="urn:acme:rendition-t1"/>
  </iirds:Topic>
  <iirds:Rendition rdf:about="urn:acme:rendition-t1">
    <iirds:format>application/xhtml+xml</iirds:format>
    <iirds:source>content/t1.xhtml</iirds:source>
  </iirds:Rendition>

  <iirds:Topic rdf:about="urn:acme:t2">
    <iirds:title>Installation</iirds:title>
    <iirds:has-rendition rdf:resource="urn:acme:rendition-t2"/>
  </iirds:Topic>
  <iirds:Rendition rdf:about="urn:acme:rendition-t2">
    <iirds:format>application/xhtml+xml</iirds:format>
    <iirds:source>content/t2.xhtml</iirds:source>
  </iirds:Rendition>

  <iirds:Identity rdf:about="urn:acme:identity">
    <iirds:identifier>FAN3000-OI-EN</iirds:identifier>
    <iirds:has-identity-domain rdf:resource="urn:acme:domain"/>
  </iirds:Identity>
  <iirds:IdentityDomain rdf:about="urn:acme:domain">
    <rdfs:label xml:lang="en">Acme document numbers</rdfs:label>
    <iirds:relates-to-party rdf:resource="urn:acme:party"/>
  </iirds:IdentityDomain>

  <iirds:ContentLifeCycleStatus rdf:about="urn:acme:status">
    <iirds:has-content-lifecycle-status-value rdf:resource="http://iirds.tekom.de/iirds#Released"/>
    <iirds:dateOfStatus rdf:datatype="http://www.w3.org/2001/XMLSchema#dateTimeStamp">2026-08-01T09:00:00+09:00</iirds:dateOfStatus>
  </iirds:ContentLifeCycleStatus>

  <iirds:Party rdf:about="urn:acme:party">
    <iirds:has-party-role rdf:resource="http://iirds.tekom.de/iirds#Manufacturer"/>
    <iirds:relates-to-vcard rdf:resource="urn:acme:card"/>
  </iirds:Party>
  <vcard:Organization rdf:about="urn:acme:card">
    <vcard:organization-name>Acme Fans GmbH</vcard:organization-name>
  </vcard:Organization>

  <iirds:DirectoryNode rdf:about="urn:acme:nav">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-first-child rdf:resource="urn:acme:nav1"/>
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:acme:nav1">
    <iirds:relates-to-information-unit rdf:resource="urn:acme:t1"/>
    <iirds:has-next-sibling rdf:resource="urn:acme:nav2"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:acme:nav2">
    <iirds:relates-to-information-unit rdf:resource="urn:acme:t2"/>
    <iirds:has-next-sibling rdf:resource="http://iirds.tekom.de/iirds#nil"/>
  </iirds:DirectoryNode>
</rdf:RDF>
"""


def realistic(tmp_path):
    return build_package(
        tmp_path, "fan3000.iirds", metadata=METADATA, content=(),
        extra=(("content/doc.xhtml", XHTML % (("Operating instructions",) * 2)),
               ("content/t1.xhtml", XHTML % (("Safety",) * 2)),
               ("content/t2.xhtml", XHTML % (("Installation",) * 2))))


def test_an_ordinary_correct_package_reports_nothing_at_all(tmp_path):
    report = runner.run(realistic(tmp_path), runner.ALL_KINDS)
    assert [(f.rule.id, f.violation.subject) for f in report.findings] == []
    assert report.ok
    assert report.checked > 100
