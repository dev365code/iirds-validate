#!/usr/bin/env python3
"""Regenerate the rule catalogue from plusmeta's iiRDS Validation Tool (MIT).

The catalogue is *metadata only* — rule ids, priorities, the specification
sentence each rule enforces, and which versions/variants it applies to.
No plusmeta code is copied; the assertions in this project are independent
implementations that operate on an RDF graph rather than an XML DOM.

Usage:  python tools/extract_catalog.py [--offline DIR]

Requires network unless --offline points at a checkout of
https://github.com/plusmeta/iirds-validation-tool
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.request

#: Pinned so the catalogue is reproducible. NOTICE and THIRD_PARTY.md rest on
#: provenance, and regenerating against a moved `master` would silently produce
#: a different file. Pass --ref master to see what upstream has changed.
DEFAULT_REF = "0bcf19ddaec369289f128f3016c5a3c3f0c95f4d"
RAW = ("https://raw.githubusercontent.com/plusmeta/iirds-validation-tool/"
       "{ref}/src/config/validation/{name}.js")
FILES = ("container-rules", "schema-rules", "system-rules")
OUT = pathlib.Path(__file__).resolve().parents[1] / "src/iirds_validate/data/rule-catalog.json"

# plusmeta's IdConst values -> our variant vocabulary
VARIANT_MAP = {
    "IIRDS_VARIANT_UNRESTRICTED": "unrestricted",
    "IIRDS_VARIANT_A": "A",
    "IIRDS_VARIANT_H": "H",
}


def fetch(name: str, offline, ref: str) -> str:
    if offline:
        return (pathlib.Path(offline) / "src/config/validation" / f"{name}.js").read_text("utf-8")
    with urllib.request.urlopen(RAW.format(ref=ref, name=name), timeout=30) as fh:
        return fh.read().decode("utf-8")


def split_objects(src: str) -> list:
    """Split a JS array literal into top-level object literals by brace depth."""
    out, depth, start, in_str, quote, esc = [], 0, None, False, "", False
    for i, ch in enumerate(src):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in "\"'`":
            in_str, quote = True, ch
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                out.append(src[start:i + 1])
                start = None
    return out


def field(block: str, name: str):
    m = re.search(rf'\b{name}:\s*"((?:[^"\\]|\\.)*)"', block)
    return json.loads(f'"{m.group(1)}"') if m else None


def array(block: str, name: str):
    m = re.search(rf"\b{name}:\s*\[([^\]]*)\]", block)
    if not m:
        return None
    return [t.strip() for t in re.findall(r'"([^"]*)"|(\w+\.\w+)', m.group(1)) for t in (t,) if False] or \
           [x.strip().strip('"') for x in m.group(1).split(",") if x.strip()]


def test_files(block: str):
    """The rule's own pass/fail fixtures.

    Authoritative, unlike the file names: several fixtures are named after a
    different rule than the one whose list they appear in.
    """
    m = re.search(r"testFiles:\s*\{(.*?)\n\s*\}", block, re.S)
    if not m:
        return {}
    out = {}
    for key in ("true", "false"):
        km = re.search(r'"%s":\s*\[(.*?)\]' % key, m.group(1), re.S)
        if km:
            out[key] = [f.rsplit("/", 1)[-1] for f in re.findall(r'"([^"]+)"', km.group(1))]
    return out


def localized(block: str, lang: str):
    m = re.search(rf'"{lang}":\s*"((?:[^"\\]|\\.)*)"', block)
    return json.loads(f'"{m.group(1)}"') if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", help="path to a local clone of the plusmeta repo")
    ap.add_argument("--ref", default=DEFAULT_REF,
                    help="git ref to extract from (default: the pinned commit)")
    ap.add_argument("--check", action="store_true",
                    help="do not write; exit 1 if the result differs from the committed file")
    args = ap.parse_args()

    rules, seen = [], set()
    for name in FILES:
        kind = name.split("-")[0]
        src = fetch(name, args.offline, args.ref)
        # system-rules.js exports an object map, the others export arrays;
        # peel the outer braces so the values are seen as top-level objects.
        body = src.split("export default", 1)[-1].lstrip()
        if body.startswith("{"):
            src = body[1:body.rfind("}")]
        for block in split_objects(src):
            rid = field(block, "id")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            versions = array(block, "version")
            variants = array(block, "iirdsVariant")
            rules.append({
                "id": rid,
                "kind": kind,
                "prio": field(block, "prio"),
                "category": field(block, "category"),
                "versions": versions or ["1.0", "1.0.1", "1.1", "1.2", "1.3"],
                "variants": [VARIANT_MAP.get(v.split(".")[-1], v) for v in variants] if variants else [],
                "spec": field(block, "spec"),
                "path": field(block, "path"),
                "testFiles": test_files(block),
                "en": localized(block, "en"),
                "de": localized(block, "de"),
            })

    for r in rules:
        r["versions"] = [v[1:] if v.startswith("V") else v for v in r["versions"]]

    payload = json.dumps({
        "_source": "https://github.com/plusmeta/iirds-validation-tool",
        "_commit": args.ref,
        "_retrieved": "2026-08-17",
        "_licence": "MIT, Copyright 2020 plusmeta GmbH — metadata only, see THIRD_PARTY.md",
        "_generated_by": "tools/extract_catalog.py",
        "rules": rules,
    }, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        current = OUT.read_text("utf-8") if OUT.exists() else ""
        if current == payload:
            print("catalogue is up to date with %s" % args.ref[:12])
            return 0
        print("catalogue differs from %s — upstream rules have changed" % args.ref[:12],
              file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(payload, "utf-8")

    from collections import Counter
    print(f"{len(rules)} rules -> {OUT}")
    print("  kind:", dict(Counter(r["kind"] for r in rules)))
    print("  prio:", dict(Counter(r["prio"] for r in rules)))
    print("  1.3 :", sum("1.3" in r["versions"] for r in rules))
    print("  H   :", sum("H" in r["variants"] for r in rules))
    return 0


if __name__ == "__main__":
    sys.exit(main())
