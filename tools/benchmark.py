#!/usr/bin/env python3
"""Where the practical ceiling is, measured rather than promised.

"Can it handle large packages?" is the first question a manufacturing
evaluator asks, and it is really three questions, because validation grows
along three independent axes:

  graph     how many information units the metadata describes
  entries   how many files the archive carries
  batch     how many packages one invocation validates

This synthesises packages along each axis and prints time and peak memory, so
the README's numbers are something anyone can re-derive on their own hardware
with one command — the same standard the rest of this repository holds its
claims to.

    python tools/benchmark.py            # the quick preset, ~half a minute
    python tools/benchmark.py --full     # the scales the README quotes

Memory grows with the metadata graph and only with it: rdflib holds the graph
in memory, content files are streamed one at a time, and metadata above 64 MiB
is refused before parsing. Entry count and batch size are disk-bound.
"""
from __future__ import annotations

import argparse
import io
import resource
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iirds_validate import runner  # noqa: E402

TOPIC = """  <iirds:Topic rdf:about="urn:bench:t%d">
    <iirds:title>Topic %d</iirds:title>
    <iirds:has-rendition><iirds:Rendition>
      <iirds:format>application/xhtml+xml</iirds:format>
      <iirds:source>content/t%d.xhtml</iirds:source>
    </iirds:Rendition></iirds:has-rendition>
  </iirds:Topic>
"""
HEAD = ('<?xml version="1.0" encoding="utf-8"?>\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
        '         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n'
        '         xmlns:iirds="http://iirds.tekom.de/iirds#">\n'
        '<iirds:Package rdf:about="urn:bench:package">'
        '<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>'
        '<iirds:title>Benchmark</iirds:title></iirds:Package>\n')
XHTML = ('<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
         '<head><title>t</title></head><body><p>body</p></body></html>')


def synthesise(directory: Path, name: str, topics: int, extra_entries: int = 0) -> Path:
    metadata = HEAD + "".join(TOPIC % (i, i, i) for i in range(topics)) + "</rdf:RDF>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/iirds+zip")
        archive.writestr("META-INF/metadata.rdf", metadata)
        for i in range(topics):
            archive.writestr("content/t%d.xhtml" % i, XHTML)
        for i in range(extra_entries):
            archive.writestr("media/asset%06d.png" % i, b"\x89PNG\r\n")
    path = directory / name
    path.write_bytes(buffer.getvalue())
    return path


def rss_mb() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak / (1024 * 1024 if sys.platform == "darwin" else 1024))


def measure(label: str, path: Path, runs=None) -> None:
    started = time.monotonic()
    if runs is None:
        report = runner.run(path, runner.ALL_KINDS)
        outcome = "findings %d, ok=%s" % (len(report.findings), report.ok)
    else:
        clean = sum(1 for p in runs if runner.run(p, runner.ALL_KINDS).ok)
        outcome = "%d of %d clean" % (clean, len(runs))
    elapsed = time.monotonic() - started
    print("  %-34s %7.1fs   peak %4d MB   %s" % (label, elapsed, rss_mb(), outcome))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="the scales the README quotes")
    args = ap.parse_args()

    graph_axis = (1_000, 5_000, 20_000, 50_000) if args.full else (1_000, 5_000)
    entry_axis = (20_000, 70_000) if args.full else (10_000,)
    batch_size = 200 if args.full else 40

    workspace = Path(tempfile.mkdtemp(prefix="iirds-bench-"))
    try:
        print("graph axis — information units in the metadata (memory lives here)")
        for topics in graph_axis:
            package = synthesise(workspace, "graph%d.iirds" % topics, topics)
            measure("%6d topics, %5.1f MB metadata" % (
                topics, len(HEAD) * 0 + package.stat().st_size / 1e6), package)

        print("entry axis — archive entries beyond the graph (disk-bound)")
        for entries in entry_axis:
            package = synthesise(workspace, "entries%d.iirds" % entries, 100, entries)
            measure("%6d entries, 100 topics" % (entries + 202), package)

        print("batch axis — many packages, one invocation")
        batch_dir = workspace / "batch"
        batch_dir.mkdir()
        packages = [synthesise(batch_dir, "p%03d.iirds" % i, 20) for i in range(batch_size)]
        measure("%6d packages x 20 topics" % batch_size, batch_dir, runs=packages)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    print("\nPeak memory is cumulative for the process (ru_maxrss never falls), so the")
    print("honest per-package ceiling is the graph-axis row for your largest package.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
