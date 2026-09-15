#!/usr/bin/env python3
"""Explain, per rule, why this validator stays quiet where the reference tool reports.

`crossvalidate.py` produces a number. A number is not a diagnosis, and the
three reasons a rule can be silent need very different responses:

  invisible   the fixture's defect does not exist in the RDF graph at all —
              usually a statement repeated verbatim, which RDF collapses into
              one. Nothing to fix; the two tools are reading different things.
  mismatched  the fixture does contain a defect, but not one this rule is
              about. The corpus lists it under this rule anyway. Their problem.
  ours        the fixture contains exactly the defect the rule describes and
              the rule missed it. Our bug.

The classification is mechanical: parse the rule's `false` fixture and its
`true` fixtures, canonicalise both, and diff. What the diff contains decides
the category, and the diff is printed so the judgement can be checked rather
than trusted.

    python tools/explain_silence.py               # every silent rule
    python tools/explain_silence.py --rule M24.2  # one
    python tools/explain_silence.py --category ours
    python tools/explain_silence.py --check       # the record has not moved

`docs/divergences.md` states this classification a figure at a time -- seven
rows of a table, and sentences that restate them. Nothing read the two
together, so a paragraph said 34 where the table said 32, and "Six pairs" sat
four weeks beside a table that said thirteen. So the classification is written
down the way `docs/crossvalidate` writes agreement: `docs/silence.json`, one
line per pair, and the tests hold each figure to the bucket it names rather
than to a total, which two rows swapping values would pass.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "silence.json"

#: Every bucket, in the order the human view prints them. One list: the
#: record is built from the buckets and checked against this, so a bucket
#: that exists and is not named here stops the tool rather than vanishing.
ORDER = ("ours", "invisible", "mismatched", "gated", "neither", "malformed",
         "unclassified")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from rdflib import Graph  # noqa: E402
from rdflib.compare import graph_diff, to_isomorphic  # noqa: E402

from crossvalidate import load_fixtures  # noqa: E402
from iirds_validate import runner  # noqa: E402
from iirds_validate.model import PACKAGE_BASE  # noqa: E402
from iirds_validate.registry import CATALOG, PROVENANCE, implemented_ids  # noqa: E402

RDF_ABOUT = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about"
RDF_RESOURCE = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource"

#: Categories of the reference tool's rules whose assertion is simple enough to
#: reimplement exactly. Together they are 61 of its 135 schema rules, and they
#: are the ones this project generates from a table, so being able to run their
#: version against the same fixture settles disagreements outright.
PORTABLE = {"must have iri", "absolute iri",
            "not intended to be used directly.", "not intented to be used directly."}


def reference_says_ok(meta, path: Path):
    """Run the reference tool's own assertion. None if it is not portable.

    Both families select elements by local name and inspect rdf:about, which
    means an element that is not present at all cannot fail them: `every()`
    over an empty list is true. That matters, because their corpus lists
    fixtures under rules whose class the fixture never mentions.
    """
    category = (meta.get("category") or "").strip().lower()
    if category not in PORTABLE:
        return None
    names = {n.strip() for n in (meta.get("path") or "").split(",") if n.strip()}
    if not names:
        return None

    import xml.etree.ElementTree as ElementTree
    try:
        root = ElementTree.parse(str(path)).getroot()
    except ElementTree.ParseError:
        return None
    selected = [el for el in root.iter() if el.tag.split("}")[-1] in names]

    if category.startswith("not int"):
        return len(selected) == 0
    return all(el.get(RDF_ABOUT) not in (None, "") for el in selected)


def parse(path: Path):
    graph = Graph()
    graph.parse(data=path.read_bytes(), format="xml", publicID=PACKAGE_BASE)
    return graph


def wrap(path: Path, tmp: Path) -> Path:
    out = tmp / ("%d.iirds" % abs(hash(path.name)))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, b"application/iirds+zip")
        zf.writestr("META-INF/metadata.rdf", path.read_bytes())
        zf.writestr("content/placeholder.xhtml", "<html/>")
    out.write_bytes(buf.getvalue())
    return out


def short(term) -> str:
    text = str(term)
    for prefix in ("http://iirds.tekom.de/iirds/domain/", "http://iirds.tekom.de/iirds#",
                   "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                   "http://www.w3.org/2000/01/rdf-schema#", PACKAGE_BASE):
        text = text.replace(prefix, "")
    return text[:52]


def triple(t) -> str:
    return "%s  %s  %s" % tuple(short(x) for x in t)


def write_record(verdicts: dict) -> int:
    """Record which bucket each silent pair is in, so a figure has a source.

    Not a target and not a score, the same as `docs/agreement.json`: what is
    asserted is that it does not move without somebody saying so. The figures
    in `docs/divergences.md` are read from here per bucket, which is what a
    total could not do -- two rows swapping values leave the total alone.
    """
    counts = dict.fromkeys(ORDER, 0)
    for bucket in verdicts.values():
        counts[bucket] += 1
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps({
        "_commit": PROVENANCE["_commit"],
        "_generated_by": "tools/explain_silence.py --write-record",
        "_note": ("Why this validator is silent on each pair the reference tool "
                  "reports, one line per pair. `ours` is this project's bug and "
                  "the rest are not; regenerate deliberately, and say in "
                  "docs/divergences.md what moved."),
        "counts": dict(sorted(counts.items())),
        "verdicts": dict(sorted(verdicts.items())),
    }, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print("recorded %d pairs: %s" % (len(verdicts), dict(sorted(counts.items()))))
    return 0


def compare_to_record(verdicts: dict) -> int:
    if not RECORD.exists():
        print("no record; run --write-record", file=sys.stderr)
        return 2
    document = json.loads(RECORD.read_text("utf-8"))
    recorded = document["verdicts"]

    # The counts are what `docs/divergences.md` is held to, and comparing the
    # pairs alone leaves them unchecked: swapping two numbers in this field and
    # making the document agree with the swap passed both gates green.
    tally = dict.fromkeys(ORDER, 0)
    for bucket in recorded.values():
        tally[bucket] = tally.get(bucket, 0) + 1
    if document.get("counts") != tally:
        print("docs/silence.json counts %s, and its own pairs are %s"
              % (document.get("counts"), tally), file=sys.stderr)
        return 1

    changed = sorted(k for k in set(recorded) & set(verdicts) if recorded[k] != verdicts[k])
    gone = sorted(set(recorded) - set(verdicts))
    fresh = sorted(set(verdicts) - set(recorded))

    for key in changed:
        print("  %-64s %s -> %s" % (key[:64], recorded[key], verdicts[key]))
    for key in gone:
        print("  %-64s %s -> pair no longer silent" % (key[:64], recorded[key]))
    for key in fresh:
        print("  %-64s newly silent, %s" % (key[:64], verdicts[key]))

    if changed or gone or fresh:
        print("\nthe classification has moved from the record. If that is intended, "
              "rerun with --write-record and say why in docs/divergences.md.",
              file=sys.stderr)
        return 1
    print("classification unchanged: %d pairs: %s" % (len(verdicts), tally))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rule")
    ap.add_argument("--category",
                    choices=("invisible", "mismatched", "ours", "gated", "neither",
                             "malformed", "unclassified"))
    ap.add_argument("--quiet", action="store_true", help="counts only")
    ap.add_argument("--write-record", action="store_true",
                    help="record the current classification in docs/silence.json")
    ap.add_argument("--check", action="store_true",
                    help="fail if the classification has moved from the record")
    args = ap.parse_args()
    # Neither combination has a use, and both would quietly replace a record
    # that a failing --check is pointing at.
    if args.write_record and args.check:
        ap.error("--write-record and --check ask opposite questions")
    if args.write_record and (args.rule or args.category):
        ap.error("--write-record records every pair; --rule and --category do not")

    fixtures = load_fixtures()
    implemented = implemented_ids()
    tmp = Path(tempfile.mkdtemp(prefix="iirds-explain-"))
    fired_cache = {}

    def fired(name):
        if name not in fired_cache:
            path = fixtures.get(name)
            fired_cache[name] = None if path is None else {
                f.rule.id for f in runner.run(wrap(path, tmp), ("schema",)).findings}
        return fired_cache[name]

    buckets = {"malformed": [], "gated": [], "neither": [], "invisible": [], "mismatched": [], "ours": [],
               "unclassified": []}
    registered = {r.id: r for r in __import__("iirds_validate.registry",
                                              fromlist=["all_rules"]).all_rules()}

    for rule_id, meta in sorted(CATALOG.items()):
        if args.rule and rule_id != args.rule:
            continue
        files = meta.get("testFiles") or {}
        for bad_name in files.get("false", []):
            ids = fired(bad_name)
            if ids is None or rule_id in ids:
                continue                                   # untestable, or we caught it

            bad = fixtures[bad_name]

            # A fixture that is not well-formed XML cannot be assessed for
            # graph rules at all; the parse failure is what gets reported. A
            # browser DOMParser recovers a partial document and carries on,
            # which is why the reference tool still evaluates these.
            try:
                parse(bad)
            except Exception as exc:
                buckets["malformed"].append(
                    (rule_id, bad_name, "not well-formed: %s" % str(exc)[:52], []))
                continue

            # Their unit test calls validateSingleRule directly, which skips
            # the version and variant filters their own product applies. A rule
            # that does not apply to the fixture's declared version would be
            # skipped by their tool too, so silence here is agreement.
            rule = registered.get(rule_id)
            if rule is not None:
                ctx = runner.load(wrap(bad, tmp))
                if not rule.applies_to(ctx.version, ctx.variant):
                    buckets["gated"].append(
                        (rule_id, bad_name,
                         "rule is %s/%s; fixture is %s/%s" % (
                             ",".join(rule.versions) or "any", ",".join(rule.variants) or "any",
                             ctx.version, ctx.variant), []))
                    continue

            # Does their own assertion fire here? If not, the pair is broken in
            # their corpus and says nothing about this implementation.
            if reference_says_ok(meta, bad) is True:
                buckets["neither"].append((rule_id, bad_name, "reference passes it too", []))
                continue

            good_names = [n for n in files.get("true", []) if n in fixtures]
            if not good_names:
                buckets["unclassified"].append((rule_id, bad_name, "no passing fixture", []))
                continue

            best = None
            for good_name in good_names:
                try:
                    removed, added = graph_diff(to_isomorphic(parse(fixtures[good_name])),
                                                to_isomorphic(parse(bad)))[1:]
                except Exception as exc:                    # pragma: no cover
                    buckets["unclassified"].append((rule_id, bad_name, str(exc)[:60], []))
                    best = "error"
                    break
                size = len(removed) + len(added)
                if best is None or size < best[0]:
                    best = (size, good_name, removed, added)
            if best == "error":
                continue

            _size, good_name, removed, added = best
            changes = ([("-", t) for t in sorted(removed, key=str)][:6] +
                       [("+", t) for t in sorted(added, key=str)][:6])

            if not changes:
                category = "invisible"
            else:
                # Does anything that changed mention the property or class this
                # rule is about? The catalogue's `path` names it.
                needle = (meta.get("path") or "").split(",")[0].strip().split(" ")[0].lower()
                touched = any(needle and needle in short(t).lower()
                              for _sign, tr in changes for t in tr)
                category = "ours" if touched else "mismatched"

            buckets[category].append((rule_id, bad_name, good_name, changes))

    order = ORDER
    # Built from what was filled, not from the printing order: a bucket missing
    # from that tuple dropped its pairs out of the record while the header
    # above still counted them, and `--check` read the loss as a movement.
    assert set(buckets) == set(ORDER), sorted(set(buckets) ^ set(ORDER))
    verdicts = {"%s|%s" % (rule_id, bad_name): name
                for name, rows in buckets.items()
                for rule_id, bad_name, _why, _changes in rows}
    if args.write_record:
        return write_record(verdicts)
    if args.check:
        return compare_to_record(verdicts)

    print()
    print("=" * 78)
    print("Why this validator is silent, %d rule/fixture pairs" %
          sum(len(v) for v in buckets.values()))
    print("=" * 78)
    for name in order:
        print("  %-13s %d" % (name, len(buckets[name])))

    for name in order:
        rows = buckets[name]
        if not rows or (args.category and name != args.category) or args.quiet:
            continue
        print("\n" + "-" * 78)
        print(name.upper())
        print("-" * 78)
        for rule_id, bad_name, good_name, changes in rows:
            flag = "" if rule_id in implemented else "  [NOT IMPLEMENTED]"
            print("\n%s%s  path=%r" % (rule_id, flag, CATALOG[rule_id].get("path")))
            print("   %s" % (CATALOG[rule_id].get("en") or "")[:100])
            print("   %s  vs  %s" % (bad_name[:44], str(good_name)[:30]))
            for sign, tr in changes:
                print("     %s %s" % (sign, triple(tr)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
