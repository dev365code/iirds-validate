#!/usr/bin/env python3
"""Which iiRDS terms existed in which version, and whether the rules agree.

Every `versions` array in the rule catalogue came from the reference tool, and
none had ever been checked against anything. A rule declaring itself applicable
to a version in which its own vocabulary did not exist is wrong in a way that
produces no finding, no traceback and no other sign: it runs, matches nothing,
and reports a clean package. What it corrupts is the claim -- `iirds rules`
says the rule applies where it cannot, and per-version coverage is overstated.

Checking it needs the vocabulary of each version, so the schema files of
every published edition are fetched once from the Consortium's own downloads
(1.3 from the bundled ontologies) and reduced to a list of term IRIs. Only the
list is committed -- into the package, where the L15 rule reads it. A set of
names is a fact about the vocabulary rather than a copy of the work, which
keeps this clear of the CC BY-ND terms the ontology files carry and keeps the
repository small.

    python tools/version_inventory.py --refresh   # needs the network, once
    python tools/version_inventory.py             # check, offline

Every edition from 1.0 on has an inventory; the file keeps an `_unavailable`
list so that an edition published faster than its schemas is recorded as
unchecked rather than conflated with checked and clean.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rdflib import Graph  # noqa: E402

from iirds_validate import terms as T  # noqa: E402
from iirds_validate.model import VERSIONS  # noqa: E402
from iirds_validate.ontology import load  # noqa: E402
from iirds_validate.registry import all_rules  # noqa: E402
from iirds_validate.rules.schema_tables import MUST_HAVE_IRI, NAMESPACES  # noqa: E402

INVENTORY = ROOT / "src" / "iirds_validate" / "data" / "version-terms.json"
NAMESPACE = "http://iirds.tekom.de/"

#: The Consortium's own downloads, one URL set per published version. This
#: began life against the GitHub tags of iirds-consortium/models, which carry
#: only 1.1 and 1.2 — so 1.0 and 1.0.1 sat in an "unavailable" list and two
#: questions about them stayed open. iirds.org publishes every edition's
#: schema files at stable fileadmin URLs, which also settled one of those
#: questions the day they were first fetched: the 1.0 *prose* names the Event
#: properties `eventCode`/`eventType`, but the 1.0 *ontology* already says
#: `has-event-code`/`has-event-type`, so M16.1/M16.2 check the right names for
#: every edition. 1.3 still comes from the bundle, so a refresh cannot
#: silently disagree with what ships.
_RDFS = "https://www.iirds.org/fileadmin/downloads/documents/rdfs/%s/%s"
_CORE3 = ("iirds-core.rdf", "iirds-machinery.rdf", "iirds-software.rdf")
SOURCES = {
    "1.0":   tuple(_RDFS % ("1.0", f) for f in _CORE3),
    "1.0.1": tuple(_RDFS % ("1.0.1", f) for f in _CORE3),
    "1.1":   tuple(_RDFS % ("1.1", f) for f in _CORE3),
    # The 1.2 page links its skos file from a 1.2.1 directory; that is
    # upstream's layout, not a typo here.
    "1.2":   tuple(_RDFS % ("1.2", f) for f in _CORE3) + (_RDFS % ("1.2.1", "iirds-skos.rdf"),),
}

#: Every published edition now has a source. Kept so the check still refuses
#: to conflate "not checked" with "checked and clean" if an edition is ever
#: added faster than its schema files appear.
UNAVAILABLE: tuple = ()


def terms_named_by(rule) -> list:
    """Every iiRDS IRI a rule mentions.

    Read out of the source rather than out of the catalogue's prose, which is
    the same choice made everywhere else here and for the same reason: prose
    and code have disagreed before.
    """
    named = []
    try:
        source = inspect.getsource(rule.fn)
    except (OSError, TypeError):
        source = ""
    for name in dict.fromkeys(re.findall(r"T\.([A-Za-z_0-9]+)", source)):
        value = getattr(T, name, None)
        if value is not None and str(value).startswith(NAMESPACE):
            named.append(str(value))

    # The generated rules build their class IRI from a table rather than from
    # a `T.` attribute, so the regex above cannot see it.
    for rule_id, prefix, class_name in MUST_HAVE_IRI:
        if rule_id == rule.id:
            named.append(str(NAMESPACES[prefix][class_name]))
    return named


def refresh() -> int:
    inventory = {}
    for version, urls in SOURCES.items():
        graph = Graph()
        for url in urls:
            with urllib.request.urlopen(url, timeout=60) as handle:
                graph.parse(data=handle.read(), format="xml")
        inventory[version] = sorted({str(s) for s in set(graph.subjects())
                                     if str(s).startswith(NAMESPACE)})

    inventory["1.3"] = sorted({str(s) for s in set(load().graph.subjects())
                               if str(s).startswith(NAMESPACE)})

    INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY.write_text(json.dumps({
        "_source": "iirds.org official schema downloads (%s); 1.3 from the bundled ontologies"
                   % ", ".join(sorted(SOURCES)),
        "_generated_by": "tools/version_inventory.py --refresh",
        "_note": ("Term IRIs only. The ontology files themselves are CC BY-ND and are not "
                  "redistributed here; a list of names is a fact about the vocabulary."),
        "_unavailable": list(UNAVAILABLE),
        "terms": inventory,
    }, indent=1) + "\n", "utf-8")

    for version, terms in sorted(inventory.items()):
        print("  %-6s %d terms" % (version, len(terms)))
    return check()


def check() -> int:
    if not INVENTORY.exists():
        print("no inventory; run --refresh", file=sys.stderr)
        return 2
    inventory = {k: set(v) for k, v in
                 json.loads(INVENTORY.read_text("utf-8"))["terms"].items()}

    problems = []
    for rule in all_rules():
        named = terms_named_by(rule)
        # `versions=()` means "every edition", which is how the registry reads
        # it at runtime -- and `or ()` made it mean "no edition" here, so 23
        # rules were exempt from the one check that asks whether a rule cites
        # a term its edition predates. Two of them, R3 and R11, were written
        # with that spelling while their neighbours R10 and R12 spell the same
        # meaning as five entries and are checked.
        for version in rule.versions or VERSIONS:
            if version not in inventory:
                continue
            absent = sorted(t.split("#")[-1].split("/")[-1]
                            for t in named if t not in inventory[version])
            if absent:
                problems.append((rule.id, version, absent))

    for rule_id, version, absent in problems:
        print("  %-9s claims %-5s where %s did not exist"
              % (rule_id, version, ", ".join(absent[:3])), file=sys.stderr)

    if problems:
        print("\n%d rule/version claim(s) name vocabulary that version did not have."
              % len(problems), file=sys.stderr)
        return 1

    checked = sorted(inventory)
    tail = "; %s have no schema source" % ", ".join(UNAVAILABLE) if UNAVAILABLE else ""
    print("no rule claims a version whose vocabulary lacks the terms it names "
          "(checked against %s%s)" % (", ".join(checked), tail))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-fetch every edition's schema files and rewrite the inventory")
    args = ap.parse_args()
    return refresh() if args.refresh else check()


if __name__ == "__main__":
    sys.exit(main())
