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
import itertools
import json
import re
import xml.etree.ElementTree as ElementTree
import xml.parsers.expat as expat
from typing import List, Optional, Tuple

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


def _declares_entities(raw: bytes, encoding: Optional[str] = None) -> bool:
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

    `encoding` is the one to read the document as; left out, the document's
    own declaration decides. The caller asks both ways, because the parser
    under the graph reads the document as UTF-8 whatever it declares: asked
    only under the declaration, this answered for a text the parser never
    saw wherever the two readings differed.
    """
    parser = expat.ParserCreate(encoding)
    parser.EntityDeclHandler = lambda *_args: _raise(_Declared)
    parser.StartElementHandler = lambda *_args: _raise(_RootReached)
    try:
        parser.Parse(raw, True)
    except _Declared:
        return True
    except _RootReached:
        return False
    except Exception:
        # Caught broadly: what expat cannot read under a declared encoding it
        # cannot answer for, and the answer that decides is the one asked as
        # UTF-8, the way the parser under the graph reads. Raising is not an
        # option either: parse_errors promises that reading never does.
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


class _Element(Exception):
    """The first element, by its expanded name."""


class _FirstElement:
    """A tree builder's place, taken by one that stops at the first element."""

    def start(self, tag, _attributes):
        raise _Element(tag)

    def close(self):
        return None


def _document_element_as_utf8(raw: bytes) -> Optional[str]:
    """The first element's expanded name as the parser under the graph reads
    the document -- as UTF-8, whatever it declares -- or None where that
    reading cannot say.

    Fed at once: the target's stop ends the reading at the first element,
    and fed in pieces a long comment before it cost the square of its length.
    Asked beside _document_element for the reason the entity guard is asked
    twice: a judge that followed only the declaration read other text and let
    a document through. Bytes that are not UTF-8 in a name are the parser's
    to refuse, and it does; older expat hands such a name on unchecked and
    decoding it raised, which is answered here as nothing to say.
    """
    parser = ElementTree.XMLParser(target=_FirstElement(), encoding="utf-8")
    try:
        parser.feed(raw)
        parser.close()
    except _Element as first:
        return first.args[0]
    except (ElementTree.ParseError, UnicodeDecodeError):
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
    if fmt == "xml" and (_declares_entities(raw) or _declares_entities(raw, "UTF-8")):
        return None, "%s: refused: the document declares XML entities" % name

    # Whether the document is RDF/XML at all is decided here, on the decoded
    # bytes, for the reason the entity guard is: a judge that read the stored
    # bytes saw no element in a UTF-32 document -- expat does not know the
    # encoding -- and let it through. rdflib reads `<manual>` into two
    # triples about an element name; the grammar (§7.2.1) defines no such
    # document, so nothing was read, and the reader says so rather than
    # handing on a graph nobody wrote.
    if fmt == "xml":
        for element in (_document_element(raw), _document_element_as_utf8(raw)):
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
    return "%s %r %r %r" % (kind, str(term),
                            getattr(term, "datatype", None),
                            getattr(term, "language", None))


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
