#!/usr/bin/env python3
"""Check this implementation against the reference tool's own test corpus.

plusmeta's validator ships roughly two hundred RDF fixtures, each named after
the rule it is built to violate — `metadata_iirds_sample-M11_false.rdf` breaks
M11 and nothing else, `..._pass.rdf` breaks nothing. That corpus is the closest
thing to an independent oracle this domain has, and it is MIT licensed.

So: fetch it, run every fixture through this validator, and compare what fires
against what the file name says should fire.

    python tools/crossvalidate.py                  # fetch and run
    python tools/crossvalidate.py --cache DIR      # reuse a previous download
    python tools/crossvalidate.py --rule M11       # one rule

Disagreement is not automatically a bug here. The fixtures encode the reference
tool's reading of the specification, and where the two implementations differ
the interesting question is which reading is right. The report separates
"we miss what they catch" from "we catch what they pass", because those two
failures mean very different things.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iirds_validate import runner  # noqa: E402
from iirds_validate.registry import CATALOG, implemented_ids  # noqa: E402

REPO = "plusmeta/iirds-validation-tool"
FIXTURE_DIR = "tests/files/util/iirds-validation"
API = "https://api.github.com/repos/%s/git/trees/master?recursive=1" % REPO
RAW = "https://raw.githubusercontent.com/%s/master/%%s" % REPO

EMPTY_UPSTREAM = []

def wrap(rdf_bytes: bytes, out: Path) -> Path:
    """The fixtures are bare metadata; the validator wants a container."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, b"application/iirds+zip")
        zf.writestr("META-INF/metadata.rdf", rdf_bytes)
        zf.writestr("content/placeholder.xhtml", "<html/>")
    out.write_bytes(buf.getvalue())
    return out


def fetch_fixtures(cache: Path) -> dict:
    """Download the corpus, and insist that what arrived is usable.

    Several fixture names contain spaces. An unescaped request for those
    silently returns an empty body rather than an error, and a directory of
    zero-byte files reads as "this validator misses everything" — which is how
    an earlier run of this script produced a badly wrong number.
    """
    cache.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(API, timeout=60) as fh:
        tree = json.load(fh)["tree"]
    entries = [e for e in tree
               if e["path"].startswith(FIXTURE_DIR) and e["path"].endswith(".rdf")]

    #: Some fixtures are committed upstream as zero-byte files. That is a gap in
    #: their corpus, not a download failure, and conflating the two is how this
    #: script first reported a badly wrong number.
    global EMPTY_UPSTREAM
    EMPTY_UPSTREAM = sorted(Path(e["path"]).name for e in entries if e.get("size") == 0)
    paths = [e["path"] for e in entries if e.get("size", 1) > 0]

    fetched = 0
    for path in paths:
        target = cache / Path(path).name
        if target.exists() and target.stat().st_size > 0:
            continue
        url = RAW % urllib.parse.quote(path)
        with urllib.request.urlopen(url, timeout=60) as fh:
            body = fh.read()
        if not body.strip():
            raise SystemExit("empty response for %s" % url)
        target.write_bytes(body)
        fetched += 1
    if fetched:
        print("downloaded %d fixture(s)" % fetched, file=sys.stderr)

    empty = [p.name for p in cache.glob("*.rdf") if p.stat().st_size == 0]
    if empty:
        raise SystemExit("zero-byte fixtures after download: %s" % empty[:5])
    return {p.name: p for p in cache.glob("*.rdf")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default=str(ROOT / ".crossvalidate-cache"))
    ap.add_argument("--rule", help="only fixtures for this rule id")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    fixtures = fetch_fixtures(Path(args.cache))
    if not fixtures:
        print("no fixtures", file=sys.stderr)
        return 2

    implemented = implemented_ids()
    tmp = Path(tempfile.mkdtemp(prefix="iirds-xval-"))
    cache = {}

    def fired(name):
        """Which rule ids this validator reports for a fixture."""
        if name not in cache:
            path = fixtures.get(name)
            if path is None:
                cache[name] = None
            else:
                pkg = wrap(path.read_bytes(), tmp / ("%d.iirds" % abs(hash(name))))
                cache[name] = {f.rule.id for f in runner.run(pkg, ("schema",)).findings}
        return cache[name]

    results = {"agree": [], "missed": [], "extra": [], "absent": []}
    clean_noise = defaultdict(int)

    for rule_id, meta in sorted(CATALOG.items()):
        if args.rule and rule_id != args.rule:
            continue
        files = meta.get("testFiles") or {}
        for name in files.get("false", []):
            ids = fired(name)
            if ids is None:
                results["absent"].append((rule_id, name))
            elif rule_id in ids:
                results["agree"].append((rule_id, name))
            else:
                results["missed"].append((rule_id, name,
                                          "implemented but silent" if rule_id in implemented
                                          else "not implemented"))
            if args.verbose and ids is not None:
                print("  %-9s %-56s -> %s" % (rule_id, name[:54], sorted(ids)))
        for name in files.get("true", []):
            ids = fired(name)
            if ids is None:
                continue
            if rule_id in ids:
                results["extra"].append((rule_id, name))
            for other in ids:
                clean_noise[other] += 1

    total = len(results["agree"]) + len(results["missed"])
    print()
    print("=" * 74)
    print("Cross-validation against %s" % REPO)
    print("=" * 74)
    print("  rule/fixture pairs the tool says must fail : %d" % total)
    print("  our rule fires as expected                 : %d  (%.0f%%)"
          % (len(results["agree"]), 100.0 * len(results["agree"]) / max(total, 1)))
    print("  our rule stays silent                      : %d" % len(results["missed"]))
    print("  fires on a fixture the tool says passes    : %d" % len(results["extra"]))
    if results["absent"]:
        print("  fixture is empty upstream, so untestable    : %d" % len(results["absent"]))
    if EMPTY_UPSTREAM:
        print("  (zero-byte fixtures in their repo          : %d)" % len(EMPTY_UPSTREAM))

    if results["missed"]:
        print("\n--- silent where the reference tool reports ---")
        for rule_id, name, why in sorted(results["missed"]):
            print("  %-9s %-52s %s" % (rule_id, name[:50], why))
    if results["extra"]:
        print("\n--- fires on a fixture the reference tool passes ---")
        for rule_id, name in sorted(results["extra"]):
            print("  %-9s %s" % (rule_id, name[:60]))
    if clean_noise:
        print("\n--- what fires across the 'should pass' fixtures ---")
        print("    (these files isolate one rule, so unrelated findings are")
        print("     often true of the fixture rather than wrong)")
        for rule_id, n in sorted(clean_noise.items(), key=lambda kv: -kv[1])[:15]:
            print("  %-9s %d fixture(s)" % (rule_id, n))

    return 1 if results["missed"] or results["extra"] else 0


if __name__ == "__main__":
    sys.exit(main())
