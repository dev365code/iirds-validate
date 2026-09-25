"""Parsing untrusted metadata safely.

Written first in the checker's context module and moved here. An .iirds
package arrives from a supplier, so its metadata is untrusted input, and the
guards it has to pass before a parser sees it belong in the layer every tool
shares -- not re-invented per tool. `iirds_validate.context` imports these
from here; there is one copy.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import re
import xml.etree.ElementTree as ElementTree
import xml.parsers.expat as expat
from typing import Dict, List, Optional, Tuple

from rdflib import BNode, Graph, Literal

#: Two cheap guards, applied before the parser sees anything.
MAX_METADATA_BYTES = 64 * 1024 * 1024


#: rdflib decodes a bytes payload as UTF-8 unconditionally, so a document that
#: declares — and marks with a byte order mark — any other encoding fails to
#: parse at all. XML says the BOM decides, so it is honoured here and the
#: payload handed on as UTF-8.
#: Longest mark first, because a UTF-32 mark begins with a UTF-16 one and the
#: order is what tells them apart.
#:
#: Every codec here must be one that *consumes* the mark. `utf-16-le` and
#: `utf-32-le` do not: they leave U+FEFF at the front of the text, the
#: declaration is then no longer the first thing in it, and the substitution
#: below -- which may only match the first thing, because that is the only
#: place a declaration may sit -- stops firing. The bytes go on to say UTF-8
#: while the declaration still says UTF-16, and the two readers disagree about
#: the document: one refuses it, the other reads it and expands what it
#: declares. The mark is not data; a codec that hands it back is the wrong
#: codec.
_BOMS = ((b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
         (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"),
         (b"\xef\xbb\xbf", "utf-8-sig"))


def _sniff(raw: bytes):
    """The encoding expat will take an unmarked document for, or None.

    XML requires a byte order mark on a UTF-16 document and expat does not
    insist, autodetecting instead -- so a document can be UTF-16 to the parser
    and opaque bytes to every guard below, which is how `<!ENTITY` in UTF-16
    was invisible to a pattern that only ever matches UTF-8.

    Decided on the *shape* of the first two characters, not on what they are.
    Two earlier versions of this keyed on the document beginning with `<` and
    both were wrong, in the same way and for the same reason: `<` is a
    property of the fixtures, not of XML. A document may open with `Misc*` --
    whitespace, a comment, a processing instruction -- and may carry no
    declaration at all. Whitespace was the lead that got through.

    An ASCII character in UTF-16LE is `xx 00`, in UTF-16BE `00 xx`, and in
    UTF-32 three of the four bytes are null. Every legal first character of an
    XML document is ASCII, so two characters settle it whatever they are.
    Unmarked UTF-32 is refused by expat, so nothing can be smuggled in it, and
    claiming to read it here would admit documents the parser will not.
    """
    if len(raw) < 4:
        return None
    null = tuple(byte == 0 for byte in raw[:4])
    if null in ((False, True, True, True), (True, True, True, False)):
        return None                                 # unmarked UTF-32
    if null == (False, True, False, True):
        return "utf-16-le"
    if null == (True, False, True, False):
        return "utf-16-be"
    return None


class _Declared(Exception):
    """An entity declaration reached the parser."""


class _RootReached(Exception):
    """The prolog is over, and nothing after it can declare an entity."""


def _raise(exception):
    raise exception()


def _declares_entities(raw: bytes) -> Optional[bool]:
    """Whether the parser will be handed declarations to expand.

    Asked of the parser rather than of the bytes. A pattern over bytes has to
    decide the encoding for itself and then agree with the parser about it,
    and the two did not: a declaration written UTF-16 walked past a pattern
    that matches UTF-8. It also has to know where the grammar permits a
    declaration, and it did not: the token in a CDATA section or a comment is
    characters, so a document *describing* the vocabulary it is written in was
    refused for declaring nothing.

    expat settles both, being the thing that would do the expanding. The
    handler fires when a declaration is read and before any reference to it is
    expanded. Stopped at the root element: declarations live in the DTD, the
    DTD precedes the root, and an external one is not fetched -- so an
    external DTD passes, declaring nothing this parser will see.

    Read as the parser under the graph reads it: as UTF-8, whatever the
    document declares, because that is how rdflib reads it. Left to follow the
    declaration, expat read some documents as other text than rdflib did, and
    its answer was about that other text. None where expat cannot read the
    document at all, which the caller refuses.
    """
    parser = expat.ParserCreate("UTF-8")
    parser.EntityDeclHandler = lambda *_args: _raise(_Declared)
    parser.StartElementHandler = lambda *_args: _raise(_RootReached)
    try:
        parser.Parse(raw, True)
    except _Declared:
        return True
    except _RootReached:
        return False
    except (expat.ExpatError, UnicodeDecodeError):
        # A syntax error is the document's, and the parser under the graph,
        # reading the same text the same way, meets it and says so in its own
        # words. So are bytes that are not UTF-8, which older expat hands on
        # unchecked inside a name, where decoding the name raises: rdflib
        # decodes the document as UTF-8, a piece at a time, before its parser
        # reads those bytes, and stops at them, so nothing at or past them --
        # a declaration included -- reaches its parser.
        return False
    except Exception:
        # What else arrives is not answered for, and not raised either:
        # parse_errors promises that reading never raises.
        return None
    return False


#: The category `parse_metadata` returns for a well-formed XML document the
#: RDF/XML grammar does not define. Part of the error string's shape --
#: ``"<name>: <category>: <detail>"`` -- and exported because the validator
#: routes on it: this refusal is the metadata being the wrong kind of
#: document, not the document being damaged.
NOT_RDFXML = "not an RDF/XML document"

#: A document naming an encoding this reader does not read: one no codec
#: answers to, one outside the encodings it decodes, or a name XML does not
#: allow. Refused, not read: XML requires the declaration to name a charset the
#: processor can handle, and a processor that cannot must say so rather than
#: guess. It has its own category because the alternative was the exception
#: escaping this function -- `LookupError` out of the reader below, past a
#: contract that promises `(graph, None)` or `(None, error)`, into a caller
#: told otherwise.
UNREADABLE_ENCODING = "declares an encoding this reader does not read"

#: A document whose declaration and this reader disagree about what it says.
#: rdflib decodes as UTF-8 whatever the declaration names, so where the
#: declaration names something else there are two readings of one file. Where
#: they are the same text -- every byte under 128 in a code page that keeps
#: ASCII where ASCII is, which is most of a conformant package that happens to
#: declare one -- there is nothing to report and nothing is reported. Where they differ, one of them is what
#: the supplier meant and this reader is holding the other, so it refuses
#: instead of choosing. That case was silent before: the refusal was rdflib
#: failing on a high byte, which caught the document written in the codepage
#: it declared and missed the one whose declaration was simply false over
#: UTF-8 bytes.
UNUSED_ENCODING = "declares an encoding this reader reads differently"

#: A document whose declaration names one encoding while its byte order mark,
#: or the first two characters of unmarked UTF-16, say another. XML makes that
#: a fatal error (section 4.3.3) where no transport protocol gives the
#: encoding -- and none gives a ZIP member's, so the premise holds for every
#: file in a package. Not a declaration this reader leaves unused: one the
#: bytes contradict.
CONTRADICTED_ENCODING = "declares an encoding its bytes contradict"

#: A UTF-32 document with no declaration: XML makes an entity with none, in an
#: encoding other than UTF-8 or UTF-16, a fatal error (section 4.3.3).
UNDECLARED_ENCODING = "declares no encoding where XML requires one"

#: Names the RDF/XML grammar takes out of `nodeElementURIs` (§7.2.5): the
#: core syntax terms (§7.2.2), `rdf:li`, and the old terms (§7.2.4). Anything
#: else that is an absolute IRI names a node element -- the class of a typed
#: node, or rdf:Description for an untyped one.
NOT_NODE_ELEMENTS = frozenset(("RDF", "ID", "about", "parseType", "resource", "nodeID",
                               "datatype", "li", "aboutEach", "aboutEachPrefix", "bagID"))
_RDF_NAMESPACE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def is_absolute_name(text: str) -> bool:
    """An absolute IRI has a scheme. `urn:uuid:...` counts; a bare name does not."""
    return bool(_SCHEME.match(text))


def is_rdfxml_document_element(tag: str) -> bool:
    """Is this element, as ElementTree names it, one an RDF/XML document may start with?

    §7.2.1 of the grammar: a standalone document starts with production doc
    -- the rdf:RDF element -- or with production nodeElement; §2.6 says the
    same in prose, "when there is only one top-level node element inside
    rdf:RDF, the rdf:RDF can be omitted although any XML namespaces must
    still be declared". A node element's name is any absolute IRI except
    the reserved ones (§7.2.5), so an element with no namespace is not one:
    its name is not an IRI. Only the document element is judged here; what
    the body does with the grammar is the parser's to say.
    """
    namespace, local = _split(tag)
    if namespace == _RDF_NAMESPACE and local == "RDF":
        return True
    if not is_absolute_name(namespace + local):
        return False
    return not (namespace == _RDF_NAMESPACE and local in NOT_NODE_ELEMENTS)


def _split(tag: str) -> Tuple[str, str]:
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        return namespace, local
    return "", tag


#: The `encoding=` of an XML declaration, which may sit only at the front,
#: behind a UTF-8 byte order mark at most. `<?xml` and then white space: a
#: processing instruction whose target merely starts with those letters --
#: `<?xml-stylesheet` -- is not a declaration.
_DECLARED = re.compile(br'^(?:\xef\xbb\xbf)?<\?xml\s[^>]*?\sencoding\s*=\s*(["\'])(.*?)\1',
                       re.DOTALL)

#: A name XML allows for an encoding (XML 1.0, production 81).
_ENCODING_NAME = re.compile(r"[A-Za-z][A-Za-z0-9._-]*")

#: The two encodings XML requires beside UTF-8, by name with case, `-`, `_`
#: and `.` set aside. Every other encoding a document is decoded under, to be
#: compared with UTF-8, is one that reads a character from each byte.
_UTF16_OR_32 = frozenset({"utf16", "utf16le", "utf16be", "utf32", "utf32le", "utf32be"})

#: Names Python gives a code page that differs from one Windows machine to
#: the next, and that no other system has: a declaration of one would be read
#: one way here, another there, and not at all on Linux. Refused by name
#: everywhere, so that a verdict does not depend on the machine that gave it.
_PLATFORM_CODECS = frozenset({"mbcs", "dbcs", "ansi", "oem"})

#: Bytes a codec with escapes or shifting states reads as fewer characters
#: than there are bytes: a backslash escape, HZ's and ISO-2022's shifts, and
#: UTF-7's. Asked first, so that an escape codec never sees the bytes below.
_SHIFTS = b"\\u0041~{\x1b$B+-"

#: Every byte once.
_EVERY_BYTE = bytes(range(256))


def _one_character_a_byte(name: str) -> bool:
    """Whether the named codec reads one character from each byte, as the
    single-byte families do -- ASCII under any of its names, Latin, ISO 8859,
    the Windows, DOS, Mac and EBCDIC pages, KOI8, TIS-620.

    Asked of the codec rather than of its name: a list of names refused
    `ANSI_X3.4-1968`, which is ASCII's own, and let through Johab, which pairs
    bytes. A byte the codec has no character for is replaced here, and only
    here, because the question is how many characters come out, not which. A
    multi-byte codec pairs bytes and gives fewer; one with escapes or states
    gives fewer on `_SHIFTS`; and one that raises -- punycode, idna, a name no
    codec answers to -- is not decoded at all. Asked on so few bytes that the
    answer costs nothing whatever the codec is. UTF-8's own names
    pass too -- no two neighbours in every byte once make a sequence UTF-8
    pairs -- which is harmless: such a document is compared UTF-8 with UTF-8.
    """
    try:
        return (len(_SHIFTS.decode(name, "replace")) == len(_SHIFTS)
                and len(_EVERY_BYTE.decode(name, "replace")) == len(_EVERY_BYTE))
    except Exception:
        return False


#: Longer than the name of any codec there is -- the longest is a third of
#: this. A name as long is refused before a codec is asked for it: asking
#: costs time with the length of the name, and the answer is kept.
_LONGEST_NAME = 60


def _declared_encoding_name(raw: bytes) -> Optional[str]:
    """The name the document declares, as written, or None where it declares
    none. Cut one character past the longest a codec has, which is enough to
    refuse it by: a name is as long as its sender makes it."""
    found = _DECLARED.match(raw)
    return found.group(2)[:_LONGEST_NAME + 1].decode("latin-1") if found else None


def _shown(name: str) -> str:
    """A declared name as it can be printed: a name carried a terminal escape
    and a line break into the report, and wrote a line of its own there. Cut
    to sixty characters, before it is escaped as well as after."""
    shown = name[:_LONGEST_NAME + 1].encode("unicode_escape").decode("ascii")
    shown = shown if len(shown) <= 60 else shown[:57] + "..."
    # A space at either end escapes nothing and reads as no space at all:
    # "utf-8 " refused looked like UTF-8 refused.
    return "'%s'" % shown if shown != shown.strip(" ") else shown


def _decoded(raw: bytes, encoding: str):
    """The text those bytes are under that encoding, or None where they are
    not that encoding at all.

    Both readings are taken so they can be compared. Nothing here decodes
    with `errors=` set: a replacement character is this reader deciding what
    a supplier's byte meant and then saying nothing about it, which is the
    one thing an input layer must not do.
    """
    try:
        return raw.decode(encoding)
    except Exception:
        return None


def _is_utf8_name(name: str) -> bool:
    """Whether a declaration names UTF-8: `UTF-8`, `utf8` or `utf_8`, in any
    case, since XML encoding names are not case sensitive.

    Those spellings exactly. Stripping `-` and `_` first made `U-T-F-8`, a
    name no codec answers to, into UTF-8 here, and a padded name into one
    XML does not allow; any other spelling is asked of the codec like every
    other name. Compared rather than looked up: `codecs.lookup` would be a
    new import in a library whose import list is itself a gate.
    """
    return name.lower() in ("utf-8", "utf8", "utf_8")


class _Element(Exception):
    """The first element, by its expanded name."""


class _FirstElement:
    """A tree builder's place, taken by one that stops at the first element."""

    def start(self, tag, _attributes):
        raise _Element(tag)

    def close(self):
        return None


def _document_element(raw: bytes) -> Optional[str]:
    """The expanded name of the first element, or None where XML itself
    cannot say -- which the parser then reports in its own words.

    Read as UTF-8 whatever the document declares, for the reason the entity
    guard is: that is the text rdflib parses, and a judge that followed the
    declaration read other text and let a document through."""
    parser = ElementTree.XMLParser(target=_FirstElement(), encoding="utf-8")
    try:
        parser.feed(raw)
        parser.close()
    except _Element as first:
        return first.args[0]
    except Exception:
        # `ParseError`, which the parser under the graph reports in its own
        # words.
        return None
    return None


def _why_not_rdfxml(tag: str) -> str:
    namespace, local = _split(tag)
    if not namespace:
        return "document element is %s, which has no namespace" % local
    if not is_absolute_name(namespace + local):
        return "document element is %s in namespace %s, which is not an absolute IRI" % (local, namespace)
    return "document element is rdf:%s, a name the grammar reserves" % local


def _decode(raw: bytes) -> bytes:
    """The document as UTF-8, decided the way the parser will decide it.

    Everything after this point reads text. If this disagrees with expat
    about what the bytes say, every guard below is looking at a different
    document from the one that gets parsed.
    """
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return _as_utf8(raw.decode(encoding))
    encoding = _sniff(raw)
    if encoding is not None:
        return _as_utf8(raw.decode(encoding))
    return raw


def _as_utf8(text: str) -> bytes:
    # The declaration would now contradict the bytes, so it goes. Anchored to
    # the front, because that is the only place a declaration may sit: without
    # the anchor the first match could be anywhere, and where the real
    # declaration named no encoding it was -- a passage quoting a declaration
    # came back into the graph with a piece missing, so the file said one thing
    # and the graph said another.
    text = re.sub(r'^(<\?xml[^>]*?)\s+encoding\s*=\s*(["\'])[^"\']*\2',
                  r"\1", text, count=1)
    return text.encode("utf-8")


def _fetches_in_context(source, found):
    """Everything a JSON-LD context source names for the parser to go and get.

    Two constructs, and only two. A *string* in context position is a
    reference: the parser dereferences it whether or not it carries a scheme,
    and the scheme-less one is the worse case -- it resolves against the
    process's working directory and is read off the operator's disk, with no
    socket involved. And `@import` (JSON-LD 1.1) names one more, fetched
    before the rest of the context object is even read.

    The distinction that decides whether this refuses every conformant
    package: a string under a *term* key inside a context object is that
    term's IRI mapping -- inline data, never fetched, never flagged. It is
    the slot that makes a string a reference, not the string.

    Two shapes are refused that rdflib would not fetch, knowingly. `@import`
    inside a term definition is one; a `@context` key inside a value the
    document coerces to `@type: @json` is the other, because that value is
    opaque data and knowing so would mean interpreting the context to find
    out which terms are coerced. Both are invalid or vanishingly rare in
    iiRDS metadata, and both fail loudly with the reference named, which is
    recoverable -- unlike the silence this replaced.
    """
    if isinstance(source, str):
        found.append(source)
    elif isinstance(source, list):
        for element in source:
            _fetches_in_context(element, found)
    elif isinstance(source, dict):
        for key, value in source.items():
            if key == "@context":
                # A context object holding @context is unwrapped by the
                # parser, and a term definition's @context is that term's
                # scoped context. Both are context sources again.
                _fetches_in_context(value, found)
            elif key == "@import":
                if isinstance(value, str):
                    found.append("@import " + value)
            elif isinstance(value, dict):
                _fetches_in_context(value, found)
    return found


def _remote_contexts(node, found=None):
    """Every context this document sends the parser somewhere else to get.

    "Remote" means "not in this document" -- a URL, and equally a name the
    parser resolves against whatever directory the tool happens to be run
    from. From a supplier's package those are three problems, not one: it
    breaks the promise that reading touches no network, it lets the sender
    choose a host for a machine inside the plant to connect to, and it lets
    the sender read a file off the machine doing the reading.

    Contexts nest -- in arrays, in `@graph` and `@included` entries, on any
    node, and scoped inside a term definition -- so the whole document is
    walked rather than just the top level.
    """
    found = [] if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "@context":
                _fetches_in_context(value, found)
            else:
                _remote_contexts(value, found)
    elif isinstance(node, list):
        for item in node:
            _remote_contexts(item, found)
    return found


def _oversize(name: str, size: int) -> str:
    # "more than", because the reader stops one byte past the limit rather
    # than decompressing the rest to find out how much more there was.
    return ("%s: refused: more than %d bytes uncompressed, above the %d byte limit"
            % (name, size - 1, MAX_METADATA_BYTES))


def _declaration_refused(name: str, stored: bytes) -> Optional[str]:
    """Why the document's declaration refuses it, or None where it does not.

    rdflib decodes as UTF-8 whatever the declaration names. A name XML does
    not allow, or one this reader does not decode, is refused by name, with
    nothing decoded. Any other name is read both ways -- under the name, and
    as UTF-8 -- and where the two are different text there are two readings
    of one file, so it is refused rather than one chosen. Where they are the
    same, as they are for a code page that keeps ASCII where ASCII is over
    bytes all under 128, nothing is said.
    """
    declared = _declared_encoding_name(stored)
    if declared is None or _is_utf8_name(declared):
        return None
    shown = _shown(declared)
    normal = declared.lower().replace("-", "").replace("_", "").replace(".", "")
    if (len(declared) > _LONGEST_NAME or not _ENCODING_NAME.fullmatch(declared)
            or normal in _PLATFORM_CODECS
            or not (normal in _UTF16_OR_32 or _one_character_a_byte(declared))):
        return "%s: %s: %s" % (name, UNREADABLE_ENCODING, shown)
    body = stored[3:] if stored.startswith(b"\xef\xbb\xbf") else stored
    theirs, ours = _decoded(body, declared), _decoded(body, "utf-8")
    if theirs is None and ours is None:
        return None          # neither reads it, and the parser says so itself
    if theirs is None or ours is None or theirs != ours:
        return "%s: %s: %s" % (name, UNUSED_ENCODING, shown)
    return None


#: What a document's first bytes mark it as: a byte order mark, and the codec
#: that reads past it. Unmarked UTF-16 is marked by its first two characters,
#: which `_sniff` reads.
_MARKS = ((b"\xef\xbb\xbf", "UTF-8", "utf-8-sig"),
          (b"\xff\xfe\x00\x00", "UTF-32LE", "utf-32"), (b"\x00\x00\xfe\xff", "UTF-32BE", "utf-32"),
          (b"\xff\xfe", "UTF-16LE", "utf-16"), (b"\xfe\xff", "UTF-16BE", "utf-16"))

#: The IANA names that agree with a UTF-16 or UTF-32 mark, without regard to
#: case (section 4.3.3 recommends IANA names): a family name in either byte
#: order, a byte-order name only in its own.
_AGREEING = {
    "UTF-16LE": frozenset({"utf-16", "iso-10646-ucs-2", "utf-16le"}),
    "UTF-16BE": frozenset({"utf-16", "iso-10646-ucs-2", "utf-16be"}),
    "UTF-32LE": frozenset({"utf-32", "iso-10646-ucs-4", "utf-32le"}),
    "UTF-32BE": frozenset({"utf-32", "iso-10646-ucs-4", "utf-32be"}),
}

#: Spellings of UTF-16 and UTF-32 that are not their IANA names: Python's
#: codecs answer to them, and a declaration of one is a name this reader does
#: not read, not one it can hold against the mark.
_UNREGISTERED_UTF = frozenset({"utf16", "utf16le", "utf16be", "utf32", "utf32le", "utf32be"})

#: The `encoding=` of a declaration in a document already decoded, as far as
#: the quote that opens its value.
_ENCODING_OPENS = re.compile(r'<\?xml\s[^>]*?\sencoding\s*=\s*(["\'])', re.DOTALL)


def _declared_behind_mark(stored: bytes, codec: str) -> Optional[str]:
    """The encoding a marked document's declaration names, or None where it
    names none.

    Read as far as the declaration runs, a larger piece each time: XML lets
    white space stand between its attributes, and a fixed piece let an
    `encoding=` pushed past it go unread. Once the quote that opens the value
    is found, the piece grows until the one that closes it is: a value
    holding `?>` -- which no encoding's name can -- ended the reading there,
    and the declaration went unread.
    """
    limit = 4096
    while True:
        try:
            head = stored[:limit].decode(codec, "ignore").lstrip("\ufeff")
        except Exception:
            return None
        opened = _ENCODING_OPENS.match(head)
        whole = limit >= len(stored)
        if opened is not None:
            closing = head.find(opened.group(1), opened.end())
            if closing >= 0:
                return head[opened.end():closing]
            if whole:
                return head[opened.end():]
        elif "?>" in head or whole:
            return None
        limit *= 8


def _marked_declaration_refused(name: str, stored: bytes) -> Optional[str]:
    """Why a document its first bytes mark as UTF-8, UTF-16 or UTF-32 is
    refused for its declaration, or None where it is not.

    XML makes it a fatal error for a document to arrive in an encoding other
    than the one its declaration names, and for one that declares nothing to
    be in any but UTF-8 or UTF-16 (section 4.3.3). A parser reading the
    bytes as stored stops at either; the decode below believed the mark,
    dropped the declaration, and read the document all the same. The mark's
    encoding and the declaration are both named in the refusal, since the
    remedy is to make one say what the other does. Which bytes mark which
    encoding is read as XML's Appendix F reads it -- a non-normative table,
    which calls UTF-32 by its older name, UCS-4.
    """
    sniffed = _sniff(stored)
    found_mark = next(((mark, codec) for bom, mark, codec in _MARKS if stored.startswith(bom)), None)
    if found_mark is None and sniffed is not None:
        found_mark = ("UTF-16LE" if sniffed == "utf-16-le" else "UTF-16BE", sniffed)
    if found_mark is None:
        return None
    mark, codec = found_mark
    where = ("its byte order mark says" if stored[:2] in (b"\xff\xfe", b"\xfe\xff")
             or stored[:3] == b"\xef\xbb\xbf" or stored[:4] == b"\x00\x00\xfe\xff"
             else "its first bytes say")
    declared = _declared_behind_mark(stored, codec)
    if declared is None:
        if mark.startswith("UTF-32"):
            return ("%s: %s: %s %s and it declares no encoding; XML 1.0 section 4.3.3 "
                    "makes an undeclared encoding other than UTF-8 or UTF-16 a fatal error -- "
                    "declare UTF-32, or save the file as UTF-8" % (name, UNDECLARED_ENCODING, where, mark))
        return None
    declared = declared[:_LONGEST_NAME + 1]
    shown = _shown(declared)
    lowered = declared.lower()
    normal = lowered.replace("-", "").replace("_", "").replace(".", "")
    if mark == "UTF-8" and _is_utf8_name(declared):
        return None
    if mark != "UTF-8" and lowered in _AGREEING[mark]:
        return None
    # A name this reader does not read is refused as that, as it is with no
    # mark in front of it: saving the file in the encoding it names is no
    # remedy where that encoding is refused too.
    if (len(declared) > _LONGEST_NAME or not _ENCODING_NAME.fullmatch(declared)
            or normal in _PLATFORM_CODECS
            or (normal in _UNREGISTERED_UTF and lowered not in {n for a in _AGREEING.values() for n in a})
            or not (normal in _UTF16_OR_32 or _is_utf8_name(declared)
                    or _one_character_a_byte(declared))):
        return "%s: %s: %s" % (name, UNREADABLE_ENCODING, shown)
    return ("%s: %s: %s %s and its declaration says %s; XML 1.0 section 4.3.3 makes that "
            "a fatal error -- make the declaration name the encoding the bytes are in, or save "
            "the file in the one it names" % (name, CONTRADICTED_ENCODING, where, mark, shown))


def parse_metadata(name: str, raw: bytes, *, base: str) -> Tuple[Optional[Graph], Optional[str]]:
    """One metadata document, guarded, parsed into its own Graph.

    Returns ``(graph, None)`` on success, ``(None, error)`` on refusal or
    parse failure. The error string always leads with the file name --
    ``"<name>: <detail>"`` -- and that shape is an interface, not a habit:
    the validator routes these strings into its per-file findings by
    partitioning on the first ``": "``. Three refusals carry a named
    category after the file name, ``"<name>: <category>: <detail>"``:
    NOT_RDFXML, which the validator reports under a different rule from a
    damaged file, and the two a declaration draws, UNREADABLE_ENCODING and
    UNUSED_ENCODING.

    ``base`` has no default on purpose: a parse needs a base IRI and the
    caller owns that decision (the container reader passes PACKAGE_BASE).
    The format follows the file name -- ``.jsonld``/``.json`` parse as
    JSON-LD, everything else as RDF/XML, the two serialisations iiRDS names.
    The graph is the document's default graph; parse_metadata_graphs hands
    on a JSON-LD document's named graphs as well.
    """
    graph, _named, error = parse_metadata_graphs(name, raw, base=base)
    return graph, error


def parse_metadata_graphs(name: str, raw: bytes, *,
                          base: str) -> Tuple[Optional[Graph], Dict[object, Graph], Optional[str]]:
    """As parse_metadata, and the named graphs a JSON-LD document puts
    statements in.

    JSON-LD 1.1 reads a document as a dataset: a default graph and named
    graphs, and rdflib gives a named graph to every `@graph` that has an `@id`
    beside it -- a top-level one included, which puts everything in a graph
    of that name. Returns
    ``(graph, named, error)``: the default graph, the named graphs that hold
    statements, keyed by their names as rdflib gives them -- a URIRef, or a
    BNode where a blank node names the graph -- and the error as
    parse_metadata gives it. Keyed by the term, not its text: an IRI can be
    spelled like a blank node's label. RDF/XML names no graph, and a refused
    document has none.
    """
    named: Dict[object, Graph] = {}
    graph, error = _parse_metadata(name, raw, base, named)
    return graph, (named if graph is not None else {}), error


def _parse_metadata(name: str, raw: bytes, base: str,
                    named: Dict[object, Graph]) -> Tuple[Optional[Graph], Optional[str]]:
    """parse_metadata's work; a JSON-LD document's named graphs go into
    `named`."""
    fmt = "json-ld" if name.endswith((".jsonld", ".json")) else "xml"

    # Size first, and on the *stored* bytes: the limit is the validator's,
    # and the validator applies it to the container entry's uncompressed
    # size. A UTF-32 payload shrinks fourfold under the BOM re-encode, so
    # checking afterwards would admit what the validator refuses.
    if len(raw) > MAX_METADATA_BYTES:
        return None, _oversize(name, len(raw))

    # The byte order mark decides the codec; the bytes then have to survive
    # it, and a transfer cut short is enough that they do not -- half a code
    # unit at the end, nothing hostile about it. Every other failure in this
    # function hands back a string, and Package.parse_errors promises that
    # reading it never raises, so this one does too. Caught broadly like the
    # two below: what escaped here was not a class anybody had enumerated.
    # The declaration is asked of the bytes as they were stored, before the
    # mark is taken off: the decode below drops a UTF-8 mark and the
    # declaration behind it, and a false declaration behind the mark went
    # unread.
    if fmt == "xml":
        refused = _marked_declaration_refused(name, raw) or _declaration_refused(name, raw)
        if refused is not None:
            return None, refused

    try:
        raw = _decode(raw)
    except Exception as exc:
        return None, "%s: %s: %s" % (name, type(exc).__name__, exc)

    # Nested internal entities expand geometrically: a few hundred bytes of
    # declarations can occupy the parser indefinitely. iiRDS metadata has no
    # legitimate use for them, so refuse rather than try to bound the damage.
    #
    # Asked after the decode, not before, because these are the bytes that get
    # parsed. A document whose declaration names one encoding while its bytes
    # are another is refused outright by a parser reading it as it arrived --
    # and a guard that stopped there would answer "no declarations" about a
    # document the decode was about to make readable, entities and all.
    if fmt == "xml":
        declares = _declares_entities(raw)
        if declares is None:
            return None, "%s: refused: the document could not be read for XML entities" % name
        if declares:
            return None, "%s: refused: the document declares XML entities" % name

    # Whether the document is RDF/XML at all is decided here, on the decoded
    # bytes, for the reason the entity guard is: a judge that read the stored
    # bytes saw no element in a UTF-32 document -- expat does not know the
    # encoding -- and let it through. rdflib reads `<manual>` into two
    # triples about an element name; the grammar (§7.2.1) defines no such
    # document, so nothing was read, and the reader says so rather than
    # handing on a graph nobody wrote.
    if fmt == "xml":
        element = _document_element(raw)
        if element is not None and not is_rdfxml_document_element(element):
            return None, "%s: %s: %s" % (name, NOT_RDFXML, _why_not_rdfxml(element))


    if fmt == "json-ld":
        try:
            document = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            return None, "%s: %s: %s" % (name, type(exc).__name__, exc)
        # Guarded like every other failure here: this function's contract is
        # (graph, None) or (None, error), and a walker over a document a
        # supplier wrote is not the place to assume the list of what can go
        # wrong is closed.
        try:
            remote = _remote_contexts(document)
        except Exception as exc:
            return None, "%s: %s: %s" % (name, type(exc).__name__, exc)
        if remote:
            return None, ("%s: refused: @context must be inline, not fetched from %s"
                          % (name, ", ".join(sorted(set(remote))[:3])))

    try:
        graph = Graph()
        graph.parse(data=raw, format=fmt, publicID=base)
        if fmt == "json-ld":
            # rdflib files a JSON-LD document's named graphs in the store under
            # the graph it parsed into, beside that graph's own statements --
            # the default graph, which is what is handed on, as it was. Read
            # out of that one parse, so the default graph, its prefixes and
            # what the parse costs are what they were, on every rdflib: a
            # Dataset names its default graph after the base before rdflib 7
            # and after itself from 7, and neither was the graph read here.
            # Read out in one pass over the store into graphs of their own,
            # the default graph too where there are named ones: the store keeps
            # every graph a statement is in with the statement, and reading one
            # graph after another there, or taking a graph out of it, cost the
            # square of the graphs a statement repeats in.
            held = {}
            for triple, contexts in graph.store.triples((None, None, None), None):
                for context in contexts:
                    if context.identifier != graph.identifier:
                        held.setdefault(context.identifier, []).append(triple)
            for identifier, triples in held.items():
                part = Graph()
                for triple in triples:
                    part.add(triple)
                named[identifier] = part
            if held:
                alone = Graph()
                for prefix, namespace in graph.namespaces():
                    alone.bind(prefix, namespace, override=True, replace=True)
                for triple in graph:
                    alone.add(triple)
                graph = alone
    except Exception as exc:
        named.clear()
        return None, "%s: %s: %s" % (name, type(exc).__name__, exc)
    return graph, None


def merge_sources(graphs, refused: Optional[List[str]] = None) -> Graph:
    """A mapping of name -> Graph, merged into one graph, in mapping order.

    Merge, unless a source is the same graph again. Blank nodes cannot be
    co-identified across documents, so naively unioning two serialisations
    of one graph doubles every blank-node-rooted structure and a count
    over the merge fails a conformant package ("2 domains" where the
    metadata has one). Isomorphic sources therefore merge as one;
    genuinely divergent sources still union -- their disagreement is the
    validator's finding to report, and hiding either side would hide the
    evidence.

    A source that cannot be compared with one before it -- where either holds
    more blank nodes outside trees than MAX_COMPARED_BLANK_NODES, see `_rows`
    -- is neither: merging it could double what it repeats, and leaving it
    out without a word would hide it. It is left out and said so, as
    ``"<name>: <NOT_COMPARED>: <detail>"``: appended to `refused` where the
    caller passes a list, and raised as ValueError where it does not.
    """
    merged = Graph()
    kept = []                   # [name, graph, its fingerprint once asked for]
    for name, single in graphs.items():
        if kept:
            holder = name
            try:
                mine = _fingerprint(single)
                for entry in kept:
                    if entry[2] is None:
                        holder = entry[0]
                        entry[2] = _fingerprint(entry[1])
            except _NotCompared as exc:
                reason = _not_compared(name, holder, exc.count)
                if refused is None:
                    raise ValueError(reason) from None
                refused.append(reason)
                continue
            if any(mine == entry[2] for entry in kept):
                continue
        merged += single
        kept.append([name, single, None])
    return merged


#: The most blank nodes outside trees a graph may hold for the comparison to
#: be run on it -- see `_rows` for what a tree is here. Every metadata document
#: in the corpus holds none: an anonymous rendition inside each information
#: unit is a tree, and so is any chain of them, however long. What is left is a
#: blank node two blank nodes point at, or a cycle of them, and there the exact
#: answer tries every order of the nodes that look alike, which is a factorial.
#: rdflib's search, used first, was no better bounded: sixteen such nodes in one
#: structure took it twenty-one seconds. At eight, the most orders there can be
#: is 40,320; measured, the slowest shape tried -- eight nodes each linked to
#: every other and to itself -- took under half a second, and a whole `check`
#: of a package carrying it in both files, which names each file twice, under
#: two.
MAX_COMPARED_BLANK_NODES = 8

#: The category `merge_sources` reports for a source it did not compare and so
#: left out. Part of the error string's shape -- ``"<name>: <category>:
#: <detail>"`` -- and exported for the reason NOT_RDFXML is: the validator
#: routes on it, because nothing in the document was found wrong.
NOT_COMPARED = "not compared with the metadata before it, so left out"


class _NotCompared(Exception):
    """More blank nodes outside trees than MAX_COMPARED_BLANK_NODES."""

    def __init__(self, count: int):
        super().__init__(count)
        self.count = count


def _not_compared(name: str, holder: str, count: int) -> str:
    return ("%s: %s: %s holds %d blank nodes outside trees -- a blank node two "
            "statements from blank nodes point at, or a cycle of them, and every blank "
            "node joined to one -- and this compares at most %d"
            % (name, NOT_COMPARED, "it" if holder == name else holder, count,
               MAX_COMPARED_BLANK_NODES))


def _term(term) -> str:
    """A term rendered by what distinguishes it from another term.

    `str()` keeps the lexical form and nothing else, so `"1"^^xsd:integer` and
    `"1"^^xsd:decimal` rendered alike, and so did `<http://example.org/o>` and
    the string that spells it. The fingerprint built on that was a coarsening
    of isomorphism rather than an equivalent of it, which is not what the
    caller below promises. What separates two terms is the pair they are made
    of -- what kind of term, and its lexical form -- plus the datatype and the
    language tag a literal carries; `repr` renders each of those without two
    of them ever colliding.

    The kind is the RDF one -- resource, literal, blank -- and not the Python
    class. Written as `type(term).__name__` first, which splits a `Genid` from
    the `URIRef` it subclasses: two terms `isomorphic` calls equal and this
    called different, a false split in the direction that matters, since the
    caller below promises the two agree by construction.

    `n3()` says the same things and was used here first, and it is a writer:
    asked for a term it cannot write as N3 -- an IRI holding a space, a brace,
    a bar, any of the characters RFC 3987 leaves out -- it raises. Nothing on
    the way in refuses those, so a supplier's metadata.rdf can carry one, and
    comparing is not writing: a comparison that refuses its input has decided
    nothing. It refused as a bare `Exception` from inside a round-trip check,
    which is neither the `ValueError` `write_metadata` documents nor anything
    a caller can catch by kind, on graphs rdflib still writes.
    """
    kind = "L" if isinstance(term, Literal) else "B" if isinstance(term, BNode) else "U"
    # A language tag without regard to case, as rdflib compares literals: `de`
    # and `DE` are one term to it, and were two to this.
    language = getattr(term, "language", None)
    return "%s %r %r %r" % (kind, str(term),
                            getattr(term, "datatype", None),
                            language.lower() if language else language)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rows(graph: Graph):
    """Every statement of `graph`, rendered so that two graphs are isomorphic
    exactly when their renderings are the same multiset -- a blank node
    rendered by its place in the graph, not by the label a parser gave it.

    Returns ``(rows, label)``: `rows` pairs each rendering with the statement
    it renders, and `label` gives each blank node the name it is rendered by.
    Raises `_NotCompared` before anything is compared where the blank nodes
    outside trees number more than MAX_COMPARED_BLANK_NODES.

    Blank nodes are joined into structures by the statements between them. A
    structure is a tree when exactly one of its nodes has no blank node
    pointing at it and every other has one statement doing so. A tree's node
    is named by a digest of what it says -- its statements about everything
    that is not a blank node, and the names of its children -- worked out
    from the leaves up, in one pass whatever the depth. Under that condition
    the names are exact: two trees are the same exactly when their roots are
    named alike. Statements pointing at a blank node from named nodes join
    its name when there are two or more statements pointing at it in all:
    otherwise two graphs could agree on every name and every rendering and
    still differ in which node was the one pointed at twice.

    A structure that is not a tree has no leaves to start from. Each of its
    nodes is described by what it says and each pair by the predicates
    between them, so that what naming it costs depends on the blank nodes
    alone and not on how much the file says about each one, and
    `_structure_name` names the whole structure from that -- exactly, and
    only where there are few of them.

    A blank node standing as a predicate is rendered by its label. No reader
    here produces one, and RDF/XML cannot write one.
    """
    rows = []
    blanks = set()
    out = {}          # blank node -> [(predicate, object)]
    parents = {}      # blank node -> [the blank subject of each statement pointing at it]
    named_in = {}     # blank node -> [(subject, predicate)] from subjects that are not blank
    for triple in graph:
        subject, predicate, obj = triple
        if isinstance(subject, BNode):
            blanks.add(subject)
            out.setdefault(subject, []).append((predicate, obj))
        if isinstance(obj, BNode):
            blanks.add(obj)
            if isinstance(subject, BNode):
                parents.setdefault(obj, []).append(subject)
            else:
                named_in.setdefault(obj, []).append((subject, predicate))

    joined = {node: node for node in blanks}

    def find(node):
        while joined[node] != node:
            joined[node] = joined[joined[node]]
            node = joined[node]
        return node

    for child, sources in parents.items():
        for parent in sources:
            one, other = find(parent), find(child)
            if one != other:
                joined[one] = other
    structures = {}
    for node in blanks:
        structures.setdefault(find(node), []).append(node)

    label = {}
    outside = []
    for nodes in structures.values():
        roots = [node for node in nodes if node not in parents]
        if len(roots) == 1 and all(len(parents.get(node, ())) <= 1 for node in nodes):
            _name_tree(roots[0], out, parents, named_in, label)
        else:
            outside.append(nodes)
    count = sum(len(nodes) for nodes in outside)
    if count > MAX_COMPARED_BLANK_NODES:
        raise _NotCompared(count)
    for nodes in outside:
        name = "n" + _structure_name(nodes, out, named_in)
        for node in nodes:
            label[node] = name

    def side(term):
        return "_:" + label[term] if isinstance(term, BNode) else _term(term)

    for triple in graph:
        subject, predicate, obj = triple
        rows.append(("%s %s %s" % (side(subject), _term(predicate), side(obj)), triple))
    return rows, label


def _name_tree(root, out, parents, named_in, label) -> None:
    """Name every node of the tree under `root`, leaves first, without
    recursion: a chain of anonymous nodes is as deep as the file makes it.

    Each node is entered once whatever the graph is. In a tree that changes
    nothing; if the condition that sent a structure here were ever wrong, a
    cycle would otherwise be walked for as long as memory lasts, and a name
    asked for before it exists is an error rather than that."""
    stack, entered = [(root, False)], set()
    while stack:
        node, ready = stack.pop()
        if not ready:
            if node in entered:
                continue
            entered.add(node)
            stack.append((node, True))
            stack.extend((obj, False) for _, obj in out.get(node, ()) if isinstance(obj, BNode))
            continue
        parts = ["%s %s" % (_term(predicate),
                            "_:" + label[obj] if isinstance(obj, BNode) else _term(obj))
                 for predicate, obj in out.get(node, ())]
        pointing = named_in.get(node, ())
        if len(pointing) + len(parents.get(node, ())) > 1:
            parts.extend("< %s %s" % (_term(subject), _term(predicate))
                         for subject, predicate in pointing)
        parts.sort()
        label[node] = _digest("\n".join(parts))


def _structure_name(nodes, out, named_in) -> str:
    """A structure of blank nodes that is not a tree, named exactly.

    Each node is described by what it says -- its statements about terms
    that are not blank nodes, and the named nodes pointing at it -- and each
    ordered pair of nodes by the predicates from one to the other. Nodes that
    differ in what they say, or in the links they have, are kept apart; the
    name is the smallest encoding of the links over every order of the nodes
    that keeps them so. Two structures are named alike exactly when they are
    isomorphic, and every run names one structure the same way. rdflib's
    canonical form, used here first, does not: on a structure with symmetry
    its search can end on either of two labellings, and two identical files
    compared different in some runs and the same in others.

    Every order is tried, so the cost is the product of the factorials of the
    groups kept apart: for at most MAX_COMPARED_BLANK_NODES nodes, at most
    that many factorial orders, on a structure that is as small as that.
    """
    says, links = {}, {}
    for node in nodes:
        parts, between = [], {}
        for predicate, obj in out.get(node, ()):
            if isinstance(obj, BNode):
                between.setdefault(obj, []).append(_term(predicate))
            else:
                parts.append("> %s %s" % (_term(predicate), _term(obj)))
        parts.extend("< %s %s" % (_term(subject), _term(predicate))
                     for subject, predicate in named_in.get(node, ()))
        says[node] = _digest("\n".join(sorted(parts)))
        for obj, predicates in between.items():
            links[node, obj] = _digest("\n".join(sorted(predicates)))

    def kind(node):
        return repr((says[node],
                     sorted(name for (one, _), name in links.items() if one == node),
                     sorted(name for (_, other), name in links.items() if other == node)))

    # Numbered once, before the orders are tried: a blank node is an rdflib
    # term, and the JSON-LD reader makes a new one for every reference to the
    # same node, so a lookup by node falls through to a comparison written in
    # Python -- forty thousand orders' worth of them.
    number = {node: index for index, node in enumerate(nodes)}
    edges = [(number[one], number[other], name) for (one, other), name in links.items()]
    groups = {}
    for node in nodes:
        groups.setdefault(kind(node), []).append(number[node])
    kinds = sorted(groups)
    place = [0] * len(nodes)
    best = None
    for arrangement in itertools.product(*(itertools.permutations(groups[key]) for key in kinds)):
        position = 0
        for group in arrangement:
            for index in group:
                place[index] = position
                position += 1
        encoding = sorted((place[one], place[other], name) for one, other, name in edges)
        if best is None or encoding < best:
            best = encoding
    return _digest(repr(([key for key in kinds for _ in groups[key]], best)))


def _fingerprint(graph: Graph):
    """The renderings of `_rows`, sorted: equal for two graphs exactly when
    they are isomorphic."""
    return sorted(rendering for rendering, _ in _rows(graph)[0])


def graph_difference(one: Graph, other: Graph):
    """The statements each of two graphs holds and the other lacks, as
    isomorphism counts them: ``(only_in_one, only_in_other)``.

    Each is a list of statements with every blank node replaced by one named
    for its place in its graph, so that a difference prints the same way on
    every run, sorted. Both are empty exactly when the graphs are isomorphic.
    A structure repeated -- the same anonymous node twice under one subject
    in one graph and once in the other -- is counted as often as it repeats.

    Raises ValueError, naming MAX_COMPARED_BLANK_NODES, where either graph
    holds more blank nodes outside trees than that; nothing is compared then.
    """
    try:
        rows_one, label_one = _rows(one)
        rows_other, label_other = _rows(other)
    except _NotCompared as exc:
        raise ValueError("not compared: a graph holds %d blank nodes outside trees, and this "
                         "compares at most %d" % (exc.count, MAX_COMPARED_BLANK_NODES)) from None

    def counted(rows):
        counts = {}
        for rendering, _ in rows:
            counts[rendering] = counts.get(rendering, 0) + 1
        return counts

    def only(rows, label, mine, theirs):
        left = {rendering: number - theirs.get(rendering, 0)
                for rendering, number in mine.items() if number > theirs.get(rendering, 0)}
        found = []
        for rendering, triple in sorted(rows, key=lambda row: row[0]):
            if left.get(rendering, 0) > 0:
                left[rendering] -= 1
                found.append(tuple(BNode(label[term]) if isinstance(term, BNode) and term in label
                                   else term for term in triple))
        return found

    counts_one, counts_other = counted(rows_one), counted(rows_other)
    return (only(rows_one, label_one, counts_one, counts_other),
            only(rows_other, label_other, counts_other, counts_one))


def merge_graphs_of(graphs):
    """One document's graphs -- a mapping of name -> Graph, the default graph
    first -- merged into one, a graph that repeats another counted once.

    A blank node's label names one node across a JSON-LD document, so graphs
    that share one are about the same node and are joined as they are. A
    graph with blank nodes of its own that repeats one already joined -- the
    same triples, its blank nodes aside -- is left out: joined, its copies
    would be second nodes. A repeat is found by the graph's fingerprint, taken
    once per graph -- one pass where its blank nodes form trees, a search over
    the few that do not -- so the cost is the document's size.

    A graph holding more blank nodes outside trees than
    MAX_COMPARED_BLANK_NODES has no fingerprint, and cannot be told from a
    repeat where another graph with blank nodes is its size. It is joined as
    it is and named; the document it is in then holds more than the limit
    too, so a caller comparing it will not compare it either.

    Returns ``(merged, repeats, uncounted)``: the merged graph, the names of
    graphs left out as repeats, and the names of graphs that could not be
    counted.
    """
    items = list(graphs.items())
    blanks = [{term for triple in graph for term in triple if isinstance(term, BNode)}
              for _name, graph in items]
    shared, seen = set(), set()
    for nodes in blanks:
        shared |= nodes & seen
        seen |= nodes
    sizes = {}
    for (_name, graph), nodes in zip(items, blanks):
        if nodes:
            sizes[len(graph)] = sizes.get(len(graph), 0) + 1
    merged = Graph()
    kept = set()
    repeats, uncounted = [], []
    for (name, graph), nodes in zip(items, blanks):
        if nodes and not nodes & shared:
            try:
                key = tuple(_fingerprint(graph))
            except _NotCompared:
                key = None
            if key is None and sizes[len(graph)] > 1:
                uncounted.append(name)
            elif key is not None:
                if key in kept:
                    repeats.append(name)
                    continue
                kept.add(key)
        merged += graph
    return merged, repeats, uncounted


def _reads_back_the_same(written: Graph, original: Graph) -> bool:
    """Did the round trip preserve the graph?

    Raises `ValueError` where the comparison is not run -- more blank nodes
    outside trees than MAX_COMPARED_BLANK_NODES. `write_metadata` passes
    that on, and it is the one exception either of them documents.

    rdflib's isomorphism check answers this for any two graphs, and prices
    itself for the general case: it canonicalises, and on a graph whose blank
    nodes number in the hundreds -- an ordinary manual, since iiRDS nests a
    rendition inside every information unit -- the cost stops being linear
    long before the package stops being ordinary. Measured on renditions
    nested that way, doubling the topic count multiplied the time by four to
    six, reaching three quarters of a minute at eight hundred topics, and by
    then the check is ninety-seven per cent of what writing costs.

    `_rows` answers it in one pass wherever the blank nodes form trees, and
    names what is left by trying every order of its few nodes; that is not an
    approximation of the general check -- the two agree by construction, and
    where rdflib's search could end on either of two labellings, this does
    not.
    """
    if len(written) != len(original):
        return False
    try:
        return _fingerprint(written) == _fingerprint(original)
    except _NotCompared as exc:
        raise ValueError("this graph cannot be checked after writing: it holds %d blank "
                         "nodes outside trees -- a blank node two statements from blank nodes "
                         "point at, or a cycle of them, and every blank node joined to one -- "
                         "and the check compares at most %d"
                         % (exc.count, MAX_COMPARED_BLANK_NODES)) from None


def write_metadata(graph: Graph, destination=None) -> bytes:
    """Serialise `graph` as a metadata.rdf document, self-verified.

    The bytes are parsed straight back through parse_metadata -- the same
    reader every consumer here uses -- and compared isomorphically before
    being handed over, so "the validator can read what the SDK wrote" is
    enforced at write time rather than discovered at delivery time. The
    output is byte-stable for repeated writes of the same Graph object,
    and no more than that: rdflib mints blank-node labels from a
    process-global counter, so even identically-built graphs serialise
    apart, and a canonicalisation layer would be a different, heavier
    promise than writing.

    `destination`, when given, is written (parents created) and the same
    bytes are still returned.

    Raises `ValueError`, and nothing else, for a graph this cannot write or
    cannot check: RDF/XML declining to serialise it, the reparse not matching,
    or more blank nodes outside trees than MAX_COMPARED_BLANK_NODES, which the
    check does not compare.
    """
    # Serialise a base-less copy. graph.serialize inherits graph.base, and
    # for an opaque urn base (iirds.PACKAGE_BASE, which callers naturally
    # build on) rdflib emits an xml:base plus relative rdf:about that it
    # then cannot resolve on the way back in -- so the self-check below
    # would reject the library's own output. A fresh graph carries the
    # same triples and namespace bindings but no base.
    fresh = Graph()
    for triple in graph:
        fresh.add(triple)
    for prefix, namespace in graph.namespaces():
        fresh.bind(prefix, namespace)
    try:
        raw = fresh.serialize(format="xml", encoding="utf-8")
    except Exception as exc:
        raise ValueError("this graph cannot be written as iiRDS metadata "
                         "(RDF/XML could not serialise it): %s" % exc) from exc

    parsed, error = parse_metadata("META-INF/metadata.rdf", raw,
                                   base="urn:iirds:write-check:")
    if error is not None or not _reads_back_the_same(parsed, graph):
        # The bytes do not read back to the same graph. This is the input's
        # problem far more often than the library's: a predicate IRI RDF/XML
        # cannot split, or a literal holding characters XML forbids. Name
        # the likely cause rather than telling the caller to report a bug.
        raise ValueError("this graph cannot be written as metadata.rdf that "
                         "reads back identically -- most often a predicate IRI "
                         "the RDF/XML syntax cannot split, or a literal with "
                         "characters XML forbids: %s"
                         % (error or "the reparse was not isomorphic"))
    if destination is not None:
        from pathlib import Path
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return raw
