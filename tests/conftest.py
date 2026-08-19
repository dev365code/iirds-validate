"""Fixtures that build iiRDS containers in memory.

Nothing here reads a real package from disk: the test corpus is generated, so
the suite runs anywhere and every fixture states exactly what it is testing.
"""
from __future__ import annotations

import io
import zipfile

import pytest

MIMETYPE = b"application/iirds+zip"

MINIMAL_RDF = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:title>Test package</iirds:title>
  </iirds:Package>
  <iirds:Topic rdf:about="urn:test:topic1">
    <iirds:title>A topic</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>application/xhtml+xml</iirds:format>
        <iirds:source>content/topic1.xhtml</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Topic>
</rdf:RDF>
"""

#: The same graph as MINIMAL_RDF, written the other legal way round: types via
#: rdf:Description + rdf:type, and a different namespace prefix. A validator
#: that walks the XML tree sees nothing here.
DESCRIPTION_STYLE_RDF = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:ii="http://iirds.tekom.de/iirds#">
  <rdf:Description rdf:about="urn:test:package">
    <rdf:type rdf:resource="http://iirds.tekom.de/iirds#Package"/>
    <ii:iiRDSVersion>1.3</ii:iiRDSVersion>
    <ii:title>Test package</ii:title>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:topic1">
    <rdf:type rdf:resource="http://iirds.tekom.de/iirds#Topic"/>
    <ii:title>A topic</ii:title>
    <ii:has-rendition rdf:resource="urn:test:rendition1"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:rendition1">
    <rdf:type rdf:resource="http://iirds.tekom.de/iirds#Rendition"/>
    <ii:format>application/xhtml+xml</ii:format>
    <ii:source>content/topic1.xhtml</ii:source>
  </rdf:Description>
</rdf:RDF>
"""

#: And once more as JSON-LD, which iiRDS 1.3 accepts as an alternative.
MINIMAL_JSONLD = """{
  "@context": {
    "iirds": "http://iirds.tekom.de/iirds#",
    "title": "iirds:title",
    "format": "iirds:format",
    "source": "iirds:source",
    "iiRDSVersion": "iirds:iiRDSVersion",
    "has-rendition": {"@id": "iirds:has-rendition", "@type": "@id"}
  },
  "@graph": [
    {"@id": "urn:test:package", "@type": "iirds:Package",
     "iiRDSVersion": "1.3", "title": "Test package"},
    {"@id": "urn:test:topic1", "@type": "iirds:Topic",
     "title": "A topic", "has-rendition": "urn:test:rendition1"},
    {"@id": "urn:test:rendition1", "@type": "iirds:Rendition",
     "format": "application/xhtml+xml", "source": "content/topic1.xhtml"}
  ]
}
"""


def build_package(tmp_path, name="test.iirds", *, metadata=MINIMAL_RDF, jsonld=None,
                  content=("content/topic1.xhtml",), mimetype=MIMETYPE,
                  mimetype_first=True, mimetype_stored=True, extra=()):
    """Write a container with exactly the properties a test needs."""
    path = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def write_mimetype():
            if mimetype is None:
                return
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED if mimetype_stored else zipfile.ZIP_DEFLATED
            zf.writestr(info, mimetype)

        if mimetype_first:
            write_mimetype()
        if metadata is not None:
            zf.writestr("META-INF/metadata.rdf", metadata)
        if jsonld is not None:
            zf.writestr("META-INF/metadata.jsonld", jsonld)
        for rel in content:
            zf.writestr(rel, "<html/>")
        for rel, data in extra:
            zf.writestr(rel, data)
        if not mimetype_first:
            write_mimetype()

    path.write_bytes(buf.getvalue())
    return path


@pytest.fixture
def make_package(tmp_path):
    def factory(**kwargs):
        return build_package(tmp_path, **kwargs)
    return factory
