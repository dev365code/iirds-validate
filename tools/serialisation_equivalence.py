#!/usr/bin/env python3
"""Prove the central claim against a real package.

Takes an .iirds container, re-serialises its metadata graph into the other legal
forms, repacks each one, validates all of them and compares the findings. Same
graph in, same result out — or this tool is not doing what it says.

    python tools/serialisation_equivalence.py path/to/package.iirds

Exit code 0 if every serialisation agrees, 1 otherwise.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rdflib import Graph                                            # noqa: E402

from iirds_validate import runner                                   # noqa: E402
from iirds_validate.model import METADATA_JSONLD, METADATA_RDF      # noqa: E402
from iirds_validate.package import Package                          # noqa: E402

#: "xml" leans on rdf:Description + rdf:type; "pretty-xml" prefers typed
#: elements. Both are conformant RDF/XML and describe the same graph.
FORMS = (("original", None, METADATA_RDF),
         ("rdf:Description style", "xml", METADATA_RDF),
         ("typed-element style", "pretty-xml", METADATA_RDF),
         ("JSON-LD", "json-ld", METADATA_JSONLD))


def rewrite(source: Path, out: Path, fmt, target: str) -> Path:
    with Package(source) as pkg:
        graph = Graph()
        graph.parse(data=pkg.read(METADATA_RDF), format="xml")
        payload = graph.serialize(format=fmt)
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        with zipfile.ZipFile(source) as src, zipfile.ZipFile(out, "w") as dst:
            for info in src.infolist():
                if info.filename in (METADATA_RDF, METADATA_JSONLD):
                    continue
                data = src.read(info.filename)
                clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                clone.compress_type = info.compress_type
                dst.writestr(clone, data)
            dst.writestr(target, payload)
    return out


def fingerprint(report):
    return sorted((f.rule.id, f.violation.message, f.violation.subject or "")
                  for f in report.findings)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("-k", "--kinds", default="all", choices=("all", "check", "lint"))
    args = ap.parse_args()

    kinds = {"all": runner.ALL_KINDS, "check": runner.CONFORMANCE_KINDS,
             "lint": runner.LINT_KINDS}[args.kinds]
    source = Path(args.package)
    tmp = Path(tempfile.mkdtemp(prefix="iirds-equiv-"))
    baseline = None
    failures = 0

    try:
        for label, fmt, target in FORMS:
            if fmt is None:
                candidate = tmp / source.name
                shutil.copy(source, candidate)
            else:
                candidate = rewrite(source, tmp / ("%s.iirds" % fmt.replace(":", "-")), fmt, target)

            report = runner.run(candidate, kinds)
            marks = fingerprint(report)
            if baseline is None:
                baseline = marks
                verdict = "baseline"
            elif marks == baseline:
                verdict = "identical"
            else:
                verdict = "DIFFERENT"
                failures += 1

            print("  %-22s %2d finding(s), %2d rules run   %s"
                  % (label, len(marks), report.checked, verdict))

            if verdict == "DIFFERENT":
                only_here = [m for m in marks if m not in baseline]
                only_there = [m for m in baseline if m not in marks]
                for m in only_here:
                    print("      + %s %s %s" % m)
                for m in only_there:
                    print("      - %s %s %s" % m)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("  every serialisation agrees" if not failures
          else "  %d serialisation(s) disagreed" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
