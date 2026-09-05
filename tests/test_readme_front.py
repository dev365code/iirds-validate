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


def test_the_cache_busters_are_the_files_they_point_at():
    """The front page loads two SVGs from raw.githubusercontent, each with a
    `?v=` that exists to defeat the CDN's cache. A cache-buster is a promise
    that this URL means this file, and it is a number somebody types — so it
    goes stale silently and the reader keeps seeing the old picture.

    Both were stale when this test was written: the README said `c31c4de1`
    and `82f3f8d1`, and the files hashed to `c341d7c2` and `9b629295`. The
    numbers live in a test now, like every other published figure here.
    """
    import hashlib
    import re

    readme = (ROOT / "README.md").read_text("utf-8")
    stated = dict(re.findall(r"docs/assets/([\w.-]+)\?v=([0-9a-f]{8})", readme))
    assert stated, "the README no longer loads its assets with a cache-buster"
    for name, said in sorted(stated.items()):
        path = ROOT / "docs" / "assets" / name
        assert path.exists(), "README points at docs/assets/%s, which is not here" % name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
        assert said == actual, (
            "docs/assets/%s is %s and the README asks for ?v=%s — regenerate the "
            "asset or move the number, but they have to be the same file"
            % (name, actual, said))


#: The package `docs/assets/tenseconds.svg` says it is a picture of. Built
#: here rather than kept in `fixtures/`, because what has to stay true is that
#: the picture matches a run, and a fixture that drifts from the picture is the
#: same problem one level down.
TERMSHOT_PACKAGE = {
    "mimetype": b"application/zip",
    "META-INF/metadata.rdf": (
        '<?xml version="1.0"?><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:iirds="http://iirds.tekom.de/iirds#">'
        '<iirds:Topic rdf:about="urn:x:t1">'
        "<iirds:title>A topic</iirds:title></iirds:Topic></rdf:RDF>"),
    "content/topic1.xhtml": "<html/>",
}


def test_the_terminal_picture_is_a_run_that_happened(tmp_path):
    """`docs/assets/tenseconds.svg` is captioned "Real iirds check output" and
    the front page leads with it. Its tail said "164 rules checked, 21 not
    applicable" while a run of the package it depicts said 171 and 24, and its
    two errors were in the other order — M3 sorts first now that it is marked
    a cause, which a change to the rules did without anybody looking at the
    picture.

    So the two numbers and the order are read off a real run. The prose in
    between is the rules' own text and is left alone; what goes stale is what
    a release moves.
    """
    import io
    import re
    import zipfile

    from iirds_validate import runner

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, TERMSHOT_PACKAGE["mimetype"])
        for name, body in TERMSHOT_PACKAGE.items():
            if name != "mimetype":
                archive.writestr(name, body)
    package = tmp_path / "broken.iirds"
    package.write_bytes(buf.getvalue())

    report = runner.check(package)
    picture = (ROOT / "docs" / "assets" / "tenseconds.svg").read_text("utf-8")

    stated = re.search(r"(\d+) rules checked, (\d+) not applicable", picture)
    assert stated, "the picture no longer states how many rules ran"
    skipped = sum(len(v) for v in report.not_applicable.values())
    assert (int(stated.group(1)), int(stated.group(2))) == (report.checked, skipped), (
        "the picture says %s and the run says %s"
        % (stated.groups(), (report.checked, skipped)))

    shown = re.findall(r">(C\d+|M\d+(?:\.\d+)?)<", picture)
    reported = [f.rule.id for f in report.findings]
    assert shown == [r for r in reported if r in shown], (
        "the picture shows %s and the report reads %s" % (shown, reported))

    # The third copy, and the one that goes stale unwatched: the `alt` text
    # states the same run in prose, for a screen reader and for anyone whose
    # image does not load. It said "ERROR C5 …; ERROR M3 …; FAIL, 164 rules
    # checked" while the picture beside it had been corrected to M3 first and
    # 171 — a caption reading "Real output" describing a run that stopped
    # happening. Two copies were held and the third was not, which is how the
    # first two came to be wrong in the first place.
    readme = (ROOT / "README.md").read_text("utf-8")
    alt = re.search(r'alt="(Real iirds check output[^"]*)"', readme)
    assert alt, "the README no longer describes the terminal picture"
    caption = alt.group(1)
    said = re.search(r"(\d+) rules checked", caption)
    assert said and int(said.group(1)) == report.checked, (
        "the alt text says %s rules checked and the run says %d"
        % (said and said.group(1), report.checked))
    assert re.findall(r"ERROR (C\d+|M\d+(?:\.\d+)?)", caption) == shown, (
        "the alt text lists %s and the picture shows %s"
        % (re.findall(r"ERROR (C\d+|M\d+(?:\.\d+)?)", caption), shown))
