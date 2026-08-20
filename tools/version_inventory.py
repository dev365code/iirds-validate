#!/usr/bin/env python3
"""Which iiRDS terms existed in which version, and whether the rules agree.

Every `versions` array in the rule catalogue came from the reference tool, and
none had ever been checked against anything. A rule declaring itself applicable
to a version in which its own vocabulary did not exist is wrong in a way that
produces no finding, no traceback and no other sign: it runs, matches nothing,
and reports a clean package. What it corrupts is the claim -- `iirdsv rules`
says the rule applies where it cannot, and per-version coverage is overstated.

Checking it needs the vocabulary of each version, so the ontologies are fetched
once from the consortium's tagged releases and reduced to a list of term IRIs.
Only the list is committed. A set of names is a fact about the vocabulary
rather than a copy of the work, which keeps this clear of the CC BY-ND terms
the ontology files carry and keeps the repository small.

    python tools/version_inventory.py --refresh   # needs the network, once
    python tools/version_inventory.py             # check, offline

iiRDS 1.0 and 1.0.1 are not tagged in that repository, so no inventory exists
for them and no rule is checked against them. That gap is recorded in the file
rather than papered over.
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
from iirds_validate.ontology import load  # noqa: E402
from iirds_validate.registry import all_rules  # noqa: E402
from iirds_validate.rules.schema_tables import MUST_HAVE_IRI, NAMESPACES  # noqa: E402

INVENTORY = ROOT / "docs" / "version-terms.json"
NAMESPACE = "http://iirds.tekom.de/"
REPO = "iirds-consortium/models"
RAW = "https://raw.githubusercontent.com/%s/%%s/%%s" % REPO

#: The tagged releases, and the ontology files each carries. 1.3 comes from the
#: bundle instead, so a refresh cannot silently disagree with what ships.
TAGGED = {
    "1.1": ("iirds-core.rdf", "iirds-machinery.rdf", "iirds-software.rdf"),
    "1.2": ("iirds-core.rdf", "iirds-machinery.rdf", "iirds-software.rdf", "iirds-skos.rdf"),
}

#: Published versions with no tagged ontology, so nothing can be checked
#: against them. Named rather than omitted, because "not checked" and "checked
#: and clean" must not look the same.
UNAVAILABLE = ("1.0", "1.0.1")


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
    for tag, files in TAGGED.items():
        graph = Graph()
        for name in files:
            url = RAW % (urllib.parse.quote(tag), urllib.parse.quote(name))
            with urllib.request.urlopen(url, timeout=60) as handle:
                graph.parse(data=handle.read(), format="xml")
        inventory[tag] = sorted({str(s) for s in set(graph.subjects())
                                 if str(s).startswith(NAMESPACE)})

    inventory["1.3"] = sorted({str(s) for s in set(load().graph.subjects())
                               if str(s).startswith(NAMESPACE)})

    INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY.write_text(json.dumps({
        "_source": "https://github.com/%s, tags %s; 1.3 from the bundled ontologies"
                   % (REPO, ", ".join(sorted(TAGGED))),
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
        for version in rule.versions or ():
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
    print("no rule claims a version whose vocabulary lacks the terms it names "
          "(checked against %s; %s have no tagged ontology)"
          % (", ".join(checked), ", ".join(UNAVAILABLE)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-fetch the tagged ontologies")
    args = ap.parse_args()
    return refresh() if args.refresh else check()


if __name__ == "__main__":
    sys.exit(main())
