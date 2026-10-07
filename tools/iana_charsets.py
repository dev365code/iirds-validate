#!/usr/bin/env python3
"""Generate the reader's offline IANA name/alias registry from its CSV.

--refresh fetches the source; --check regenerates from the committed CSV.
The runtime reader loads only the JSON and never uses the network.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.iana.org/assignments/character-sets/character-sets-1.csv"
DATA = ROOT / "src/iirds/data"
CSV = DATA / "iana-charsets.csv"
JSON = DATA / "iana-charsets.json"


def build(text, accessed):
    records = []
    names = {}
    for row in csv.DictReader(io.StringIO(text)):
        record = {"mib": int(row["MIBenum"]), "name": row["Name"],
                  "aliases": row["Aliases"].splitlines()}
        for name in [record["name"], *record["aliases"]]:
            old = names.setdefault(name.lower(), record["mib"])
            if old != record["mib"]:
                raise ValueError("IANA name belongs to two records: %s" % name)
        records.append(record)
    return {"source_url": URL, "access_date": accessed,
            "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "records": sorted(records, key=lambda r: r["mib"])}


def render(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--refresh", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.refresh:
        with urllib.request.urlopen(URL, timeout=30) as response:
            if response.status != 200 or response.headers.get_content_type() != "text/csv":
                raise ValueError("IANA response is not HTTP 200 text/csv")
            text = response.read().decode("utf-8-sig").replace("\r\n", "\n")
        fresh = build(text, date.today().isoformat())
        DATA.mkdir(exist_ok=True)
        CSV.write_text(text, "utf-8")
        JSON.write_text(render(fresh), "utf-8")
        print("IANA charsets: %d records written" % len(fresh["records"]))
        return 0
    committed = json.loads(JSON.read_text("utf-8"))
    fresh = build(CSV.read_text("utf-8"), committed["access_date"])
    if render(fresh) != JSON.read_text("utf-8"):
        print("IANA charsets differ from their source; run tools/iana_charsets.py --refresh",
              file=sys.stderr)
        return 1
    print("IANA charsets: %d records match the committed source" % len(fresh["records"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
