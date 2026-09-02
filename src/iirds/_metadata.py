"""Parsing untrusted metadata safely.

Written first in the checker's context module and moved here. An .iirds
package arrives from a supplier, so its metadata is untrusted input, and the
guards it has to pass before a parser sees it belong in the layer every tool
shares -- not re-invented per tool. `iirds_validate.context` imports these
from here; there is one copy.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import xml.etree.ElementTree as ElementTree
import xml.parsers.expat as expat
from typing import Optional, Tuple

from rdflib import BNode, Graph
from rdflib.compare import isomorphic

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


def _declares_entities(raw: bytes) -> bool:
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
    """
    parser = expat.ParserCreate()
    parser.EntityDeclHandler = lambda *_args: _raise(_Declared)
    parser.StartElementHandler = lambda *_args: _raise(_RootReached)
    try:
        parser.Parse(raw, True)
    except _Declared:
        return True
    except _RootReached:
        return False
    except Exception:
        # Caught broadly, and this is the honest part: what expat cannot read
        # it cannot answer for, and the parser underneath the graph is not
        # this one. So a document expat refuses and rdflib accepts would pass
        # here unexamined. The decode above is what keeps that set empty -- it
        # hands on bytes whose declaration agrees with them, so the two read
        # the same document -- and the tests hold that, with and without a
        # byte order mark, because a mark was how they came apart. Raising is
        # not an option either: parse_errors promises that reading never does.
        return False
    return False


#: The category `parse_metadata` returns for a well-formed XML document the
#: RDF/XML grammar does not define. Part of the error string's shape --
#: ``"<name>: <category>: <detail>"`` -- and exported because the validator
#: routes on it: this refusal is the metadata being the wrong kind of
#: document, not the document being damaged.
NOT_RDFXML = "not an RDF/XML document"

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


def _document_element(raw: bytes) -> Optional[str]:
    """The expanded name of the first element, or None where XML itself
    cannot say -- which the parser then reports in its own words."""
    try:
        for _event, element in ElementTree.iterparse(io.BytesIO(raw), events=("start",)):
            return element.tag
    except ElementTree.ParseError:
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


def parse_metadata(name: str, raw: bytes, *, base: str) -> Tuple[Optional[Graph], Optional[str]]:
    """One metadata document, guarded, parsed into its own Graph.

    Returns ``(graph, None)`` on success, ``(None, error)`` on refusal or
    parse failure. The error string always leads with the file name --
    ``"<name>: <detail>"`` -- and that shape is an interface, not a habit:
    the validator routes these strings into its per-file findings by
    partitioning on the first ``": "``. One refusal has a named category
    after the file name, ``"<name>: <NOT_RDFXML>: <detail>"``, because the
    validator reports it under a different rule from a damaged file.

    ``base`` has no default on purpose: a parse needs a base IRI and the
    caller owns that decision (the container reader passes PACKAGE_BASE).
    The format follows the file name -- ``.jsonld``/``.json`` parse as
    JSON-LD, everything else as RDF/XML, the two serialisations iiRDS names.
    """
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
    if fmt == "xml" and _declares_entities(raw):
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
    except Exception as exc:
        return None, "%s: %s: %s" % (name, type(exc).__name__, exc)
    return graph, None


def merge_sources(graphs) -> Graph:
    """A mapping of name -> Graph, merged into one graph, in mapping order.

    Merge, unless a source is the same graph again. Blank nodes cannot be
    co-identified across documents, so naively unioning two serialisations
    of one graph doubles every blank-node-rooted structure and a count
    over the merge fails a conformant package ("2 domains" where the
    metadata has one). Isomorphic sources therefore merge as one;
    genuinely divergent sources still union -- their disagreement is the
    validator's finding to report, and hiding either side would hide the
    evidence.
    """
    merged = Graph()
    kept = []
    for single in graphs.values():
        if not any(isomorphic(single, seen) for seen in kept):
            merged += single
            kept.append(single)
    return merged


#: How deep a chain of blank nodes the fast comparison below will walk before
#: handing the graph to the general check. Well past anything iiRDS nests --
#: a rendition inside an information unit is one level -- and low enough that
#: the recursion cannot reach Python's own limit.
_MAX_BLANK_DEPTH = 40


class _TooDeep(Exception):
    """A blank-node chain longer than this comparison will follow."""


def _blank_forest(graph: Graph) -> bool:
    """Is every blank node in `graph` referred to at most once, and by nobody
    it can reach?

    Under that condition -- which every metadata document in the corpus meets
    -- a blank node's identity is completely determined by the subtree hanging
    off it, so two graphs are isomorphic exactly when those subtrees match.
    A shared blank node breaks it (two graphs can agree on every subtree and
    still differ in which node is shared), and so does a cycle (there is no
    subtree to hash).
    """
    seen = set()
    for _, _, obj in graph:
        if isinstance(obj, BNode):
            if obj in seen:
                return False          # referred to twice: not a forest
            seen.add(obj)
    blanks = {s for s in graph.subjects() if isinstance(s, BNode)} | seen
    walking = set()

    def acyclic(node, depth):
        if depth > _MAX_BLANK_DEPTH:
            return False
        walking.add(node)
        for _, obj in graph.predicate_objects(node):
            if isinstance(obj, BNode) and (
                    obj in walking or not acyclic(obj, depth + 1)):
                return False
        walking.discard(node)
        return True

    return all(acyclic(node, 0) for node in blanks)


def _blank_key(graph: Graph, node, memo, depth: int = 0) -> str:
    """A blank node named by what hangs off it, not by its label."""
    if node in memo:
        return memo[node]
    if depth > _MAX_BLANK_DEPTH:
        raise _TooDeep
    parts = []
    for predicate, obj in graph.predicate_objects(node):
        rendered = ("_:" + _blank_key(graph, obj, memo, depth + 1)
                    if isinstance(obj, BNode) else str(obj))
        parts.append("%s %s" % (predicate, rendered))
    parts.sort()
    memo[node] = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return memo[node]


def _fingerprint(graph: Graph):
    memo = {}
    rows = []
    for subject, predicate, obj in graph:
        left = ("_:" + _blank_key(graph, subject, memo)
                if isinstance(subject, BNode) else str(subject))
        right = ("_:" + _blank_key(graph, obj, memo)
                 if isinstance(obj, BNode) else str(obj))
        rows.append("%s %s %s" % (left, predicate, right))
    rows.sort()
    return rows


def _reads_back_the_same(written: Graph, original: Graph) -> bool:
    """Did the round trip preserve the graph?

    rdflib's isomorphism check answers this for any two graphs, and prices
    itself for the general case: it canonicalises, and on a graph whose blank
    nodes number in the hundreds -- an ordinary manual, since iiRDS nests a
    rendition inside every information unit -- the cost stops being linear
    long before the package stops being ordinary. Measured on renditions
    nested that way, doubling the topic count multiplied the time by four to
    six, reaching three quarters of a minute at eight hundred topics, and by
    then the check is ninety-seven per cent of what writing costs.

    Where the blank nodes form a forest the answer is available directly:
    hash each one by its subtree, and compare the triples with those hashes
    standing in for the labels. That is not an approximation of the general
    check -- under the forest condition the two agree by construction, and
    where the condition does not hold this hands the graph to the general
    check unchanged.
    """
    if len(written) != len(original):
        return False
    if _blank_forest(written) and _blank_forest(original):
        try:
            return _fingerprint(written) == _fingerprint(original)
        except _TooDeep:
            pass
    return isomorphic(written, original)


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
