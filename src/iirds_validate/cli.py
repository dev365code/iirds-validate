"""Command line interface.

    iirds check pkg.iirds      conformance  (container + graph rules)
    iirds lint  pkg.iirds      interoperability  (can a consumer use it?)
    iirds check --fragment x.rdf   a bare metadata snippet, package rules suspended
    iirds all   pkg.iirds      both
    iirds rules --kind lint    what this tool knows how to check

Exit codes: 0 clean, 1 errors found, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from iirds import PackError, pack

from . import PROGRAM, __version__, runner
from .banner import banner
from .model import VERSIONS, Severity
from .package import discover
from .registry import CATALOG, all_rules, coverage
from .report import render

EXIT_OK, EXIT_FINDINGS, EXIT_ERROR = 0, 1, 2


def _add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("package", nargs="+",
                        help="packages: a .iirds file, an unpacked container directory, "
                             "or a directory to search")
    parser.add_argument("-f", "--format", choices=("text", "json"), default="text")
    parser.add_argument("--iirds-version", dest="version", default=None, choices=VERSIONS,
                        metavar="{%s}" % ",".join(VERSIONS),
                        help="validate against this version instead of the declared one")
    parser.add_argument("-v", "--verbose", action="store_true", help="include spec links")
    parser.add_argument("-q", "--quiet", action="store_true", help="exit code only")
    parser.add_argument("-W", "--warnings-as-errors", action="store_true",
                        help="fail the run on warnings too")
    parser.add_argument("--fragment", action="store_true",
                        help="treat each path as a bare metadata file (a spec example, a "
                             "snippet): wrap it in a throwaway container and suspend the "
                             "package-level rules a fragment cannot satisfy")


def _targets(paths):
    """Expand what the user pointed at into packages.

    A path can be a package, a directory that is one unpacked, or a directory
    with packages somewhere underneath. Pointing at a build output directory
    should do the obvious thing rather than require a shell glob.
    """
    found, missing, empty = [], [], []
    for path in paths:
        if not os.path.exists(path):
            missing.append(path)
            continue
        expanded = discover(path)
        if expanded:
            found.extend(expanded)
        else:
            empty.append(path)
    return found, missing, empty


def _run(args, kinds) -> int:
    # A path that is not there is an operator error, not a validation result:
    # exit 2. A file that opens but is not a valid container is a finding about
    # the package, so it goes through the rules and exits 1.
    if getattr(args, "fragment", False):
        # Fragments are files, named one by one; discovery is for containers.
        missing = [p for p in args.package if not os.path.isfile(p)]
        for path in missing:
            print("%s: no such file: %s" % (PROGRAM, path), file=sys.stderr)
        if missing:
            return EXIT_ERROR
        reports = [runner.run_fragment(path, kinds, version=args.version)
                   for path in args.package]
    else:
        targets, missing, empty = _targets(args.package)
        for path in missing:
            print("%s: no such file or directory: %s" % (PROGRAM, path), file=sys.stderr)
        for path in empty:
            print("%s: no iiRDS package found under %s" % (PROGRAM, path), file=sys.stderr)
        if missing or empty:
            return EXIT_ERROR
        reports = [runner.run(path, kinds, version=args.version) for path in targets]

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

    if len(reports) > 1 and args.format == "text" and not args.quiet:
        bad = sum(1 for r in reports if not r.ok)
        print("\n%d packages: %d passed, %d failed"
              % (len(reports), len(reports) - bad, bad))
    return EXIT_FINDINGS if failed else EXIT_OK


def _cmd_pack(args) -> int:
    """Write the archive, then validate the archive.

    Validating what was just written rather than the directory is the point:
    the six requirements about the ZIP that a directory cannot answer are now
    answerable, and answered against the file that will actually be delivered.
    """
    try:
        output = pack(args.directory, args.output, overwrite=args.overwrite)
    except PackError as exc:
        # The SDK's pack() speaks API ("pass overwrite=True"); this is a
        # terminal, so the one remedy it names is translated to its flag.
        message = str(exc).replace("pass overwrite=True", "pass --overwrite")
        print("%s: %s" % (PROGRAM, message), file=sys.stderr)
        return EXIT_ERROR

    if not args.quiet and args.format == "text":
        print("wrote %s (%.0f KB)\n" % (output, output.stat().st_size / 1024))

    args.package = [str(output)]
    return _run(args, runner.ALL_KINDS)


def _cmd_rules(args) -> int:
    rules = all_rules()
    if args.kind:
        rules = [r for r in rules if r.kind == args.kind]
    if args.ids:
        wanted = {rid.upper() for rid in args.ids}
        rules = [r for r in rules if r.id.upper() in wanted]
        missing = wanted - {r.id.upper() for r in rules}
        if missing:
            print("no such rule: %s" % ", ".join(sorted(missing)), file=sys.stderr)
            return EXIT_ERROR
        args.verbose = True          # asking for one rule means asking about it

    if args.format == "json":
        json.dump([{"id": r.id, "kind": r.kind, "priority": r.prio, "severity": str(r.severity),
                    "versions": list(r.versions), "variants": list(r.variants),
                    "title": r.title, "spec": r.spec,
                    "source": "catalogue" if r.id in CATALOG else "iirds-validate",
                    "covers": list(r.covers), "fix": r.fix} for r in rules],
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return EXIT_OK

    for r in rules:
        variants = ("/" + ",".join(r.variants)) if r.variants else ""
        print("%-9s %-9s %-9s %s" % (r.id, r.kind, r.prio + variants, r.title[:96]))
        if args.verbose:
            source = "catalogue" if r.id in CATALOG else "this project"
            print("          versions: %s   source: %s"
                  % (", ".join(r.versions) if r.versions else "all", source))
            if r.spec:
                print("          spec: %s" % r.spec)
            if r.covers:
                print("          covers: %s" % ", ".join(r.covers))
            if r.fix:
                print("          fix: %s" % r.fix)
            print()

    if args.ids:
        return EXIT_OK              # asked about specific rules; no summary tail

    print()
    cov = coverage()
    labels = {"container": "the ZIP and its layout",
              "schema": "the metadata graph",
              "system": "the run itself",
              "content": "iiRDS XHTML5 (Appendix B)",
              "lint": "will a consumer be able to use it"}
    for kind in ("container", "schema", "system", "content", "lint"):
        c = cov.get(kind)
        if not c or not (c["total"] or c["ours"]):
            continue
        catalogued = "%d/%d" % (c["implemented"], c["total"]) if c["total"] else "-"
        ours = ("  +%d of its own" % c["ours"]) if c["ours"] else ""
        print("%-10s %-8s %s%s" % (kind, catalogued, labels[kind], ours))
    print()
    print("%d of %d catalogued rules, plus %d of this project's own" % (
        sum(c["implemented"] for c in cov.values()), len(CATALOG),
        sum(c["ours"] for c in cov.values())))
    return EXIT_OK


def _cmd_serve(args) -> int:
    """The drop page. A refused bind address is an operator error, not a
    verdict, so it exits 2 the way a missing path does."""
    from . import serve as serve_module

    try:
        return serve_module.serve(args.host, args.port,
                                  open_browser=args.open_browser,
                                  verbose=args.verbose)
    except ValueError as exc:
        print("%s: %s" % (PROGRAM, exc), file=sys.stderr)
        return EXIT_ERROR


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Offline validator and interoperability linter for iiRDS packages.")
    parser.add_argument("--version", action="version", version="%s %s" % (PROGRAM, __version__))
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="conformance: container structure and metadata graph")
    _add_target(p_check)

    p_lint = sub.add_parser("lint", help="interoperability: can a consumer actually use this?")
    _add_target(p_lint)

    p_all = sub.add_parser("all", help="check and lint together")
    _add_target(p_all)

    p_pack = sub.add_parser(
        "pack", help="write a directory as a conformant .iirds and check it")
    p_pack.add_argument("directory")
    p_pack.add_argument("-o", "--output", default=None,
                        help="where to write it (default: alongside the directory)")
    p_pack.add_argument("--overwrite", action="store_true")
    p_pack.add_argument("-f", "--format", choices=("text", "json"), default="text")
    p_pack.add_argument("--iirds-version", dest="version", default=None, choices=VERSIONS)
    p_pack.add_argument("-v", "--verbose", action="store_true")
    p_pack.add_argument("-q", "--quiet", action="store_true")
    p_pack.add_argument("-W", "--warnings-as-errors", action="store_true")

    p_serve = sub.add_parser(
        "serve", help="a drop page on this machine, for people who do not read terminals")
    p_serve.add_argument("--host", default="127.0.0.1",
                         help="loopback only; anything else is refused")
    p_serve.add_argument("--port", type=int, default=0,
                         help="0 picks a free one (default)")
    p_serve.add_argument("--no-open", dest="open_browser", action="store_false",
                         help="do not open a browser")
    p_serve.add_argument("-v", "--verbose", action="store_true",
                         help="log requests; they carry the name of the file dropped")

    p_rules = sub.add_parser("rules", help="list the rules this tool implements")
    p_rules.add_argument("ids", nargs="*", metavar="RULE",
                         help="show only these rules, in full (e.g. M11 B8 R3)")
    p_rules.add_argument("--kind",
                         choices=("container", "schema", "system", "content", "lint"))
    p_rules.add_argument("-v", "--verbose", action="store_true",
                         help="also print versions, spec link, source and remedy")
    p_rules.add_argument("-f", "--format", choices=("text", "json"), default="text")

    # `iirds some/path` with no subcommand means `all`. Typing the verb is
    # friction, and "check it" is what anybody pointing at a package wants.
    argv = list(sys.argv[1:] if argv is None else argv)
    known = {"check", "lint", "all", "pack", "rules", "serve",
             "-h", "--help", "--version"}
    if argv and argv[0] not in known and not argv[0].startswith("-"):
        argv.insert(0, "all")

    args = parser.parse_args(argv)

    if args.command is None:
        # Bare `iirds`. argparse would exit 2 with a usage error, which is a
        # poor answer to someone who has just installed the thing.
        cov = coverage()
        print(banner("%d of %d catalogued rules, plus %d of its own. no network access."
                     % (sum(v["implemented"] for v in cov.values()), len(CATALOG),
                        sum(v["ours"] for v in cov.values()))))
        return EXIT_OK

    try:
        if args.command == "check":
            return _run(args, runner.CONFORMANCE_KINDS)
        if args.command == "lint":
            return _run(args, runner.LINT_KINDS)
        if args.command == "all":
            return _run(args, runner.ALL_KINDS)
        if args.command == "pack":
            return _cmd_pack(args)
        if args.command == "rules":
            return _cmd_rules(args)
        if args.command == "serve":
            return _cmd_serve(args)
    except KeyboardInterrupt:
        return EXIT_ERROR
    except OSError as exc:
        print("%s: %s" % (PROGRAM, exc), file=sys.stderr)
        return EXIT_ERROR
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
