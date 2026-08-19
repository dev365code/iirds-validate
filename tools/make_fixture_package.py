#!/usr/bin/env python3
"""Build an .iirds container with exactly the properties you ask for.

The single place a test container is constructed. `tests/conftest.py` imports
`build_package` from here, and CI calls this module to produce something for the
installed-wheel smoke test to validate — a committed binary fixture would be
opaque, and two builders would drift.

    python tools/make_fixture_package.py out.iirds
    python tools/make_fixture_package.py out.iirds --broken mimetype
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

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

#: The same graph, written the other legal way round: types via rdf:Description
#: plus rdf:type, references instead of nesting, and a different prefix. A
#: validator that walks the XML tree sees nothing here.
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


def build_package(directory, name="test.iirds", *, metadata=MINIMAL_RDF, jsonld=None,
                  content=("content/topic1.xhtml",), mimetype=MIMETYPE,
                  mimetype_first=True, mimetype_stored=True, extra=()):
    """Write a container. Every keyword exists so a test can break one thing."""
    path = Path(directory) / name
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


BREAKAGE = {
    "none": {},
    "mimetype": {"mimetype": b"application/iirds+zip\n"},
    "missing-format": {"metadata": MINIMAL_RDF.replace(
        "        <iirds:format>application/xhtml+xml</iirds:format>\n", "")},
    "missing-content": {"content": ()},
    "description-style": {"metadata": DESCRIPTION_STYLE_RDF},
    "jsonld-only": {"metadata": None, "jsonld": MINIMAL_JSONLD},
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output", help="path of the .iirds file to write")
    ap.add_argument("--broken", choices=sorted(BREAKAGE), default="none",
                    help="introduce one specific defect (default: none)")
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    path = build_package(out.parent, out.name, **BREAKAGE[args.broken])
    print("%s (%d bytes, %s)" % (path, path.stat().st_size, args.broken))
    return 0


if __name__ == "__main__":
    sys.exit(main())
