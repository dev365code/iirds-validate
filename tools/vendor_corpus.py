#!/usr/bin/env python3
"""Bring the reference fixture corpus into the repository, at a fixed revision.

Cross-validation against plusmeta's own corpus is the only external check this
project has, and every number it produces was being computed against a corpus
downloaded at run time from a moving branch. A figure nobody else can reproduce
is a figure, not evidence — and this repository's whole argument is that a
validator should be able to show its work.

So the corpus is vendored: 130 files, about 4 MB, under the revision the rule
catalogue was extracted from, with a hash for each one. That makes "these are
their fixtures, unmodified" checkable rather than trusted, offline and
tomorrow, by someone who is not us. It is the same treatment the bundled
ontologies already get, for the same reason.

    python tools/vendor_corpus.py            # fetch and write the manifest
    python tools/vendor_corpus.py --check    # verify what is committed, offline

The fixtures are NOT repaired. Some are malformed and two are zero-byte, and
those are recorded by name rather than fixed: a repaired fixture is our reading
of what plusmeta meant, and it would contaminate the one oracle here that is
not ours.

A third category is separated out because conflating it with the second would
be its own small dishonesty. Many fixtures are excerpts from the standard's
numbered examples and carry no `rdf:RDF` element, so they raise "unbound
prefix" on their own. Those are fragments, not breakage: material this project
could be checking and currently is not.

MIT, Copyright 2020 plusmeta GmbH. Their LICENSE is fetched alongside and kept
next to the files it covers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from crossvalidate import API, FIXTURE_DIR, RAW, REF, REPO  # noqa: E402

CORPUS = ROOT / "tests" / "corpus" / "plusmeta"
FILES = CORPUS / "files"
MANIFEST = CORPUS / "MANIFEST.json"
LICENCE = CORPUS / "LICENSE"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


#: The prefixes the specification's examples assume are already in scope.
#:
#: Many fixtures are excerpts lifted straight out of the standard's numbered
#: examples, so they carry no `rdf:RDF` element and declare no namespaces —
#: the surrounding prose did that. Parsed on their own they raise "unbound
#: prefix", which is a fragment, not a defect, and the difference matters: one
#: is material this project could be checking and is not, the other is upstream
#: breakage nobody can act on. Recorded here rather than left as a constant in
#: whatever script needs it next, so the classification below is reproducible.
NAMESPACE_WRAPPER = (
    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
    ' xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"'
    ' xmlns:iirds="http://iirds.tekom.de/iirds#"'
    ' xmlns:dcterms="http://purl.org/dc/terms/"'
    ' xmlns:skos="http://www.w3.org/2004/02/skos/core#"'
    ' xmlns:owl="http://www.w3.org/2002/07/owl#"'
    ' xmlns:vcard="http://www.w3.org/2006/vcard/ns#">%s</rdf:RDF>')


def parses(data: bytes) -> bool:
    try:
        ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return False
    return True


def classify(data: bytes) -> str:
    """One of: ok, zero_byte, needs_namespace_wrapper, malformed_xml."""
    if not data.strip():
        return "zero_byte"
    if parses(data):
        return "ok"
    text = data.decode("utf-8", "replace")
    body = text.split("?>", 1)[1] if text.lstrip().startswith("<?xml") else text
    if parses((NAMESPACE_WRAPPER % body).encode("utf-8")):
        return "needs_namespace_wrapper"
    return "malformed_xml"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as handle:
        return handle.read()


def download(retrieved: str) -> dict:
    tree = json.loads(fetch(API))["tree"]
    entries = sorted((e for e in tree
                      if e["path"].startswith(FIXTURE_DIR) and e["path"].endswith(".rdf")),
                     key=lambda e: e["path"])
    if not entries:
        raise SystemExit("no fixtures at %s — has the upstream layout moved?" % REF)

    FILES.mkdir(parents=True, exist_ok=True)
    for stale in FILES.glob("*.rdf"):
        stale.unlink()

    files = {}
    buckets = {"zero_byte": [], "needs_namespace_wrapper": [], "malformed_xml": []}
    for entry in entries:
        name = Path(entry["path"]).name
        # Several fixture names contain spaces. An unescaped request for those
        # returns an empty body rather than an error, which is how an earlier
        # run of the cross-validator produced a badly wrong number.
        body = b"" if entry.get("size") == 0 else fetch(RAW % urllib.parse.quote(entry["path"]))
        if entry.get("size", 0) > 0 and not body.strip():
            raise SystemExit("empty response for %s" % entry["path"])
        (FILES / name).write_bytes(body)
        verdict = classify(body)
        files[name] = {"sha256": digest(body), "bytes": len(body), "parses": verdict}
        if verdict != "ok":
            buckets[verdict].append(name)

    LICENCE.write_bytes(fetch("https://raw.githubusercontent.com/%s/%s/LICENSE.md" % (REPO, REF)))

    return {
        "_source": "https://github.com/%s" % REPO,
        "_commit": REF,
        "_path": FIXTURE_DIR,
        "_retrieved": retrieved,
        "_licence": "MIT, Copyright 2020 plusmeta GmbH — see LICENSE beside this file",
        "_generated_by": "tools/vendor_corpus.py",
        "_note": ("Verbatim. The defective fixtures below are upstream's and are "
                  "recorded rather than repaired: a repaired fixture would be our "
                  "reading of what they meant, and would contaminate the only "
                  "external oracle this project has."),
        "_namespace_wrapper": NAMESPACE_WRAPPER,
        "zero_byte": sorted(buckets["zero_byte"]),
        "needs_namespace_wrapper": sorted(buckets["needs_namespace_wrapper"]),
        "malformed_xml": sorted(buckets["malformed_xml"]),
        "files": dict(sorted(files.items())),
    }


def check() -> int:
    if not MANIFEST.exists():
        print("no manifest; run without --check first", file=sys.stderr)
        return 2
    manifest = json.loads(MANIFEST.read_text("utf-8"))

    if manifest["_commit"] != REF:
        print("manifest is at %s, the catalogue is at %s" % (manifest["_commit"], REF),
              file=sys.stderr)
        return 1

    problems = []
    on_disk = {p.name for p in FILES.glob("*.rdf")}
    recorded = set(manifest["files"])
    for name in sorted(recorded - on_disk):
        problems.append("missing: %s" % name)
    for name in sorted(on_disk - recorded):
        problems.append("not in the manifest: %s" % name)
    for name in sorted(recorded & on_disk):
        if digest((FILES / name).read_bytes()) != manifest["files"][name]["sha256"]:
            problems.append("modified: %s" % name)

    for line in problems[:10]:
        print("  " + line, file=sys.stderr)
    if problems:
        print("%d problem(s); the corpus is not upstream's" % len(problems), file=sys.stderr)
        return 1

    print("%d fixtures verified against %s — upstream's, unmodified" % (
        len(recorded), manifest["_commit"][:12]))
    print("  %d parse as they stand, %d are fragments needing a namespace wrapper, "
          "%d are malformed, %d are zero-byte"
          % (sum(1 for f in manifest["files"].values() if f["parses"] == "ok"),
             len(manifest["needs_namespace_wrapper"]),
             len(manifest["malformed_xml"]), len(manifest["zero_byte"])))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify the committed corpus, offline")
    ap.add_argument("--retrieved", default="unrecorded",
                    help="date of retrieval, recorded in the manifest")
    args = ap.parse_args()

    if args.check:
        return check()

    manifest = download(args.retrieved)
    CORPUS.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return check()


if __name__ == "__main__":
    sys.exit(main())
