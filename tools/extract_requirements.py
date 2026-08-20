#!/usr/bin/env python3
"""Every normative statement in the specification, enumerated from the source.

The README asserted from its first day that iiRDS states "254 absolute requirements".
`grep -rn 254` returned exactly one hit: that sentence. No script, no data, no
way for anybody to arrive at the number again -- which is the same species of
problem this project objects to in validators, one level up. A document whose
argument is that claims should be checkable cannot itself carry an unsourced
one.

So the number is derived here instead. The specification marks every RFC 2119
keyword with `<em class="rfc2119">`, which removes the whole question of
whether a given "REQUIRED" is normative or a table's ordinary English, and
makes the count a matter of parsing rather than of judgement.

    python tools/extract_requirements.py --refresh   # fetch and re-derive
    python tools/extract_requirements.py             # check, offline

What is committed is the derived index -- keyword, section, and the sentence --
not the specification. The spec is CC BY 4.0, attribution only, so quoting the
sentences is free; mirroring the document is still not this project's business.

This is the first half of the requirement map. It answers "what does the
standard require", by enumeration. It does not yet answer "and which rule
covers it", which is the half that makes coverage sayable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Pinned, like everything else here. A moving URL would make the count
#: unreproducible again in the one way that matters.
RELEASE = "20251103-1.3-release"
SPEC_URL = "https://www.iirds.org/fileadmin/iiRDS_specification/%s/index.html" % RELEASE
CACHE = ROOT / ".spec-cache" / ("%s.html" % RELEASE)
INDEX = ROOT / "docs" / "requirements.json"

#: RFC 2119 words that impose an obligation. RECOMMENDED, MAY and OPTIONAL are
#: extracted too and marked, because a map that lists only the obligations
#: cannot show that a permission was read as one -- which has happened here
#: twice, in B8 and in M96.4.
ABSOLUTE = ("MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT")

BLOCKS = ("p", "td", "th", "li", "dd", "dt", "figcaption")
_SENTENCE = re.compile(r"(?<=[.:;])\s+(?=[A-Z(])")
_QNAME = re.compile(r"[A-Za-z][\w.-]*:[A-Za-z][\w.-]*")

#: Obligations the specification states as a range instead of a word.
#:
#: Sixty rows in the property tables read `0..1 iirds:dateOfEffect property -
#: xsd:dateTimeStamp`, and not one of them carries an RFC 2119 keyword. They are
#: obligations all the same -- "at most one" is a MUST NOT have two, and a whole
#: family of rules here exists to enforce exactly them: M2.3 to M2.9, M21.2 to
#: M21.6, M24.1 to M24.4, M95.
#:
#: Which means the count of marked keywords, taken alone, understates what the
#: standard requires. The two sets do not overlap at all: zero of the sixty rows
#: contains a marker. Every one observed is `0..1`; a `0..n` would be a
#: permission and is excluded by the pattern rather than by assumption.
_CARDINALITY = re.compile(r"\b0\.\.1\b\s*(?:&nbsp;|\s)*([A-Za-z][\w:.-]*)?")


class Requirements(HTMLParser):
    """Walks the document once, in order, tracking three things.

    The nearest heading, so a requirement can be found again by a person. The
    block element a keyword sits in, because the requirement is the sentence
    around it rather than the word. And whether we are inside an `<aside>`,
    which the specification uses for notes and examples -- none of the 379
    markers is in one today, and if that ever changes the count must not move
    silently.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section = ("", "")
        self.hits = []
        self._open = []
        self._heading = None
        self._heading_text = []
        self._block = None
        self._block_text = []
        self._block_hits = []
        self._rfc_depth = 0
        self._pending = None
        self._row = []
        self.subject = ("", "")
        self._dfn = None
        self._dfn_text = []

    # -- structure ---------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self._open.append(tag)

        if tag == "tr":
            self._row = []
        if tag == "dfn":
            # Appendix A gives every class and property its own <dfn> and then a
            # table. Without this, sixty requirements read "IRI: REQUIRED" under
            # one section anchor, indistinguishable from each other and useless
            # to anyone trying to find the one a rule covers.
            self._dfn = attributes.get("id") or ""
            self._dfn_text = []
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = attributes.get("id") or ""
            self._heading_text = []
        elif tag in BLOCKS and self._block is None:
            self._block, self._block_text, self._block_hits = tag, [], []
        elif tag == "em" and "rfc2119" in attributes.get("class", ""):
            if self._rfc_depth == 0:
                self._pending = len("".join(self._block_text))
            self._rfc_depth += 1

    def handle_endtag(self, tag):
        if tag == "em" and self._rfc_depth:
            self._rfc_depth -= 1
        if tag == "dfn" and self._dfn is not None:
            self.subject = (self._dfn, _clean("".join(self._dfn_text)))
            self._dfn = None
        if re.fullmatch(r"h[1-6]", tag) and self._heading is not None:
            self.section = (self._heading, _clean("".join(self._heading_text)))
            self._heading = None
            # A heading closes any <dfn> scope. Without this the extractor
            # carried the last definition forward for ever, and a third of the
            # index — 145 of 439 statements — was filed under
            # dfn-iirds-zip-archive#N, including Party rules from §6.8 and
            # serialization rules from §6.12. Ids that look like spec anchors
            # and point at the wrong definition are worse than opaque ones,
            # and they re-key wholesale at the next release.
            self.subject = ("", "")
        elif tag == self._block:
            self._flush()
        if tag in self._open:
            while self._open and self._open.pop() != tag:
                pass

    def handle_data(self, data):
        if self._dfn is not None:
            self._dfn_text.append(data)
        if self._heading is not None:
            self._heading_text.append(data)
            return
        if self._block is None:
            return
        if self._rfc_depth and self._pending is not None:
            self._block_hits.append((self._pending, data.strip()))
            self._pending = None
        self._block_text.append(data)

    # -- collection --------------------------------------------------------
    def _flush(self):
        text = _clean("".join(self._block_text))
        cell = self._block in ("td", "th")

        # A cardinality table states its requirement across a row: the label is
        # in one cell and the obligation in the next, so a cell on its own reads
        # "REQUIRED" and says nothing. 122 of the 123 normative rows have that
        # shape, which is a third of every marker in the document -- recording
        # them as bare keywords would have made a third of this index useless
        # while looking complete.
        label = _clean(" ".join(self._row)) if cell and self._row else ""

        tokens = (label or "").split()
        qnames = [tok for tok in tokens if _QNAME.fullmatch(tok)]
        #: What this row is about, when no <dfn> governs it: the first
        #: qualified name in the row, else the row's first token — Appendix
        #: B's data-role table names its subjects ("safety-alert-symbol")
        #: without a namespace.
        row_subject = qnames[0] if qnames else (tokens[0] if tokens else None)

        if cell:
            for match in _CARDINALITY.finditer(text):
                # Two table shapes state cardinalities. Appendix A.1 puts the
                # property in the same cell ("0..1 iirds:dateOfEffect ..."),
                # under a class <dfn> that supplies the subject. Appendix A.5
                # is an overview: domain, property and range are earlier cells
                # of the row, the cardinality cell says only "0..1", and there
                # is no <dfn> — so both the subject and the property have to
                # come from the row. The sticky-scope bug used to hide this by
                # lending these rows whichever definition came last.
                prop = match.group(1) or (qnames[1] if len(qnames) >= 2 else None)
                subject = self.subject[1] or row_subject
                self.hits.append({
                    "keyword": "0..1",
                    "absolute": True,
                    "stated_as": "cardinality",
                    "section": self.section[0],
                    "section_title": self.section[1],
                    "subject": subject,
                    "subject_anchor": self.subject[0] or None,
                    "block": self._block,
                    "in_aside": "aside" in self._open,
                    "sentence": ("0..1 %s (at most one)" % prop) if prop
                                else _clean(match.group(0)) + " (at most one)",
                    "context": ("%s | %s" % (label, text)).strip(" |"),
                    "row_label": label or None,
                    "cites": None,
                })

        for offset, keyword in self._block_hits:
            self.hits.append({
                "keyword": keyword,
                "absolute": keyword in ABSOLUTE,
                "stated_as": "rfc2119",
                "section": self.section[0],
                "section_title": self.section[1],
                "subject": self.subject[1] or (row_subject if cell else None),
                "subject_anchor": self.subject[0] or None,
                "block": self._block,
                "in_aside": "aside" in self._open,
                "sentence": ("%s %s" % (label, text)).strip() if label
                            else (_sentence_at(text, offset) or text),
                "cites": "%s %s" % (self.subject[1], label or "") if cell and self.subject[1]
                         else None,
                "context": ("%s | %s" % (label, text)).strip(" |") if cell else text,
                "row_label": label or None,
            })
        if cell:
            self._row.append(text)
        self._block, self._block_text, self._block_hits = None, [], []
        self._pending = None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sentence_at(text: str, offset: int) -> str:
    """The sentence the keyword falls in.

    A block often states several obligations, and a map whose unit is the
    paragraph cannot say which of them a rule covers. Split on terminal
    punctuation followed by a capital; imperfect on abbreviations, and the
    whole block is kept alongside so nothing is lost when it misjudges.
    """
    start = 0
    for match in _SENTENCE.finditer(text):
        if match.start() > offset:
            return text[start:match.start()].strip()
        start = match.end()
    return text[start:].strip()


def _identify(hits):
    """A stable id per requirement: the narrowest anchor plus an ordinal in it.

    The <dfn> where there is one, because Appendix A repeats the same sentence
    for every class and the section anchor cannot tell them apart. Never a
    global counter: inserting a class must not renumber every requirement after
    it and turn a one-line change into a whole-file diff.
    """
    seen = {}
    for hit in hits:
        scope = hit["subject_anchor"] or hit["section"] or "unsectioned"
        seen[scope] = seen.get(scope, 0) + 1
        hit["id"] = "%s#%d" % (scope, seen[scope])
    return hits


def fetch() -> str:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(SPEC_URL, timeout=120) as handle:
        body = handle.read().decode("utf-8", "replace")
    CACHE.write_text(body, "utf-8")
    return body


def build(html: str) -> dict:
    parser = Requirements()
    parser.feed(html)
    hits = _identify(parser.hits)

    absolute = [h for h in hits if h["absolute"]]
    counts, by_form = {}, {}
    for hit in hits:
        counts[hit["keyword"]] = counts.get(hit["keyword"], 0) + 1
        by_form[hit["stated_as"]] = by_form.get(hit["stated_as"], 0) + 1

    return {
        "_source": SPEC_URL,
        "_release": RELEASE,
        "_source_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "_generated_by": "tools/extract_requirements.py --refresh",
        "_licence": "iiRDS specification text, CC BY 4.0, (c) the document editors",
        "_note": ("One entry per RFC 2119 keyword the specification marks with "
                  "<em class=\"rfc2119\">, not per sentence: a sentence stating two "
                  "obligations appears twice. This is the enumeration of what the "
                  "standard requires. It does not say which rule covers what."),
        "absolute_keywords": list(ABSOLUTE),
        "counts": dict(sorted(counts.items())),
        "stated_as": dict(sorted(by_form.items())),
        "absolute": len(absolute),
        "total": len(hits),
        "requirements": hits,
    }


def check() -> int:
    if not INDEX.exists():
        print("no index; run --refresh", file=sys.stderr)
        return 2
    index = json.loads(INDEX.read_text("utf-8"))

    problems = []
    if index["_release"] != RELEASE:
        problems.append("index is for %s, this tool targets %s"
                        % (index["_release"], RELEASE))
    expected = sum(index["counts"].get(k, 0) for k in ABSOLUTE) + index["counts"].get("0..1", 0)
    if index["absolute"] != expected:
        problems.append("the absolute count does not match the per-keyword counts")
    if not index["counts"].get("0..1"):
        problems.append("no cardinality obligations found; the property tables state sixty "
                        "of them and they carry no RFC 2119 keyword, so losing them would "
                        "quietly shrink the denominator")
    if any(r["in_aside"] for r in index["requirements"]):
        problems.append("a keyword is inside an <aside>; notes and examples are not "
                        "normative and the count must not include one silently")
    bare = [r["id"] for r in index["requirements"]
            if r["block"] in ("td", "th") and r["sentence"].strip() == r["keyword"]]
    if bare:
        problems.append("%d table requirement(s) recorded as a bare keyword with no row "
                        "label, which says nothing: %s" % (len(bare), bare[:3]))
    blank = [r["id"] for r in index["requirements"] if not r["sentence"]]
    if blank:
        problems.append("%d requirement(s) extracted no sentence: %s" % (len(blank), blank[:3]))
    if len({r["id"] for r in index["requirements"]}) != len(index["requirements"]):
        problems.append("requirement ids are not unique")

    for line in problems:
        print("  " + line, file=sys.stderr)
    if problems:
        return 1

    print("%d normative statements, %d of them absolute, across %d sections of %s"
          % (index["total"], index["absolute"],
             len({r["section"] for r in index["requirements"]}), index["_release"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="fetch the specification and re-derive")
    ap.add_argument("--offline", action="store_true", help="re-derive from the cached copy")
    args = ap.parse_args()

    if not (args.refresh or args.offline):
        return check()

    html = fetch() if args.refresh else CACHE.read_text("utf-8")
    index = build(html)
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", "utf-8")
    for keyword, n in sorted(index["counts"].items(), key=lambda kv: -kv[1]):
        print("  %-12s %3d%s" % (keyword, n, "  (absolute)" if keyword in ABSOLUTE else ""))
    print("  %-12s %3d" % ("absolute", index["absolute"]))
    return check()


if __name__ == "__main__":
    sys.exit(main())
