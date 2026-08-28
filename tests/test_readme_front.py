"""The README's front sample is generated output, not prose about output.

It was hand-written twice and stale within a commit both times: first missing
the remedy lines the tool always prints, then showing a summary wording and a
rule count one release behind. A sample nobody regenerates is a screenshot of
a program that no longer exists — so the block is compared, byte for byte,
against what the tool prints for a package built here. When the output
changes, this fails, and regenerating is one command:

    python tests/test_readme_front.py > /tmp/block.txt   # then paste, or let
    python tests/test_readme_front.py --write            # it edit README.md
"""
from __future__ import annotations

import io
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: A small package with exactly two stories: a Rendition missing its format
#: (M11, the specification violation) and a relation to an IRI the package
#: never describes (L1, the interoperability warning). Everything else about
#: it is clean, so the sample stays two findings long.
METADATA = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:example:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:title>Operating manual</iirds:title>
  </iirds:Package>
  <iirds:Document rdf:about="urn:example:manual">
    <iirds:title>Operating manual</iirds:title>
    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>
    <iirds:relates-to-event rdf:resource="urn:example:event/al-204"/>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:source>content/manual.xhtml</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Document>
</rdf:RDF>
"""
XHTML = ('<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
         '<head><title>Manual</title></head><body><p>…</p></body></html>')


def expected_block() -> str:
    from iirds_validate import report, runner

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "manual.iirds"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/iirds+zip")
            archive.writestr("META-INF/metadata.rdf", METADATA)
            archive.writestr("content/manual.xhtml", XHTML)
        path.write_bytes(buffer.getvalue())

        out = io.StringIO()
        report.render_text(runner.run(path, runner.ALL_KINDS), stream=out)
        body = out.getvalue().rstrip("\n")

    return "$ iirds manual.iirds\n%s\n$ echo $?\n1" % body


FENCE = re.compile(r"```console\n\$ iirds manual\.iirds\n.*?\n```", re.S)


def test_the_front_sample_is_what_the_tool_prints():
    readme = (ROOT / "README.md").read_text("utf-8")
    match = FENCE.search(readme)
    assert match, "the README has lost its front sample"
    assert match.group(0) == "```console\n%s\n```" % expected_block(), \
        "the front sample is stale; run: python tests/test_readme_front.py --write"


def test_the_sample_package_tells_exactly_the_two_stories():
    """One error, one warning, nothing else — or the sample stops teaching."""
    from iirds_validate import runner

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "manual.iirds"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/iirds+zip")
            archive.writestr("META-INF/metadata.rdf", METADATA)
            archive.writestr("content/manual.xhtml", XHTML)
        path.write_bytes(buffer.getvalue())
        result = runner.run(path, runner.ALL_KINDS)

    assert [f.rule.id for f in result.findings] == ["M11", "L1"]


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    block = "```console\n%s\n```" % expected_block()
    if "--write" in sys.argv:
        readme_path = ROOT / "README.md"
        text = readme_path.read_text("utf-8")
        updated, count = FENCE.subn(lambda _m: block, text)
        if count != 1:
            sys.exit("could not find exactly one front sample to replace")
        readme_path.write_text(updated, "utf-8")
        print("README.md front sample regenerated")
    else:
        print(block)
