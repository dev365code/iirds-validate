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

from rdflib import Graph, URIRef  # noqa: E402

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


def _source_the_rule_reaches(fn, seen=None) -> str:
    """The rule's own source, plus the module-local helpers it calls.

    One level was not enough and got less adequate as the code improved. Most
    rules here are three lines calling a builder — that is where the
    duplication went — so the terms a rule actually looks for live one call
    away, and reading only `rule.fn` measured the shape of the code instead.
    Parameterising the section 8.3.2 family took `iirds:Manufacturer` out of
    M15.7b's inventory and left `iirds:Document`; seventeen rules were hiding
    a term this way, `iirds:has-identity-type` among them, which is a 1.1 term.

    Any callable of this package, not only the underscore-prefixed ones. The
    leading underscore was the convention the rule modules follow among
    themselves and it is not the whole of what they call: `package_nodes` and
    `container_packages` are public, six rules reach `iirds:Package` and
    `iirds:is-part-of-package` only through them, and the check could not see
    a term moved into either. Membership is decided by `__module__`, which
    keeps rdflib and the standard library out without a naming rule to
    remember.
    """
    seen = set() if seen is None else seen
    # `inspect.getsource` raises on a partial, and returning "" for it made
    # both this and `_reads_the_graph` blind -- the rule was then neither
    # answered nor refused. Guarding the crash without unwrapping turned a
    # loud failure into a silent pass, which is worse than the crash.
    fn = getattr(fn, "func", fn)
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return ""
    module = sys.modules.get(getattr(fn, "__module__", None) or "")
    if module is None:
        return source
    out = [source]

    # `ctx.<method>` too, not only module-level helpers. L1 and L8 name
    # `iirds:title` through `Context.label_of` and read the whole defined-term
    # set through it, and this walker resolved callables with
    # `getattr(module, name)` -- a Context method is on neither the rule's
    # module nor any module. Both read as naming no term at all, which is a
    # third kind of silence the classification below had no word for.
    from iirds_validate.context import Context
    for name in dict.fromkeys(re.findall(r"\bctx\.([A-Za-z_][A-Za-z_0-9]*)\s*\(", source)):
        method = getattr(Context, name, None)
        if callable(method) and name not in seen:
            seen.add(name)
            out.append(_source_the_rule_reaches(method, seen))

    for name in dict.fromkeys(re.findall(r"\b([A-Za-z_][A-Za-z_0-9]*)\s*\(", source)):
        if name in seen:
            continue
        seen.add(name)
        helper = getattr(module, name, None)
        if helper is None:
            # A helper reached through its module -- `schema._points_at(...)`
            # rather than an imported name -- is not an attribute of the
            # caller's module, so `getattr` above finds nothing and the
            # helper's body, and every term in it, drops out of the reached
            # source in silence. That is one call style away from blinding this
            # check, and `schema.py` is about to be split by specification
            # section. Looked up across the rules package instead of left to a
            # convention somebody has to remember.
            for other in list(sys.modules.values()):
                if getattr(other, "__name__", "").startswith("iirds_validate.rules"):
                    candidate = getattr(other, name, None)
                    if candidate is not None:
                        helper = candidate
                        break
        if callable(helper) and getattr(
                helper, "__module__", "").startswith("iirds_validate"):
            out.append(_source_the_rule_reaches(helper, seen))
    return "\n".join(out)


#: Rules that read the RDF and name no iiRDS term, with one line of what each
#: looks at instead. Enumerated so a new one has to be looked at by somebody,
#: and refused when it names a rule that no longer exists.
#:
#: **Which kind** of silence each is, this does not say. Two attempts at that
#: got it wrong: a table of prose reasons had five of fourteen false, and
#: deriving it from the source split on how the access is spelled rather than
#: on what is read -- L13 and L14 both scan the ontology's whole defined-term
#: set and landed on opposite sides. What the enumeration is for is that
#: somebody looks; a label this file cannot make true is worse than no label.
#:
#: Not filtered by kind. C16.2 is `kind="container"` and reads the graph, and
#: a filter on schema/lint left it outside the gate entirely.
NAMES_NO_TERM = {
    "C16.2": "asks whether any metadata file mentions an iiRDS term at all",
    "L5": "asks whether a class is in an iiRDS namespace, not which class",
    "L9": "compares the two metadata files as graphs",
    "L13": "reads every name the ontology defines, to spot one it does not",
    "L14": "measures how far a namespace is from an iiRDS one, and reads the "
           "defined-term set to know it is not one",
    "L15": "reads the per-edition inventory itself -- it is the rule that "
           "reports a name the declared edition does not have",
    "L16": "reads the ontology's own relation/attribute split; eight of the "
           "forty-six relations are absent from 1.0, which is why this rule "
           "filters by the declared edition itself",
    "M5": "walks every iiRDS subject to ask whether rdf:about is absolute",
    "M30": "asks whether a subject is in an iiRDS namespace, not which term",
    "R18": "reads the vocabulary classes, from the ontology's own instances",
}


def _reads_the_graph(rule) -> bool:
    """Does the rule look at the RDF at all? Container and system rules whose
    subject is ZIP bytes or the run itself are answered truthfully by naming
    nothing; C16.2 is `kind="container"` and reads the graph, so the question
    is what the rule touches and not what its id begins with."""
    source = _source_the_rule_reaches(rule.fn)
    # `self.` as well as `ctx.`: the reached source now holds the bodies of the
    # Context methods a rule calls, and inside those the access is spelled
    # `self.graph`. M5 reads the whole graph through `ctx.iirds_subjects()` and
    # read as not touching it at all -- and the comment beside its absence
    # from the list called that a decision, which it was not.
    return bool(re.search(r"\b(ctx|self)\.(graph|ontology|per_source|instances_of"
                          r"|values|has|iirds_subjects)\b", source))




def terms_named_by(rule) -> list:
    """Every iiRDS IRI a rule mentions, directly or through its helpers.

    Read out of the source rather than out of the catalogue's prose, which is
    the same choice made everywhere else here and for the same reason: prose
    and code have disagreed before.

    The limit of reading it this way: a rule whose population comes from the
    ontology at run time names no term and so cannot be answered for. `check`
    counts those out loud rather than letting them pass as clean.
    """
    named = []
    source = _source_the_rule_reaches(rule.fn)
    for name in dict.fromkeys(re.findall(r"T\.([A-Za-z_0-9]+)", source)):
        value = getattr(T, name, None)
        if value is not None and str(value).startswith(NAMESPACE):
            named.append(str(value))

    # The generated rules build their class IRI from a table rather than from
    # a `T.` attribute, so the regex above cannot see it.
    for rule_id, prefix, class_name, _requirement in MUST_HAVE_IRI:
        if rule_id == rule.id:
            named.append(str(NAMESPACES[prefix][class_name]))

    # And a rule built by a factory names its terms at the call site, so they
    # never appear in the function this reads. For the factories here they are
    # in the function object -- default arguments and closure cells -- so this
    # is a limit of where the tool looked. Nine rules were passing vacuously
    # for that reason and the one above: R19 to R23 and R1 and R2 bind their
    # terms at a call site, and L1, L8 and M2.1 reach theirs through a
    # `Context` method. "Four" was this comment's first guess, made from the
    # family being repaired rather than from a measurement.
    #
    # Two limits, stated because neither is going to be argued away.
    # **A term in a module-level table the body indexes is invisible** -- it is
    # in neither the defaults nor the closure, and this codebase does reach for
    # that shape. **And binding is not using**: a term bound as an exemption
    # sentinel, or used only inside a message, is counted as named, so a rule
    # correct for its edition can be failed over a term it never reads. That
    # direction is loud -- somebody sees a failing gate and looks -- which is
    # the trade this whole check exists to make.
    named.extend(_iirds_terms_bound_into(rule.fn))
    return list(dict.fromkeys(named))


def _iirds_terms_bound_into(fn) -> list:
    """iiRDS IRIs sitting in a function's defaults or closure, at any depth."""
    def walk(value, depth=0):
        if isinstance(value, URIRef):
            text = str(value)
            return [text] if text.startswith(NAMESPACE) else []
        # Sequences, not dicts. Walking dict values was added to close the
        # "terms live in a table" hole and does not: a table a rule indexes is
        # a module global, which is in neither the defaults nor the closure.
        # What it did do is charge a rule that closes over a shared table with
        # every term in it, including ones its declared edition may lack. It
        # bought nothing and cost a way to fail a correct rule.
        if depth < 6 and isinstance(value, (tuple, list, set, frozenset)):
            return [t for item in value for t in walk(item, depth + 1)]
        return []

    found = []
    for value in (getattr(fn, "args", None) or ()):
        found += walk(value)
    for value in (getattr(fn, "keywords", None) or {}).values():
        found += walk(value)
    # A rule is whatever callable was registered. `functools.partial` and a
    # callable class instance are both legal and neither has `__defaults__`;
    # reading it unguarded took the whole check down with an AttributeError,
    # which is a strange way for a gate to report that it cannot see something.
    for value in (getattr(fn, "__defaults__", None) or ()):
        found += walk(value)
    for value in (getattr(fn, "__kwdefaults__", None) or {}).values():
        found += walk(value)
    for cell in (getattr(fn, "__closure__", None) or ()):
        try:
            found += walk(cell.cell_contents)
        except ValueError:                      # an empty cell
            continue
    wrapped = getattr(fn, "__wrapped__", None)
    if wrapped is not None:
        found += _iirds_terms_bound_into(wrapped)
    return found


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

    problems, unanswerable, unclassified = [], [], []
    for rule in all_rules():
        named = terms_named_by(rule)
        # A rule that names nothing passes by naming nothing. For a container
        # or system rule that is the truth -- its subject is ZIP bytes or the
        # run itself. For a rule that reads the graph it means the population
        # is derived from the ontology at run time, and this check cannot
        # answer for it: L16 declared all five editions while eight of the
        # relations it watches are absent from 1.0, and this printed a clean
        # line. Reported rather than refused, because refusing wants a reason
        # written per rule and there are sixteen of them.
        if not named and _reads_the_graph(rule):
            unanswerable.append(rule.id)
            if rule.id not in NAMES_NO_TERM:
                unclassified.append(rule.id)
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

    stale = sorted(set(NAMES_NO_TERM) - {rule.id for rule in all_rules()})
    if stale:
        print("\nNAMES_NO_TERM names %d rule(s) that no longer exist: %s"
              % (len(stale), ", ".join(stale)), file=sys.stderr)
        return 1

    if unclassified:
        print("\n%d graph rule(s) name no iiRDS term and are not declared in "
              "NAMES_NO_TERM: %s\n  This check passes a rule that names nothing "
              "by saying nothing about it. Add a line saying what it looks at "
              "instead; which kind of silence it is comes from the code."
              % (len(unclassified), ", ".join(sorted(unclassified))), file=sys.stderr)
        return 1

    if problems:
        print("\n%d rule/version claim(s) name vocabulary that version did not have."
              % len(problems), file=sys.stderr)
        return 1

    checked = sorted(inventory)
    tail = "; %s have no schema source" % ", ".join(UNAVAILABLE) if UNAVAILABLE else ""
    print("no rule claims a version whose vocabulary lacks the terms it names "
          "(checked against %s%s)" % (", ".join(checked), tail))
    if unanswerable:
        print("  %d rule(s) read the graph and name no iiRDS term, so this check "
              "says nothing about them: %s"
              % (len(unanswerable), ", ".join(sorted(unanswerable))))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-fetch every edition's schema files and rewrite the inventory")
    args = ap.parse_args()
    return refresh() if args.refresh else check()


if __name__ == "__main__":
    sys.exit(main())
