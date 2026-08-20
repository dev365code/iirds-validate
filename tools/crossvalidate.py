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
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iirds_validate import runner  # noqa: E402
from iirds_validate.registry import CATALOG, PROVENANCE, implemented_ids  # noqa: E402

REPO = "plusmeta/iirds-validation-tool"
FIXTURE_DIR = "tests/files/util/iirds-validation"
#: The revision the rule catalogue was extracted from, not a branch.
#:
#: `extract_catalog.py` pins a commit and explains why in its own docstring:
#: regenerating against a moved `master` would silently produce a different
#: file. The same argument applies with more force here, because this script
#: compares the two — fetching fixtures from `master` while the rules came from
#: a commit means the corpus and the catalogue can drift apart with nothing
#: saying so, and every figure in docs/divergences.md was computed that way.
REF = PROVENANCE["_commit"]
CORPUS = ROOT / "tests" / "corpus" / "plusmeta"
FIXTURES = CORPUS / "files"
MANIFEST = CORPUS / "MANIFEST.json"
API = "https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (REPO, REF)
RAW = "https://raw.githubusercontent.com/%s/%s/%%s" % (REPO, REF)


def cache_dir(base, ref: str = REF) -> Path:
    """Cached fixtures live under the revision they were fetched from.

    They were previously keyed by bare filename, so changing the pin would have
    silently reused files downloaded from the old one — the same defect as the
    unpinned URL, one layer down, and the one that would have survived fixing
    the URL alone.
    """
    return Path(base) / ref[:12]

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


def load_fixtures() -> dict:
    """Read the vendored corpus. No network, no cache, no branch.

    This used to download from `master` on every run, which meant two things
    that only look like one. Cross-validation needed the internet, so nobody on
    a locked-down machine could reproduce a single number this project
    published — a poor look for a tool whose entire argument is that validation
    should not require a network. And the corpus could move underneath the
    pinned catalogue, so the figures were computed against an input that no
    longer existed by the time anyone read them.

    `tools/vendor_corpus.py` brings the fixtures in at the catalogue's own
    revision and records a SHA-256 for each; `tests/test_corpus_integrity.py`
    checks them on every test run, on every platform. By the time this function
    is reached the bytes have been vouched for, so it does the cheap
    consistency check and gets out of the way.
    """
    if not MANIFEST.exists():
        raise SystemExit("no vendored corpus; run tools/vendor_corpus.py")
    manifest = json.loads(MANIFEST.read_text("utf-8"))

    if manifest["_commit"] != REF:
        raise SystemExit("corpus is at %s, the catalogue is at %s — re-run "
                         "tools/vendor_corpus.py" % (manifest["_commit"][:12], REF[:12]))

    #: Two fixtures are committed upstream as zero-byte files. That is a gap in
    #: their corpus, not a download failure, and conflating the two is how this
    #: script once reported a badly wrong number. They are on disk, empty, and
    #: excluded here so that "no fixture" and "an empty fixture" stay distinct.
    global EMPTY_UPSTREAM
    EMPTY_UPSTREAM = list(manifest["zero_byte"])

    fixtures = {name: FIXTURES / name for name in manifest["files"]
                if name not in manifest["zero_byte"]}
    missing = sorted(name for name, path in fixtures.items() if not path.exists())
    if missing:
        raise SystemExit("corpus incomplete: %s" % missing[:5])
    return fixtures


BASELINE = ROOT / "docs" / "agreement.json"


def write_baseline(verdicts: dict) -> int:
    """Record what the agreement is, so that CI can notice it changing.

    Not a target, and not a score. Every figure quoted in docs/divergences.md
    is derived from this file, and the only thing asserted about it is that it
    does not move without somebody saying so — which is the difference between
    a number in a document and a number anybody is accountable for.
    """
    counts = {}
    for verdict in verdicts.values():
        counts[verdict] = counts.get(verdict, 0) + 1
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps({
        "_commit": REF,
        "_generated_by": "tools/crossvalidate.py --write-baseline",
        "_note": ("Per-pair agreement with the reference tool over the vendored "
                  "corpus. Regenerate deliberately, never to make CI green: a "
                  "pair moving from agree to silent is a regression, and a pair "
                  "moving the other way still wants a look at why."),
        "counts": dict(sorted(counts.items())),
        "verdicts": dict(sorted(verdicts.items())),
    }, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print("recorded %d pairs: %s" % (len(verdicts), dict(sorted(counts.items()))))
    return 0


def compare_to_baseline(verdicts: dict) -> int:
    if not BASELINE.exists():
        print("no baseline; run --write-baseline", file=sys.stderr)
        return 2
    recorded = json.loads(BASELINE.read_text("utf-8"))["verdicts"]

    changed = sorted(k for k in set(recorded) & set(verdicts) if recorded[k] != verdicts[k])
    gone = sorted(set(recorded) - set(verdicts))
    new = sorted(set(verdicts) - set(recorded))

    for key in changed:
        print("  %-64s %s -> %s" % (key[:64], recorded[key], verdicts[key]))
    for key in gone:
        print("  %-64s %s -> pair no longer exists" % (key[:64], recorded[key]))
    for key in new:
        print("  %-64s new pair, %s" % (key[:64], verdicts[key]))

    if changed or gone or new:
        print("\nagreement has moved from the baseline. If the change is intended, "
              "rerun with --write-baseline and say why in docs/divergences.md.",
              file=sys.stderr)
        return 1
    print("agreement unchanged: %d pairs" % len(verdicts))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)

    ap.add_argument("--rule", help="only fixtures for this rule id")
    ap.add_argument("--write-baseline", action="store_true",
                    help="record the current agreement in docs/agreement.json")
    ap.add_argument("--check", action="store_true",
                    help="fail if the agreement has moved from the recorded baseline")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    fixtures = load_fixtures()
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

    verdicts = {}
    for rule_id, name in results["agree"]:
        verdicts["%s|%s" % (rule_id, name)] = "agree"
    for rule_id, name, _why in results["missed"]:
        verdicts["%s|%s" % (rule_id, name)] = "silent"
    for rule_id, name in results["extra"]:
        verdicts["%s|%s" % (rule_id, name)] = "extra"
    for rule_id, name in results["absent"]:
        verdicts["%s|%s" % (rule_id, name)] = "untestable"

    if args.write_baseline:
        return write_baseline(verdicts)
    if args.check:
        return compare_to_baseline(verdicts)

    # Plain runs report; they do not judge. "Silent on a pair the reference
    # reports" was an exit code 1, which made the whole exercise unusable in
    # CI — most of that silence is explained, and a tool that always fails is
    # a tool nobody wires up. What CI gates on is movement, via --check.
    return 0


if __name__ == "__main__":
    sys.exit(main())
