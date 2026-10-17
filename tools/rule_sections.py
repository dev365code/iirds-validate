#!/usr/bin/env python3
"""Every rule names the section of the standard it reads, or says it has none.

    python tools/rule_sections.py            # write src/iirds_validate/sections.py
    python tools/rule_sections.py --check    # regenerate in memory and compare

A finding carries a link to the words of the standard behind it when its rule
has one, and fifty-two rules had none. Seventeen of them claim obligations and
gave no link to the sentences they claim; thirty-five claim nothing, and for
those nothing in the rule or its report said whether there was a section to
give at all.

Where the link can be derived, it is, so that it cannot drift from what the
rule claims:

  * a rule that carries its own link -- the catalogue's, or one given where it
    is registered -- keeps it, and nothing here touches it;
  * a rule that claims obligations names the section of the first sentence it
    claims, read from `docs/requirements.json`;
  * a rule that claims nothing names the section of the sentence its finding is
    about (SENTENCE below), or a section by its anchor where the words a reader
    needs carry no keyword (SECTION), or says why no section is behind it
    (NONE).

The last three are written by hand, because no index says which sentence a
piece of advice is about. They are checked rather than trusted: a sentence id
has to be in the index, an anchor has to be a section of the specification --
of the index, or of a cached copy where the index does not reach -- every rule
has to land in exactly one place, and an entry for a rule that no longer needs
one is an error instead of a line nobody reads.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "src" / "iirds_validate" / "sections.py"
INDEX = ROOT / "docs" / "requirements.json"

#: Rules that claim nothing, and the requirement whose sentence their finding
#: is about. Naming the sentence rather than the section keeps the section
#: derived: it is read from the index row, as it is for a rule that claims.
SENTENCE = {
    "B9": "b-6-additional-semantic-tagging-of-content#3",
    "B10": "b-6-additional-semantic-tagging-of-content#3",
    "C2": "dfn-iirds-package#1",
    "L2": "x6-3-content-references-of-information-units#3",
    "L3": "x6-9-1-directory-nodes#1",
    "L4": "x6-9-1-directory-nodes#1",
    "L5": "x7-3-proprietary-iirds-extensions#2",
    "L12": "x5-1-3-names-of-files-and-directories#2",
    "L13": "x7-3-proprietary-iirds-extensions#2",
    "L17": "x6-12-rdf-serialization#2",
    "R43": "x8-2-1-2-graphics-formats#1",
    "R44": "x8-2-1-3-video-formats#2",
    "R45": "x8-2-1-4-audio-formats#2",
    "S6": "dfn-iirds-container#1",
    "S11": "x6-2-information-units#5",
}

#: Rules that claim nothing and whose words have no keyword sentence to name:
#: a vocabulary table, an example, the list of namespaces, a sentence the
#: specification states as normative without a keyword.
SECTION = {
    "L6": "x7-3-1-adding-a-proprietary-instance",
    "L7": "a-1-1-class-definitions",
    "L10": "a-1-1-class-definitions",
    "L14": "x6-1-the-iirds-rdf-schema-and-identifiers",
    "L16": "a-1-3-relations",
    "S4": "a-1-2-property-definitions",
    "S5": "x8-1-1-unrestricted-iirds-vs-restricted-iirds",
    # The ZIP format is the standard's by reference: "The ZIP archive file
    # format is defined in [ZIP]", which is where C1 and C2 point too.
    "S10": "x5-2-iirds-zip-archive",
    # "All other files in the ZIP are either uncompressed ("Stored"
    # compression mode) or compressed in "Deflated" mode" -- normative, and
    # without a keyword, so the index does not hold it as a sentence.
    "S14": "x5-2-2-content-encoding",
    "S15": "x5-2-iirds-zip-archive",
}

#: Rules with no section behind them, and why. Each is about the run itself or
#: is this project's own advice.
NONE = {
    "L1": "this project's advice about what a consumer can resolve, not a reading "
          "of a sentence of the standard",
    "L8": "this project's note on what a consumer without network access cannot "
          "resolve, not a reading of a sentence of the standard",
    "L11": "about this run: where the iiRDS XHTML5 rules did not read a file "
           "through its rendition",
    "L15": "this project's advice about the vocabulary of the declared edition, "
           "not a reading of a sentence of the standard",
    "S1": "about this run: the path could not be read",
    "S2": "about this run: no metadata was read, so no rule about the graph ran",
    "S3": "about this run: a rule raised instead of answering",
    "S9": "about this run: the content it decompressed reached its stated ceiling",
    "S12": "about this run: the search for the package's own ontology reached its "
           "ceiling",
    "S16": "about this run: no content rule got a parsed document for the file",
}

HEADING = re.compile(r'<h[1-6][^>]*\bid="([^"]+)"')


def _index():
    data = json.loads(INDEX.read_text("utf-8"))
    rows = {row["id"]: row for row in data["requirements"]}
    return data, rows, {row["section"] for row in rows.values()}


def _cached_sections(data):
    """The specification's section anchors, from a cached copy, or None.

    The specification is not redistributable, so CI has no copy; under `make`
    the absence is a failure, because an anchor outside the index is otherwise
    checked by nothing."""
    cache = ROOT / ".spec-cache" / ("%s.html" % data["_release"])
    if cache.exists():
        return set(HEADING.findall(cache.read_text("utf-8")))
    if os.environ.get("IIRDS_REQUIRE_SPEC_CACHE"):
        raise SystemExit("IIRDS_REQUIRE_SPEC_CACHE is set and %s is not here; run "
                         "`python tools/extract_requirements.py --refresh`" % cache)
    return None


def derive():
    """(sections, none, problems): rule id -> link, rule id -> reason, and what
    is wrong with the hand-written tables."""
    from iirds_validate import registry

    data, rows, indexed = _index()
    base = data["_source"]
    rules = registry.all_rules()
    sections, none, problems, unverified = {}, {}, [], []
    cache = {}

    def anchor_ok(rule_id, anchor):
        if anchor in indexed:
            return
        if "sections" not in cache:
            cache["sections"] = _cached_sections(data)
        if cache["sections"] is None:
            unverified.append(anchor)
        elif anchor not in cache["sections"]:
            problems.append("%s names %s, which is no section of the specification"
                            % (rule_id, anchor))

    hand = {**dict.fromkeys(SENTENCE, "SENTENCE"), **dict.fromkeys(SECTION, "SECTION")}
    for k in NONE:
        if k in hand:
            problems.append("%s is in %s and in NONE" % (k, hand[k]))
        hand[k] = "NONE"
    for k in set(SENTENCE) & set(SECTION):
        problems.append("%s is in SENTENCE and in SECTION" % k)

    for rule in rules:
        own = registry.own_spec(rule.id)
        where = hand.get(rule.id)
        if own or rule.covers:
            if where:
                problems.append("%s is in %s, but it %s" % (
                    rule.id, where, "carries its own link" if own else
                    "claims obligations, and its section is derived from them"))
            if own:
                continue
            first = rule.covers[0]
            if first not in rows:
                problems.append("%s claims %s, which is not in the index" % (rule.id, first))
                continue
            sections[rule.id] = "%s#%s" % (base, rows[first]["section"])
        elif rule.id in SENTENCE:
            sentence = SENTENCE[rule.id]
            if sentence not in rows:
                problems.append("%s names %s, which is not in the index" % (rule.id, sentence))
                continue
            sections[rule.id] = "%s#%s" % (base, rows[sentence]["section"])
        elif rule.id in SECTION:
            anchor_ok(rule.id, SECTION[rule.id])
            sections[rule.id] = "%s#%s" % (base, SECTION[rule.id])
        elif rule.id in NONE:
            if not NONE[rule.id].strip():
                problems.append("%s is in NONE with no reason" % rule.id)
                continue
            none[rule.id] = NONE[rule.id]
        else:
            problems.append("%s carries no link, claims nothing, and is in none of "
                            "SENTENCE, SECTION and NONE" % rule.id)

    registered = {rule.id for rule in rules}
    for k in sorted(set(hand) - registered):
        problems.append("%s is in %s, and no rule has that id" % (k, hand[k]))
    return sections, none, problems, unverified


def render(sections, none) -> str:
    lines = ['"""Where each rule\'s words are in the standard, for the rules that do not',
             "say so themselves. Written by tools/rule_sections.py; edit that, not this.",
             "",
             "A rule carrying its own link keeps it. SECTIONS gives the rest a section of",
             "the specification; NO_SECTION says why a rule has none.",
             '"""',
             "",
             "SECTIONS = {"]
    lines += ["    %r: %r," % (k, v) for k, v in sections.items()]
    lines += ["}", "", "NO_SECTION = {"]
    lines += ["    %r: %r," % (k, v) for k, v in none.items()]
    lines += ["}", ""]
    return "\n".join(lines)


#: What `sections.py` holds before anything has been derived. The registry
#: imports the table this tool writes, so without one the tool could not start.
EMPTY = "SECTIONS = {}\nNO_SECTION = {}\n"


def _shown(path):
    """A path as a reader of this repository would type it, where it is one."""
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def _readable(path) -> bool:
    try:
        compile(path.read_text("utf-8"), str(path), "exec")
    except (OSError, SyntaxError, ValueError):
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="regenerate in memory and compare with the committed file")
    args = ap.parse_args()

    if not _readable(OUT):
        if args.check:
            print("  %s is missing or does not parse; run `python tools/rule_sections.py`"
                  % _shown(OUT), file=sys.stderr)
            return 1
        OUT.write_text(EMPTY, "utf-8")

    sections, none, problems, unverified = derive()
    for line in problems:
        print("  " + line, file=sys.stderr)
    if problems:
        return 1
    text = render(sections, none)
    if unverified:
        print("  not verified without a cached specification: %s" % ", ".join(sorted(set(unverified))))
    if args.check:
        if OUT.read_text("utf-8") != text:
            print("  %s does not match what this generator writes; run "
                  "`python tools/rule_sections.py`" % _shown(OUT), file=sys.stderr)
            return 1
        print("  %d rules name a section here, %d say they have none"
              % (len(sections), len(none)))
        return 0
    OUT.write_text(text, "utf-8")
    print("  wrote %s: %d rules name a section here, %d say they have none"
          % (_shown(OUT), len(sections), len(none)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
