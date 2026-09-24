#!/usr/bin/env python3
"""`docs/what-it-catches.md`, written from what the commands actually print.

    python tools/gen_what_it_catches.py            # write the page
    python tools/gen_what_it_catches.py --check    # it still says what they print

A page of examples is the most quotable thing a project publishes and the
easiest to leave behind: the output was real on the day it was pasted, and
nothing reads it afterwards. This repository has had to learn that on its own
release notes, so this page is not written by hand. Every
block below `$` is a command run from the repository root, and everything under
it is that command's own output, captured on this run.

Three rules taken from `tools/gen_stable_section.py`, which learned them the
hard way, plus one this page needs of its own:

* **Every command answers offline, from a checkout with nothing built.** The
  containers are built here, with the generator `make` and CI use, because
  `fixtures/` is not committed.
* **A command whose verdict is not the one the case is about is a failure, not
  a value.** A case that stops firing must break the build rather than quietly
  publish a `PASS` under a heading that promises an error. `_verdict` is where
  that is enforced: each case states the exit code and the rule id it is about,
  and both are checked before the output reaches the page.
* **Paths are relative to the repository root**, so the text a reader sees is
  the text this run produced rather than somebody's home directory.
* **No claim about any other tool.** A sentence about somebody else's validator
  could not be checked from here.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from rdflib import Graph
from rdflib.compare import isomorphic

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "what-it-catches.md"
BUILT = Path("fixtures") / "what-it-catches"


class Failed(Exception):
    """A command this page quotes did not behave the way the case says."""


def _run(args, env_extra=None):
    env = dict(os.environ, PYTHONPATH="src", PYTHONDONTWRITEBYTECODE="1",
               NO_COLOR="1", COLUMNS="88")
    env.update(env_extra or {})
    done = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True,
                          text=True, env=env)
    return done.returncode, (done.stdout + done.stderr).rstrip()


def _must(args):
    code, said = _run(args)
    if code != 0:
        raise Failed("%s exited %d:\n%s" % (" ".join(args), code, said))
    return said


def _verdict(package: str, *, exit_code: int, names: str):
    """The output of `iirds check`, once it is the verdict the case is about.

    Both halves matter. A case that promises an `ERROR C5` and prints a `PASS`
    is a page that lies about the tool; a case that still fails but under a
    different rule is a page that lies about which requirement it is showing.
    """
    code, said = _run(["-m", "iirds_validate", "check", package])
    if code != exit_code:
        raise Failed("%s exited %d, the case says %d:\n%s"
                     % (package, code, exit_code, said))
    if names and names not in said:
        raise Failed("%s was to show %s and did not:\n%s" % (package, names, said))
    return said


def _build(name: str, broken: str) -> str:
    """One container, built where the page can name it by a relative path."""
    (ROOT / BUILT).mkdir(parents=True, exist_ok=True)
    where = BUILT / ("%s.iirds" % name)
    _must(["tools/make_fixture_package.py", where.as_posix()]
          + ([] if broken == "none" else ["--broken", broken]))
    return where.as_posix()


def _not_a_container() -> str:
    (ROOT / BUILT).mkdir(parents=True, exist_ok=True)
    where = BUILT / "not-a-container.iirds"
    (ROOT / where).write_bytes(b"not a zip at all")
    return where.as_posix()


#: Each case: how the container is made, what the finding is, and the two
#: sentences around it. `cites` is the rule whose `spec` field carries the
#: obligation, or None where the rule is this project's own judgement -- the
#: distinction the page is largely for.
CASES = [
    ("not-a-container", "The container is not a container", None, "S13", 1,
     "The standard describes a container, and a file that will not open is not "
     "one yet. The last line is the point: the run says how many rules it never "
     "put, rather than leaving a reader to assume they passed."),
    ("mimetype", "`mimetype` with a trailing newline", "mimetype", "C5", 1,
     "The finding prints the bytes it read, because an editor shows nothing "
     "wrong with a file that ends in a newline."),
    ("no-metadata-rdf", "No `metadata.rdf`", "jsonld-only", "C8", 1,
     "A JSON-LD file alongside `metadata.rdf` is allowed; instead of it is not."),
    ("no-format", "A rendition with no format", "missing-format", "M11", 1,
     "The finding names the subject and how many were found. A rendition with an "
     "IRI of its own is named by it; one written as a blank node, as here, is named "
     "by the unit that has it, so two of those under one unit read alike."),
    ("missing-content", "Metadata that points at a file the package does not carry",
     "missing-content", "L2", 1,
     "The graph is well-formed and no rule but `L2` has anything to say about it. "
     "A reader of the package finds no document where the metadata points. None "
     "of the rules taken from the upstream catalogue fires on it."),
]


#: What the page says of a rule that neither links to the standard nor claims
#: an obligation of it. One string, so the test that checks the claim reads
#: the label the page is written with rather than its own copy of it.
OWN_RULE = "**This tool's own rule** (`%s`), no specification reference."


def spec_of(rule_id: str):
    """What the rule says, the standard's own words, and the link, or None.

    The three are kept apart on purpose. A rule's `title` is this project's
    statement of the obligation and is not always the specification's sentence
    -- `C8`'s stops before "containing all metadata in RDF 1.1 XML syntax",
    `M11`'s drops "also" -- so quoting a title under "the standard says so"
    would attribute near-quotes to the standard. The quotable text is the
    fragment the link itself highlights, because that string and the link are
    the same string: if the quotation were wrong the link would miss.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from iirds_validate.registry import all_rules

    rule = {r.id: r for r in all_rules()}.get(rule_id)
    if rule is None:
        raise Failed("%s is not a rule in this build" % rule_id)
    return rule.title, _quoted(rule.spec), rule.spec, tuple(rule.covers)


def _quoted(spec):
    """The standard's words, out of the link's own text fragment.

    `#:~:text=A` highlights A; `#:~:text=A,B` highlights from A to B, which is
    rendered with an ellipsis rather than the comma that separates them, since
    the comma is syntax and not something the specification wrote.
    """
    import urllib.parse

    if not spec or ":~:text=" not in spec:
        return None
    fragment = urllib.parse.unquote(spec.split(":~:text=")[-1])
    parts = [part.strip() for part in fragment.split(",") if part.strip()]
    if len(parts) == 2:
        return "%s ... %s" % (parts[0], parts[1])
    return fragment.strip()


def _wrapped(prose: str):
    """Prose at the width the other documents here are written to.

    Never breaking a word. `textwrap` splits at hyphens by default, and the
    first requirement id placed in prose here -- `dfn-iirds-package#1` -- came
    out as `dfn-iirds-` on one line and `package#1` on the next, which renders
    as a different id with a space in it. A line longer than 78 is the lesser
    fault.
    """
    import textwrap

    return textwrap.wrap(prose, width=78, break_on_hyphens=False, break_long_words=False)


#: Which axis of `docs/capabilities.json` each case is evidence for. A case
#: goes under the one axis it demonstrates and no other; an axis with no case
#: here shows none rather than borrowing one.
AXIS_OF = {
    "not-a-container": "coverage",      # S13 claims an obligation the count holds
    "mimetype": "coverage",
    "no-metadata-rdf": "coverage",
    "no-format": "coverage",
    "missing-content": "explanation",   # L2 names no section: the item not done
}

CAPABILITIES = ROOT / "docs" / "capabilities.json"


def _case_block(slug, heading, broken, rule_id, exit_code, note):
    package = _not_a_container() if broken is None else _build(slug, broken)
    said = _verdict(package, exit_code=exit_code, names=rule_id)
    title, quotable, spec, claims = spec_of(rule_id)
    out = ["### %s" % heading, ""]
    if broken is None:
        # `fixtures/` is not in a clone; the other builds make it themselves.
        out.append("    $ mkdir -p %s && printf 'not a zip at all' > %s" % (BUILT, package))
    else:
        out.append("    $ python3 tools/make_fixture_package.py %s --broken %s"
                   % (package, broken))
    out.append("    $ iirds check %s" % package)
    out.append("")
    out.extend("    " + line if line else "" for line in said.splitlines())
    out.append("")
    out.append("Exit code %d." % exit_code)
    out.append("")
    if spec:
        out.extend(_wrapped("**The standard says so.** The link below lands "
                            "on these words, which are the specification's own:"))
        out.append("")
        out.extend(_wrapped("> %s" % quotable) if quotable
                   else ["> (the link carries no text fragment)"])
        out.append("")
        out.append("<%s>" % spec)
        out.append("")
        out.extend(_wrapped("`%s` states that obligation as: %s" % (rule_id, title)))
    elif claims:
        # A claim with no link is still a claim. Deciding "this tool's own" by
        # the absence of a link called S13 that while it claims "An iiRDS
        # package MUST implement an iiRDS ZIP archive" and counts toward the
        # coverage the front page publishes.
        out.extend(_wrapped(
            "**The standard states this obligation**, and `%s` claims it as %s; "
            "the rule carries no link to the sentence, so the page has none to "
            "quote. `%s` states it as: %s"
            % (rule_id, ", ".join("`%s`" % c for c in claims), rule_id, title)))
    else:
        out.append(OWN_RULE % rule_id)
    out.append("")
    out.extend(_wrapped(note))
    out.append("")
    return out


def _now_and_after(axis):
    """What is there now and what 1.0 asks, in the data's own words.

    Checklist items are printed exactly as `docs/capabilities.json` spells them,
    because the picture's gate looks for each one inside this axis's section and
    a paraphrase here would be a second text for one fact.
    """
    out = ["**Now.**", ""]
    if "items" in axis:
        for item in axis["items"]:
            out.append("- %s -- %s" % ("done" if item["done"] else "not yet", item["text"]))
    else:
        out.append("- %s" % axis["now_text"])
    out.extend(["", "**Before 1.0.** %s" % axis["target_text"], ""])
    return out


def page() -> str:
    import json

    axes = json.loads(CAPABILITIES.read_text("utf-8"))["axes"]
    out = ["# What this catches, and what it says when it does", "",
           "Written by `tools/gen_what_it_catches.py`; every block is the output of",
           "the command above it, captured on the run that wrote this file. Build the",
           "containers and reproduce any of it with the commands each case names: one",
           "that builds its container and one that checks it, two of each for the pair",
           "that is not flagged.",
           "It is arranged by the six things the picture on the front page draws, and",
           "an axis with no case to show shows none.", "",
           "The cases here are about this tool alone.", ""]

    placed = set()
    said = set()
    for axis in axes:
        out.extend(["## %s" % axis["label"], ""])
        if axis["key"] == "explanation":
            said.add("explanation")
            out.extend(_wrapped(
                "A finding carries a link to the sentence of the standard it enforces "
                "when its rule has one, and where a case on this page has one it quotes "
                "the words the link lands on. Some rules claim an obligation of the "
                "standard without a link to its sentence; a finding does not carry that "
                "claim, and `iirds rules <id> -v` shows it. Some rules have neither -- "
                "this project's interoperability and run rules among them, and a few "
                "from the upstream catalogue -- and for those nothing in the rule or its "
                "report yet says there is no section to give. Until every rule names its section or says it has "
                "none, that item is not done."))
            out.append("")
        for case in CASES:
            if AXIS_OF.get(case[0]) == axis["key"]:
                out.extend(_case_block(*case))
                placed.add(case[0])
        if axis["key"] == "report":
            out.extend(_same_graph())
            said.add("report")
        out.extend(_now_and_after(axis))

    # A case is shown under the axis its key names, and only there. Grouping
    # made that a lookup, and a lookup that finds nothing drops the case
    # without a word -- renaming one key in the data left one case of six on
    # the page while this still printed "6 cases". So a case that lands under
    # no axis is refused here rather than silently left out.
    missing = sorted(slug for slug, *_ in CASES if slug not in placed)
    if missing:
        raise Failed("these cases name no axis the data has, so the page would "
                     "leave them out: %s" % ", ".join(missing))
    # The paragraph on where a finding comes from, and the pair that is not
    # flagged, hang off one axis each: renaming that key would drop them from
    # the page as quietly as it dropped a case.
    unsaid = sorted({"explanation", "report"} - said)
    if unsaid:
        raise Failed("the page hangs text off axes the data no longer has: %s"
                     % ", ".join(unsaid))

    return "\n".join(out).rstrip() + "\n"


def _same_graph():
    """The pair that must NOT be flagged, and the comparison stated as measured.

    RDF/XML has many legal serialisations of one graph. If the two disagree the
    validator is testing the writer rather than the package, so the page says
    how far they agree and the generator is what decides how far that is.
    """
    a = _build("element-style", "none")
    b = _build("attribute-style", "attribute-style")
    graphs = []
    for where in (a, b):
        with zipfile.ZipFile(ROOT / where) as container:
            graphs.append(Graph().parse(data=container.read("META-INF/metadata.rdf"),
                                        format="xml"))
    if not isomorphic(*graphs):
        raise Failed("the pair that is not flagged is no longer one graph written two ways")
    for where in (a, b):
        _verdict(where, exit_code=0, names="PASS")
    reports = []
    for where in (a, b):
        document = json.loads(_must(["-m", "iirds_validate", "check", where, "-f", "json"]))
        for key in ("package", "packageDigest"):
            document.pop(key, None)
        reports.append(json.dumps(document, sort_keys=True))
    if reports[0] != reports[1]:
        raise Failed("the two serialisations no longer report the same document")
    # Each report under its own command. This block showed `iirds check a &&
    # iirds check b` above a's report alone, on a page whose first line says
    # every block is the output of the command above it.
    shown = ["### What it does not flag, and why", "",
             "    $ python3 tools/make_fixture_package.py %s" % a,
             "    $ python3 tools/make_fixture_package.py %s --broken attribute-style" % b,
             ""]
    for where in (a, b):
        said = _run(["-m", "iirds_validate", "check", where])[1]
        shown += ["    $ iirds check %s" % where, ""]
        shown += ["    " + line if line else "" for line in said.splitlines()]
        shown.append("")
    return shown + [
            "Both pass, and the two reports are the same document: every key identical",
            "apart from the package's own path and digest, which is what a different",
            "file is. One is written with typed elements and nested properties, the",
            "other with the package's and the topic's literals as attributes, the",
            "rendition as `rdf:parseType=\"Resource\"` and every type as `rdf:type`;",
            "the graph is the same graph -- this page is not written unless it is -- so",
            "the answer is the same answer. `--broken` is only the name of the",
            "generator's one switch; `attribute-style` is not a defect.", ""]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="fail if the page is not what a run produces now")
    args = ap.parse_args()
    try:
        written = page()
    except Failed as why:
        print(why, file=sys.stderr)
        return 1
    if args.check:
        if not PAGE.exists():
            print("%s is not there; run this without --check" % PAGE, file=sys.stderr)
            return 1
        if PAGE.read_text("utf-8") != written:
            print("%s is not what the commands print now; run this without --check"
                  % PAGE, file=sys.stderr)
            return 1
        print("what-it-catches: %d cases, each still the verdict it says" % (len(CASES) + 1))
        return 0
    PAGE.write_text(written, "utf-8")
    print("wrote %s (%d cases)" % (PAGE, len(CASES) + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
