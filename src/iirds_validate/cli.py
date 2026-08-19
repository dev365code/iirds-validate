"""Command line interface.

    iirdsv check pkg.iirds      conformance  (container + graph rules)
    iirdsv lint  pkg.iirds      interoperability  (can a consumer use it?)
    iirdsv all   pkg.iirds      both
    iirdsv rules --kind lint    what this tool knows how to check

Exit codes: 0 clean, 1 errors found, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, runner
from .banner import banner
from .model import VERSIONS, Severity
from .registry import CATALOG, all_rules, coverage
from .report import render

EXIT_OK, EXIT_FINDINGS, EXIT_ERROR = 0, 1, 2


def _add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("package", nargs="+", help="one or more .iirds containers")
    parser.add_argument("-f", "--format", choices=("text", "json"), default="text")
    parser.add_argument("--iirds-version", dest="version", default=None, choices=VERSIONS,
                        metavar="{%s}" % ",".join(VERSIONS),
                        help="validate against this version instead of the declared one")
    parser.add_argument("-v", "--verbose", action="store_true", help="include spec links")
    parser.add_argument("-q", "--quiet", action="store_true", help="exit code only")
    parser.add_argument("-W", "--warnings-as-errors", action="store_true",
                        help="fail the run on warnings too")


def _run(args, kinds) -> int:
    # A file that is not there is an operator error, not a validation result:
    # exit 2. A file that opens but is not a valid container is a finding about
    # the package, so it goes through the rules and exits 1.
    missing = [p for p in args.package if not os.path.exists(p)]
    if missing:
        for path in missing:
            print("iirds-validate: no such file: %s" % path, file=sys.stderr)
        return EXIT_ERROR

    reports = [runner.run(path, kinds, version=args.version) for path in args.package]

    if args.format == "json":
        payload = [r.as_dict() for r in reports]
        json.dump(payload[0] if len(payload) == 1 else payload,
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    elif not args.quiet:
        for i, report in enumerate(reports):
            if i:
                print()
            render(report, "text", verbose=args.verbose)

    failed = any(not r.ok for r in reports)
    if args.warnings_as_errors:
        failed = failed or any(r.count(Severity.WARNING) for r in reports)
    return EXIT_FINDINGS if failed else EXIT_OK


def _cmd_rules(args) -> int:
    rules = all_rules()
    if args.kind:
        rules = [r for r in rules if r.kind == args.kind]

    if args.format == "json":
        json.dump([{"id": r.id, "kind": r.kind, "priority": r.prio, "severity": str(r.severity),
                    "versions": list(r.versions), "variants": list(r.variants),
                    "title": r.title, "spec": r.spec} for r in rules],
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return EXIT_OK

    for r in rules:
        variants = ("/" + ",".join(r.variants)) if r.variants else ""
        print("%-9s %-9s %-9s %s" % (r.id, r.kind, r.prio + variants, r.title[:96]))

    print()
    cov = coverage()
    for kind in ("container", "schema", "system", "lint"):
        if kind not in cov:
            continue
        c = cov[kind]
        if kind == "lint":
            print("lint       %d rules (this project only — not in the plusmeta catalogue)" % c["total"])
        else:
            print("%-10s %d/%d implemented" % (kind, c["implemented"], c["total"]))
    total_impl = sum(c["implemented"] for k, c in cov.items() if k != "lint")
    print("%-10s %d/%d of the catalogue" % ("total", total_impl, len(CATALOG)))
    return EXIT_OK


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="iirds-validate",
        description="Offline validator and interoperability linter for iiRDS packages.")
    parser.add_argument("--version", action="version", version="iirds-validate %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="conformance: container structure and metadata graph")
    _add_target(p_check)

    p_lint = sub.add_parser("lint", help="interoperability: can a consumer actually use this?")
    _add_target(p_lint)

    p_all = sub.add_parser("all", help="check and lint together")
    _add_target(p_all)

    p_rules = sub.add_parser("rules", help="list the rules this tool implements")
    p_rules.add_argument("--kind", choices=("container", "schema", "lint", "system"))
    p_rules.add_argument("-f", "--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)

    if args.command is None:
        # Bare `iirdsv`. argparse would exit 2 with a usage error, which is a
        # poor answer to someone who has just installed the thing.
        cov = coverage()
        catalogued = sum(v["implemented"] for k, v in cov.items() if k != "lint")
        print(banner("%d of %d catalogued rules, plus %d of its own. no network access."
                     % (catalogued, len(CATALOG), cov["lint"]["total"])))
        return EXIT_OK

    try:
        if args.command == "check":
            return _run(args, runner.CONFORMANCE_KINDS)
        if args.command == "lint":
            return _run(args, runner.LINT_KINDS)
        if args.command == "all":
            return _run(args, runner.ALL_KINDS)
        if args.command == "rules":
            return _cmd_rules(args)
    except KeyboardInterrupt:
        return EXIT_ERROR
    except OSError as exc:
        print("iirds-validate: %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
